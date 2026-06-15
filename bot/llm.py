import config
import logging
from google import genai
from google.genai import types

SYSTEM_INSTRUCTION = (
    "You are a helpful and intelligent AI Telegram Agent. "
    "Respond in the same language in which the user wrote the message "
    "(e.g., if the user writes in Russian, respond in Russian; if in "
    "English, respond in English). "
    "Use ONLY Telegram HTML formatting for your answers. "
    "Supported tags are: <b>bold</b>, <i>italic</i>, <u>underline</u>, "
    "<s>strikethrough</s>, <code>code</code>, <pre>pre-formatted code block</pre>.\n"
    "CRITICAL RULES FOR TELEGRAM HTML FORMATTING:\n"
    "1. Never use markdown syntax (such as **, *, __, ```, etc.).\n"
    "2. Never use HTML tags that are not supported by Telegram (like "
    "<h3>, <p>, <ul>, <li>, etc.). Use plain text spacing instead.\n"
    "3. Ensure all HTML tags are correctly opened and closed. "
    "Mismatched or unclosed tags will break the Telegram message parser.\n"
    "4. Properly nest HTML tags (e.g., <b><i>text</i></b>, NOT "
    "<b><i>text</b></i>).\n"
    "5. You MUST escape all literal '<', '>', and '&' characters "
    "that are not part of HTML tags: '<' as &lt;, '>' as &gt;, "
    "and '&' as &amp;.\n"
    "6. If the user asks for a document file (.docx), you can generate it. "
    "To do this, use the following structure: "
    "[CHAT_RESPONSE: Your brief message for the chat.] "
    "[DOCUMENT_CONTENT: filename.docx | The full content of the document.]"
)


def _extract_text(response_or_chunk) -> str:
    if not response_or_chunk.candidates:
        return ""
    candidate = response_or_chunk.candidates[0]
    if not candidate.content or not candidate.content.parts:
        return ""
    text_parts = []
    for part in candidate.content.parts:
        if part.text:
            text_parts.append(part.text)
    return "".join(text_parts)


async def summarize_history(messages: list[dict]) -> str:
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)

        gemini_messages = []
        for msg in messages:
            if msg["role"] in ["user", "assistant"]:
                role = "model" if msg["role"] == "assistant" else "user"

                content = msg["content"]
                if msg.get("user_name"):
                    prefix = f"[{msg['user_name']}]: "
                    content = prefix + content

                gemini_messages.append(
                    {
                        "role": role,
                        "parts": [types.Part.from_text(text=content)],
                    }
                )

        prompt_text = (
            "Please provide a concise summary of the above conversation so far."
        )
        prompt = {"role": "user", "parts": [types.Part.from_text(text=prompt_text)]}
        gemini_messages.append(prompt)

        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=gemini_messages,
        )
        return _extract_text(response)
    except Exception as e:
        print(f"Error summarizing history with Gemini: {e}")
        return ""


async def generate_llm_response(messages: list[dict], media_parts: list[dict] = None):
    """
    Calls the Gemini API and yields chunks of text as they arrive.
    """
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    summary_content = ""
    gemini_messages = []
    for i, msg in enumerate(messages):
        if msg["role"] == "summary":
            summary_content = msg["content"]
        elif msg["role"] in ["user", "assistant"]:
            role = "model" if msg["role"] == "assistant" else "user"

            content = msg["content"]
            if msg.get("user_name"):
                name = msg["user_name"]
                if role == "model":
                    prefix = "Assistant: "
                else:
                    prefix = f"[{name}]: "
                content = prefix + content

            parts = [types.Part.from_text(text=content)]

            # Attach media parts to the very last user message
            if media_parts and i == len(messages) - 1 and role == "user":
                for part in media_parts:
                    if isinstance(part, dict):
                        if "data" in part and "mime_type" in part:
                            parts.append(
                                types.Part.from_bytes(
                                    data=part["data"], mime_type=part["mime_type"]
                                )
                            )
                    else:
                        parts.append(part)

            gemini_messages.append({"role": role, "parts": parts})

    sys_inst = SYSTEM_INSTRUCTION
    if summary_content:
        sys_inst += f"\n\nSummary of the previous conversation:\n{summary_content}"

    try:
        response = await client.aio.models.generate_content_stream(
            model=config.GEMINI_MODEL,
            contents=gemini_messages,
            config=types.GenerateContentConfig(system_instruction=sys_inst),
        )
        async for chunk in response:
            text = _extract_text(chunk)
            if text:
                yield text
    except Exception:
        logging.exception("Error connecting to Gemini API")
        yield "Sorry, an error occurred while connecting to Gemini."
