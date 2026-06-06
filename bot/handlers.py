import asyncio
import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.exceptions import TelegramBadRequest

from db import check_and_consume_quota, grant_package, get_user, is_admin, get_history, add_message, clear_history
from llm import generate_llm_response, summarize_history, analyze_images

router = Router()

# Tracks active generation task per user so /new can cancel it
_active_tasks: dict[int, asyncio.Task] = {}

# Buffer for media group albums: media_group_id -> {user_id, text, photos, message}
_media_groups: dict[str, dict] = {}
_media_group_tasks: dict[str, asyncio.Task] = {}

def _cancel_user_task(user_id: int):
    task = _active_tasks.pop(user_id, None)
    if task and not task.done():
        task.cancel()

async def _compress_history(user_id: int, messages_to_summarize: list, keep_count: int):
    """Background task: summarize old messages and compress history after response is delivered."""
    summary = await summarize_history(messages_to_summarize)
    if not summary:
        return
    current_history = await get_history(user_id)
    recent = current_history[-keep_count:] if len(current_history) >= keep_count else current_history
    await clear_history(user_id)
    await add_message(user_id, "summary", summary)
    for msg in recent:
        await add_message(user_id, msg["role"], msg["content"])
    print(f"[summary] History compressed for user {user_id}: {len(current_history)} -> {keep_count + 1} messages")

PACKAGES = {
    "buy_50": {"price": 100, "name": "50 messages", "type": "50_messages"},
    "buy_200": {"price": 300, "name": "200 messages", "type": "200_messages"},
    "buy_unlimited": {"price": 500, "name": "Unlimited (1 month)", "type": "unlimited_month"},
}

