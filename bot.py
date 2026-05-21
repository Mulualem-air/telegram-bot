import os
import logging
import requests
import time
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TELEGRAM_BOT_TOKEN = "8967105953:AAEH95HkGCjnKA8uErDKla6Smuv2zG8vspY"
GROQ_API_KEY       = "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"
CHANNEL_USERNAME   = "@mullerapp"
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

logging.basicConfig(level=logging.INFO)
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are a helpful assistant in a Telegram group.
- Answer ONLY the question asked â€” keep it brief and clear (2â€“4 sentences max).
- Detect the user's language automatically and reply in the SAME language (Amharic or English).
- Never make up information. If unsure, say so honestly.
- Do not add unnecessary greetings or filler words."""


def clear_conflict():
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        r = requests.get(url, timeout=10)
        logging.info(f"Webhook cleared: {r.json()}")
    except Exception as e:
        logging.warning(f"Could not clear webhook: {e}")


def ask_groq(question: str) -> str:
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ],
        max_tokens=300
    )
    return response.choices[0].message.content.strip()


async def handle_mention(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    bot_username = (await context.bot.get_me()).username
    if f"@{bot_username}" not in message.text:
        return
    question = message.text.replace(f"@{bot_username}", "").strip()
    if not question:
        await message.reply_text("â“ Please ask me a question after mentioning me!")
        return
    await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
    try:
        answer = ask_groq(question)
        await message.reply_text(answer)
    except Exception as e:
        logging.error(f"Groq error: {e}")
        await message.reply_text(f"âš ï¸ Error: {str(e)[:200]}")


def main():
    clear_conflict()
    time.sleep(3)
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mention))
    print("âœ… Bot is running with Groq!")
    app.run_polling(allowed_updates=["message"], drop_pending_updates=True)


if __name__ == "__main__":
    main()
