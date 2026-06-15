import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set.")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

ADSGRAM_BLOCK_ID = os.getenv("ADSGRAM_BLOCK_ID", "")
BASE_URL = os.getenv("BASE_URL", "")
PORT = int(os.getenv("PORT", "8080"))
ADSGRAM_SECRET = os.getenv("ADSGRAM_SECRET", "")
ADSGRAM_API_TOKEN = os.getenv("ADSGRAM_API_TOKEN", "")


def is_valid_url(url: str) -> bool:
    if not url:
        return False
    if url in ("https://your-domain.com", "http://your-domain.com", ""):
        return False
    return url.startswith("http://") or url.startswith("https://")


IS_ADSGRAM_ACTIVE = (
    is_valid_url(BASE_URL)
    and bool(ADSGRAM_BLOCK_ID)
    and bool(ADSGRAM_SECRET)
    and bool(ADSGRAM_API_TOKEN)
)
