import json
import os
import pathlib
import urllib.request
import urllib.parse
import urllib.error
import html
import sys
import xml.etree.ElementTree as ET

REPO_FILE = pathlib.Path("releases-watcher/repos.json")
STATE_DIR = pathlib.Path(".releases-watcher/telegram")
STATE_DIR.mkdir(parents=True, exist_ok=True)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
IS_MANUAL = os.environ.get("IS_MANUAL") == "true"
IS_DRY_RUN = os.environ.get("DRY_RUN") == "true"

# 支持的托管平台
GITHUB = "github"
CODEBERG = "codeberg"

HOSTS = {
    GITHUB: {"name": "GitHub", "domain": "github.com", "api": "https://api.github.com"},
    CODEBERG: {"name": "Codeberg", "domain": "codeberg.org", "api": "https://codeberg.org/api/v1"},
}

# RSS/Atom 源：只用来发现“有没有变化”，不消耗 API 配额
FEEDS = {
    GITHUB: "https://github.com/{owner}/{name}/releases.atom",
    CODEBERG: "https://codeberg.org/{owner}/{name}/releases.atom",
}

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

# 条目前缀 -> 平台，例如 "codeberg:owner/repo"、"codeberg.org/owner/repo"
HOST_PREFIXES = {
    "github:": GITHUB,
    "codeberg:": CODEBERG,
    "codeberg.org/": CODEBERG,
    "https://codeberg.org/": CODEBERG,
}

if not TG_BOT_TOKEN:
    print("Missing TG_BOT_TOKEN")
    sys.exit(1)

if not TG_CHAT_ID:
    print("Missing TG_CHAT_ID")
    sys.exit(1)

if not REPO_FILE.exists():
    print("repos.json not found")
    sys.exit(1)


def parse_repo(entry):
    """把 repos.json 里的条目解析成 (host, owner, name)，无法识别时返回 None。

    支持写法：
      owner/repo                  -> GitHub
      github:owner/repo           -> GitHub
      codeberg:owner/repo         -> Codeberg
      codeberg.org/owner/repo     -> Codeberg
    """
    text = str(entry).strip().replace("\\", "/")

    host = GITHUB
    for prefix, prefix_host in HOST_PREFIXES.items():
        if text.lower().startswith(prefix):
            host = prefix_host
            text = text[len(prefix):]
            break

    text = text.strip().strip("/")
    if text.lower().endswith(".git"):
        text = text[:-4]

    parts = [p for p in text.split("/") if p]
    if len(parts) != 2:
        return None

    owner, name = parts
    return host, owner, name


def load_repos():
    data = json.loads(REPO_FILE.read_text())
    repos = []
    for r in data:
        parsed = parse_repo(r)
        if parsed:
            repos.append({"raw": str(r).strip(), "host": parsed[0], "owner": parsed[1], "name": parsed[2]})
        else:
            print("Skip invalid repo entry:", r)
    return repos


def api_get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "releases-watcher", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def pick_latest_published(rels):
    """从 release 列表里挑出最新的正式版本。"""
    published = [r for r in rels if not r.get("draft")]
    stable = [r for r in published if not r.get("prerelease")]
    candidates = stable or published
    return candidates[0] if candidates else None


def tag_from_entry(entry):
    """从 Atom 条目里取 tag：优先 release 链接，其次 <id>。

    注意 <title> 是 Release 的名称（"Source files for Version 2.005"），不是 tag。
    """
    for link in entry.findall("a:link", ATOM_NS):
        href = link.get("href") or ""
        if "/releases/tag/" in href:
            return urllib.parse.unquote(href.split("/releases/tag/", 1)[1]).strip("/")
    entry_id = (entry.findtext("a:id", default="", namespaces=ATOM_NS) or "").strip()
    if "/" in entry_id:
        return entry_id.rsplit("/", 1)[-1]
    return ""


