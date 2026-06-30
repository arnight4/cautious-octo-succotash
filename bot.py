import os
import re
import logging

from dotenv import load_dotenv
from email_validator import validate_email, EmailNotValidError

import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GOOGLE_CREDENTIALS_PATH = os.environ["GOOGLE_CREDENTIALS_PATH"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SHEET_NAME = os.environ["SHEET_NAME"]

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Простой, но надёжный поиск email в произвольном тексте
EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def get_worksheet():
    """
    Открывает конкретный лист (вкладку) по имени внутри таблицы.
    Все остальные листы при этом не затрагиваются — мы работаем
    только с объектом конкретного worksheet.
    """
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = spreadsheet.worksheet(SHEET_NAME)
    return worksheet


def extract_and_validate_emails(text: str):
    candidates = EMAIL_REGEX.findall(text)
    valid = []
    for candidate in candidates:
        try:
            result = validate_email(candidate, check_deliverability=False)
            valid.append(result.normalized)
        except EmailNotValidError:
            continue
    return valid


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пришлите email - проверю его и добавлю новой строкой в таблицу."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    emails = extract_and_validate_emails(text)

    if not emails:
        await update.message.reply_text(
            "Это не похоже на корректный email. Пришлите адрес вида name@example.com"
        )
        return

    try:
        worksheet = get_worksheet()
    except Exception:
        logger.exception("Не удалось открыть таблицу/лист")
        await update.message.reply_text(
            "Ошибка доступа к Google Таблице. Проверьте настройки (см. README)."
        )
        return

    added = []
    for email in emails:
        try:
            worksheet.append_row([email], value_input_option="USER_ENTERED")
            added.append(email)
        except Exception:
            logger.exception("Не удалось добавить email: %s", email)

    if added:
        await update.message.reply_text("Добавлено в таблицу:\n" + "\n".join(added))
    else:
        await update.message.reply_text("Не удалось записать email в таблицу.")


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Бот запущен и слушает сообщения...")
    app.run_polling()


if __name__ == "__main__":
    main()
