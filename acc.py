import asyncio
import json
import logging
import os
import random
import html
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = "8305631349:AAFQgbKljongzgdzCW8DhNCGYck-HAcz21c"
ADMIN_ID = 8024332236
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AccountBot")

PLATFORMS_FILE = DATA_DIR / "platforms.json"
USER_STATE_FILE = DATA_DIR / "user_state.json"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving {path}: {e}")


platforms = load_json(PLATFORMS_FILE, {})
user_state = load_json(USER_STATE_FILE, {})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "👋 Hello! I’m the Account Bot.\n\nUse /get to receive an account."
        )
    except Exception as e:
        logger.error(f"Start error: {e}")


async def up(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.id != ADMIN_ID:
            return await update.message.reply_text("❌ You are not the admin.")
        await update.message.reply_text("📄 Please send a .txt file (format: user:pass).")
        context.user_data["awaiting_file"] = True
    except Exception as e:
        logger.error(f"/up error: {e}")


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        if user_id != ADMIN_ID or "awaiting_file" not in context.user_data:
            return

        doc = update.message.document
        file_path = DATA_DIR / doc.file_name

        telegram_file = await doc.get_file()
        await telegram_file.download_to_drive(file_path)

        context.user_data["uploaded_file"] = str(file_path)
        context.user_data.pop("awaiting_file", None)
        context.user_data["awaiting_platform_name"] = True

        await update.message.reply_text(
            "✅ File uploaded!\n\nNow tell me what platform these accounts."
        )
    except Exception as e:
        logger.error(f"File handle error: {e}")
        await update.message.reply_text("⚠️ Failed to process file. Try again.")


async def handle_platform_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.id != ADMIN_ID or "awaiting_platform_name" not in context.user_data:
            return

        name = update.message.text.strip()
        file_path = context.user_data.pop("uploaded_file", None)
        if not file_path or not os.path.exists(file_path):
            return await update.message.reply_text("❌ Uploaded file missing. Try again.")

        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if ":" in line]

        platforms[name] = lines
        save_json(PLATFORMS_FILE, platforms)
        context.user_data.pop("awaiting_platform_name", None)

        await update.message.reply_text(f"✅ {len(lines)} accounts saved under platform: {name}")
    except Exception as e:
        logger.error(f"Platform name error: {e}")


async def get_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.message.from_user.id
        if user_id in user_state and user_state[user_id].get("need_review"):
            return await update.message.reply_text(
                "⚠️ Please review your previous account first before getting a new one."
            )

        if not platforms:
            return await update.message.reply_text("😕 No platforms available right now.")

        buttons = [[InlineKeyboardButton(p, callback_data=f"get|{p}")] for p in platforms.keys()]
        await update.message.reply_text(
            "👇 Select a platform to get a random account:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logger.error(f"/get error: {e}")


async def give_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if user_id in user_state and user_state[user_id].get("need_review"):
            return await query.answer("⚠️ Please review your previous account first.", show_alert=True)

        _, platform = query.data.split("|", 1)
        accounts = platforms.get(platform, [])
        if not accounts:
            return await query.answer("❌ No accounts left for this platform.", show_alert=True)

        account = random.choice(accounts)
        platforms[platform].remove(account)
        save_json(PLATFORMS_FILE, platforms)

        user_state[user_id] = {"need_review": True, "platform": platform, "account": account}
        save_json(USER_STATE_FILE, user_state)

        user, pwd = account.split(":", 1)
        buttons = [
            [
                InlineKeyboardButton("✅ Working", callback_data="review|working"),
                InlineKeyboardButton("❌ Not Working", callback_data="review|not_working"),
            ]
        ]

        safe_user = html.escape(user)
        safe_pwd = html.escape(pwd)

        await query.edit_message_text(
            f"🔐 <b>Your Details:</b>\nUser: <code>{safe_user}</code>\nPass: <code>{safe_pwd}</code>\n\n"
            "After checking, click below to submit your review.\n\n"
            "⚠️ You must review before getting a new account.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    except Exception as e:
        logger.error(f"give_account error: {e}")
        try:
            await query.answer("⚠️ Something went wrong. Try again later.", show_alert=True)
        except:
            pass


async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id

        if user_id not in user_state or not user_state[user_id].get("need_review"):
            return await query.answer("❌ No pending review.", show_alert=True)

        data = user_state[user_id]
        platform = data["platform"]
        account = data["account"]
        review_type = "Working ✅" if query.data.endswith("working") else "Not Working ❌"

        await context.bot.send_message(
            ADMIN_ID,
            f"📝 <b>New Review Received</b>\n\n👤 User ID: <code>{user_id}</code>\n"
            f"💠 Platform: <b>{platform}</b>\n🔑 Account: <code>{account}</code>\n💬 Review: <b>{review_type}</b>",
            parse_mode=ParseMode.HTML,
        )

        user_state[user_id]["need_review"] = False
        save_json(USER_STATE_FILE, user_state)

        user, pwd = account.split(":", 1)
        safe_user = html.escape(user)
        safe_pwd = html.escape(pwd)

        await query.edit_message_text(
            f"🔐 <b>Your Details:</b>\nUser: <code>{safe_user}</code>\nPass: <code>{safe_pwd}</code>\n\n"
            "🙏 Thank you for your review!\nYou can now use /get to manually request a new account.",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Review error: {e}")


async def delete_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message.from_user.id != ADMIN_ID:
            return await update.message.reply_text("❌ You are not the admin.")
        if len(context.args) == 0:
            return await update.message.reply_text("Usage: /del <platform>")

        platform = " ".join(context.args)
        if platform not in platforms:
            return await update.message.reply_text("❌ No such platform exists.")

        del platforms[platform]
        save_json(PLATFORMS_FILE, platforms)
        await update.message.reply_text(f"🗑️ All accounts for platform '{platform}' have been deleted.")
    except Exception as e:
        logger.error(f"/del error: {e}")


def main():
    try:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("up", up))
        app.add_handler(CommandHandler("get", get_accounts))
        app.add_handler(CommandHandler("del", delete_platform))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_platform_name))
        app.add_handler(CallbackQueryHandler(give_account, pattern=r'^get\|'))
        app.add_handler(CallbackQueryHandler(handle_review, pattern=r'^review\|'))
        logger.info("Bot started successfully.")
        app.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.critical(f"Fatal startup error: {e}")


if __name__ == "__main__":
    main()
