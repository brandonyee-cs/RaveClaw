from telegram.ext import ApplicationBuilder, MessageHandler, filters
from telegram_handler import handle_photo, handle_message
from aci import init_client
from settings import TELEGRAM_BOT_TOKEN


def main():
    print("Initializing Instagram session...")
    init_client()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("RaveClaw running.")
    app.run_polling()


if __name__ == "__main__":
    main()