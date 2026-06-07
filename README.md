# Telegram AI Agent Starter Kit

[![GitHub license](https://img.shields.io/github/license/br1ge/TelegramAI)](https://github.com/br1ge/TelegramAI/blob/main/LICENSE)

A customizable, containerized AI-powered Telegram Agent starter kit. This repository provides a complete foundation to build and deploy your own multimodal AI agent powered exclusively by the Google Gemini API.

🚀 **Demo Bot**: Try the live version of this agent starter kit on Telegram: [@brige_help_bot](https://t.me/brige_help_bot)

## Features

- **Gemini API Integration**: Native integration with Google Gemini models using the modern `google-genai` Python SDK.
- **Multimodal capabilities**: Easily handles both text prompts and images (single or media group albums) using Gemini's native vision capabilities.
- **Customizable Subscription & Quotas**: Built-in quota manager (Adsgram video ads for unlimited free requests, fallback to 5 free requests once per day, and Telegram Stars packages) using SQLite.
- **Admin System**: Separate administration management commands allowing admin users to bypass quotas.
- **Group Chat Support**: Participate in group chats. The bot only responds when mentioned (via `@username`). Chat history is grouped by `chat_id` for context isolation, while quotas are tracked individually by `user_id`.
- **Ultra-lightweight Containerized Deployment**: Fully Dockerized setup. Only the bot service is launched, consuming minimal system resources and memory. Extremely suitable for weak servers or low-budget VPS hosting.

---

## Project Structure

```
├── README.md               # You are here
├── LICENSE                 # MIT License
├── Makefile                # Automation commands
├── docker-compose.yml      # Docker compose configuration
├── Dockerfile.bot          # Dockerfile for the Telegram bot
├── requirements.txt        # Telegram bot dependencies
├── bot/
│   ├── bot.py              # Bot entrypoint & runner
│   ├── handlers.py         # Commands, pricing, callbacks, checkout & album processing
│   ├── db.py               # Database manager (aiosqlite)
│   ├── llm.py              # Async HTTP client wrappers for Gemini API
│   ├── admin_cli.py        # Command-line interface for admin users
│   └── test_handlers.py    # Local test suite
└── data/                   # Unified folder for persistent database
    └── bot_db.sqlite3      # SQLite database (created automatically on startup)
```

---

## Quick Start

### 1. Prerequisites

Make sure you have installed:
- [Docker](https://www.docker.com/) and Docker Compose.
- `make` utility.

### 2. Configure Environment

Create a `.env` file in the root directory:

```env
TELEGRAM_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.1-flash-lite
```

- **`TELEGRAM_TOKEN`**: The token you obtain from [@BotFather](https://t.me/BotFather) on Telegram when creating a new bot.
- **`GEMINI_API_KEY`**: Your Google AI Studio API key. This is required to process conversation & vision tasks.
- **`GEMINI_MODEL`**: The name of the Gemini model to use. Defaults to `gemini-3.1-flash-lite` (highly recommended as the most cost-effective, fast, and lightweight option).

### 3. Run the Bot

To build and start the application, simply run:

```bash
make build
```

For subsequent quick starts (without rebuilding container images):

```bash
make up
```

---

## Makefile Automation Commands

All infrastructure operations are automated through `Makefile` commands:

| Command | Description |
|---|---|
| `make up` | Start existing containers quickly |
| `make build` | Rebuild changed container images and start |
| `make rebuild` | Full clean build from scratch (bypasses Docker cache) |
| `make down` | Stop and remove all running containers |
| `make logs` | View and follow real-time logs |
| `make list-admins` | List all registered administrator Telegram IDs |
| `make add-admin ID=123` | Grant administrator privileges to a specific Telegram ID |
| `make remove-admin ID=123` | Revoke administrator privileges from a specific Telegram ID |

---

## Quota & Payments Configuration

By default, the application implements the following plans:

- **Free Tier**: Watch a short video advertisement (Adsgram Integration) to get **5 free requests** (unlimited views allowed), or claim **5 free requests** once per day via manual click if Adsgram is inactive.
- **50 Messages**: 100 ⭐️ (Telegram Stars).
- **200 Messages**: 300 ⭐️ (Telegram Stars).
- **Unlimited (1 month)**: 500 ⭐️ (Telegram Stars).

To customize prices or create new packages, edit the `PACKAGES` dictionary in [bot/handlers.py](bot/handlers.py).

For details on how to register on Adsgram, configure your ad blocks, and set up Nginx reverse proxy routing, see the [Adsgram Integration Guide](docs/adsgram.md).


---

## Deployment

This repository includes a pre-configured CI/CD pipeline using **GitHub Actions** and **Docker**:

- **CI Pipeline (`.github/workflows/ci.yml`)**: Automatically triggers on any Pull Request to the `main` branch. It lints the codebase and executes the test suite inside a Docker container to ensure no syntax or bot handler logic issues are introduced.
- **CD Pipeline (`.github/workflows/deploy.yml`)**: Automatically triggers on any push or merge to the `main` branch. It establishes a secure SSH connection to your server and redeploys the services in the background using `make deploy`.

For a step-by-step guide on setting up a secure non-root deployment user on Ubuntu, configuring Docker permissions, and adding GitHub Secrets, see the [Secure Deployment Guide](docs/deploy.md).

---

## License

This project is licensed under the MIT License. You are free to copy, modify, and fork it, provided you include the original copyright notice and attribute authorship. See the [LICENSE](LICENSE) file for details.
