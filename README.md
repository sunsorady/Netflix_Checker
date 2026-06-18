# Netflix Cookie Checker Telegram Bot

Read Netflix cookies and return a login link (NFToken) via PC or mobile. Cookies are publicly sourced and this project is for **educational purposes only**.

> **Disclaimer:** Everyone can modify or adjust this bot at their own risk. Use only on accounts and cookies you are authorized to test.

## Features

- Multi-threaded Netflix cookie checking via Telegram
- Supports Netscape `.txt` cookie files
- Cookie validation, account info extraction, and NFToken generation
- Organized output by plan type
- Proxy support with retry rotation
- Duplicate filtering
- Flask webhook backend for Telegram

## Requirements

```bash
pip install -r requirements.txt
```

Optional for SOCKS proxies:
```bash
pip install requests[socks]
```

## Quick Start

1. Clone the repo.
2. Install dependencies.
3. Put cookie files in `cookies/`.
4. Edit `config.yml` with your Telegram bot token.
5. Set `BOT_TOKEN` and `WEBHOOK_URL` environment variables.
6. Run:

```bash
python telegram_bot.py
```

Or deploy on Heroku/Docker with the included `Procfile`.

## Cookie Files

Cookie files are in Netscape format (`.txt`). These cookies are found from public sources. Each file should contain at minimum `NetflixId` and `SecureNetflixId` cookies.

## Configuration

Edit `config.yml` to control:
- `txt_fields` - which account fields to extract
- `nftoken` - NFToken generation mode (`false`, `"pc"`, `"mobile"`, `"both"`)
- `notifications` - webhook and Telegram notification settings
- `retries` - network retry attempts
- `performance` - timeout and fallback options

## Output Layout

```
cookies/
output/
output/run_YYYY-MM-DD_HH-MM-SS/
output/run_.../Premium/
output/run_.../Premium (Extra Member)/
output/run_.../Standard/
output/run_.../Standard With Ads/
output/run_.../Basic/
output/run_.../Mobile/
output/run_.../Free/
output/run_.../Duplicate/
output/run_.../On Hold/<Plan>/
failed/
broken/
proxy.txt
config.yml
```

## License

MIT License. See `LICENSE`.
