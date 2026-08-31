"""Run: python test_scan.py"""
from scan import parse_amount as p, classify_comments

assert p("$500 bounty") == 500
assert p("Bounty: $1,000.00") == 1000
assert p("pays 250 USD") == 250
assert p("$2k reward") == 2000
assert p("500 USDC for this") == 500
assert p("\U0001f4b0 $75") == 75
assert p("takes the larger: $50 or $300") == 300
assert p("fix bug in v2.1.0") is None, "version numbers are not money"
assert p("issue #4242") is None, "issue refs are not money"
assert p("$0 bounty") is None, "zero is not a bounty"
assert p("$999999 scam") is None, "implausible amounts rejected"
assert p("") is None and p(None) is None

def bot(body):
    return {"user": {"login": "algora-pbc[bot]"}, "body": body}

amt, status = classify_comments([bot("## \U0001f48e $500 bounty created")])
assert (amt, status) == (500, "open")

amt, status = classify_comments([
    bot("## \U0001f48e $500 bounty created"),
    bot("Note: @someone is already attempting to complete issue #1"),
])
assert status == "claimed"

amt, status = classify_comments([
    bot("## \U0001f48e $500 bounty created"),
    bot("Note: @someone is already attempting to complete issue #1"),
    bot("\U0001f389 @someone has been awarded **$500**!"),
])
assert status == "awarded", "awarded must win even after a claimed comment"

amt, status = classify_comments([
    {"user": {"login": "randomuser"}, "body": "has been awarded, definitely, 100%"},
])
assert status == "open", "only the algora bot's own words count, not a human quoting them"

print("ok")
