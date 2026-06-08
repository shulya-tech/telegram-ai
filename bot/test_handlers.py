import asyncio
import os
from db import init_db, add_message, get_history, clear_history


async def generate_mock_llm_response(history: list[dict], has_image: bool = False):
    user_prompt = ""
    for msg in history:
        if msg["role"] == "user":
            user_prompt = msg["content"]
            break
    yield f"This is a mock LLM response to your prompt: '{user_prompt}'. "
    yield f"The chat history is active, it has {len(history)} messages so far. "
    if has_image:
        yield "I noticed you attached an image."


async def run_tests():
    os.makedirs("data", exist_ok=True)
    await init_db()

    user_id = 9999

    # 1. Test clear history
    await clear_history(user_id)
    history = await get_history(user_id)
    assert len(history) == 0, "History should be empty"

    # 2. Test add message and get history
    await add_message(user_id, "user", "Hello bot!")
    await add_message(user_id, "assistant", "Hello user!")
    history = await get_history(user_id)
    assert len(history) == 2, "History should have 2 messages"
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello bot!"
    assert history[1]["role"] == "assistant"

    # 3. Test LLM mock with history and no image
    stream = generate_mock_llm_response(history, has_image=False)
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    full_text = "".join(chunks)
    assert "it has 2 messages so far" in full_text
    assert "mock LLM response to your prompt: 'Hello bot!'" in full_text

    # 4. Test LLM mock with image
    stream2 = generate_mock_llm_response(history, has_image=True)
    chunks2 = []
    async for chunk in stream2:
        chunks2.append(chunk)
    full_text2 = "".join(chunks2)
    assert "noticed you attached an image" in full_text2

    # 5. Test group filtering
    await test_group_filtering()

    # 6. Test Gemini mode routing
    await test_gemini_routing()

    # 7. Test quota logic
    await test_quota_logic()

    # 8. Test Media Service
    await test_media_service()

    print("All tests passed!")


async def test_group_filtering():
    from unittest.mock import AsyncMock, MagicMock, patch
    from handlers import handle_message
    from aiogram.types import Chat, User, Message
    import datetime

    # 1. Setup mock bot info
    import handlers

    handlers._bot_id = None
    handlers._bot_username = None

    mock_bot = AsyncMock()
    mock_bot.id = 12345
    mock_bot.get_me = AsyncMock(return_value=MagicMock(id=12345, username="test_bot"))

    # 2. Test group chat - No mention, no reply to bot -> should be ignored
    chat = Chat(id=-1001, type="group")
    user = User(id=999, is_bot=False, first_name="User", username="test_user")
    message = Message(
        message_id=1,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Hello world",
    )
    message._bot = mock_bot

    with patch("handlers._process_message", new_callable=AsyncMock) as mock_process:
        await handle_message(message)
        mock_process.assert_not_called()

    # 3. Test group chat - Mentioned -> should process with stripped text
    message_mention = Message(
        message_id=2,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Hello @test_bot check this",
    )
    message_mention._bot = mock_bot
    with patch("handlers._process_message", new_callable=AsyncMock) as mock_process:
        await handle_message(message_mention)
        mock_process.assert_called_once()
        args, kwargs = mock_process.call_args
        assert args[0] == -1001  # chat_id
        assert args[1] == 999  # user_id
        assert args[2] == "Hello check this"  # stripped text

    # 3b. Test group chat - Partial mention -> should be ignored
    message_partial_mention = Message(
        message_id=22,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Hello @test_botty check this",
    )
    message_partial_mention._bot = mock_bot
    with patch("handlers._process_message", new_callable=AsyncMock) as mock_process:
        await handle_message(message_partial_mention)
        mock_process.assert_not_called()

    # 3c. Test group chat - Anonymous sender (from_user is None) -> should be ignored safely
    message_anonymous = Message(
        message_id=23,
        date=datetime.datetime.now(),
        chat=chat,
        text="Hello @test_bot check this",
    )
    message_anonymous._bot = mock_bot
    with patch("handlers._process_message", new_callable=AsyncMock) as mock_process:
        await handle_message(message_anonymous)
        mock_process.assert_not_called()

    # 3d. Test group chat - Sender is bot -> should be ignored safely
    bot_user = User(id=888, is_bot=True, first_name="Other Bot", username="other_bot")
    message_from_bot = Message(
        message_id=24,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=bot_user,
        text="Hello @test_bot check this",
    )
    message_from_bot._bot = mock_bot
    with patch("handlers._process_message", new_callable=AsyncMock) as mock_process:
        await handle_message(message_from_bot)
        mock_process.assert_not_called()

    # 4. Test group chat - Reply to bot -> should NOT process anymore (to prevent loops)
    reply_to_user = User(
        id=12345, is_bot=True, first_name="Test Bot", username="test_bot"
    )
    reply_message = Message(
        message_id=3,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=reply_to_user,
        text="I am bot response",
    )
    reply_message._bot = mock_bot
    message_reply = Message(
        message_id=4,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Reply text",
        reply_to_message=reply_message,
    )
    message_reply._bot = mock_bot
    with patch("handlers._process_message", new_callable=AsyncMock) as mock_process:
        await handle_message(message_reply)
        mock_process.assert_not_called()


