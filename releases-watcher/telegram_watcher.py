import html
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request


REPO_FILE = pathlib.Path("releases-watcher/repos.json")
STATE_DIR = pathlib.Path(".releases-watcher/telegram")
STATE_DIR.mkdir(parents=True, exist_ok=True)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()
IS_MANUAL = os.environ.get("IS_MANUAL", "").strip().lower() == "true"

GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "releases-watcher",
}


def fail(msg: str) -> None:
    print(msg)
    sys.exit(1)


if not TG_BOT_TOKEN:
    fail("Missing secret: TG_BOT_TOKEN")

if not TG_CHAT_ID:
    fail("Missing secret: TG_CHAT_ID")

if not REPO_FILE.exists():
    fail(f"Repo file not found: {REPO_FILE}")


def load_repos() -> list[str]:
    try:
        data = json.loads(REPO_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"Failed to read repos.json: {e}")

    if not isinstance(data, list):
        fail("repos.json must be a JSON array")

    repos: list[str] = []
    seen: set[str] = set()

    for item in data:
        repo = str(item).strip()
        if not repo:
            continue
        if "/" not in repo:
            print(f"Skip invalid repo entry: {repo}")
            continue
        if repo in seen:
            continue
        seen.add(repo)
        repos.append(repo)

    return repos


def get_json(url: str, headers: dict | None = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_latest_release(repo: str) -> dict:
    owner, name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{name}/releases/latest"
    return get_json(url, headers=GITHUB_HEADERS)


def send_telegram(text: str) -> bool:
    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "releases-watcher",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            print("Telegram returned:", body)
            return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"Telegram HTTPError {e.code}: {err_body}")
        return False
    except Exception as e:
        print(f"Telegram send failed: {e}")
        return False


def state_file_for(repo: str) -> pathlib.Path:
    return STATE_DIR / f"{repo.replace('/', '__')}.txt"


def main() -> int:
    repos = load_repos()
    notifications_sent = 0
    state_changed = False

    print("Repos loaded:", len(repos))
    print("Manual run:", IS_MANUAL)

    for repo in repos:
        print("=" * 60)
        print("Checking:", repo)

        sf = state_file_for(repo)
        has_state = sf.exists()
        old_tag = sf.read_text(encoding="utf-8").strip() if has_state else ""

        try:
            rel = get_latest_release(repo)
        except urllib.error.HTTPError as e:
            print(f"{repo} latest release HTTP error: {e.code}")
            continue
        except Exception as e:
            print(f"{repo} latest release failed: {e}")
            continue

        new_tag = str(rel.get("tag_name") or "").strip()
        name = str(rel.get("name") or new_tag).strip()
        html_url = str(rel.get("html_url") or "").strip()

        print("Old tag:", old_tag)
        print("New tag:", new_tag)

        if not new_tag:
            print("No release tag found, skip.")
            continue

        escaped_repo = html.escape(repo)
        escaped_name = html.escape(name)
        escaped_new_tag = html.escape(new_tag)
        escaped_old_tag = html.escape(old_tag)
        escaped_url = html.escape(html_url, quote=True)

        if not has_state:
            text = (
                "<b>GitHub Release</b>\n"
                "<b>Repo:</b> {}\n"
                "<b>Name:</b> {}\n"
                "<b>Tag:</b> {}\n"
                "<b>Status:</b> first notification\n"
                "<a href=\"{}\">Open Release</a>"
            ).format(
                escaped_repo,
                escaped_name,
                escaped_new_tag,
                escaped_url,
            )

            ok = send_telegram(text)
            if not ok:
                print("First notification failed, state file will not 
