# Telegram AI Agent Starter Kit

[![GitHub stars](https://img.shields.io/github/stars/yourusername/yourrepo?style=social)](https://github.com/yourusername/yourrepo)
[![GitHub downloads](https://img.shields.io/github/downloads/yourusername/yourrepo/total?logo=github)](https://github.com/yourusername/yourrepo)

A customizable, containerized AI-powered Telegram Agent starter kit. This repository provides a complete foundation to build, fine-tune, and deploy your own multimodal AI agent capable of handling text and images.

🌟 **If you find this project useful, please give it a star on GitHub! It helps more developers discover this template.**

## Features

- **Multimodal AI**: Leverages `Qwen/Qwen2.5-0.5B-Instruct` for text generation and `Salesforce/blip-image-captioning-large` with `EasyOCR` for image description and text extraction.
- **Customizable Subscription & Quotas**: Built-in quota manager (5 free requests per day by default) and Telegram Stars payment integration (50 messages, 200 messages, Unlimited month) using SQLite.
- **Admin System**: Separate administration management commands allowing admin users to bypass quotas.
- **LoRA Fine-Tuning**: Built-in script for fine-tuning the base LLM on your own dataset.
- **Containerized Deployment**: Fully Dockerized setup with single-command startup.

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
```

- **`TELEGRAM_TOKEN`**: The token you obtain from [@BotFather](https://t.me/BotFather) on Telegram when creating a new bot.
- **`HF_TOKEN`** (Hugging Face User Access Token): This is optional but highly recommended.
  - **What is Hugging Face (HF)?** Hugging Face is the leading hub for open-source AI models, datasets, and machine learning tools.
  - **Why do you need a token?** The token is used to authenticate requests to download models from Hugging Face. While the models used in this starter kit (`Qwen/Qwen2.5-0.5B-Instruct` and `Salesforce/blip-image-captioning-large`) are public and do not strictly require authentication, having a token avoids rate-limiting issues. If you decide to customize this project and use gated or private models (like Llama models), a Hugging Face token is mandatory. You can generate a token in your [Hugging Face settings](https://huggingface.co/settings/tokens).
- **`USE_GPU`**: Set to `true` if you have an Nvidia GPU and want to run training/inference with GPU acceleration.

### 3. Run the Bot

To build and start all containers, simply run:

```bash
make build
```

For subsequent quick starts (without rebuilding container images):

```bash
make up
```

The system will start:
- `ai_service` on port `8000` (FastAPI)
- `bot` (Telegram bot long polling)

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

## Roadmap & Future Tasks

Here is a list of features planned for future updates. Contributions are welcome!

1. **Ollama Support**: Integrate Ollama to enable parallel request handling instead of sequential Hugging Face processing.
2. **Group Chat Support**: Add the ability for the bot to participate in group chats and respond when mentioned (e.g., using `@your_bot_username`).
3. **Multipurpose Media Handling**: Support additional Telegram media formats, such as voice messages (with speech-to-text transcoding) and document attachments.

---

## License

This project is licensed under the MIT License. You are free to copy, modify, and fork it, provided you include the original copyright notice and attribute authorship. See the [LICENSE](file:///Users/brige/Documents/TelegramAI/LICENSE) file for details.
