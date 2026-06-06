# Telegram AI Agent Starter Kit

[![GitHub stars](https://img.shields.io/github/stars/br1ge/TelegramAI?style=social)](https://github.com/br1ge/TelegramAI)
[![GitHub forks](https://img.shields.io/github/forks/br1ge/TelegramAI?style=social)](https://github.com/br1ge/TelegramAI/network/members)
[![GitHub license](https://img.shields.io/github/license/br1ge/TelegramAI)](https://github.com/br1ge/TelegramAI/blob/main/LICENSE)

A customizable, containerized AI-powered Telegram Agent starter kit. This repository provides a complete foundation to build, fine-tune, and deploy your own multimodal AI agent capable of handling text and images.

🌟 **If you find this project useful, please give it a star on GitHub! It helps more developers discover this template.**

🚀 **Demo Bot**: Try the live version of this agent starter kit on Telegram: [@brige_help_bot](https://t.me/brige_help_bot)

## Features

- **Hybrid AI Mode (Local / Cloud)**: Seamless hybrid routing to switch from local open-source models to Google Gemini. If `GEMINI_API_KEY` is provided, requests are handled by Gemini. If not, the system runs local models.
- **Multimodal AI**: Leverages `Qwen/Qwen2.5-0.5B-Instruct` for text generation and `Salesforce/blip-image-captioning-large` with `EasyOCR` for image description and text extraction (when in local mode), or uses Gemini's native multimodal vision capabilities (when in Gemini mode).
- **Customizable Subscription & Quotas**: Built-in quota manager (5 free requests per day by default) and Telegram Stars payment integration (50 messages, 200 messages, Unlimited month) using SQLite.
- **Admin System**: Separate administration management commands allowing admin users to bypass quotas.
- **Group Chat Support**: Ability to participate in group chats. The bot only responds when mentioned (via `@username`) or replied to, using Telegram's Reply feature to quote the original message. Chat history is grouped by `chat_id` for context isolation, while quotas are tracked individually by `user_id`.
- **LoRA Fine-Tuning**: Built-in script for fine-tuning the base LLM on your own dataset (local mode).
- **Containerized & Optimized Deployment**: Fully Dockerized setup. When using Gemini mode, startup is highly optimized: only the bot service is launched, consuming minimal system resources and memory. Useful for deploying on very weak servers.

## Limitations

- **No Parallel Requests**: The current version does not use an external inference server like Ollama. Since the HuggingFace models are run directly inside the Python container on a single GPU/CPU instance, requests are processed sequentially (no parallel processing).

---

## Project Structure

```
├── README.md               # You are here
├── LICENSE                 # MIT License
├── Makefile                # Automation commands
├── docker-compose.yml      # Docker compose configuration
├── Dockerfile.ai           # Dockerfile for the AI FastAPI service
├── Dockerfile.bot          # Dockerfile for the Telegram bot
├── Dockerfile.train        # Dockerfile for the LLM fine-tuning service
├── requirements.txt        # AI service dependencies
├── requirements-bot.txt    # Telegram bot dependencies
├── ai_service/
│   ├── main.py             # FastAPI entrypoint & endpoints
│   ├── llm_orchestrator.py # LLM orchestration, summarization & prompt setup
│   ├── vlm.py              # Vision model + EasyOCR runner
│   └── train.py            # LoRA fine-tuning training script
├── bot/
│   ├── bot.py              # Bot entrypoint & runner
│   ├── handlers.py         # Commands, pricing, callbacks, checkout & album processing
│   ├── db.py               # Database manager (aiosqlite)
│   ├── llm.py              # Async HTTP client wrappers for the AI service
│   ├── admin_cli.py        # Command-line interface for admin users
│   └── test_handlers.py    # Local test suite
└── data/                   # Unified folder for persistent data & models
    ├── dataset.jsonl       # Fine-tuning dataset template
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
HF_TOKEN=your_huggingface_token_optional
USE_GPU=false
GEMINI_API_KEY=your_gemini_api_key_optional
GEMINI_MODEL=gemini-3.1-flash-lite
```

- **`TELEGRAM_TOKEN`**: The token you obtain from [@BotFather](https://t.me/BotFather) on Telegram when creating a new bot.
- **`HF_TOKEN`** (Hugging Face User Access Token): This is optional but highly recommended for local mode.
  - **What is Hugging Face (HF)?** Hugging Face is the leading hub for open-source AI models, datasets, and machine learning tools.
  - **Why do you need a token?** The token is used to authenticate requests to download models from Hugging Face. While the models used in this starter kit (`Qwen/Qwen2.5-0.5B-Instruct` and `Salesforce/blip-image-captioning-large`) are public and do not strictly require authentication, having a token avoids rate-limiting issues. If you decide to customize this project and use gated or private models (like Llama models), a Hugging Face token is mandatory. You can generate a token in your [Hugging Face settings](https://huggingface.co/settings/tokens).
- **`USE_GPU`**: Set to `true` if you have an Nvidia GPU and want to run training/inference with GPU acceleration.
- **`GEMINI_API_KEY`**: Paste your Google AI Studio API key here to enable Gemini mode. If provided, the bot will bypass local Hugging Face models and route all conversation & vision tasks to Gemini API. If empty, the bot operates in local mode.
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

#### Startup Optimization:
- **With Gemini Mode (`GEMINI_API_KEY` is set)**: Running the app via `Makefile` targets (`make up` / `make build` / `make rebuild`) will automatically build and start only the `bot` container using the `--no-deps` flag. The heavy `ai_service` container and Hugging Face model loading are bypassed, making the bot startup instant and extremely lightweight (highly suitable for weak servers or low-budget VPS hosting). Note that running `docker compose up` directly will still start `ai_service` due to the static `depends_on` link.
- **With Local Mode (`GEMINI_API_KEY` is not set)**: Running `make up` / `make build` starts both the `bot` and `ai_service` containers, and the local models are downloaded and preloaded on port `8000`.

---

## Makefile Automation Commands

All infrastructure operations are automated through `Makefile` commands:

| Command | Description |
|---|---|
| `make up` | Start existing containers quickly |
| `make build` | Rebuild any changed container images and start |
| `make rebuild` | Full clean build from scratch (bypasses Docker cache) |
| `make down` | Stop and remove all running containers |
| `make logs` | View and follow real-time logs from all services |
| `make train` | Run the fine-tuning script inside Docker (uses CPU or GPU based on `.env`) |
| `make list-admins` | List all registered administrator Telegram IDs |
| `make add-admin ID=123` | Grant administrator privileges to a specific Telegram ID |
| `make remove-admin ID=123` | Revoke administrator privileges from a specific Telegram ID |

---

## Quota & Payments Configuration

By default, the application implements the following plans:

- **Free Tier**: 5 messages per day (resets daily).
- **50 Messages**: 100 ⭐️ (Telegram Stars).
- **200 Messages**: 300 ⭐️ (Telegram Stars).
- **Unlimited (1 month)**: 500 ⭐️ (Telegram Stars).

To customize prices or create new packages, edit the `PACKAGES` dictionary in [bot/handlers.py](file:///Users/brige/Documents/TelegramAI/bot/handlers.py).

---

## Fine-Tuning the Model

You can fine-tune the `Qwen2.5-0.5B-Instruct` model on your own dataset. 

1. Edit [data/dataset.jsonl](file:///Users/brige/Documents/TelegramAI/data/dataset.jsonl) and add your custom training dialogues in ChatML format.
2. Trigger the training pipeline:
   ```bash
   make train
   ```
3. The LoRA adapter weights will be saved directly into `data/models/qwen_lora/`.
4. On the next startup of the `ai_service`, the adapter weights will be loaded automatically if present.

To enable training on Nvidia GPU, set `USE_GPU=true` in your `.env` file.

---

## Deployment

This repository includes a pre-configured CI/CD pipeline using **GitHub Actions** and **Docker**:

- **CI Pipeline (`.github/workflows/ci.yml`)**: Automatically triggers on any Pull Request to the `main` branch. It lints the codebase and executes the test suite inside a Docker container to ensure no syntax or bot handler logic issues are introduced.
- **CD Pipeline (`.github/workflows/deploy.yml`)**: Automatically triggers on any push or merge to the `main` branch. It establishes a secure SSH connection to your server and redeploys the services in the background using `make deploy`.

For a step-by-step guide on setting up a secure non-root deployment user on Ubuntu, configuring Docker permissions, and adding GitHub Secrets, see the [Secure Deployment Guide](docs/deploy.md).

---

## Roadmap & Future Tasks

Here is a list of features planned for future updates. Contributions are welcome!

- [ ] **Ollama Support**: Integrate Ollama to enable parallel request handling instead of sequential Hugging Face processing.
- [x] **Group Chat Support**: Add the ability for the bot to participate in group chats and respond when mentioned (e.g., using `@your_bot_username`).
- [x] **Google Gemini Integration**: Support cloud model failover and hybrid routing using Google AI Studio API for faster and cheaper VPS deployments.
- [x] **Auto-Deployment Pipelines**: Set up CI/CD pipelines (e.g., GitHub Actions) for automatic deployment to your server upon pushing to `main` branch.
- [ ] **Multipurpose Media Handling**: Support additional Telegram media formats, such as voice messages (with speech-to-text transcoding) and document attachments.
- [ ] **MCP Support**: Integrate Model Context Protocol (MCP) to allow the model to call different tools or request information dynamically.

---

## License

This project is licensed under the MIT License. You are free to copy, modify, and fork it, provided you include the original copyright notice and attribute authorship. See the [LICENSE](file:///Users/brige/Documents/TelegramAI/LICENSE) file for details.
