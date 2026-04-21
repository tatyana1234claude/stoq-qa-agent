"""
Telegram бот для запуска QA агента через GitHub Actions
Запускается локально или на сервере
"""

import asyncio
import os
import urllib.request
import urllib.parse
import json

BOT_TOKEN = "8783683988:AAHczUKaneFo3FK2JTuRlrN7bLxXgdIgUA0"
ALLOWED_USER_ID = 7245888111

# Заполни после создания репозитория на GitHub:
GITHUB_TOKEN = ""        # Settings → Developer settings → Tokens → Generate new token (repo + workflow)
GITHUB_OWNER = ""        # твой username на GitHub
GITHUB_REPO  = "stoq-qa-agent"   # название репозитория

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def tg_request(method, data=None):
    url = f"{API}/{method}"
    payload = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def send_message(chat_id, text, reply_markup=None):
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    tg_request("sendMessage", data)


def trigger_github_action():
    if not GITHUB_TOKEN or not GITHUB_OWNER:
        return False, "GitHub токен не настроен в боте"
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/workflows/qa.yml/dispatches"
    payload = json.dumps({"ref": "main"}).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return True, "OK"
    except Exception as e:
        return False, str(e)


def get_latest_run_status():
    if not GITHUB_TOKEN or not GITHUB_OWNER:
        return None
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs?per_page=1"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            runs = data.get("workflow_runs", [])
            if runs:
                run = runs[0]
                return {
                    "status": run["status"],
                    "conclusion": run["conclusion"],
                    "url": run["html_url"],
                    "created": run["created_at"]
                }
    except:
        pass
    return None


MAIN_KEYBOARD = {
    "keyboard": [
        [{"text": "▶ Запустить проверку"}],
        [{"text": "📊 Статус последней проверки"}],
        [{"text": "ℹ️ Помощь"}]
    ],
    "resize_keyboard": True
}


def run_bot():
    print("Бот запущен. Ожидаю команды...")
    offset = 0

    while True:
        try:
            resp = tg_request("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": ["message"]})
            updates = resp.get("result", [])

            for update in updates:
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                user_id = msg["from"]["id"]
                text = msg.get("text", "")

                if user_id != ALLOWED_USER_ID:
                    send_message(chat_id, "Нет доступа.")
                    continue

                if text in ("/start", "/menu"):
                    send_message(chat_id,
                        "👋 <b>QA Agent для stoq.ai</b>\n\n"
                        "Нажми кнопку чтобы запустить проверку.\n"
                        "Результат придёт через ~3 минуты.",
                        reply_markup=MAIN_KEYBOARD
                    )

                elif text == "▶ Запустить проверку":
                    send_message(chat_id, "⏳ Запускаю проверку на GitHub...\nРезультат придёт через ~3 минуты.")
                    ok, err = trigger_github_action()
                    if ok:
                        send_message(chat_id,
                            "✅ <b>Проверка запущена!</b>\n\n"
                            f"Следи за статусом: https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions\n\n"
                            "Отчёт появится там же после завершения.",
                            reply_markup=MAIN_KEYBOARD
                        )
                    else:
                        send_message(chat_id,
                            f"❌ Ошибка запуска: {err}\n\nПроверь GITHUB_TOKEN в боте.",
                            reply_markup=MAIN_KEYBOARD
                        )

                elif text == "📊 Статус последней проверки":
                    run = get_latest_run_status()
                    if run:
                        status_emoji = {"completed": "✅", "in_progress": "⏳", "queued": "🕐"}.get(run["status"], "❓")
                        conclusion_emoji = {"success": "✅", "failure": "❌", "cancelled": "⚠️"}.get(run.get("conclusion") or "", "")
                        send_message(chat_id,
                            f"{status_emoji} <b>Статус:</b> {run['status']} {conclusion_emoji}\n"
                            f"🔗 <a href='{run['url']}'>Открыть на GitHub</a>",
                            reply_markup=MAIN_KEYBOARD
                        )
                    else:
                        send_message(chat_id, "Нет данных о проверках. Настрой GITHUB_TOKEN.", reply_markup=MAIN_KEYBOARD)

                elif text == "ℹ️ Помощь":
                    send_message(chat_id,
                        "<b>Как пользоваться:</b>\n\n"
                        "1. Нажми <b>▶ Запустить проверку</b>\n"
                        "2. Подожди ~3 минуты\n"
                        "3. Зайди на GitHub Actions — там будет HTML-отчёт\n\n"
                        "<b>Что проверяется:</b>\n"
                        "• Горизонтальный скролл\n"
                        "• Сломанные картинки\n"
                        "• Overflow элементов\n"
                        "• Битые ссылки\n"
                        "• JS ошибки\n"
                        "• Скорость загрузки\n"
                        "• На 4 разрешениях экрана",
                        reply_markup=MAIN_KEYBOARD
                    )

        except Exception as e:
            print(f"Ошибка: {e}")
            import time
            time.sleep(5)


if __name__ == "__main__":
    run_bot()
