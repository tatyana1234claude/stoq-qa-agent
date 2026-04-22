import os
import time
import requests
import threading

BOT_TOKEN = "8783683988:AAHczUKaneFo3FK2JTuRlrN7bLxXgdIgUA0"
ALLOWED_USER_IDS = [7245888111, 1245843153]
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
        [{"text": "\u25b6 \u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443"}],
        [{"text": "\ud83d\udcca \u0421\u0442\u0430\u0442\u0443\u0441 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0439 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438"}],
        [{"text": "\u2139\ufe0f \u041f\u043e\u043c\u043e\u0449\u044c"}]
    ],
    "resize_keyboard": True
}

# Защита от двойного запуска
_watching = False
_watch_lock = threading.Lock()


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
    try:
        r = SESSION.get(
            f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/actions/runs/{run_id}/jobs",
            headers=GH_HEADERS,
            timeout=15
        )
        jobs = r.json().get("jobs", [])
        if jobs:
            return jobs[0].get("steps", [])
    except Exception as e:
        print(f"get_jobs error: {e}")
    return []


def format_report(run, steps):
    conclusion = run.get("conclusion", "unknown")
    run_number = run.get("run_number", "?")
    url = run.get("html_url", "")

    duration_sec = 0
    try:
        from datetime import datetime
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        t1 = datetime.strptime(run["created_at"], fmt)
        t2 = datetime.strptime(run["updated_at"], fmt)
        duration_sec = int((t2 - t1).total_seconds())
    except:
        pass

    if conclusion == "success":
        header = f"\u2705 <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 #{run_number} \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u0430!</b>"
    elif conclusion == "failure":
        header = f"\u274c <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 #{run_number} \u0432\u044b\u044f\u0432\u0438\u043b\u0430 \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u044b!</b>"
    else:
        header = f"\u26a0\ufe0f <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 #{run_number}: {conclusion}</b>"

    lines = [header, f"\u23f1 \u0412\u0440\u0435\u043c\u044f: {duration_sec}\u0441", ""]

    step_icons = {"success": "\u2705", "failure": "\u274c", "skipped": "\u23ed", "cancelled": "\u26a0\ufe0f"}
    important = ["Run QA Agent", "Install dependencies", "Upload report", "Setup Python"]

    lines.append("<b>\u0428\u0430\u0433\u0438 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438:</b>")
    for step in steps:
        name = step.get("name", "")
        status = step.get("conclusion") or step.get("status", "")
        icon = step_icons.get(status, "\u2b55")
        if any(s in name for s in important):
            lines.append(f"  {icon} {name}")

    lines.append("")

    if conclusion == "success":
        lines.append(f"\ud83d\udcc4 <b>\u041e\u0442\u0447\u0451\u0442 \u043d\u0430 GitHub:</b>")
        lines.append(f'<a href="{url}">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u0437\u0430\u043f\u0443\u0441\u043a #{run_number}</a>')
        lines.append("")
        lines.append("\ud83d\udca1 \u0412 \u0440\u0430\u0437\u0434\u0435\u043b\u0435 <b>Artifacts</b> \u2014 HTML \u0441\u043e \u0441\u043a\u0440\u0438\u043d\u0448\u043e\u0442\u0430\u043c\u0438 \u0438 \u043f\u043e\u0434\u0440\u043e\u0431\u043d\u043e\u0441\u0442\u044f\u043c\u0438.")
    else:
        lines.append(f'\ud83d\udd17 <a href="{url}">\u041f\u043e\u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c \u043e\u0448\u0438\u0431\u043a\u0438 \u043d\u0430 GitHub</a>')

    return "\n".join(lines)


