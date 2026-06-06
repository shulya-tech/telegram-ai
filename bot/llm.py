import asyncio
import os
import aiohttp
import base64

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000")

async def analyze_image(image_bytes: bytes) -> str:
    url = f"{AI_SERVICE_URL}/analyze-image"
    payload = {"image_base64": base64.b64encode(image_bytes).decode('utf-8')}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("description", "")
        except Exception as e:
            print(f"Error analyzing image: {e}")
    return ""

async def analyze_images(images: list[bytes]) -> str:
    """Analyze multiple images and return combined description."""
    if not images:
        return ""
    descriptions = []
    for i, img in enumerate(images, 1):
        desc = await analyze_image(img)
        if desc:
            label = f"Photo {i}" if len(images) > 1 else "Photo"
            descriptions.append(f"[{label}: {desc}]")
    return "\n".join(descriptions)

async def summarize_history(messages: list[dict]) -> str:
    url = f"{AI_SERVICE_URL}/summarize"
    payload = {
        "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("summary", "")
        except Exception as e:
            print(f"Error summarizing history: {e}")
    return ""

async def generate_llm_response(messages: list[dict], image_bytes: bytes = None):
    """
    Calls the AI service and yields chunks of text as they arrive.
    """
    url = f"{AI_SERVICE_URL}/chat"

    # Format messages to match the AI service expected payload
    formatted_messages = []
    for msg in messages:
        if msg["role"] in ["user", "assistant"]:
            formatted_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

    payload = {
        "messages": formatted_messages,
    }

    if image_bytes:
        payload["image_base64"] = base64.b64encode(image_bytes).decode('utf-8')

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    yield "Sorry, an error occurred while connecting to the AI service."
                    return

                async for chunk in response.content.iter_any():
                    if chunk:
                        yield chunk.decode('utf-8', errors='replace')
        except Exception as e:
            print(f"Error connecting to AI service: {e}")
            yield "Sorry, the AI service is temporarily unavailable."