async def test_gemini_routing():
    from unittest.mock import AsyncMock, patch
    import handlers
    import config
    from aiogram.types import Chat, User, Message
    import datetime

    # Mock DB functions
    patch_quota = patch(
        "handlers.check_and_consume_quota", new_callable=AsyncMock, return_value=True
    )
    patch_add = patch("handlers.add_message", new_callable=AsyncMock)
    mock_history = [{"role": "user", "content": "Hello"}]
    patch_hist = patch(
        "handlers.get_history", new_callable=AsyncMock, return_value=mock_history
    )

    with patch_quota, patch_add, patch_hist:

        # Mock generate_llm_response
        async def mock_stream(*args, **kwargs):
            yield "Hello "
            yield "world!"

        with patch(
            "handlers.generate_llm_response", side_effect=mock_stream
        ) as mock_generate:
            # Setup mock message & chat
            chat = Chat(id=123, type="private")
            user = User(id=999, is_bot=False, first_name="User", username="test_user")

            # Setup mock processing message that edit_text calls on
            mock_processing_msg = AsyncMock()
            message = Message(
                message_id=1,
                date=datetime.datetime.now(),
                chat=chat,
                from_user=user,
                text="Hello bot",
            )
            object.__setattr__(
                message, "answer", AsyncMock(return_value=mock_processing_msg)
            )

            # Force GEMINI_API_KEY to be set
            old_key = config.GEMINI_API_KEY
            config.GEMINI_API_KEY = "mock_key"

            try:
                # Call _process_message
                await handlers._process_message(123, 999, "Hello bot", [], message)

                # Wait for async background task _run_generation to complete
                task = handlers._active_tasks.get((123, 999))
                if task:
                    await task

                # Check that generate_llm_response was called
                mock_generate.assert_called_once()

                # Check that edit_text was called with parse_mode='HTML'
                called_args, called_kwargs = mock_processing_msg.edit_text.call_args
                got_mode = called_kwargs.get("parse_mode")
                assert got_mode == "HTML", f"Expected parse_mode='HTML', got {got_mode}"

            finally:
                config.GEMINI_API_KEY = old_key


async def test_quota_logic():
    import aiosqlite
    from db import (
        check_and_consume_quota,
        add_reward_quota,
        claim_free_daily_quota,
        get_user,
        grant_package,
        DB_PATH,
    )

    test_user_id = 11111

    # Reset user state in DB
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
        await db.commit()

    # 1. Initially user should have 5 requests
    user = await get_user(test_user_id)
    assert (
        user["ad_messages_remaining"] == 5
    ), f"Expected 5 initial ad messages, got {user['ad_messages_remaining']}"

    # Consume 5 times
    for i in range(5):
        has_quota = await check_and_consume_quota(test_user_id)
        assert has_quota, f"User should have quota at iteration {i}"

    # 6th attempt should fail
    has_quota = await check_and_consume_quota(test_user_id)
    assert not has_quota, "User should run out of quota after 5 consumes"

    # 2. Add reward quota (Adsgram)
    await add_reward_quota(test_user_id, 5)
    user = await get_user(test_user_id)
    assert (
        user["ad_messages_remaining"] == 5
    ), f"Expected 5 ad messages, got {user['ad_messages_remaining']}"

    # 3. Consume reward quota
    has_quota = await check_and_consume_quota(test_user_id)
    assert has_quota, "User should have quota after reward"
    user = await get_user(test_user_id)
    assert (
        user["ad_messages_remaining"] == 4
    ), f"Expected 4 ad messages, got {user['ad_messages_remaining']}"

    # 4. Daily free claim
    # Reset user state again
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
        await db.commit()

    success = await claim_free_daily_quota(test_user_id)
    assert success, "First daily free claim should succeed"
    user = await get_user(test_user_id)
    assert (
        user["ad_messages_remaining"] == 10
    ), f"Expected 10 ad messages after free claim (5 initial + 5 daily), got {user['ad_messages_remaining']}"

    # Attempt to claim again on the same day - should fail
    success_retry = await claim_free_daily_quota(test_user_id)
    assert not success_retry, "Subsequent daily free claim on the same day should fail"

    # 5. Precedence: bought messages first, then ad_messages_remaining
    # Reset user state
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (test_user_id,))
        await db.commit()

    # Grant package of 50 messages (bought messages)
    await grant_package(test_user_id, "50_messages")
    # Add ad messages
    await add_reward_quota(test_user_id, 3)

    user = await get_user(test_user_id)
    assert (
        user["messages_bought"] == 50
    ), f"Expected 50 bought messages, got {user['messages_bought']}"
    assert (
        user["ad_messages_remaining"] == 8
    ), f"Expected 8 ad messages (5 initial + 3 added), got {user['ad_messages_remaining']}"

    # Consume quota - should decrement messages_bought
    has_quota = await check_and_consume_quota(test_user_id)
    assert has_quota
    user = await get_user(test_user_id)
    assert (
        user["messages_bought"] == 49
    ), f"Expected 49 bought messages, got {user['messages_bought']}"
    assert (
        user["ad_messages_remaining"] == 8
    ), f"Expected 8 ad messages to be intact, got {user['ad_messages_remaining']}"

    # 6. Test callback guard when Adsgram is active
    from unittest.mock import AsyncMock, MagicMock
    from handlers import process_free_requests_callback
    import config

    old_adsgram_active = config.IS_ADSGRAM_ACTIVE
    config.IS_ADSGRAM_ACTIVE = True

    try:
        mock_callback = AsyncMock()
        mock_callback.from_user = MagicMock(id=test_user_id)
        mock_callback.answer = AsyncMock()

        await process_free_requests_callback(mock_callback)

        mock_callback.answer.assert_called_once_with(
            "⚠️ Free daily claims are only available when Adsgram is inactive.",
            show_alert=True,
        )
    finally:
        config.IS_ADSGRAM_ACTIVE = old_adsgram_active


