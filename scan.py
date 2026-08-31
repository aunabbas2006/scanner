"""Scan GitHub for open bounty issues, write docs/bounties.json, ping ntfy on new ones."""
import json, os, re, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://api.github.com/search/issues"
OUT = os.path.join("docs", "bounties.json")
CACHE = ".repo_cache.json"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
NTFY = os.environ.get("NTFY_TOPIC", "")
GEM = "\U0001f48e Bounty"  # the label Algora actually applies

# "$500" / "$1,000.00" / "500 USD" / "$2k". Bare numbers ignored: version/issue noise.
_MONEY = re.compile(
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(k\b)?"
    r"|\b([\d,]+(?:\.\d{1,2})?)\s*(k\b)?\s*(?:USD|usd|usdc|USDC)\b")


def parse_amount(text):
    """Largest plausible dollar figure in text, or None."""
    best = None
    for m in _MONEY.finditer(text or ""):
        raw, kilo = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            val = float(raw.replace(",", ""))
        except ValueError:
            continue
        if kilo:
            val *= 1000
        if 0 < val <= 100000 and (best is None or val > best):
            best = val
    return best


def get(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "bounty-radar",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


_stars = json.load(open(CACHE)) if os.path.exists(CACHE) else {}


def stars(repo):
    """Star count, cached across runs. Spam repos have ~0; this is the junk filter."""
    if repo not in _stars:
        try:
            _stars[repo] = get(f"https://api.github.com/repos/{repo}").get("stargazers_count", 0)
        except Exception:
            _stars[repo] = 0
    return _stars[repo]


def classify_comments(comments):
    """Pure classifier: Algora leaves the bounty label on forever, even after payout —
    the bot's comment thread is the only real signal of whether it's still claimable.
    Returns (amount, status): status is 'awarded' > 'claimed' > 'open'."""
    amount, status = None, "open"
    for c in comments:
        body = c.get("body", "")
        if amount is None:
            amount = parse_amount(body) or amount
        if "algora" not in c.get("user", {}).get("login", "").lower():
            continue
        low = body.lower()
        if "has been awarded" in low:
            status = "awarded"
        elif "already attempting" in low and status == "open":
            status = "claimed"
    return amount, status


def bounty_status(issue):
    """Fetch the full comment thread and classify it. Award comments land late in
    long threads, so page to the end rather than trusting just the first page."""
    n_pages = max(1, -(-issue.get("comments", 0) // 100))
    try:
        comments = []
        for page in range(1, n_pages + 1):
            comments += get(f"{issue['comments_url']}?per_page=100&page={page}")
        return classify_comments(comments)
    except Exception:
        return None, "open"


def search(query):
    """GitHub's search API allows 30 req/min. With ~50 watched repos we WILL hit that,
    and a silent 403 means silently missing bounties — so back off and retry instead."""
    url = f"{API}?q={urllib.parse.quote(query)}&sort=created&order=desc&per_page=50"
    for attempt in range(4):
        try:
            return get(url).get("items", [])
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 3:
                wait = 20 * (attempt + 1)
                print(f"  . rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  ! {e.code} on {query!r}", file=sys.stderr)
            return []
    return []


def collect(cfg):
    queries = list(cfg["queries"])
    queries += [f'repo:{r} is:issue is:open label:"{GEM}"' for r in cfg.get("watch_repos", [])]
    watched = set(cfg.get("watch_repos", []))
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=cfg.get("max_age_days", 45))
    watch_cutoff = now - timedelta(days=cfg.get("watch_max_age_days", 400))
    found = {}
    for q in queries:
        items = search(q)
        print(f"  {len(items):3d}  {q}")
        for it in items:
            if it.get("pull_request"):
                continue
            url = it["html_url"]
            repo = "/".join(url.split("/")[3:5])
            # created_at is the issue's birthdate, not the bounty's — a stale issue can
            # get a bounty slapped on today, so updated_at is the freshness signal.
            # A years-old thread with zero recent activity is usually genuinely
            # abandoned or too hard for anyone to have finished — skip it either way.
            updated = datetime.fromisoformat(it["updated_at"].replace("Z", "+00:00"))
            if updated < (watch_cutoff if repo in watched else cutoff):
                continue
            # watched repos bypass the star gate; you vouched for them already
            if url in found or (repo not in watched and stars(repo) < cfg.get("min_stars", 300)):
                continue
            amount = parse_amount(" ".join([it["title"], it.get("body") or ""]))
            status = "open"
            if amount is None or it.get("comments", 0) > 0:
                # need the thread anyway to check for a hidden "awarded" comment
                c_amount, status = bounty_status(it)
                amount = amount or c_amount
            if amount is None or not (cfg.get("min_amount", 0) <= amount <= cfg.get("max_amount", 1e9)):
                continue
            if status == "awarded":
                continue
            found[url] = {
                "url": url,
                "title": it["title"],
                "repo": repo,
                "stars": _stars.get(repo, 0),
                "watched": repo in watched,
                "amount": amount,
                "status": status,
                "labels": [l["name"] for l in it.get("labels", [])],
                "comments": it.get("comments", 0),
                "created_at": it["created_at"],
                "assigned": bool(it.get("assignee")),
            }
    return found


def notify(items):
    if not (NTFY and items):
        return
    top = sorted(items, key=lambda b: -b["amount"])[:5]
    body = "\n".join(f"${int(b['amount'])} {b['repo']}: {b['title'][:60]}" for b in top)
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY}", data=body.encode(),
        headers={"Title": f"{len(items)} new bounty(s)", "Priority": "high",
                 "Click": top[0]["url"], "Tags": "moneybag"})
    try:
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"  ! ntfy failed: {e}", file=sys.stderr)


def main():
    cfg = json.load(open("config.json"))
    prev = {}
    if os.path.exists(OUT):
        prev = {b["url"]: b for b in json.load(open(OUT)).get("bounties", [])}

    found = collect(cfg)
    now = datetime.now(timezone.utc).isoformat()

    new = []
    for url, b in found.items():
        if url in prev:
            b["first_seen"] = prev[url].get("first_seen", now)
        else:
            b["first_seen"] = now
            new.append(b)

    bounties = sorted(found.values(), key=lambda b: (b["status"] != "open", -b["amount"]))
    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": now, "new_count": len(new), "bounties": bounties}, f, indent=1)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(_stars, f)

    print(f"{len(bounties)} open, {len(new)} new, ${sum(b['amount'] for b in bounties):,.0f} total")
    notify(new)


if __name__ == "__main__":
    main()
