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
    os.makedirs('data', exist_ok=True)
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
        text="Hello world"
    )
    message._bot = mock_bot

    with patch('handlers._process_message', new_callable=AsyncMock) as mock_process:
        await handle_message(message)
        mock_process.assert_not_called()

    # 3. Test group chat - Mentioned -> should process with stripped text
    message_mention = Message(
        message_id=2,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Hello @test_bot check this"
    )
    message_mention._bot = mock_bot
    with patch('handlers._process_message', new_callable=AsyncMock) as mock_process:
        await handle_message(message_mention)
        mock_process.assert_called_once()
        args, kwargs = mock_process.call_args
        assert args[0] == -1001  # chat_id
        assert args[1] == 999    # user_id
        assert args[2] == "Hello check this"  # stripped text

    # 3b. Test group chat - Partial mention -> should be ignored
    message_partial_mention = Message(
        message_id=22,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Hello @test_botty check this"
    )
    message_partial_mention._bot = mock_bot
    with patch('handlers._process_message', new_callable=AsyncMock) as mock_process:
        await handle_message(message_partial_mention)
        mock_process.assert_not_called()

    # 3c. Test group chat - Anonymous sender (from_user is None) -> should be ignored safely
    message_anonymous = Message(
        message_id=23,
        date=datetime.datetime.now(),
        chat=chat,
        text="Hello @test_bot check this"
    )
    message_anonymous._bot = mock_bot
    with patch('handlers._process_message', new_callable=AsyncMock) as mock_process:
        await handle_message(message_anonymous)
        mock_process.assert_not_called()

    # 3d. Test group chat - Sender is bot -> should be ignored safely
    bot_user = User(id=888, is_bot=True, first_name="Other Bot", username="other_bot")
    message_from_bot = Message(
        message_id=24,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=bot_user,
        text="Hello @test_bot check this"
    )
    message_from_bot._bot = mock_bot
    with patch('handlers._process_message', new_callable=AsyncMock) as mock_process:
        await handle_message(message_from_bot)
        mock_process.assert_not_called()

    # 4. Test group chat - Reply to bot -> should process
    reply_to_user = User(id=12345, is_bot=True, first_name="Test Bot", username="test_bot")
    reply_message = Message(
        message_id=3,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=reply_to_user,
        text="I am bot response"
    )
    reply_message._bot = mock_bot
    message_reply = Message(
        message_id=4,
        date=datetime.datetime.now(),
        chat=chat,
        from_user=user,
        text="Reply text",
        reply_to_message=reply_message
    )
    message_reply._bot = mock_bot
    with patch('handlers._process_message', new_callable=AsyncMock) as mock_process:
        await handle_message(message_reply)
        mock_process.assert_called_once_with(-1001, 999, "Reply text", [], message_reply)

async def test_gemini_routing():
    from unittest.mock import AsyncMock, MagicMock, patch
    import handlers
    import config
    from aiogram.types import Chat, User, Message
    import datetime

    # Mock DB functions
    with patch('handlers.check_and_consume_quota', new_callable=AsyncMock, return_value=True), \
         patch('handlers.add_message', new_callable=AsyncMock) as mock_add_message, \
         patch('handlers.get_history', new_callable=AsyncMock, return_value=[{"role": "user", "content": "Hello"}]) as mock_get_history:
         
        # Mock generate_llm_response
        async def mock_stream(*args, **kwargs):
            yield "Hello "
            yield "world!"
            
        with patch('handlers.generate_llm_response', side_effect=mock_stream) as mock_generate:
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
                text="Hello bot"
            )
            object.__setattr__(message, 'answer', AsyncMock(return_value=mock_processing_msg))
            
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
                assert called_kwargs.get("parse_mode") == "HTML", f"Expected parse_mode='HTML', got {called_kwargs.get('parse_mode')}"
                
            finally:
                config.GEMINI_API_KEY = old_key

if __name__ == "__main__":
    asyncio.run(run_tests())
