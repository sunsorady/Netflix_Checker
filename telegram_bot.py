import copy
import json
import logging
import os
import random
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
    move_cookie_with_reason,
    cookies_folder,
    failed_folder,
    broken_folder,
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

user_lang = {}

LANG = {
    "en": {
        "menu": "\U0001f3e0 Menu",
        "get_netflix_btn": "\U0001f3ac Get a Netflix",
        "help_btn": "\u2753 Help",
        "about_btn": "\u2139\ufe0f About",
        "format_btn": "\U0001f4cb Format",
        "guide_btn": "\U0001f4f1 Guide",
        "lang_btn": "\U0001f1f7\U0001f1f1 KH",
        "checking": "\u23f3 Checking cookie... Please wait.",
        "get_netflix_checking": "\U0001f3b2 Picking a random cookie and checking...",
        "no_cookies_left": "\U0001f4ad No cookies left in the pool.",
        "cookie_removed": "\U0001f5d1\ufe0f Dead cookie removed from pool.",
        "alive": "\u2705 Cookie is LIVE!",
        "dead": "\u274c Cookie is dead, try another.",
        "plan": "\U0001f4e6 Plan",
        "country": "\U0001f30d Country",
        "mobile_login": "\U0001f4f1 Mobile Login",
        "expires": "\u23f3 Token expires",
        "no_link": "\u26a0\ufe0f Could not generate mobile link: {err}",
        "start_msg": "\U0001f916 <b>Dan Sun - Netflix Cookie Checker</b>\n\nI check Netflix cookies and generate mobile login links.\n\n\U0001f447 Choose an option below or send a cookie directly:",
        "help_msg": "\U0001f4ac <b>How to use</b>\n\n1. Get a Netflix cookie (Netscape .txt or JSON format)\n2. Paste it here as a message\n3. I'll check if it's valid\n4. If live, you get a mobile NFToken login link\n\n<b>Supported formats:</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\txxx</code>\nor JSON array format.",
        "about_msg": "\U0001f916 <b>Dan Sun - Netflix Cookie Checker</b>\n\n\u2705 Checks Netflix cookies\n\U0001f4f1 Generates mobile NFToken login links\n\U0001f310 Free 24/7 hosted on Render\n\nJust send a cookie to get started!",
        "guide_msg": "\U0001f4f1 <b>How to use the mobile link</b>\n\n\U0001f5a5 <b>Android:</b>\n1. Clear Netflix app cache or delete app data\n2. Copy the generated login link\n3. Paste into default browser\n4. Auto login to Netflix\n\n\U0001f4f1 <b>iPhone / iPad:</b>\n1. Logout from previous Netflix app account\n2. Copy the generated login link\n3. Paste into default browser\n4. Auto login to Netflix app",
        "format_msg": "<b>Netscape format (.txt):</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tyourNetflixIdHere\n.netflix.com\tTRUE\t/\tTRUE\t0\tSecureNetflixId\tyourSecureIdHere</code>\n\n<b>JSON format:</b>\n<code>[{{\"domain\":\".netflix.com\",\"name\":\"NetflixId\",\"value\":\"xxx\"}}]</code>\n\nJust copy and paste the whole thing here.",
        "cookie_text": "Cookie text:",
        "language_set": "\u2705 Language set to English",
    },
    "kh": {
        "menu": "\U0001f3e0 ម៉ឺនុយ",
        "get_netflix_btn": "\U0001f3ac យក Netflix",
        "help_btn": "\u2753 ជំនួយ",
        "about_btn": "\u2139\ufe0f អំពី",
        "format_btn": "\U0001f4cb ទម្រង់",
        "guide_btn": "\U0001f4f1 ការណែនាំ",
        "lang_btn": "\U0001f1fa\U0001f1f8 EN",
        "checking": "\u23f3 កំពុងពិនិត្យ Cookie... សូមរង់ចាំ។",
        "get_netflix_checking": "\U0001f3b2 កំពុងជ្រើសរើស cookie ចៃដន្យ និងពិនិត្យ...",
        "no_cookies_left": "\U0001f4ad គ្មាន cookie នៅសល់ក្នុងបញ្ជីទេ។",
        "cookie_removed": "\U0001f5d1\ufe0f Cookie ស្លាប់ត្រូវបានដកចេញពីបញ្ជី។",
        "alive": "\u2705 Cookie នៅរស់!",
        "dead": "\u274c Cookie ស្លាប់ហើយ សូមសាកល្បងមួយផ្សេងទៀត។",
        "plan": "\U0001f4e6 គម្រោង",
        "country": "\U0001f30d ប្រទេស",
        "mobile_login": "\U0001f4f1 ចូលតាមទូរស័ព្ទ",
        "expires": "\u23f3 ផុតកំណត់",
        "no_link": "\u26a0\ufe0f មិនអាចបង្កើតតំណភ្ជាប់បានទេ: {err}",
        "start_msg": "\U0001f916 <b>Dan Sun - អ្នកពិនិត្យ Cookie Netflix</b>\n\nខ្ញុំពិនិត្យ Netflix cookies និងបង្កើតតំណភ្ជាប់ចូលតាមទូរស័ព្ទ។\n\n\U0001f447 ជ្រើសរើសជម្រើសខាងក្រោម ឬផ្ញើ cookie ដោយផ្ទាល់:",
        "help_msg": "\U0001f4ac <b>របៀបប្រើប្រាស់</b>\n\n1. យក Netflix cookie (ទម្រង់ Netscape .txt ឬ JSON)\n2. បិទភ្ជាប់វានៅទីនេះ\n3. ខ្ញុំនឹងពិនិត្យថាតើវានៅរស់ឬទេ\n4. បើនៅរស់ អ្នកនឹងទទួលបានតំណចូលតាមទូរស័ព្ទ\n\n<b>ទម្រង់ដែលគាំទ្រ:</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\txxx</code>\nឬ JSON array ។",
        "about_msg": "\U0001f916 <b>Dan Sun - អ្នកពិនិត្យ Cookie Netflix</b>\n\n\u2705 ពិនិត្យ Netflix cookies\n\U0001f4f1 បង្កើតតំណចូលតាមទូរស័ព្ទ\n\U0001f310 ដំណើរការ 24/7 ដោយឥតគិតថ្លៃ\n\nគ្រាន់តែផ្ញើ cookie ដើម្បីចាប់ផ្តើម!",
        "guide_msg": "\U0001f4f1 <b>របៀបប្រើតំណភ្ជាប់ទូរស័ព្ទ</b>\n\n\U0001f5a5 <b>Android:</b>\n1. សម្អាត cache ឬលុបទិន្នន័យកម្មវិធី Netflix\n2. ចម្លងតំណភ្ជាប់ដែលបានបង្កើត\n3. បិទភ្ជាប់ទៅក្នុង browser ធម្មតា\n4. ចូល Netflix ដោយស្វ័យប្រវត្តិ\n\n\U0001f4f1 <b>iPhone / iPad:</b>\n1. ចាកចេញពីគណនី Netflix មុន\n2. ចម្លងតំណភ្ជាប់ដែលបានបង្កើត\n3. បិទភ្ជាប់ទៅក្នុង browser ធម្មតា\n4. ចូលកម្មវិធី Netflix ដោយស្វ័យប្រវត្តិ",
        "format_msg": "<b>ទម្រង់ Netscape (.txt):</b>\n<code>.netflix.com\tTRUE\t/\tTRUE\t0\tNetflixId\tyourNetflixIdHere\n.netflix.com\tTRUE\t/\tTRUE\t0\tSecureNetflixId\tyourSecureIdHere</code>\n\n<b>ទម្រង់ JSON:</b>\n<code>[{{\"domain\":\".netflix.com\",\"name\":\"NetflixId\",\"value\":\"xxx\"}}]</code>\n\nគ្រាន់តែចម្លង និងបិទភ្ជាប់វានៅទីនេះ។",
        "cookie_text": "អត្ថបទ Cookie:",
        "language_set": "\u2705 បានប្តូរទៅជាភាសាខ្មែរ",
    },
}


