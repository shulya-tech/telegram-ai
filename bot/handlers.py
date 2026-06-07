import asyncio
import datetime
from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    WebAppInfo,
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
)
from llm import generate_llm_response, summarize_history

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


# Buffer for media group albums: media_group_id -> {user_id, text, photos, message}
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
        await add_message(chat_id, msg["role"], msg["content"])
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
                    web_app=WebAppInfo(url=f"{config.BASE_URL}/ad?user_id={user_id}"),
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

    # Администратор — безлимит
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

    lines = ["📋 Your Plan\n"]
    if user["messages_bought"] > 0:
        lines.append(f"💬 Messages remaining: {user['messages_bought']}")
    else:
        lines.append("💬 Messages remaining: 0")
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
    """Wait briefly for all album photos to arrive, then process as one request."""
    await asyncio.sleep(0.5)
    group = _media_groups.pop(group_id, None)
    _media_group_tasks.pop(group_id, None)
    if not group:
        return

    # Check if we should process in group chats
    message = group["message"]
    is_group = message.chat.type in ("group", "supergroup")
    if is_group and not group.get("is_mentioned"):
        return

    await _process_message(
        group["chat_id"],
        group["user_id"],
        group["text"],
        group["photos"],
        group["message"],
    )


async def _process_message(
    chat_id: int, user_id: int, text, images: list, message: Message
):
    if not text and not images:
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
                bot_info = await message.bot.get_me()
                bot_username = bot_info.username
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

    if images:
        processing_msg = await send_msg("Thinking...")
        prompt = text if text else "Describe the images."
    else:
        processing_msg = await send_msg("Thinking...")

    await add_message(chat_id, "user", prompt)

    messages = await get_history(chat_id)

    needs_summary = len(messages) >= 20
    if needs_summary:
        messages_to_summarize = messages[:-10]
        messages_for_response = messages[-10:]
    else:
        messages_to_summarize = None
        messages_for_response = messages

    parse_mode = "HTML"

    stream_generator = generate_llm_response(messages_for_response, images=images)

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

            await add_message(chat_id, "assistant", full_text)

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
                await add_message(chat_id, "assistant", full_text)
        except Exception as e:
            await send_msg("An error occurred while generating response.")
            print(f"Error streaming response: {e}")
            if full_text:
                await add_message(chat_id, "assistant", full_text)
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

    # Handle media group (album with multiple photos)
    if message.media_group_id and message.photo:
        group_id = message.media_group_id
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file = await message.bot.download_file(file_info.file_path)
        image_bytes = file.read()

        if group_id not in _media_groups:
            _media_groups[group_id] = {
                "chat_id": chat_id,
                "user_id": user_id,
                "text": None,
                "photos": [],
                "message": message,
                "is_mentioned": False,
            }
        _media_groups[group_id]["photos"].append(image_bytes)
        if text:
            _media_groups[group_id]["text"] = text
        if is_mentioned:
            _media_groups[group_id]["is_mentioned"] = True

        # Restart timer on each new photo to wait for the rest
        if group_id in _media_group_tasks:
            _media_group_tasks[group_id].cancel()
        _media_group_tasks[group_id] = asyncio.create_task(
            _handle_media_group(group_id)
        )
        return

    # Single photo or text-only message
    if is_group and not is_mentioned:
        return

    image_bytes = None
    if message.photo:
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file = await message.bot.download_file(file_info.file_path)
        image_bytes = file.read()

    if not text and not image_bytes:
        return

    await _process_message(
        chat_id, user_id, text, [image_bytes] if image_bytes else [], message
    )
