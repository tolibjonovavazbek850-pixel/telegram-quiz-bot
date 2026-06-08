import os
import random
import pandas as pd
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# GURUH ID
GROUP_ID = -1003952306202


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Excel fayl yuboring (.xlsx)\n\n"
        "1-ustun: Savol\n"
        "2-ustun: To'g'ri javob\n"
        "Qolgan ustunlar: Noto'g'ri javoblar"
    )


async def handle_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.document.get_file()

        path = "questions.xlsx"
        await file.download_to_drive(path)

        df = pd.read_excel(path)

        count = 0
        skipped = 0

        for index, row in df.iterrows():

            try:
                question = str(row.iloc[0]).strip()
                correct = str(row.iloc[1]).strip()

                if question == "" or correct == "":
                    skipped += 1
                    continue

                options = []

                for cell in row.iloc[1:]:
                    if pd.notna(cell):
                        value = str(cell).strip()

                        if value != "":
                            options.append(value)

                # Takrorlarni olib tashlash
                options = list(dict.fromkeys(options))

                # To'g'ri javob yo'qolgan bo'lsa qo'shamiz
                if correct not in options:
                    options.insert(0, correct)

                # Telegram maksimum 10 ta variant
                options = options[:10]

                # Kamida 2 ta variant bo'lishi kerak
                if len(options) < 2:
                    skipped += 1
                    print(f"O'tkazib yuborildi: {question}")
                    continue

                random.shuffle(options)

                correct_index = options.index(correct)

                await context.bot.send_poll(
                    chat_id=GROUP_ID,
                    question=question,
                    options=options,
                    type="quiz",
                    correct_option_id=correct_index,
                    is_anonymous=False,
                )

                count += 1

            except Exception as e:
                skipped += 1
                print(f"{index + 1}-savolda xato: {e}")

        await update.message.reply_text(
            f"✅ {count} ta quiz yuborildi.\n"
            f"⚠️ {skipped} ta savol o'tkazib yuborildi."
        )

    except Exception as e:
        await update.message.reply_text(f"Xato: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.Document.FileExtension("xlsx"),
            handle_excel,
        )
    )

    print("Bot ishga tushdi...")

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
