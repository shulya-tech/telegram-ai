import asyncio
import datetime
import logging
from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest
import config


from db import (
    check_and_consume_quota,
    grant_package,
    get_user,
    is_admin,
    get_history,
    add_message,
    clear_history,
    add_reward_quota,
)
from llm import generate_llm_response, summarize_history
from media_service import MediaService
from file_service import create_docx

router = Router()

# Tracks active generation task per (chat_id, user_id) so they don't cancel each other in groups
_active_tasks: dict[tuple[int, int], asyncio.Task] = {}

# Lazy cache for bot user details to prevent excessive get_me API calls
_bot_id = None
_bot_username = None


async def _get_bot_info(bot):
    global _bot_id, _bot_username
    if _bot_id is None or _bot_username is None:
        me = await bot.get_me()
        _bot_id = me.id
        _bot_username = me.username
    return _bot_id, _bot_username


# Buffer for media group albums: media_group_id -> {
#   "chat_id": int,
#   "user_id": int,
#   "text": str or None,
#   "messages": list[Message],
#   "is_mentioned": bool
# }
_media_groups: dict[str, dict] = {}
_media_group_tasks: dict[str, asyncio.Task] = {}


def _cancel_all_chat_tasks(chat_id: int):
    # Cancel all active tasks in this chat
    keys_to_cancel = [k for k in _active_tasks.keys() if k[0] == chat_id]
    for k in keys_to_cancel:
        task = _active_tasks.pop(k, None)
        if task and not task.done():
            task.cancel()


def _cancel_user_chat_task(chat_id: int, user_id: int):
    # Cancel only this user's active task in this chat
    task = _active_tasks.pop((chat_id, user_id), None)
    if task and not task.done():
        task.cancel()


async def _compress_history(chat_id: int, messages_to_summarize: list, keep_count: int):
    """Background task: summarize old messages and compress history after response is delivered."""
    summary = await summarize_history(messages_to_summarize)
    if not summary:
        return
    current_history = await get_history(chat_id)
    recent = (
        current_history[-keep_count:]
        if len(current_history) >= keep_count
        else current_history
    )
    await clear_history(chat_id)
    await add_message(chat_id, "summary", summary)
    for msg in recent:
        await add_message(chat_id, msg["role"], msg["content"], msg.get("user_name"))
    print(
        f"[summary] History compressed for chat {chat_id}: {len(current_history)} -> {keep_count + 1} messages"
    )


PACKAGES = {
    "buy_50": {"price": 100, "name": "50 messages", "type": "50_messages"},
    "buy_200": {"price": 300, "name": "200 messages", "type": "200_messages"},
    "buy_unlimited": {
        "price": 500,
        "name": "Unlimited (1 month)",
        "type": "unlimited_month",
    },
}


def get_pricing_keyboard(user_id: int, user: dict) -> InlineKeyboardMarkup:
    keyboard_rows = []
    if config.IS_ADSGRAM_ACTIVE:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="🎬 Watch Ad (+5 requests)",
                    callback_data="watch_ad",
                )
            ]
        )
    else:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="🎬 Get 5 free requests",
                    callback_data="get_free_requests",
                )
            ]
        )

    keyboard_rows.extend(
        [
            [InlineKeyboardButton(text="50 messages — 100 ⭐️", callback_data="buy_50")],
            [
                InlineKeyboardButton(
                    text="200 messages — 300 ⭐️", callback_data="buy_200"
                )
            ],
        ]
    )

    if user["messages_bought"] == 0:
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text="Unlimited (1 month) — 500 ⭐️", callback_data="buy_unlimited"
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


@router.callback_query(F.data == "get_free_requests")
async def process_free_requests_callback(callback: CallbackQuery):
    if config.IS_ADSGRAM_ACTIVE:
        await callback.answer(
            "⚠️ Free daily claims are only available when Adsgram is inactive.",
            show_alert=True,
        )
        return

    user_id = callback.from_user.id
    from db import claim_free_daily_quota

    success = await claim_free_daily_quota(user_id)
    if success:
        await callback.message.answer(
            "🎉 5 free requests have been added to your balance! Come back tomorrow for more."
        )
    else:
        await callback.message.answer(
            "⚠️ You have already claimed your free daily requests today. "
            "Please come back tomorrow or purchase a package."
        )
    await callback.answer()


