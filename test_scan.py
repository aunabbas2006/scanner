"""Run: python test_scan.py"""
from scan import parse_amount as p

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
print("ok")
