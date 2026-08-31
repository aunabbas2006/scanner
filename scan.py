"""Scan GitHub for open bounty issues, write docs/bounties.json, ping ntfy on new ones."""
import json, os, re, sys, urllib.request, urllib.parse, urllib.error
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


def amount_from_comments(issue):
    """Algora/Polar bots post the amount as a comment, not in the issue body."""
    try:
        for c in get(issue["comments_url"] + "?per_page=20"):
            amt = parse_amount(c.get("body", ""))
            if amt:
                return amt
    except Exception:
        pass
    return None


def search(query):
    url = f"{API}?q={urllib.parse.quote(query)}&sort=created&order=desc&per_page=50"
    try:
        return get(url).get("items", [])
    except urllib.error.HTTPError as e:
        print(f"  ! {e.code} on {query!r}", file=sys.stderr)
        return []


def collect(cfg):
    queries = list(cfg["queries"])
    queries += [f'repo:{r} is:issue is:open label:"{GEM}"' for r in cfg.get("watch_repos", [])]
    watched = set(cfg.get("watch_repos", []))
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.get("max_age_days", 45))
    found = {}
    for q in queries:
        items = search(q)
        print(f"  {len(items):3d}  {q}")
        for it in items:
            if it.get("pull_request"):
                continue
            created = datetime.fromisoformat(it["created_at"].replace("Z", "+00:00"))
            if created < cutoff:
                continue
            url = it["html_url"]
            repo = "/".join(url.split("/")[3:5])
            # watched repos bypass the star gate; you vouched for them already
            if url in found or (repo not in watched and stars(repo) < cfg.get("min_stars", 300)):
                continue
            amount = parse_amount(" ".join([it["title"], it.get("body") or ""]))
            if amount is None:
                amount = amount_from_comments(it)
            if amount is None or amount < cfg.get("min_amount", 0):
                continue
            found[url] = {
                "url": url,
                "title": it["title"],
                "repo": repo,
                "stars": _stars.get(repo, 0),
                "watched": repo in watched,
                "amount": amount,
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

    bounties = sorted(found.values(), key=lambda b: -b["amount"])
    os.makedirs("docs", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"updated": now, "new_count": len(new), "bounties": bounties}, f, indent=1)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(_stars, f)

    print(f"{len(bounties)} open, {len(new)} new, ${sum(b['amount'] for b in bounties):,.0f} total")
    notify(new)


if __name__ == "__main__":
    main()
