import copy
import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta

import flask
import requests
from urllib3.exceptions import InsecureRequestWarning

from main import (
    extract_netflix_cookie_bundles,
    cookies_dict_from_netscape,
    has_required_netflix_cookies,
    get_account_page,
    extract_info,
    is_subscribed_account,
    is_on_hold_account,
    derive_plan_info,
    create_nftoken,
    build_nftoken_links,
    has_usable_nftoken,
    decode_netflix_value,
)

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org/bot"
RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 15
NFTOKEN_RETRY_ATTEMPTS = 1

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

app = flask.Flask(__name__)


def check_single_cookie(cookie_text):
    bundles = extract_netflix_cookie_bundles(cookie_text)
    if not bundles:
        return {"ok": False, "error": "No Netflix cookies found in the text."}

    bundle = bundles[0]
    netscape_content = bundle.get("netscape_text", "")
    cookies = bundle.get("cookies") or cookies_dict_from_netscape(netscape_content)

    if not cookies or not has_required_netflix_cookies(cookies):
        return {"ok": False, "error": "Missing required NetflixId cookie."}

    session = requests.Session()
    session.cookies.update(cookies)

    for _ in range(2):
        try:
            response_text, status_code, extracted_info = get_account_page(
                session,
                proxy=None,
                request_timeout=REQUEST_TIMEOUT,
                fallback_account_page=True,
            )
            if status_code == 200 and response_text:
                break
            if status_code in RETRYABLE_STATUS_CODES:
                continue
            break
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Request timed out. Try again."}
        except requests.exceptions.RequestException as e:
            return {"ok": False, "error": f"Network error: {e}"}
    else:
        status_code = 0

    if status_code != 200 or not response_text:
        return {"ok": False, "error": "Cookie is dead or invalid."}

    info = extracted_info or extract_info(response_text)
    country = decode_netflix_value(info.get("countryOfSignup"))

    if not country:
        return {"ok": False, "error": "Cookie is dead or invalid."}

    is_subscribed = is_subscribed_account(info)
    plan_key, plan_label = derive_plan_info(info, is_subscribed)

    if not is_subscribed:
        return {"ok": False, "error": f"Cookie is free ({plan_label}). No active subscription."}

    on_hold = is_on_hold_account(info)
    if on_hold:
        return {"ok": False, "error": f"Account is on hold ({plan_label})."}

    nftoken_data, nftoken_error = create_nftoken(cookies, NFTOKEN_RETRY_ATTEMPTS)
    if not nftoken_data or not has_usable_nftoken(nftoken_data):
        return {
            "ok": True,
            "plan": plan_label,
            "country": country,
            "nftoken_error": nftoken_error or "NFToken unavailable",
            "mobile_link": None,
        }

    links = build_nftoken_links(nftoken_data["token"], "mobile")
    mobile_link = links[0][1] if links else None

    return {
        "ok": True,
        "plan": plan_label,
        "country": country,
        "mobile_link": mobile_link,
        "expires": nftoken_data.get("expires_at_utc"),
    }


def send_message(chat_id, text, parse_mode=None, keyboard=None):
    url = f"{API_BASE}{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        data["parse_mode"] = parse_mode
    if keyboard:
        data["reply_markup"] = json.dumps({"keyboard": keyboard, "resize_keyboard": True, "one_time_keyboard": False})
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.warning(f"sendMessage failed: {e}")


def remove_keyboard(chat_id, text, parse_mode=None):
    url = f"{API_BASE}{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True, "reply_markup": json.dumps({"remove_keyboard": True})}
    if parse_mode:
        data["parse_mode"] = parse_mode
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.warning(f"sendMessage failed: {e}")


@app.route("/", methods=["GET"])
def index():
    return "Dan Sun - Netflix Cookie Checker Bot is running."


def process_cookie_async(chat_id, text, user):
    try:
        result_data = check_single_cookie(text)
    except Exception as e:
        logger.exception("Error checking cookie")
        send_message(chat_id, f"\u274c Error: {e}")
        return

    if not result_data["ok"]:
        send_message(
            chat_id,
            f"\u274c Cookie is dead, try another.\n\n{result_data['error']}"
        )
        return

    plan = result_data.get("plan", "Unknown")
    country = result_data.get("country", "??")
    mobile_link = result_data.get("mobile_link")

    if mobile_link:
        msg_text = (
            f"\u2705 Cookie is LIVE!\n"
            f"\U0001f4e6 Plan: {plan}\n"
            f"\U0001f30d Country: {country}\n\n"
            f"\U0001f4f1 Mobile Login:\n{mobile_link}"
        )
        if result_data.get("expires"):
            msg_text += f"\n\n\u23f3 Token expires: {result_data['expires']}"
    else:
        nftoken_err = result_data.get("nftoken_error", "Unknown error")
        escaped = text[:200].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        msg_text = (
            f"\u2705 Cookie is LIVE! ({plan} | {country})\n"
            f"\u26a0\ufe0f Could not generate mobile link: {nftoken_err}\n\n"
            f"Cookie text:\n<code>{escaped}</code>"
        )

    send_message(chat_id, msg_text, parse_mode="HTML")


