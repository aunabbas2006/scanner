"""Run: python test_scan.py"""
from datetime import datetime, timezone, timedelta
from scan import parse_amount as p, classify_comments, score

# --- money parser ---
assert p("$500 bounty") == 500
assert p("Bounty: $1,000.00") == 1000
assert p("pays 250 USD") == 250
assert p("$2k reward") == 2000
assert p("500 USDC for this") == 500
assert p("takes the larger: $50 or $300") == 300
assert p("fix bug in v2.1.0") is None, "version numbers are not money"
assert p("issue #4242") is None, "issue refs are not money"
assert p("$0 bounty") is None, "zero is not a bounty"
assert p("$999999 scam") is None, "implausible amounts rejected"
assert p("") is None and p(None) is None

# --- comment classifier ---
def bot(body):
    return {"user": {"login": "algora-pbc[bot]"}, "body": body}

def human(login, body):
    return {"user": {"login": login}, "body": body}

r = classify_comments([bot("## \U0001f48e $500 bounty created")])
assert (r["amount"], r["status"]) == (500, "open")

r = classify_comments([
    bot("## \U0001f48e $500 bounty created"),
    bot("Note: @someone is already attempting to complete issue #1"),
])
assert r["status"] == "claimed"

r = classify_comments([
    bot("## \U0001f48e $500 bounty"),
    bot("Note: @someone is already attempting to complete issue #1"),
    bot("\U0001f389 @someone has been awarded **$500**!"),
])
assert r["status"] == "awarded", "awarded must win even after a claimed comment"

r = classify_comments([human("randomuser", "has been awarded, definitely, 100%")])
assert r["status"] == "open", "only the algora bot's word counts, not a human quoting it"

# competition signals
r = classify_comments([
    bot("## \U0001f48e $100 bounty"),
    human("alice", "/attempt #12"),
    human("bob", "/attempt #12"),
    human("alice", "/attempt #12"),          # same person twice = one competitor
    human("carol", "I think the bug is in foo.py"),   # not an attempt
])
assert r["attempts"] == 2, r["attempts"]

r = classify_comments([bot("\U0001f4a1 @dev submitted a pull request that claims the bounty")])
assert r["has_pr"] is True

# --- scorer ---
NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)
def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")

ideal = {"amount": 120, "status": "open", "attempts": 0, "has_pr": False,
         "assigned": False, "comments": 2, "stars": 1500, "labels": [],
         "updated_at": iso(2), "created_at": iso(5)}
hi, _ = score(ideal, NOW)
assert hi >= 85, f"clean fresh uncontested bounty should rank high, got {hi}"

contested = dict(ideal, attempts=3, status="claimed", has_pr=True, comments=60)
lo, why = score(contested, NOW)
assert lo < 25, f"heavily contested should rank low, got {lo}"
assert any("PR already submitted" in w for w in why)

stale = dict(ideal, updated_at=iso(900), created_at=iso(1200))
assert score(stale, NOW)[0] < hi, "stale must score below fresh"

huge = dict(ideal, stars=50000)
assert score(huge, NOW)[0] < hi, "giant repos are a harder merge"

assert 1 <= score(dict(ideal, attempts=99, has_pr=True, comments=500), NOW)[0] <= 100
print("ok")
