import os, logging, asyncio
from dotenv import load_dotenv
from aiohttp import web
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

from db import init_db, add_message, wipe_user
from memory import build_context, maybe_update_summary, should_summarize

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID","0"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SYSTEM_PROMPT = (
    "You are FinancialGrowth-GPT for Damarius. forward-thinking, opinionated, practical."
    "Default to numbered steps. Cut fluff. Track recurring goals and blockers. Push for clarity. Offer one bold next action at the end of each reply."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I’m live. Send me anything.\n\nCommands:\n/reset – clear memory")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    wipe_user(uid)
    await update.message.reply_text("Memory wiped. Fresh start.")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    uid = update.effective_user.id
    user_text = update.message.text.strip()

    # store user msg
    add_message(uid, "user", user_text)

    # build context (long-term + recent)
    msgs = build_context(uid, client, SYSTEM_PROMPT)

    # call OpenAI
    resp = client.responses.create(model="gpt-5", input=msgs + [{"role":"user","content":user_text}])
    answer = (resp.output_text or "").strip() or "…"  # safe fallback

    # send + store
    await update.message.reply_text(answer)
    add_message(uid, "assistant", answer)

    # background summarization (non-blocking)
    try:
        recent_pairs = sum(1 for r,_ in msgs if r in ("user","assistant")) // 2
        if should_summarize(recent_pairs):
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, maybe_update_summary, uid, client)
    except Exception as e:
        logging.warning(f"Summarize skip: {e}")

# --- Web server to receive Telegram updates ---
async def handle_webhook(request):
    app: Application = request.app["bot_app"]
    update = Update.de_json(await request.json(), app.bot)
    await app.process_update(update)
    return web.Response(text="ok")

async def health(_):
    return web.Response(text="ok")

async def main():
    init_db()

    app = (ApplicationBuilder()
           .token(BOT_TOKEN)
           .concurrent_updates(True)
           .build())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    # Aiohttp web server
    webapp = web.Application()
    webapp["bot_app"] = app
    webapp.add_routes([
        web.post("/telegram-webhook", handle_webhook),
        web.get("/healthz", health),
    ])

    # set webhook
    await app.bot.set_webhook(url=WEBHOOK_URL)

    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
    await site.start()

    logging.info("Bot + webhook running.")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())