@app.route("/webhook", methods=["POST"])
def webhook():
    update = flask.request.get_json(silent=True)
    if not update:
        return "ok", 200

    msg = update.get("message")
    if not msg or not msg.get("text"):
        return "ok", 200

    text = msg["text"].strip()
    chat_id = msg["chat"]["id"]
    user = msg["from"].get("first_name", "User")

    if text == "/start" or text == "\U0001f3e0 Menu":
        send_message(
            chat_id,
            "\U0001f916 <b>Dan Sun - Netflix Cookie Checker</b>\n\n"
            "I check Netflix cookies and generate mobile login links.\n\n"
            "\U0001f447 Choose an option below or send a cookie directly:",
            parse_mode="HTML",
            keyboard=[
                ["\u2753 Help", "\u2139\ufe0f About"],
                ["\U0001f4cb Example Format"],
            ],
        )
        return "ok", 200

    if text == "\u2753 Help" or text == "/help":
        send_message(
            chat_id,
            "\U0001f4ac <b>How to use</b>\n\n"
            "1. Get a Netflix cookie (Netscape .txt or JSON format)\n"
            "2. Paste it here as a message\n"
            "3. I'll check if it's valid\n"
            "4. If live, you get a mobile NFToken login link\n\n"
            "<b>Supported formats:</b>\n"
            "<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\txxx</code>\n"
            "or JSON array format.",
            parse_mode="HTML",
            keyboard=[["\U0001f3e0 Menu"]],
        )
        return "ok", 200

    if text == "\u2139\ufe0f About":
        send_message(
            chat_id,
            "\U0001f916 <b>Dan Sun - Netflix Cookie Checker</b>\n\n"
            "\u2705 Checks Netflix cookies\n"
            "\U0001f4f1 Generates mobile NFToken login links\n"
            "\U0001f310 Free 24/7 hosted on Render\n\n"
            "Just send a cookie to get started!",
            parse_mode="HTML",
            keyboard=[["\U0001f3e0 Menu"]],
        )
        return "ok", 200

    if text == "\U0001f4cb Example Format":
        send_message(
            chat_id,
            "<b>Netscape format (.txt):</b>\n"
            "<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tyourNetflixIdHere\n"
            ".netflix.com\tTRUE\t/\tTRUE\t0\tSecureNetflixId\tyourSecureIdHere</code>\n\n"
            "<b>JSON format:</b>\n"
            "<code>[{\"domain\":\".netflix.com\",\"name\":\"NetflixId\",\"value\":\"xxx\"}]</code>\n\n"
            "Just copy and paste the whole thing here.",
            parse_mode="HTML",
            keyboard=[["\U0001f3e0 Menu"]],
        )
        return "ok", 200

    if text == "/about":
        send_message(
            chat_id,
            "\U0001f916 <b>Dan Sun - Netflix Cookie Checker</b>\n\n"
            "\u2705 Checks Netflix cookies\n"
            "\U0001f4f1 Generates mobile NFToken login links\n"
            "\U0001f310 Free 24/7 hosted on Render\n\n"
            "Just send a cookie to get started!",
            parse_mode="HTML",
            keyboard=[["\U0001f3e0 Menu"]],
        )
        return "ok", 200

    if text.startswith("/"):
        return "ok", 200

    send_message(chat_id, "\u23f3 Checking cookie... Please wait.")
    logger.info(f"Checking cookie from {user} ({chat_id})")

    threading.Thread(
        target=process_cookie_async,
        args=(chat_id, text, user),
        daemon=True,
    ).start()

    return "ok", 200


def set_webhook():
    url = f"{API_BASE}{BOT_TOKEN}/setWebhook"
    resp = requests.post(url, json={"url": f"{WEBHOOK_URL}/webhook"}, timeout=10)
    result = resp.json()
    if result.get("ok"):
        logger.info(f"Webhook set to {WEBHOOK_URL}/webhook")
    else:
        logger.error(f"Failed to set webhook: {result}")

    commands_url = f"{API_BASE}{BOT_TOKEN}/setMyCommands"
    commands = [
        {"command": "start", "description": "Show menu and start"},
        {"command": "help", "description": "How to use the bot"},
        {"command": "about", "description": "About this bot"},
    ]
    requests.post(commands_url, json={"commands": commands}, timeout=10)

    return result


@app.route("/setup", methods=["GET"])
def setup_route():
    if not BOT_TOKEN or not WEBHOOK_URL:
        return "Set BOT_TOKEN and WEBHOOK_URL env vars first.", 400
    result = set_webhook()
    if result.get("ok"):
        return f"Webhook set to {WEBHOOK_URL}/webhook", 200
    return f"Failed: {result}", 500


# Auto-setup webhook on startup when env vars are present
if os.environ.get("BOT_TOKEN") and os.environ.get("WEBHOOK_URL"):
    BOT_TOKEN = os.environ["BOT_TOKEN"]
    WEBHOOK_URL = os.environ["WEBHOOK_URL"]
    try:
        me = requests.get(f"{API_BASE}{BOT_TOKEN}/getMe", timeout=10).json()
        if me.get("ok"):
            logger.info(f"Bot @{me['result']['username']} authenticated")
        set_webhook()
    except Exception as e:
        logger.warning(f"Webhook setup failed (will retry on /setup): {e}")


def main():
    global BOT_TOKEN, WEBHOOK_URL
    if not BOT_TOKEN:
        BOT_TOKEN = os.environ.get("BOT_TOKEN", "") or input("Bot Token: ").strip()
    if not WEBHOOK_URL:
        WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "") or input("Webhook URL (e.g. https://your-app.onrender.com): ").strip()

    if not BOT_TOKEN or not WEBHOOK_URL:
        print("BOT_TOKEN and WEBHOOK_URL are required.")
        return

    me = requests.get(f"{API_BASE}{BOT_TOKEN}/getMe", timeout=10).json()
    if me.get("ok"):
        logger.info(f"Bot @{me['result']['username']} authenticated")

    set_webhook()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
