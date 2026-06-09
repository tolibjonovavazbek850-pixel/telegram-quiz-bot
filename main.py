import os
import random
import asyncio
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    PollAnswerHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = -1003952306202

# Faol quiz holati
quiz_state = {
    "active": False,
    "questions": [],
    "current_index": 0,
    "current_poll_id": None,
    "correct_index": None,
    "scores": {},        # user_id -> {name, correct, total}
    "start_time": None,
}

# ─────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📎 Excel fayl yuboring (.xlsx)\n\n"
        "Format:\n"
        "• 1-ustun: Savol\n"
        "• 2-ustun: To'g'ri javob\n"
        "• 3-5-ustun: Noto'g'ri javoblar\n\n"
        "Yuklangandan so'ng /start_quiz buyrug'ini yuboring."
    )

# ─────────────────────────────────────────
async def handle_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.document.get_file()
        path = "questions.xlsx"
        await file.download_to_drive(path)

        df = pd.read_excel(path)
        questions = []

        for _, row in df.iterrows():
            try:
                question = str(row.iloc[0]).strip()
                correct = str(row.iloc[1]).strip()

                if not question or not correct or question.lower() == "nan" or correct.lower() == "nan":
                    continue

                # Noto'g'ri javoblarni yig'ish (3-5 ustunlar)
                wrong = []
                for cell in row.iloc[2:5]:
                    if pd.notna(cell):
                        val = str(cell).strip()
                        if val and val.lower() != "nan":
                            wrong.append(val)

                if not wrong:
                    continue

                # Variantlarni aralashtirish
                options = wrong[:3] + [correct]
                random.shuffle(options)
                correct_index = options.index(correct)

                questions.append({
                    "question": question,
                    "options": options,
                    "correct_index": correct_index,
                })

            except Exception as e:
                print(f"Savolda xato: {e}")

        if not questions:
            await update.message.reply_text("❌ Savollar topilmadi. Excel formatini tekshiring.")
            return

        # Savollarni xotiraga saqlash
        context.bot_data["questions"] = questions

        await update.message.reply_text(
            f"✅ *{len(questions)} ta savol yuklandi!*\n\n"
            f"▶️ Testni boshlash uchun /start\\_quiz yuboring.",
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")

# ─────────────────────────────────────────
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    if quiz_state["active"]:
        await update.message.reply_text("⚠️ Test allaqachon boshlangan!")
        return

    questions = context.bot_data.get("questions")
    if not questions:
        await update.message.reply_text("❌ Avval Excel fayl yuboring!")
        return

    total_time = len(questions) * 30
    m, s = divmod(total_time, 60)
    time_str = f"{m} daqiqa {s} soniya" if m else f"{s} soniya"

    quiz_state = {
        "active": True,
        "questions": questions,
        "current_index": 0,
        "current_poll_id": None,
        "correct_index": None,
        "scores": {},
        "start_time": datetime.now(),
    }

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=(
            f"🎯 *TEST BOSHLANMOQDA!*\n\n"
            f"📊 Savollar: *{len(questions)} ta*\n"
            f"⏱ Umumiy vaqt: *{time_str}*\n"
            f"⏳ Har bir savolga: *30 soniya*\n\n"
            f"Tayyor bo'ling! 3 soniyadan so'ng boshlanadi... 🚀"
        ),
        parse_mode="Markdown"
    )

    await asyncio.sleep(3)
    await send_next_question(context)

