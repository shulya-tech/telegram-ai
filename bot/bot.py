import asyncio
import logging
import os
from aiogram import Bot, Dispatcher

import config
from db import init_db
from handlers import router

logging.basicConfig(level=logging.INFO)


async def main():
    os.makedirs('data', exist_ok=True)
    await init_db()

    bot = Bot(token=config.TELEGRAM_TOKEN)
    dp = Dispatcher()

    dp.include_router(router)

    logging.info("Starting bot...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