def t(chat_id, key, **kwargs):
    lang = user_lang.get(chat_id, "en")
    text = LANG.get(lang, LANG["en"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text


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


def get_random_cookie_and_check():
    cookie_dir = cookies_folder
    if not os.path.exists(cookie_dir):
        return {"ok": False, "error": "No cookies folder found."}

    files = [f for f in os.listdir(cookie_dir) if f.lower().endswith(".txt")]
    if not files:
        return {"ok": False, "error": "No cookies available in the pool."}

    random_file = random.choice(files)
    file_path = os.path.join(cookie_dir, random_file)

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        return {"ok": False, "error": f"Failed to read cookie file: {e}", "file": random_file}

    result = check_single_cookie(content)
    result["file"] = random_file

    if not result["ok"]:
        error_reason = result.get("error", "dead")
        if any(t in error_reason.lower() for t in ("timeout", "network", "error", "equest")):
            move_cookie_with_reason(file_path, broken_folder, random_file, error_reason)
        else:
            move_cookie_with_reason(file_path, failed_folder, random_file, error_reason)

    return result


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
        send_message(chat_id, f"{t(chat_id, 'dead')}\n\n{result_data['error']}")
        return

    plan = result_data.get("plan", "Unknown")
    country = result_data.get("country", "??")
    mobile_link = result_data.get("mobile_link")

    logout_warning = "\n\n⚠️ Do not log out the account once you are in, logging out will kill the cookie"

    if mobile_link:
        msg_text = (
            f"{t(chat_id, 'alive')}\n"
            f"{t(chat_id, 'plan')}: {plan}\n"
            f"{t(chat_id, 'country')}: {country}\n\n"
            f"{t(chat_id, 'mobile_login')}:\n{mobile_link}"
            f"{logout_warning}"
        )
        if result_data.get("expires"):
            msg_text += f"\n\n{t(chat_id, 'expires')}: {result_data['expires']}"
    else:
        nftoken_err = result_data.get("nftoken_error", "Unknown error")
        escaped = text[:200].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        msg_text = (
            f"{t(chat_id, 'alive')} ({plan} | {country})\n"
            f"{t(chat_id, 'no_link', err=nftoken_err)}\n\n"
            f"{t(chat_id, 'cookie_text')}\n<code>{escaped}</code>"
        )

    send_message(chat_id, msg_text, parse_mode="HTML")


def process_get_netflix_async(chat_id):
    try:
        result_data = get_random_cookie_and_check()
    except Exception as e:
        logger.exception("Error in Get a Netflix")
        send_message(chat_id, f"\u274c Error: {e}")
        return

    if not result_data["ok"]:
        error_msg = result_data.get("error", "Unknown error")
        removed = ""
        if result_data.get("file"):
            removed = f"\n\n{t(chat_id, 'cookie_removed')}"
        send_message(chat_id, f"{t(chat_id, 'dead')}\n\n{error_msg}{removed}")
        return

    plan = result_data.get("plan", "Unknown")
    country = result_data.get("country", "??")
    mobile_link = result_data.get("mobile_link")
    cookie_file = result_data.get("file", "")

    logout_warning = "\n\n⚠️ Do not log out the account once you are in, logging out will kill the cookie"

    if mobile_link:
        msg_text = (
            f"{t(chat_id, 'alive')}\n"
            f"{t(chat_id, 'plan')}: {plan}\n"
            f"{t(chat_id, 'country')}: {country}\n\n"
            f"{t(chat_id, 'mobile_login')}:\n{mobile_link}"
            f"{logout_warning}"
        )
        if result_data.get("expires"):
            msg_text += f"\n\n{t(chat_id, 'expires')}: {result_data['expires']}"
    else:
        nftoken_err = result_data.get("nftoken_error", "Unknown error")
        msg_text = (
            f"{t(chat_id, 'alive')} ({plan} | {country})\n"
            f"{t(chat_id, 'no_link', err=nftoken_err)}"
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

    if text == "/language" or text == "\U0001f1f7\U0001f1f1 KH" or text == "\U0001f1fa\U0001f1f8 EN":
        current = user_lang.get(chat_id, "en")
        new_lang = "kh" if current == "en" else "en"
        user_lang[chat_id] = new_lang
        send_message(chat_id, t(chat_id, "language_set"), keyboard=[
            [t(chat_id, "get_netflix_btn")],
            [t(chat_id, "help_btn"), t(chat_id, "about_btn")],
            [t(chat_id, "format_btn"), t(chat_id, "guide_btn")],
            [t(chat_id, "lang_btn")],
        ])
        return "ok", 200

    if text == "/start" or text == t(chat_id, "menu"):
        send_message(
            chat_id,
            "⚠️ <b>This is the latest Cookies you can use:</b>\nhttps://t.me/dansmethod/374",
            parse_mode="HTML",
        )
        send_message(
            chat_id, t(chat_id, "start_msg"), parse_mode="HTML",
            keyboard=[
                [t(chat_id, "get_netflix_btn")],
                [t(chat_id, "help_btn"), t(chat_id, "about_btn")],
                [t(chat_id, "format_btn"), t(chat_id, "guide_btn")],
                [t(chat_id, "lang_btn")],
            ],
        )
        return "ok", 200

    if text == t(chat_id, "get_netflix_btn"):
        send_message(chat_id, t(chat_id, "get_netflix_checking"))
        threading.Thread(
            target=process_get_netflix_async,
            args=(chat_id,),
            daemon=True,
        ).start()
        return "ok", 200

    if text == "/help" or text == t(chat_id, "help_btn"):
        send_message(chat_id, t(chat_id, "help_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return "ok", 200

    if text == "/about" or text == t(chat_id, "about_btn"):
        send_message(chat_id, t(chat_id, "about_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return "ok", 200

    if text == "/guide" or text == t(chat_id, "guide_btn"):
        send_message(chat_id, t(chat_id, "guide_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return "ok", 200

    if text == t(chat_id, "format_btn"):
        send_message(chat_id, t(chat_id, "format_msg"), parse_mode="HTML",
                     keyboard=[[t(chat_id, "menu")]])
        return "ok", 200

    if text.startswith("/"):
        return "ok", 200

    send_message(chat_id, t(chat_id, "checking"))
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
        {"command": "guide", "description": "How to use mobile link"},
        {"command": "language", "description": "Switch language/ប្តូរភាសា"},
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