@router.callback_query(F.data == "watch_ad")
async def process_watch_ad_callback(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id

    # Answer callback to stop loading state on the button
    await callback.answer("Loading advertisement...")

    # Query Adsgram advbot API
    url = "https://api.adsgram.ai/advbot"
    params = {
        "tgid": str(user_id),
        "blockid": str(config.ADSGRAM_BLOCK_ID).replace("bot-", ""),
        "token": str(config.ADSGRAM_API_TOKEN),
        "language": callback.from_user.language_code or "en",
    }

    import aiohttp
    import json
    import logging

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logging.error(f"Adsgram API returned status {resp.status}")
                    await callback.message.answer(
                        "⚠️ Failed to load advertisement. Please try again later."
                    )
                    return
                body = await resp.text()
                if not body or not body.strip():
                    logging.warning(
                        "Adsgram API returned empty response — no ads available"
                    )
                    await add_reward_quota(user_id, 2)
                    await callback.message.answer(
                        "😔 No ads available right now, but we've added <b>2 free requests</b> to your balance!",
                        parse_mode="HTML",
                    )
                    return
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    logging.error(f"Adsgram API returned invalid JSON: {body[:200]}")
                    await add_reward_quota(user_id, 2)
                    await callback.message.answer(
                        "😔 No ads available right now, but we've added <b>2 free requests</b> to your balance!",
                        parse_mode="HTML",
                    )
                    return
    except Exception as e:
        logging.error(f"Error fetching ad from Adsgram: {e}")
        await callback.message.answer(
            "⚠️ An error occurred while loading the advertisement. Please try again."
        )
        return

    # Check if we have ad data
    text_html = data.get("text_html")
    if not text_html:
        await add_reward_quota(user_id, 2)
        await callback.message.answer(
            "😔 No ads available right now, but we've added <b>2 free requests</b> to your balance!",
            parse_mode="HTML",
        )
        return

    image_url = data.get("image_url")
    click_url = data.get("click_url")
    button_name = data.get("button_name", "Open Ad")
    reward_url = data.get("reward_url")
    button_reward_name = data.get("button_reward_name", "Claim Reward")

    # Construct inline keyboard for the ad
    keyboard_buttons = []
    if click_url:
        keyboard_buttons.append([InlineKeyboardButton(text=button_name, url=click_url)])
    if reward_url:
        keyboard_buttons.append(
            [InlineKeyboardButton(text=button_reward_name, url=reward_url)]
        )

    ad_keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    # Send ad message to user
    # protect_content=True is required by Adsgram to prevent ad forwarding
    try:
        if image_url:
            await bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=image_url,
                caption=text_html,
                parse_mode="HTML",
                reply_markup=ad_keyboard,
                protect_content=True,
            )
        else:
            await bot.send_message(
                chat_id=callback.message.chat.id,
                text=text_html,
                parse_mode="HTML",
                reply_markup=ad_keyboard,
                protect_content=True,
            )
    except Exception as e:
        logging.error(f"Error sending ad message: {e}")
        await callback.message.answer(
            "⚠️ Failed to display the advertisement. Please try again."
        )


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    # In groups, only group admins or bot global admins can clear history
    if message.chat.type in ("group", "supergroup"):
        try:
            member = await message.chat.get_member(user_id)
            is_group_admin = member.status in ("administrator", "creator")
        except Exception:
            is_group_admin = False

        is_bot_admin = await is_admin(user_id)
        if not is_group_admin and not is_bot_admin:
            await message.reply(
                "Only group administrators can reset the conversation history."
            )
            return

    _cancel_all_chat_tasks(chat_id)
    await clear_history(chat_id)
    await message.answer("Conversation history cleared.")


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id

    admin_status = await is_admin(user_id)
    if admin_status:
        await message.answer(
            "Welcome! I am AI Agent.\n\n"
            "You are an administrator and have **unlimited access**."
        )
        return

    user = await get_user(user_id)
    has_unlimited = False
    if user["unlimited_until"]:
        unlimited_until_date = datetime.date.fromisoformat(user["unlimited_until"])
        if datetime.date.today() <= unlimited_until_date:
            has_unlimited = True

    if has_unlimited:
        unlimited_until_date = datetime.date.fromisoformat(user["unlimited_until"])
        formatted_date = unlimited_until_date.strftime("%d.%m.%Y")
        await message.answer(
            "Welcome! I am AI Agent.\n\n"
            f"You have an active unlimited subscription until {formatted_date} 23:59."
        )
    else:
        if config.IS_ADSGRAM_ACTIVE:
            await message.answer(
                "Welcome! I am AI Agent.\n\n"
                "You can watch ads to get 5 free requests per view.\n"
                "Use /my_plan to view plans and get additional requests."
            )
        else:
            await message.answer(
                "Welcome! I am AI Agent.\n\n"
                "You can claim 5 free daily requests.\n"
                "Use /my_plan to view plans and get additional requests."
            )