@router.message(Command("new"))
async def cmd_new(message: Message):
    user_id = message.from_user.id
    _cancel_user_task(user_id)
    await clear_history(user_id)
    await message.answer("New conversation started.")

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
    if user['unlimited_until']:
        unlimited_until_date = datetime.date.fromisoformat(user['unlimited_until'])
        if datetime.date.today() <= unlimited_until_date:
            has_unlimited = True

    if has_unlimited:
        unlimited_until_date = datetime.date.fromisoformat(user['unlimited_until'])
        formatted_date = unlimited_until_date.strftime("%d.%m.%Y")
        await message.answer(
            "Welcome! I am AI Agent.\n\n"
            f"You have an active unlimited subscription until {formatted_date} 23:59."
        )
    else:
        await message.answer(
            "Welcome! I am AI Agent.\n\n"
            "You have 5 free messages per day.\n"
            "Use /my_plan to view plans and purchase additional requests."
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
    today = datetime.date.today()
    today_str = today.isoformat()

    # Active unlimited subscription - do not show prices
    if user['unlimited_until']:
        unlimited_until_date = datetime.date.fromisoformat(user['unlimited_until'])
        if today <= unlimited_until_date:
            formatted_date = unlimited_until_date.strftime("%d.%m.%Y")
            await message.answer(
                "📋 Your Plan\n\n"
                "✅ Active unlimited subscription.\n"
                f"Valid until: {formatted_date} 23:59"
            )
            return

    # Count remaining free messages for today
    if user['last_free_date'] == today_str:
        free_remaining = max(0, 5 - user['free_messages_used_today'])
    else:
        free_remaining = 5

    lines = ["📋 Your Plan\n"]
    if user['messages_bought'] > 0:
        lines.append(f"💬 Paid messages remaining: {user['messages_bought']}")
    lines.append(f"🆓 Free messages today: {free_remaining} of 5")
    lines.append("\n💳 Choose a package to purchase with Telegram Stars:")

    # If the user has paid messages, hide the unlimited option
    keyboard_rows = [
        [InlineKeyboardButton(text="50 messages — 100 ⭐️", callback_data="buy_50")],
        [InlineKeyboardButton(text="200 messages — 300 ⭐️", callback_data="buy_200")],
    ]
    if user['messages_bought'] == 0:
        keyboard_rows.append(
            [InlineKeyboardButton(text="Unlimited (1 month) — 500 ⭐️", callback_data="buy_unlimited")]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
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
        if user['messages_bought'] > 0:
            await callback.answer(
                f"You still have {user['messages_bought']} paid messages remaining. "
                "Please use them first, after which you can activate an unlimited subscription.",
                show_alert=True
            )
            return

    package = PACKAGES[package_key]

    prices = [LabeledPrice(label=package["name"], amount=package["price"])]

    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=package["name"],
        description=f"Purchase {package['name']} for {package['price']} Stars.",
        payload=package_key,
        provider_token="", # Empty for Telegram Stars
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
        await message.answer(f"Thank you for your purchase! You have been granted: {package['name']}")
    else:
        await message.answer("Payment received, but the package was not recognized. Please contact support.")

async def _handle_media_group(group_id: str):
    """Wait briefly for all album photos to arrive, then process as one request."""
    await asyncio.sleep(0.5)
    group = _media_groups.pop(group_id, None)
    _media_group_tasks.pop(group_id, None)
    if not group:
        return
    await _process_message(group["user_id"], group["text"], group["photos"], group["message"])


async def _process_message(user_id: int, text, images: list, message: Message):
    if not text and not images:
        return

    prompt = text or ""

    has_quota = await check_and_consume_quota(user_id)
    if not has_quota:
        await message.answer(
            "You have exhausted all available requests.\n"
            "Use /my_plan to view plans or wait until tomorrow."
        )
        return

    if images:
        status = "Analyzing image..." if len(images) == 1 else f"Analyzing {len(images)} images..."
        processing_msg = await message.answer(status)
        image_description = await analyze_images(images)
        if image_description:
            prompt = f"{text}\n{image_description}" if text else image_description
        else:
            prompt = text if text else "Describe the images."
        try:
            await processing_msg.edit_text("Thinking...")
        except TelegramBadRequest:
            pass
    else:
        processing_msg = await message.answer("Thinking...")

    await add_message(user_id, "user", prompt)

    messages = await get_history(user_id)

    needs_summary = len(messages) >= 20
    if needs_summary:
        messages_to_summarize = messages[:-10]
        messages_for_response = messages[-10:]
    else:
        messages_to_summarize = None
        messages_for_response = messages

    stream_generator = generate_llm_response(messages_for_response)

    async def _run_generation():
        full_text = ""
        chunk_counter = 0
        try:
            async for chunk in stream_generator:
                full_text += chunk
                chunk_counter += 1
                if chunk_counter % 3 == 0:
                    try:
                        await processing_msg.edit_text(full_text)
                    except TelegramBadRequest:
                        pass
            try:
                await processing_msg.edit_text(full_text or "Failed to get response.")
            except TelegramBadRequest:
                pass

            await add_message(user_id, "assistant", full_text)

            if needs_summary and messages_to_summarize:
                keep_count = len(messages_for_response) + 1
                asyncio.create_task(_compress_history(user_id, messages_to_summarize, keep_count))

        except asyncio.CancelledError:
            try:
                await processing_msg.edit_text(full_text + "\n\n_[Generation cancelled]_" if full_text else "_[Generation cancelled]_")
            except TelegramBadRequest:
                pass
            if full_text:
                await add_message(user_id, "assistant", full_text)
        except Exception as e:
            await message.answer("An error occurred while generating response.")
            print(f"Error streaming response: {e}")
            if full_text:
                await add_message(user_id, "assistant", full_text)
        finally:
            _active_tasks.pop(user_id, None)

    _cancel_user_task(user_id)
    task = asyncio.create_task(_run_generation())
    _active_tasks[user_id] = task


@router.message()
async def handle_message(message: Message):
    if message.text and message.text.startswith('/'):
        return

    user_id = message.from_user.id
    text = message.text or message.caption

    # Handle media group (album with multiple photos)
    if message.media_group_id and message.photo:
        group_id = message.media_group_id
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file = await message.bot.download_file(file_info.file_path)
        image_bytes = file.read()

        if group_id not in _media_groups:
            _media_groups[group_id] = {"user_id": user_id, "text": None, "photos": [], "message": message}
        _media_groups[group_id]["photos"].append(image_bytes)
        if text:
            _media_groups[group_id]["text"] = text

        # Restart timer on each new photo to wait for the rest
        if group_id in _media_group_tasks:
            _media_group_tasks[group_id].cancel()
        _media_group_tasks[group_id] = asyncio.create_task(_handle_media_group(group_id))
        return

    # Single photo or text-only message
    image_bytes = None
    if message.photo:
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file = await message.bot.download_file(file_info.file_path)
        image_bytes = file.read()

    if not text and not image_bytes:
        return

    await _process_message(user_id, text, [image_bytes] if image_bytes else [], message)
