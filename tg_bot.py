import os
import time
import requests
import threading

BOT_TOKEN = "8783683988:AAHczUKaneFo3FK2JTuRlrN7bLxXgdIgUA0"
ALLOWED_USER_ID = 7245888111
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "")
GITHUB_OWNER = "tatyana1234claude"
GITHUB_REPO  = "stoq-qa-agent"

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
GH_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

SESSION = requests.Session()
SESSION.timeout = 60

KB = {
    "keyboard": [
        [{"text": "▶ Запустить проверку"}],
        [{"text": "📊 Статус последней проверки"}],
        [{"text": "ℹ️ Помощь"}]
    ],
    "resize_keyboard": True
}


def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = keyboard
    try:
        SESSION.post(f"{API}/sendMessage", json=data, timeout=15)
    except Exception as e:
        print(f"send error: {e}")


def trigger_action():
    if not GITHUB_TOKEN:
        return False, "GH_TOKEN не задан"
    try:
        r = SESSION.post(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/qa.yml/dispatches",
            json={"ref": "main"},
            headers=GH_HEADERS,
            timeout=15
        )
        if r.status_code == 204:
            return True, "OK"
        else:
            return False, f"HTTP {r.status_code}: {r.text[:100]}"
    except Exception as e:
        return False, str(e)


def get_latest_run():
    try:
        r = SESSION.get(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1",
            headers=GH_HEADERS,
            timeout=15
        )
        runs = r.json().get("workflow_runs", [])
        if runs:
            return runs[0]
    except Exception as e:
        print(f"get_run error: {e}")
    return None


def get_run_jobs(run_id):
    """Получает детали шагов из запуска"""
    try:
        r = SESSION.get(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/jobs",
            headers=GH_HEADERS,
            timeout=15
        )
        jobs = r.json().get("jobs", [])
        if jobs:
            steps = jobs[0].get("steps", [])
            return steps
    except Exception as e:
        print(f"get_jobs error: {e}")
    return []


def format_report(run, steps):
    """Форматирует отчёт для Telegram"""
    conclusion = run.get("conclusion", "unknown")
    run_number = run.get("run_number", "?")
    url = run.get("html_url", "")
    duration_sec = 0
    if run.get("created_at") and run.get("updated_at"):
        try:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%SZ"
            t1 = datetime.strptime(run["created_at"], fmt)
            t2 = datetime.strptime(run["updated_at"], fmt)
            duration_sec = int((t2 - t1).total_seconds())
        except:
            pass

    if conclusion == "success":
        header = f"✅ <b>Проверка #{run_number} завершена успешно!</b>"
    elif conclusion == "failure":
        header = f"❌ <b>Проверка #{run_number} выявила проблемы!</b>"
    else:
        header = f"⚠️ <b>Проверка #{run_number}: {conclusion}</b>"

    lines = [header, f"⏱ Время: {duration_sec}с", ""]

    # Статус шагов
    step_icons = {
        "success": "✅",
        "failure": "❌",
        "skipped": "⏭",
        "cancelled": "⚠️"
    }

    important_steps = [
        "Run QA Agent",
        "Install dependencies",
        "Upload report",
        "Setup Python"
    ]

    lines.append("<b>Шаги проверки:</b>")
    for step in steps:
        name = step.get("name", "")
        status = step.get("conclusion") or step.get("status", "")
        icon = step_icons.get(status, "⭕")
        if any(s in name for s in important_steps):
            lines.append(f"  {icon} {name}")

    lines.append("")

    if conclusion == "success":
        lines.append("📄 <b>Отчёт доступен на GitHub:</b>")
        lines.append(f'<a href="{url}">Открыть запуск #{run_number}</a>')
        lines.append("")
        lines.append("💡 В разделе <b>Artifacts</b> — HTML с подробностями и скриншотами.")
    else:
        lines.append(f'🔗 <a href="{url}">Посмотреть ошибки на GitHub</a>')

    return "\n".join(lines)


