import json
import os
import pathlib
import urllib.request
import urllib.parse
import urllib.error
import html
import sys

REPO_FILE = pathlib.Path("releases-watcher/repos.json")
STATE_DIR = pathlib.Path(".releases-watcher/telegram")
STATE_DIR.mkdir(parents=True, exist_ok=True)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
IS_MANUAL = os.environ.get("IS_MANUAL") == "true"

if not TG_BOT_TOKEN:
    print("Missing TG_BOT_TOKEN")
    sys.exit(1)

if not TG_CHAT_ID:
    print("Missing TG_CHAT_ID")
    sys.exit(1)

if not REPO_FILE.exists():
    print("repos.json not found")
    sys.exit(1)


def load_repos():
    data = json.loads(REPO_FILE.read_text())
    repos = []
    for r in data:
        r = str(r).strip()
        if "/" in r:
            repos.append(r)
    return repos


def github(url):
    req = urllib.request.Request(url, headers={"User-Agent": "releases-watcher"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def latest_release(repo):
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
    return github(url)


def telegram(text):

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"

    payload = urllib.parse.urlencode(
        {
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()

    try:
        urllib.request.urlopen(url, payload)
        return True
    except urllib.error.HTTPError as e:
        print("Telegram HTTPError:", e.read().decode())
        return False
    except Exception as e:
        print("Telegram error:", e)
        return False


def state_file(repo):
    return STATE_DIR / f"{repo.replace('/','__')}.txt"


def first_message(repo, name, tag, url):
    return "\n".join(
        [
            "<b>GitHub Release</b>",
            f"<b>Repo:</b> {html.escape(repo)}",
            f"<b>Name:</b> {html.escape(name)}",
            f"<b>Tag:</b> {html.escape(tag)}",
            "<b>Status:</b> first notification",
            f"<a href=\"{html.escape(url)}\">Open Release</a>",
        ]
    )


def update_message(repo, name, tag, old_tag, url):
    return "\n".join(
        [
            "<b>GitHub Release Update</b>",
            f"<b>Repo:</b> {html.escape(repo)}",
            f"<b>Name:</b> {html.escape(name)}",
            f"<b>Tag:</b> {html.escape(tag)}",
            f"<b>Previous:</b> {html.escape(old_tag)}",
            f"<a href=\"{html.escape(url)}\">Open Release</a>",
        ]
    )


def summary_message(count):
    return "\n".join(
        [
            "<b>Releases Watcher</b>",
            "Check completed.",
            "No new releases.",
            f"Repos checked: {count}",
        ]
    )


repos = load_repos()
sent = 0

for repo in repos:

    sf = state_file(repo)
    old_tag = sf.read_text().strip() if sf.exists() else ""

    try:
        rel = latest_release(repo)
    except Exception as e:
        print("Release fetch failed:", repo, e)
        continue

    tag = (rel.get("tag_name") or "").strip()
    name = (rel.get("name") or tag).strip()
    url = rel.get("html_url") or ""

    if not tag:
        continue

    # 首次监控
    if not sf.exists():

        text = first_message(repo, name, tag, url)

        if telegram(text):
            sf.write_text(tag)
            sent += 1

        continue

    # 无变化
    if tag == old_tag:
        continue

    text = update_message(repo, name, tag, old_tag, url)

    if telegram(text):
        sf.write_text(tag)
        sent += 1


# 手动运行且无更新
if sent == 0 and IS_MANUAL:
    telegram(summary_message(len(repos)))

print("Notifications:", sent)
