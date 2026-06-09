import os
import random
import asyncio
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-1003952306202"))

# Global quiz holati
quiz_state = {
    "active": False,
    "questions": [],
    "current_index": 0,
    "current_msg_id": None,
    "correct_index": None,
    "scores": {},       # user_id -> {name, correct, total, wrong_list, answered}
    "start_time": None,
    "task": None,
}

# ═══════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📎 Excel fayl yuboring (.xlsx)\n\n"
        "Format:\n"
        "• 1-ustun: Savol\n"
        "• 2-ustun: To'g'ri javob\n"
        "• 3-5-ustun: Noto'g'ri javoblar\n\n"
        "Yuklangandan so'ng /start_quiz buyrug'ini yuboring."
    )

# ═══════════════════════════════════════════════
async def handle_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.document.get_file()
        path = "/tmp/questions.xlsx"
        await file.download_to_drive(path)

        df = pd.read_excel(path)
        questions = []

        for _, row in df.iterrows():
            try:
                question = str(row.iloc[0]).strip()
                correct = str(row.iloc[1]).strip()

                if not question or not correct or question.lower() == "nan" or correct.lower() == "nan":
                    continue

                wrong = []
                for cell in row.iloc[2:5]:
                    if pd.notna(cell):
                        val = str(cell).strip()
                        if val and val.lower() != "nan":
                            wrong.append(val)

                if not wrong:
                    continue

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

        context.bot_data["questions"] = questions
        await update.message.reply_text(
            f"✅ *{len(questions)} ta savol yuklandi!*\n\n"
            f"▶️ Testni boshlash uchun /start\\_quiz yuboring.",
            parse_mode="Markdown"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Xato: {e}")

# ═══════════════════════════════════════════════
def make_keyboard(options, question_idx):
    """Inline tugmalar — A, B, C, D shaklida"""
    labels = ["A", "B", "C", "D"]
    keyboard = []
    for i, opt in enumerate(options):
        label = labels[i] if i < len(labels) else str(i+1)
        keyboard.append([InlineKeyboardButton(
            f"{label}) {opt}",
            callback_data=f"ans_{question_idx}_{i}"
        )])
    return InlineKeyboardMarkup(keyboard)

# ═══════════════════════════════════════════════
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    if quiz_state["active"]:
        await update.message.reply_text("⚠️ Test allaqachon boshlangan!")
        return

    questions = context.bot_data.get("questions")
    if not questions:
        await update.message.reply_text("❌ Avval Excel fayl yuboring!")
        return

    total_sec = len(questions) * 30
    m, s = divmod(total_sec, 60)
    time_str = f"{m} daqiqa {s} soniya" if m else f"{s} soniya"

    quiz_state.update({
        "active": True,
        "questions": questions,
        "current_index": 0,
        "current_msg_id": None,
        "correct_index": None,
        "scores": {},
        "start_time": datetime.now(),
        "task": None,
    })

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
    task = asyncio.create_task(run_quiz_loop(context))
    quiz_state["task"] = task

# ═══════════════════════════════════════════════
async def run_quiz_loop(context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    questions = quiz_state["questions"]

    for idx in range(len(questions)):
        if not quiz_state["active"]:
            return

        quiz_state["current_index"] = idx
        quiz_state["correct_index"] = questions[idx]["correct_index"]

        # Har savol boshida answered foydalanuvchilarni tozalash
        for uid in quiz_state["scores"]:
            quiz_state["scores"][uid]["answered"] = False

        q = questions[idx]
        progress = f"[{idx + 1}/{len(questions)}]"
        labels = ["A", "B", "C", "D"]

        # Savol matni
        options_text = "\n".join([
            f"{labels[i]}) {opt}" for i, opt in enumerate(q['options'])
        ])

        text = (
            f"📝 *{progress} SAVOL*\n"
            f"{'━' * 28}\n\n"
            f"{q['question']}\n\n"
            f"{options_text}\n\n"
            f"⏳ *30 soniya*"
        )

        try:
            msg = await context.bot.send_message(
                chat_id=GROUP_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=make_keyboard(q["options"], idx)
            )
            quiz_state["current_msg_id"] = msg.message_id

        except Exception as e:
            print(f"Xabar yuborishda xato [{idx+1}]: {e}")
            await asyncio.sleep(2)
            continue

        # 30 soniya kutish
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return

        # Vaqt tugadi — to'g'ri javobni ko'rsatish
        if quiz_state["active"]:
            correct_i = q["correct_index"]
            correct_label = labels[correct_i] if correct_i < len(labels) else str(correct_i+1)
            correct_text = q["options"][correct_i]

            try:
                await context.bot.edit_message_text(
                    chat_id=GROUP_ID,
                    message_id=quiz_state["current_msg_id"],
                    text=(
                        f"📝 *{progress} SAVOL* ✅\n"
                        f"{'━' * 28}\n\n"
                        f"{q['question']}\n\n"
                        f"✅ To'g'ri javob: *{correct_label}) {correct_text}*"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

            await asyncio.sleep(2)

    # Hamma savol tugadi
    if quiz_state["active"]:
        await finish_quiz(context)

# ═══════════════════════════════════════════════
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    query = update.callback_query
    await query.answer()

    if not quiz_state["active"]:
        await query.answer("⚠️ Test faol emas!", show_alert=True)
        return

    data = query.data  # ans_{question_idx}_{option_idx}
    parts = data.split("_")
    if len(parts) != 3:
        return

    q_idx = int(parts[1])
    chosen = int(parts[2])

    # Faqat joriy savolga javob qabul qilish
    if q_idx != quiz_state["current_index"]:
        await query.answer("⏰ Bu savol vaqti o'tdi!", show_alert=True)
        return

    user = query.from_user
    user_id = user.id
    user_name = user.full_name or user.username or f"Foydalanuvchi{user_id}"

    # Allaqachon javob berganmi?
    if user_id in quiz_state["scores"] and quiz_state["scores"][user_id].get("answered"):
        await query.answer("✋ Siz allaqachon javob berdingiz!", show_alert=True)
        return

    is_correct = (chosen == quiz_state["correct_index"])
    labels = ["A", "B", "C", "D"]
    chosen_label = labels[chosen] if chosen < len(labels) else str(chosen+1)

    if user_id not in quiz_state["scores"]:
        quiz_state["scores"][user_id] = {
            "name": user_name,
            "correct": 0,
            "total": 0,
            "wrong_list": [],
            "answered": False,
        }

    quiz_state["scores"][user_id]["total"] += 1
    quiz_state["scores"][user_id]["answered"] = True

    if is_correct:
        quiz_state["scores"][user_id]["correct"] += 1
        await query.answer(f"✅ To'g'ri! {chosen_label} variant", show_alert=False)
    else:
        quiz_state["scores"][user_id]["wrong_list"].append(q_idx + 1)
        await query.answer(f"❌ Noto'g'ri! {chosen_label} variant", show_alert=False)

# ═══════════════════════════════════════════════
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
        await context.bot.send_message(chat_id=GROUP_ID, text="📭 Hech kim qatnashmadi.")
        return

    sorted_scores = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)
    medals = ["🥇", "🥈", "🥉"]

    reyting = []
    for i, sc in enumerate(sorted_scores):
        medal = medals[i] if i < 3 else f"{i+1}."
        pct = round(sc["correct"] / total_q * 100)
        reyting.append(f"{medal} *{sc['name']}*: {sc['correct']}/{total_q} ({pct}%)")

    tahlil = []
    for sc in sorted_scores:
        wrong = sc.get("wrong_list", [])
        if wrong:
            w_str = ", ".join(map(str, wrong[:15]))
            if len(wrong) > 15:
                w_str += f" +{len(wrong)-15} ta"
            tahlil.append(f"• *{sc['name']}*: {w_str}-savollar")

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
        f"📝 *NOTO'G'RI JAVOBLAR:*\n{tahlil_text}\n\n"
        f"{'━' * 28}\n"
        f"🏆 *G'OLIB: {winner['name']}* — {winner['correct']}/{total_q} ({winner_pct}%) 🎉"
    )

    await context.bot.send_message(chat_id=GROUP_ID, text=text, parse_mode="Markdown")

# ═══════════════════════════════════════════════
async def stop_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    if not quiz_state["active"]:
        await update.message.reply_text("⚠️ Hozir faol test yo'q.")
        return

    task = quiz_state.get("task")
    if task and not task.done():
        task.cancel()

    await update.message.reply_text("⏹ Test to'xtatilmoqda...")
    await finish_quiz(context)

# ═══════════════════════════════════════════════
async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global quiz_state

    if not quiz_state["active"]:
        await update.message.reply_text("📭 Hozir faol test yo'q.")
        return

    scores = quiz_state["scores"]
    if not scores:
        await update.message.reply_text("📊 Hali hech kim javob bermadi.")
        return

    total_q = len(quiz_state["questions"])
    idx = quiz_state["current_index"] + 1
    sorted_scores = sorted(scores.values(), key=lambda x: x["correct"], reverse=True)

    lines = [f"📊 *Joriy natijalar ({idx}/{total_q} savol):*\n"]
    for i, sc in enumerate(sorted_scores):
        pct = round(sc["correct"] / idx * 100) if idx else 0
        lines.append(f"{i+1}. *{sc['name']}*: {sc['correct']} to'g'ri ({pct}%)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# ═══════════════════════════════════════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_quiz", start_quiz))
    app.add_handler(CommandHandler("stop_quiz", stop_quiz))
    app.add_handler(CommandHandler("results", results))
    app.add_handler(MessageHandler(filters.Document.FileExtension("xlsx"), handle_excel))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^ans_"))

    print("Bot ishga tushdi...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