def watch_and_report(chat_id, run_id_to_watch):
    """Следит за запуском и присылает отчёт когда завершится"""
    print(f"Слежу за запуском {run_id_to_watch}...")
    max_wait = 60 * 15  # максимум 15 минут
    elapsed = 0
    interval = 30

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval

        run = get_latest_run()
        if not run or run["id"] != run_id_to_watch:
            continue

        status = run.get("status")
        conclusion = run.get("conclusion")

        print(f"  Статус: {status} / {conclusion} ({elapsed}с)")

        if status == "completed":
            steps = get_run_jobs(run_id_to_watch)
            report = format_report(run, steps)
            send(chat_id, report, keyboard=KB)
            return

    send(chat_id,
        "⏰ Проверка идёт уже 15 минут — возможно зависла.\n"
        f'Проверь вручную: https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions',
        keyboard=KB
    )


def run():
    print("Бот запущен! Жду команды...")
    offset = 0

    while True:
        try:
            r = SESSION.get(
                f"{API}/getUpdates",
                params={"offset": offset, "timeout": 30},
                timeout=40
            )
            updates = r.json().get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                user_id = msg["from"]["id"]
                text = msg.get("text", "")

                print(f"Сообщение от {user_id}: {text}")

                if user_id != ALLOWED_USER_ID:
                    send(chat_id, "Нет доступа.")
                    continue

                if text in ("/start", "/menu"):
                    send(chat_id,
                        "👋 <b>QA Agent — stoq.ai</b>\n\n"
                        "Нажми кнопку чтобы запустить проверку.\n"
                        "Результат пришлю сюда автоматически через ~3 минуты.",
                        keyboard=KB)

                elif text == "▶ Запустить проверку":
                    send(chat_id, "⏳ Запускаю проверку на GitHub...")
                    ok, err = trigger_action()
                    if ok:
                        time.sleep(3)
                        run_data = get_latest_run()
                        run_id = run_data["id"] if run_data else None

                        send(chat_id,
                            "✅ <b>Проверка запущена!</b>\n\n"
                            "⏳ Жди ~3 минуты — пришлю результат сюда автоматически.\n\n"
                            f'<a href="https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions">Следить на GitHub</a>',
                            keyboard=KB)

                        if run_id:
                            t = threading.Thread(
                                target=watch_and_report,
                                args=(chat_id, run_id),
                                daemon=True
                            )
                            t.start()
                    else:
                        send(chat_id, f"❌ Ошибка запуска:\n{err}", keyboard=KB)
                        print(f"GitHub error: {err}")

                elif text == "📊 Статус последней проверки":
                    run_data = get_latest_run()
                    if run_data:
                        icons = {"completed": "✅", "in_progress": "⏳", "queued": "🕐"}
                        conclusions = {
                            "success": "✅ Успешно",
                            "failure": "❌ Есть проблемы",
                            "cancelled": "⚠️ Отменено"
                        }
                        status_icon = icons.get(run_data["status"], "❓")
                        conclusion = conclusions.get(run_data.get("conclusion") or "", "В процессе")
                        send(chat_id,
                            f"{status_icon} <b>Статус:</b> {conclusion}\n"
                            f"🔢 Запуск #{run_data['run_number']}\n"
                            f'🔗 <a href="{run_data["html_url"]}">Открыть на GitHub</a>',
                            keyboard=KB)
                    else:
                        send(chat_id, "Нет данных о проверках.", keyboard=KB)

                elif text == "ℹ️ Помощь":
                    send(chat_id,
                        "<b>Как пользоваться:</b>\n\n"
                        "1️⃣ Нажми <b>▶ Запустить проверку</b>\n"
                        "2️⃣ Жди ~3 минуты\n"
                        "3️⃣ Получи результат прямо здесь\n\n"
                        "<b>Что проверяется:</b>\n"
                        "• Горизонтальный скролл\n"
                        "• Сломанные картинки\n"
                        "• Элементы выходящие за экран\n"
                        "• Битые ссылки (404)\n"
                        "• JS ошибки в консоли\n"
                        "• Скорость загрузки и FCP\n"
                        "• На 4 экранах: 📱 планшет 💻 ноутбук 🖥 десктоп",
                        keyboard=KB)

        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(3)


if __name__ == "__main__":
    run()