# ─────────────────────────────────────────
async def send_next_question(context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    if not quiz_state["active"]:
        return

    idx = quiz_state["current_index"]
    questions = quiz_state["questions"]

    if idx >= len(questions):
        await finish_quiz(context)
        return

    q = questions[idx]
    progress = f"[{idx + 1}/{len(questions)}]"

    try:
        msg = await context.bot.send_poll(
            chat_id=GROUP_ID,
            question=f"{progress} {q['question']}",
            options=q["options"],
            type="quiz",
            correct_option_id=q["correct_index"],
            is_anonymous=False,
            open_period=30,
        )
        quiz_state["current_poll_id"] = msg.poll.id
        quiz_state["correct_index"] = q["correct_index"]

    except Exception as e:
        print(f"Poll yuborishda xato: {e}")
        quiz_state["current_index"] += 1
        await send_next_question(context)
        return

    # 31 soniya kutib keyingi savolga o'tish
    await asyncio.sleep(31)

    if quiz_state["active"] and quiz_state["current_index"] == idx:
        quiz_state["current_index"] += 1
        await send_next_question(context)

# ─────────────────────────────────────────
async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    answer = update.poll_answer
    if answer.poll_id != quiz_state.get("current_poll_id"):
        return
    if not answer.option_ids:
        return

    user = answer.user
    user_id = user.id
    user_name = user.full_name or user.username or f"User{user_id}"
    chosen = answer.option_ids[0]
    is_correct = (chosen == quiz_state["correct_index"])

    if user_id not in quiz_state["scores"]:
        quiz_state["scores"][user_id] = {
            "name": user_name,
            "correct": 0,
            "total": 0,
            "wrong_list": []
        }

    quiz_state["scores"][user_id]["total"] += 1
    if is_correct:
        quiz_state["scores"][user_id]["correct"] += 1
    else:
        q_num = quiz_state["current_index"] + 1
        quiz_state["scores"][user_id]["wrong_list"].append(q_num)

# ─────────────────────────────────────────
async def finish_quiz(context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    quiz_state["active"] = False
    scores = quiz_state["scores"]
    total_q = len(quiz_state["questions"])

    elapsed = datetime.now() - quiz_state["start_time"]
    m, s = divmod(int(elapsed.total_seconds()), 60)
    elapsed_str = f"{m} daqiqa {s} soniya"

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text="⏹ *Test yakunlandi! Natijalar hisoblanmoqda...*",
        parse_mode="Markdown"
    )
    await asyncio.sleep(2)

    if not scores:
        await context.bot.send_message(
            chat_id=GROUP_ID,
            text="📭 Hech kim qatnashmadi.",
        )
        return

    sorted_scores = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]

    # Reyting
    reyting = []
    for i, s in enumerate(sorted_scores):
        medal = medals[i] if i < 3 else f"{i+1}."
        pct = round(s["correct"] / total_q * 100)
        reyting.append(f"{medal} *{s['name']}*: {s['correct']}/{total_q} ({pct}%)")

    # Xato tahlil
    tahlil = []
    for s in sorted_scores:
        wrong = s.get("wrong_list", [])
        if wrong:
            w_str = ", ".join(map(str, wrong[:10]))
            if len(wrong) > 10:
                w_str += f" +{len(wrong)-10} ta"
            tahlil.append(f"• *{s['name']}*: {w_str}-savollar noto'g'ri")

    tahlil_text = "\n".join(tahlil) if tahlil else "Hamma to'g'ri javob berdi! 🎉"

    winner = sorted_scores[0]
    winner_pct = round(winner["correct"] / total_q * 100)

    text = (
        f"🏆 *TEST NATIJALARI*\n"
        f"{'━' * 28}\n\n"
        f"📊 Savollar: *{total_q} ta*\n"
        f"⏱ Sarflangan vaqt: *{elapsed_str}*\n"
        f"👥 Qatnashchilar: *{len(scores)} kishi*\n\n"
        f"🎖 *REYTING:*\n" + "\n".join(reyting) + "\n\n"
        f"{'━' * 28}\n"
        f"📝 *XATO SAVOLLAR TAHLILI:*\n{tahlil_text}\n\n"
        f"{'━' * 28}\n"
        f"🏆 *G'OLIB: {winner['name']}* — {winner['correct']}/{total_q} ({winner_pct}%) 🎉"
    )

    await context.bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────
async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state
    if not quiz_state["active"]:
        await update.message.reply_text("⚠️ Hozir faol test yo'q.")
        return
    await update.message.reply_text("⏹ Test to'xtatilmoqda...")
    await finish_quiz(context)

async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state
    if not quiz_state["active"] or not quiz_state["scores"]:
        await update.message.reply_text("📭 Hozir natija yo'q.")
        return

    scores = quiz_state["scores"]
    total_q = len(quiz_state["questions"])
    idx = quiz_state["current_index"]
    sorted_scores = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)

    lines = [f"📊 *Joriy natijalar ({idx}/{total_q} savol):*\n"]
    for i, s in enumerate(sorted_scores):
        lines.append(f"{i+1}. *{s['name']}*: {s['correct']} to'g'ri")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_quiz", start_quiz))
    app.add_handler(CommandHandler("stop_quiz", stop_quiz))
    app.add_handler(CommandHandler("results", results))
    app.add_handler(MessageHandler(filters.Document.FileExtension("xlsx"), handle_excel))
    app.add_handler(PollAnswerHandler(handle_poll_answer))

    print("Bot ishga tushdi...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