async def test_media_service():
    from media_service import MediaService
    from aiogram.types import Message, Voice, PhotoSize, Document, Chat, User
    from unittest.mock import AsyncMock, MagicMock
    import io
    import datetime

    # 1. Test is_text_file
    assert MediaService.is_text_file("main.py", "text/x-python") is True
    assert MediaService.is_text_file("data.json", "application/json") is True
    assert MediaService.is_text_file("image.png", "image/png") is False
    assert MediaService.is_text_file("doc.pdf", "application/pdf") is False

    # Mock Message
    mock_bot = AsyncMock()

    # 2. Test Voice message
    voice = Voice(
        file_id="voice_123", duration=5, file_unique_id="v1", mime_type="audio/ogg"
    )
    msg_voice = Message(
        message_id=5,
        date=datetime.datetime.now(),
        chat=Chat(id=123, type="private"),
        from_user=User(id=999, is_bot=False, first_name="User"),
        voice=voice,
    )
    msg_voice._bot = mock_bot
    mock_file_info = MagicMock(file_path="voice_path")
    mock_bot.get_file = AsyncMock(return_value=mock_file_info)
    mock_bot.download_file = AsyncMock(return_value=io.BytesIO(b"oggdata"))

    text, parts = await MediaService.process_message_media(msg_voice)
    assert text == ""
    assert len(parts) == 1
    assert parts[0]["mime_type"] == "audio/ogg"
    assert parts[0]["data"] == b"oggdata"

    # 3. Test Text File Document
    doc_text = Document(
        file_id="doc_123",
        file_unique_id="d1",
        file_name="test.py",
        mime_type="text/x-python",
    )
    msg_doc_text = Message(
        message_id=6,
        date=datetime.datetime.now(),
        chat=Chat(id=123, type="private"),
        from_user=User(id=999, is_bot=False, first_name="User"),
        document=doc_text,
    )
    msg_doc_text._bot = mock_bot
    mock_bot.download_file = AsyncMock(return_value=io.BytesIO(b"print('hello')"))

    text, parts = await MediaService.process_message_media(msg_doc_text)
    assert "[Attached File: test.py]" in text
    assert "print('hello')" in text
    assert len(parts) == 0  # Should be empty because it was decoded as text

    # 4. Test PDF Document (Binary)
    doc_pdf = Document(
        file_id="doc_456",
        file_unique_id="d2",
        file_name="paper.pdf",
        mime_type="application/pdf",
    )
    msg_doc_pdf = Message(
        message_id=7,
        date=datetime.datetime.now(),
        chat=Chat(id=123, type="private"),
        from_user=User(id=999, is_bot=False, first_name="User"),
        document=doc_pdf,
    )
    msg_doc_pdf._bot = mock_bot
    mock_bot.download_file = AsyncMock(return_value=io.BytesIO(b"pdfdata"))

    text, parts = await MediaService.process_message_media(msg_doc_pdf)
    assert text == ""
    assert len(parts) == 1
    assert parts[0]["mime_type"] == "application/pdf"
    assert parts[0]["data"] == b"pdfdata"


if __name__ == "__main__":
    asyncio.run(run_tests())