def newest_feed_release(host, owner, name):
    """读 releases.atom，返回最新一条（RSS 判定，不花 API 配额）。"""
    url = FEEDS[host].format(owner=owner, name=name)
    req = urllib.request.Request(url, headers={"User-Agent": "releases-watcher"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())
    entries = []
    for e in root.findall("a:entry", ATOM_NS):
        tag = tag_from_entry(e)
        if not tag:
            continue
        entries.append(
            {
                "tag": tag,
                "name": (e.findtext("a:title", default="", namespaces=ATOM_NS) or "").strip(),
            }
        )
    return entries[0] if entries else None


def latest_release(host, owner, name):

    api = HOSTS[host]["api"]

    try:
        return api_get(f"{api}/repos/{owner}/{name}/releases/latest")
    except urllib.error.HTTPError as e:
        # Codeberg（Forgejo）在没有正式 Release 时 /latest 会返回 404，
        # 退回到列表接口按发布时间取最新一条。
        if host != CODEBERG or e.code != 404:
            raise
        rels = api_get(f"{api}/repos/{owner}/{name}/releases?limit=20")
        rel = pick_latest_published(rels)
        if not rel:
            raise RuntimeError("no published release")
        return rel


def telegram(text):

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"

    payload = urllib.parse.urlencode(
        {
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }
    ).encode()

    try:
        urllib.request.urlopen(url, payload, timeout=30)
        return True
    except urllib.error.HTTPError as e:
        print("Telegram HTTPError:", e.read().decode())
        return False
    except Exception as e:
        print("Telegram error:", e)
        return False


def notify(text):
    """发送通知；DRY_RUN 时只打印。返回是否“已处理”。"""
    if IS_DRY_RUN:
        print("[dry-run] would send:\n" + text + "\n")
        return True
    return telegram(text)


def state_file(host, owner, name):
    # GitHub 沿用 owner__repo.txt，保持已有状态文件兼容
    slug = f"{owner}__{name}"
    if host != GITHUB:
        slug = f"{host}__{slug}"
    return STATE_DIR / f"{slug}.txt"


def repo_label(host, owner, name):
    # GitHub 保持 owner/repo 的老样子，其它平台带上域名便于区分
    if host == GITHUB:
        return f"{owner}/{name}"
    return f"{HOSTS[host]['domain']}/{owner}/{name}"


def first_message(host, owner, name, rel_name, tag, url):
    return "\n".join(
        [
            f"<b>{HOSTS[host]['name']} Release</b>",
            f"<b>Repo:</b> {html.escape(repo_label(host, owner, name))}",
            f"<b>Name:</b> {html.escape(rel_name)}",
            f"<b>Tag:</b> {html.escape(tag)}",
            "<b>Status:</b> first notification",
            f"<a href=\"{html.escape(url)}\">Open Release</a>",
        ]
    )


def update_message(host, owner, name, rel_name, tag, old_tag, url):
    return "\n".join(
        [
            f"<b>{HOSTS[host]['name']} Release Update</b>",
            f"<b>Repo:</b> {html.escape(repo_label(host, owner, name))}",
            f"<b>Name:</b> {html.escape(rel_name)}",
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
api_checks = 0

for repo in repos:

    host, owner, name = repo["host"], repo["owner"], repo["name"]
    sf = state_file(host, owner, name)
    old_tag = sf.read_text().strip() if sf.exists() else ""

    # 1) 先用 RSS/Atom 判断有没有变化，没变化就完全不碰 API
    try:
        feed = newest_feed_release(host, owner, name)
    except Exception as e:
        print("Feed fetch failed:", repo["raw"], e)
        continue

    if not feed:
        print("No release in feed:", repo["raw"])
        continue

    if sf.exists() and feed["tag"] == old_tag:
        continue

    # 2) feed 说有新东西，再用 API 确认（过滤 prerelease/draft，并拿正式名称和链接）
    api_checks += 1
    try:
        rel = latest_release(host, owner, name)
    except Exception as e:
        print("Release fetch failed:", repo["raw"], e)
        continue

    tag = (rel.get("tag_name") or "").strip()
    rel_name = (rel.get("name") or tag).strip()
    url = rel.get("html_url") or ""

    if not tag:
        continue

    # feed 里最新那条是 prerelease/资产发布，正式 Release 没变
    if sf.exists() and tag == old_tag:
        print("Prerelease only, skip:", repo["raw"], feed["tag"])
        continue

    # 首次监控
    if not sf.exists():

        text = first_message(host, owner, name, rel_name, tag, url)

        if notify(text):
            if not IS_DRY_RUN:
                sf.write_text(tag)
            sent += 1

        continue

    text = update_message(host, owner, name, rel_name, tag, old_tag, url)

    if notify(text):
        if not IS_DRY_RUN:
            sf.write_text(tag)
        sent += 1


# 手动运行且无更新
if sent == 0 and IS_MANUAL:
    notify(summary_message(len(repos)))

print("Notifications:", sent)
print(f"API checks: {api_checks}/{len(repos)} repos, 其余走 RSS")