@router.message(Command("my_plan"))
async def cmd_my_plan(message: Message):
    user_id = message.from_user.id

    # Administrator - unlimited
    admin_status = await is_admin(user_id)
    if admin_status:
        await message.answer(
            "📋 Your Plan\n\n"
            "👑 You are an administrator.\n"
            "You have unlimited access without any restrictions."
        )
        return

    user = await get_user(user_id)

    # Active unlimited subscription - do not show prices
    if user["unlimited_until"]:
        unlimited_until_date = datetime.date.fromisoformat(user["unlimited_until"])
        if datetime.date.today() <= unlimited_until_date:
            formatted_date = unlimited_until_date.strftime("%d.%m.%Y")
            await message.answer(
                "📋 Your Plan\n\n"
                "✅ Active unlimited subscription.\n"
                f"Valid until: {formatted_date} 23:59"
            )
            return

    total = user["messages_bought"] + user.get("ad_messages_remaining", 0)
    lines = ["📋 Your Plan\n"]
    lines.append(f"💬 Messages remaining: {total}")
    if total > 0:
        breakdown = []
        if user["messages_bought"] > 0:
            breakdown.append(f"{user['messages_bought']} paid")
        if user.get("ad_messages_remaining", 0) > 0:
            breakdown.append(f"{user['ad_messages_remaining']} free")
        if len(breakdown) > 1:
            lines.append(f"({', '.join(breakdown)})")
    if config.IS_ADSGRAM_ACTIVE:
        lines.append(
            "\n🎬 Watch ads to get 5 free requests per view, or purchase a package:"
        )
    else:
        lines.append("\n🎬 Claim 5 free requests once per day, or purchase a package:")

    keyboard = get_pricing_keyboard(user_id, user)
    await message.answer("\n".join(lines), reply_markup=keyboard)


@router.callback_query(F.data.startswith("buy_"))
async def process_buy_callback(callback: CallbackQuery, bot: Bot):
    package_key = callback.data
    if package_key not in PACKAGES:
        await callback.answer("Invalid package.", show_alert=True)
        return

    # Block unlimited purchase if user has remaining paid messages
    if package_key == "buy_unlimited":
        user = await get_user(callback.from_user.id)
        if user["messages_bought"] > 0:
            await callback.answer(
                f"You still have {user['messages_bought']} paid messages remaining. "
                "Please use them first, after which you can activate an unlimited subscription.",
                show_alert=True,
            )
            return

    package = PACKAGES[package_key]

    prices = [LabeledPrice(label=package["name"], amount=package["price"])]

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=package["name"],
        description=f"Purchase {package['name']} for {package['price']} Stars.",
        payload=package_key,
        provider_token="",  # Empty for Telegram Stars
        currency="XTR",
        prices=prices,
    )
    await callback.answer()


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery, bot: Bot):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)


@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload in PACKAGES:
        package = PACKAGES[payload]
        await grant_package(message.from_user.id, package["type"])
        await message.answer(
            f"Thank you for your purchase! You have been granted: {package['name']}"
        )
    else:
        await message.answer(
            "Payment received, but the package was not recognized. Please contact support."
        )


async def _handle_media_group(group_id: str):
    """Wait briefly for all album items to arrive, then process as one request."""
    await asyncio.sleep(0.5)
    group = _media_groups.pop(group_id, None)
    _media_group_tasks.pop(group_id, None)
    if not group or not group["messages"]:
        return

    # Check if we should process in group chats
    message = group["messages"][0]
    is_group = message.chat.type in ("group", "supergroup")
    if is_group and not group.get("is_mentioned"):
        return

    # Download and process the deferred media group items
    media_parts = []
    text_accumulated = group["text"] or ""

    for msg in group["messages"]:
        extracted_text, item_parts = await MediaService.process_message_media(
            msg, override_text=""
        )
        media_parts.extend(item_parts)
        if extracted_text:
            if text_accumulated:
                text_accumulated += "\n" + extracted_text
            else:
                text_accumulated = extracted_text

    await _process_message(
        group["chat_id"],
        group["user_id"],
        text_accumulated.strip(),
        media_parts,
        message,
    )


