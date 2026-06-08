import os
import random
import pandas as pd
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")

GROUP_ID = -1003952306202


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Excel fayl yuboring (.xlsx).\n"
        "1-ustun: Savol\n"
        "2-ustun: To'g'ri javob\n"
        "Qolgan ustunlar: Noto'g'ri javoblar"
    )


async def handle_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()

    path = "questions.xlsx"
    await file.download_to_drive(path)

    df = pd.read_excel(path)

    count = 0

    for _, row in df.iterrows():
        question = str(row.iloc[0]).strip()

        correct = str(row.iloc[1]).strip()

        options = []

        for cell in row.iloc[1:]:
            if pd.notna(cell):
                options.append(str(cell).strip())

options = list(dict.fromkeys(options))

# 10 tadan ortiq variant bo'lsa kesib tashlaymiz
options = options[:10]

# Kamida 2 ta variant bo'lishi kerak
if len(options) < 2:
    print(f"O'tkazib yuborildi: {question}")
    continue

# To'g'ri javob yo'qolib qolgan bo'lsa
if correct not in options:
    options.insert(0, correct)

options = options[:10]

        random.shuffle(options)

        correct_index = options.index(correct)

        try:
            await context.bot.send_poll(
                chat_id=GROUP_ID,
                question=question,
                options=options,
                type="quiz",
                correct_option_id=correct_index,
                is_anonymous=False
            )

            count += 1

        except Exception as e:
            print(e)

    await update.message.reply_text(
        f"{count} ta quiz yuborildi."
    )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.Document.FileExtension("xlsx"),
            handle_excel
        )
    )

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
