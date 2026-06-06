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

    print("All tests passed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