def _is_only_omissions(prompt: str) -> bool:
    if not prompt:
        return True
    lines = prompt.strip().split("\n")
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        is_omission = (
            line_stripped.startswith("[")
            and "omitted because it exceeds" in line_stripped
            and line_stripped.endswith("]")
        )
        if not is_omission:
            return False
    return True


async def _process_message(
    chat_id: int, user_id: int, text, media_parts: list, message: Message
):
    if not text and not media_parts:
        return

    # Check if all media was omitted and no user text/caption was provided
    if not media_parts and _is_only_omissions(text):
        is_group = message.chat.type in ("group", "supergroup")
        send_msg = message.reply if is_group else message.answer
        await send_msg(text.strip())
        return

    prompt = text or ""

    is_group = message.chat.type in ("group", "supergroup")
    send_msg = message.reply if is_group else message.answer

    has_quota = await check_and_consume_quota(user_id)
    if not has_quota:
        user = await get_user(user_id)
        keyboard = get_pricing_keyboard(user_id, user)
        ad_or_free_text = (
            "Please watch an ad to get 5 free requests, or purchase a package below."
            if config.IS_ADSGRAM_ACTIVE
            else "Please claim 5 free daily requests, or purchase a package below."
        )
        if is_group:
            try:
                await message.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"You have exhausted all available requests.\n"
                        f"{ad_or_free_text}"
                    ),
                    reply_markup=keyboard,
                )
            except Exception:
                _, bot_username = await _get_bot_info(message.bot)
                await message.reply(
                    f"Please start a private chat with me (@{bot_username}) first "
                    "so I can send you options to get more requests."
                )
        else:
            await send_msg(
                f"You have exhausted all available requests.\n" f"{ad_or_free_text}",
                reply_markup=keyboard,
            )
        return

    if media_parts:
        processing_msg = await send_msg("Thinking...")
        if not prompt.strip() or _is_only_omissions(prompt):
            has_audio = any(
                isinstance(p, dict) and p.get("mime_type", "").startswith("audio/")
                for p in media_parts
            )
            has_image = any(
                isinstance(p, dict) and p.get("mime_type", "").startswith("image/")
                for p in media_parts
            )
            if has_audio:
                default_prompt = "Listen to the audio and reply to it."
            elif has_image:
                default_prompt = "Describe the images."
            else:
                default_prompt = "Process the attached files."

            if prompt.strip():
                prompt = default_prompt + "\n\n" + prompt.strip()
            else:
                prompt = default_prompt
    else:
        processing_msg = await send_msg("Thinking...")

    await add_message(
        chat_id,
        "user",
        prompt,
        message.from_user.first_name if message.from_user else None,
    )

    messages = await get_history(chat_id)

    needs_summary = len(messages) >= 20
    if needs_summary:
        messages_to_summarize = messages[:-10]
        messages_for_response = messages[-10:]
    else:
        messages_to_summarize = None
        messages_for_response = messages

    parse_mode = "HTML"

    stream_generator = generate_llm_response(
        messages_for_response, media_parts=media_parts
    )

    async def _run_generation():
        full_text = ""
        chunk_counter = 0
        try:
            async for chunk in stream_generator:
                full_text += chunk
                chunk_counter += 1
                if chunk_counter % 3 == 0:
                    try:
                        await processing_msg.edit_text(full_text, parse_mode=parse_mode)
                    except TelegramBadRequest:
                        pass
            try:
                await processing_msg.edit_text(
                    full_text or "Failed to get response.", parse_mode=parse_mode
                )
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                elif parse_mode == "HTML":
                    try:
                        await processing_msg.edit_text(
                            full_text or "Failed to get response."
                        )
                    except TelegramBadRequest:
                        pass
                else:
                    pass

            await add_message(chat_id, "assistant", full_text, "assistant")

            # Check for document generation request
            if "[CHAT_RESPONSE:" in full_text and "[DOCUMENT_CONTENT:" in full_text:
                import re
                
                # Extract chat response
                chat_match = re.search(
                    r"\[CHAT_RESPONSE:\s*(.*?)\]", full_text, re.IGNORECASE | re.DOTALL
                )
                chat_response = (
                    chat_match.group(1) if chat_match else "Here is your document."
                )

                # Extract document content
                doc_match = re.search(
                    r"\[DOCUMENT_CONTENT:\s*(.*?\.docx)\s*\|\s*(.*?)\]",
                    full_text,
                    re.IGNORECASE | re.DOTALL,
                )

                if doc_match:
                    filename = doc_match.group(1)
                    doc_content = doc_match.group(2).strip()

                    try:
                        # Send the brief chat response
                        await processing_msg.edit_text(
                            chat_response, parse_mode=parse_mode
                        )

                        # Generate and send the document
                        file_path = create_docx(doc_content, filename)
                        from aiogram.types import FSInputFile

                        await message.answer_document(FSInputFile(file_path))
                    except Exception as e:
                        logging.error(f"Failed to create or send docx: {e}")
                        await message.answer(
                            "⚠️ Failed to generate or send the document."
                        )
                else:
                    # Fallback if parsing failed
                    await processing_msg.edit_text(full_text, parse_mode=parse_mode)
            else:
                # Standard response without document
                pass

            if needs_summary and messages_to_summarize:
                keep_count = len(messages_for_response) + 1
                asyncio.create_task(
                    _compress_history(chat_id, messages_to_summarize, keep_count)
                )

        except asyncio.CancelledError:
            cancel_txt = "\n\n_[Generation cancelled]_"
            msg_txt = (
                full_text + cancel_txt if full_text else "_[Generation cancelled]_"
            )
            try:
                await processing_msg.edit_text(msg_txt, parse_mode=parse_mode)
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    pass
                elif parse_mode == "HTML":
                    try:
                        await processing_msg.edit_text(msg_txt)
                    except TelegramBadRequest:
                        pass
                else:
                    pass
            if full_text:
                await add_message(chat_id, "assistant", full_text, "assistant")
        except Exception as e:
            await send_msg("An error occurred while generating response.")
            print(f"Error streaming response: {e}")
            if full_text:
                await add_message(chat_id, "assistant", full_text, "assistant")
        finally:
            _active_tasks.pop((chat_id, user_id), None)

    _cancel_user_chat_task(chat_id, user_id)
    task = asyncio.create_task(_run_generation())
    _active_tasks[(chat_id, user_id)] = task