def watch_and_report(chat_id, run_id_to_watch):
    global _watching
    print(f"Слежу за запуском {run_id_to_watch}...")
    max_wait = 60 * 15
    elapsed = 0
    interval = 30

    try:
        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval

            run = get_latest_run()
            if not run or run["id"] != run_id_to_watch:
                continue

            status = run.get("status")
            print(f"  Статус: {status} ({elapsed}с)")

            if status == "completed":
                steps = get_run_jobs(run_id_to_watch)
                report = format_report(run, steps)
                send(chat_id, report, keyboard=KB)
                return

        send(chat_id,
            "\u23f0 \u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0438\u0434\u0451\u0442 \u0443\u0436\u0435 15 \u043c\u0438\u043d\u0443\u0442 \u2014 \u0432\u043e\u0437\u043c\u043e\u0436\u043d\u043e \u0437\u0430\u0432\u0438\u0441\u043b\u0430.\n"
            f'\u041f\u0440\u043e\u0432\u0435\u0440\u044c \u0432\u0440\u0443\u0447\u043d\u0443\u044e: https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions',
            keyboard=KB
        )
    finally:
        with _watch_lock:
            _watching = False


def run():
    global _watching
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

                if user_id not in ALLOWED_USER_IDS:
                    send(chat_id, "Нет доступа.")
                    continue

                if text in ("/start", "/menu"):
                    send(chat_id,
                        "\ud83d\udc4b <b>QA Agent \u2014 stoq.ai</b>\n\n"
                        "\u041d\u0430\u0436\u043c\u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u0447\u0442\u043e\u0431\u044b \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443.\n"
                        "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u043f\u0440\u0438\u0448\u043b\u044e \u0441\u044e\u0434\u0430 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0447\u0435\u0440\u0435\u0437 ~3 \u043c\u0438\u043d\u0443\u0442\u044b.",
                        keyboard=KB)

                elif text == "\u25b6 \u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443":
                    # Защита от двойного запуска
                    with _watch_lock:
                        if _watching:
                            send(chat_id,
                                "\u23f3 <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0443\u0436\u0435 \u0438\u0434\u0451\u0442!</b>\n\n"
                                "\u041f\u043e\u0434\u043e\u0436\u0434\u0438 \u043f\u043e\u043a\u0430 \u043d\u0435 \u043f\u0440\u0438\u0434\u0451\u0442 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442.",
                                keyboard=KB)
                            continue

                    # Проверяем GitHub тоже
                    run_data = get_latest_run()
                    if run_data and run_data.get("status") in ("in_progress", "queued"):
                        send(chat_id,
                            "\u23f3 <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0443\u0436\u0435 \u0438\u0434\u0451\u0442 \u043d\u0430 GitHub!</b>\n\n"
                            f'\u0421\u043b\u0435\u0434\u0438: <a href="{run_data["html_url"]}">GitHub Actions</a>',
                            keyboard=KB)
                        continue

                    send(chat_id, "\u23f3 \u0417\u0430\u043f\u0443\u0441\u043a\u0430\u044e \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443 \u043d\u0430 GitHub...")
                    ok, err = trigger_action()

                    if ok:
                        time.sleep(4)
                        run_data = get_latest_run()
                        run_id = run_data["id"] if run_data else None

                        send(chat_id,
                            "\u2705 <b>\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u0437\u0430\u043f\u0443\u0449\u0435\u043d\u0430!</b>\n\n"
                            "\u23f3 \u0416\u0434\u0438 ~3 \u043c\u0438\u043d\u0443\u0442\u044b \u2014 \u043f\u0440\u0438\u0448\u043b\u044e \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0441\u044e\u0434\u0430 \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438.\n\n"
                            f'<a href="https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/actions">\u0421\u043b\u0435\u0434\u0438\u0442\u044c \u043d\u0430 GitHub</a>',
                            keyboard=KB)

                        if run_id:
                            with _watch_lock:
                                _watching = True
                            t = threading.Thread(
                                target=watch_and_report,
                                args=(chat_id, run_id),
                                daemon=True
                            )
                            t.start()
                    else:
                        send(chat_id, f"\u274c \u041e\u0448\u0438\u0431\u043a\u0430 \u0437\u0430\u043f\u0443\u0441\u043a\u0430:\n{err}", keyboard=KB)
                        print(f"GitHub error: {err}")

                elif text == "\ud83d\udcca \u0421\u0442\u0430\u0442\u0443\u0441 \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u0435\u0439 \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0438":
                    run_data = get_latest_run()
                    if run_data:
                        icons = {"completed": "\u2705", "in_progress": "\u23f3", "queued": "\ud83d\udd50"}
                        conclusions = {
                            "success": "\u2705 \u0423\u0441\u043f\u0435\u0448\u043d\u043e",
                            "failure": "\u274c \u0415\u0441\u0442\u044c \u043f\u0440\u043e\u0431\u043b\u0435\u043c\u044b",
                            "cancelled": "\u26a0\ufe0f \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e"
                        }
                        status_icon = icons.get(run_data["status"], "\u2753")
                        conclusion = conclusions.get(run_data.get("conclusion") or "", "\u0412 \u043f\u0440\u043e\u0446\u0435\u0441\u0441\u0435")
                        send(chat_id,
                            f"{status_icon} <b>\u0421\u0442\u0430\u0442\u0443\u0441:</b> {conclusion}\n"
                            f"\ud83d\udd22 \u0417\u0430\u043f\u0443\u0441\u043a #{run_data['run_number']}\n"
                            f'\ud83d\udd17 <a href="{run_data["html_url"]}">\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043d\u0430 GitHub</a>',
                            keyboard=KB)
                    else:
                        send(chat_id, "\u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u043e \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0430\u0445.", keyboard=KB)

                elif text == "\u2139\ufe0f \u041f\u043e\u043c\u043e\u0449\u044c":
                    send(chat_id,
                        "<b>\u041a\u0430\u043a \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u044c\u0441\u044f:</b>\n\n"
                        "1\ufe0f\u20e3 \u041d\u0430\u0436\u043c\u0438 <b>\u25b6 \u0417\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0443</b>\n"
                        "2\ufe0f\u20e3 \u0416\u0434\u0438 ~3 \u043c\u0438\u043d\u0443\u0442\u044b\n"
                        "3\ufe0f\u20e3 \u041f\u043e\u043b\u0443\u0447\u0438 \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0437\u0434\u0435\u0441\u044c\n\n"
                        "<b>\u0427\u0442\u043e \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u0442\u0441\u044f:</b>\n"
                        "\u2022 \u0413\u043e\u0440\u0438\u0437\u043e\u043d\u0442\u0430\u043b\u044c\u043d\u044b\u0439 \u0441\u043a\u0440\u043e\u043b\u043b\n"
                        "\u2022 \u0421\u043b\u043e\u043c\u0430\u043d\u043d\u044b\u0435 \u043a\u0430\u0440\u0442\u0438\u043d\u043a\u0438\n"
                        "\u2022 \u042d\u043b\u0435\u043c\u0435\u043d\u0442\u044b \u0432\u044b\u0445\u043e\u0434\u044f\u0449\u0438\u0435 \u0437\u0430 \u044d\u043a\u0440\u0430\u043d\n"
                        "\u2022 \u0411\u0438\u0442\u044b\u0435 \u0441\u0441\u044b\u043b\u043a\u0438 (404)\n"
                        "\u2022 JS \u043e\u0448\u0438\u0431\u043a\u0438 \u0432 \u043a\u043e\u043d\u0441\u043e\u043b\u0438\n"
                        "\u2022 \u0421\u043a\u043e\u0440\u043e\u0441\u0442\u044c \u0437\u0430\u0433\u0440\u0443\u0437\u043a\u0438\n"
                        "\u2022 \u041d\u0430 4 \u044d\u043a\u0440\u0430\u043d\u0430\u0445: \ud83d\udcf1 \ud83d\udcf2 \ud83d\udcbb \ud83d\udda5",
                        keyboard=KB)

        except requests.exceptions.Timeout:
            pass
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(3)


if __name__ == "__main__":
    run()
