---
trigger: always_on
---

# Telegram AI Agent Starter Kit Workspace Rules

Guidelines and instructions for the Antigravity Agent when working on this workspace.

## 1. Project Stack & Architecture

- **Telegram Bot (`bot/`)**: Built using `aiogram` (v3.10), `aiosqlite` for asynchronous SQLite database operations (`data/bot_db.sqlite3`), and `google-genai` SDK for Gemini API integration.
- **Inference**: Uses Google Gemini API exclusively. No local model serving or fine-tuning pipelines.

## 2. Core Rules & Constraints

- **Gemini API usage**:
  - `GEMINI_API_KEY` is a mandatory environment variable.
  - `GEMINI_MODEL` defaults to `gemini-2.5-flash-lite`.
  - Gemini API calls are naturally asynchronous using the `client.aio.models` methods and do not block the event loop.
  - **Rule**: Always use the custom `_extract_text` helper function to extract response content to avoid SDK warnings about non-text parts (like `thought_signature`).
  - **Rule**: System instructions are passed via `GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION)` to guarantee Telegram-compliant HTML responses (`<b>`, `<i>`, etc.) without markdown.
  - **Rule**: Streaming updates (`edit_text`) must use `parse_mode='HTML'`.
- **Quota & Payments**:
  - The default free quota is 5 requests per video ad view (Adsgram). If Adsgram is inactive, users can claim 5 free requests manually once per day.
  - Subscriptions and extra package purchases are handled via **Telegram Stars** (`XTR` currency).
  - Admins (registered in the `admins` table) have unlimited quota bypass.
  - **Rule**: Quotas are always tracked individually by `user_id` even in group chats.
- **Context Isolation & DB Schema**:
  - Chat history reaches limit at 20 messages. Once reached, the older 10 messages are summarized into a `summary` type role in `chat_history`, and the recent 10 messages are preserved.
  - **Rule**: Chat history is grouped/isolated by `chat_id` rather than `user_id`. Database queries (`get_history`, `add_message`, `clear_history`) must use `chat_id`.
  - Database schema includes a `chat_id` column in `chat_history` and an index `idx_chat_history_chat_id` for optimized queries.
- **Group Chat Support**:
  - The bot only responds when explicitly mentioned (via `@username`). Reply-to-bot behavior is disabled to prevent loops.
  - In group chats, only group admins or bot global admins are allowed to clear history using the `/clear` command.
  - Active tasks cancellation is managed per chat (`_cancel_all_chat_tasks(chat_id)`) or per user-chat (`_cancel_user_chat_task(chat_id, user_id)`).


## 3. Formatting & Code Conventions

- **Language Constraint**:
  - All user-facing application text, labels, prompt configurations, and responses must be strictly in English.
- **Database Operations**:
  - Direct database interaction should go through the wrapper functions in `bot/db.py`.
  - Always use `aiosqlite` methods asynchronously and ensure commits are made when modifying data.
- **Telegram UI/UX Updates**:
  - When updating message text (e.g. streaming chunks), wrap calls in `try/except TelegramBadRequest` to prevent crashes when a user rapidly invokes commands or cancels generation.
- **Python Code Style & Quality**:
  - Code must strictly adhere to the PEP 8 style guide.
  - Always format Python files using `black==25.11.0` to maintain formatting consistency with the CI workflow. Do not use newer versions of `black` that may alter formatting and cause CI mismatches.
  - In linting workflows (such as `flake8`), the `--exit-zero` flag must **never** be used (the build must fail on any warnings or errors), except specifically for code complexity rules (like `C901`).
  - Configure code style checkers to ignore rules `E203` (whitespace before ':') and `W503` (line break before binary operator), as they conflict with formatting produced by `black==25.11.0`.