@router.message()
async def handle_message(message: Message):
    if message.text and message.text.startswith("/"):
        return

    # Guard against missing from_user (anonymous channel/admin posts) and messages from bots
    if not message.from_user or message.from_user.is_bot:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    text = message.text or message.caption

    is_group = message.chat.type in ("group", "supergroup")

    is_mentioned = False

    if is_group:
        bot_id, bot_username_raw = await _get_bot_info(message.bot)
        bot_username = f"@{bot_username_raw}"

        if text:
            import re

            pattern = rf"(?i){re.escape(bot_username)}(?![a-zA-Z0-9_])"
            if re.search(pattern, text):
                is_mentioned = True
                text = re.sub(pattern, "", text)
                text = re.sub(r"\s+", " ", text).strip()

    # Handle media group (album with multiple photos or documents)
    if message.media_group_id:
        group_id = message.media_group_id

        if group_id not in _media_groups:
            _media_groups[group_id] = {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": None,
                "messages": [],
                "is_mentioned": False,
            }

        _media_groups[group_id]["messages"].append(message)
        if text:
            if _media_groups[group_id]["text"]:
                existing_lines = _media_groups[group_id]["text"].split("\n")
                if text not in existing_lines:
                    _media_groups[group_id]["text"] += "\n" + text
            else:
                _media_groups[group_id]["text"] = text

        if is_mentioned:
            _media_groups[group_id]["is_mentioned"] = True

        # Restart timer on each new item to wait for the rest
        if group_id in _media_group_tasks:
            _media_group_tasks[group_id].cancel()
        _media_group_tasks[group_id] = asyncio.create_task(
            _handle_media_group(group_id)
        )
        return

    # Single message (with text, photo, voice, document, etc.)
    if is_group and not is_mentioned:
        return

    extracted_text, media_parts = await MediaService.process_message_media(
        message, override_text=text
    )

    if not extracted_text and not media_parts:
        return

    await _process_message(chat_id, user_id, extracted_text, media_parts, message)
