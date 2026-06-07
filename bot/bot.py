import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiohttp import web

import config
from db import init_db
from handlers import router

logging.basicConfig(level=logging.INFO)


async def handle_ad(request):
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        ad_html_path = os.path.join(current_dir, "ad.html")
        with open(ad_html_path, "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace("{{ BLOCK_ID }}", config.ADSGRAM_BLOCK_ID)
        return web.Response(text=html, content_type="text/html")
    except Exception as e:
        logging.error(f"Error serving ad.html: {e}")
        return web.Response(text="Internal Server Error", status=500)


async def handle_reward(request):
    secret = request.query.get("secret")
    if not config.ADSGRAM_SECRET or secret != config.ADSGRAM_SECRET:
        return web.Response(text="Unauthorized", status=401)

    userid_str = request.query.get("userid")
    if not userid_str:
        return web.Response(text="Missing userid parameter", status=400)
    try:
        userid = int(userid_str)
    except ValueError:
        return web.Response(text="Invalid userid parameter", status=400)

    from db import add_reward_quota

    await add_reward_quota(userid, 5)

    bot = request.app["bot"]
    try:
        await bot.send_message(
            chat_id=userid,
            text="🎉 You have successfully watched the ad! 5 requests have been added to your balance.",
        )
    except Exception as e:
        logging.warning(f"Failed to send reward message to user {userid}: {e}")

    return web.Response(text="OK", status=200)


async def main():
    os.makedirs("data", exist_ok=True)
    await init_db()

    bot = Bot(token=config.TELEGRAM_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    app = web.Application()
    app["bot"] = bot
    app.add_routes([web.get("/ad", handle_ad), web.get("/reward", handle_reward)])

    async def start_bot(app):
        app["bot_task"] = asyncio.create_task(dp.start_polling(bot))
        logging.info("Telegram Bot polling started.")

    async def stop_bot(app):
        app["bot_task"].cancel()
        try:
            await app["bot_task"]
        except Exception as e:
            logging.error(f"Error in bot task during shutdown: {e}")
        except asyncio.CancelledError:
            pass
        finally:
            await app["bot"].session.close()
            logging.info("Telegram Bot polling stopped.")

    app.on_startup.append(start_bot)
    app.on_cleanup.append(stop_bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.PORT)
    await site.start()
    logging.info(f"Web server started on port {config.PORT}")

    try:
        # Wait for the bot polling task to finish (e.g. if it crashes or completes)
        await app["bot_task"]
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
