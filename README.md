# Bounty Radar

Watches ~50 repos with active Algora bounty programs, pushes a phone notification
when a genuinely-claimable one appears, and serves a dashboard.
Runs entirely on GitHub's servers — your laptop can be off.

**Dashboard:** https://aunabbas2006.github.io/scanner/

## Setup

1. Settings → Pages → Source `Deploy from a branch`, branch `master`, folder `/docs`
2. Settings → Actions → General → Workflow permissions → **Read and write**
3. (Optional) Install the [ntfy](https://ntfy.sh) app, subscribe to an unguessable
   topic, add it as a repo secret named `NTFY_TOPIC` for phone alerts
4. Actions → `bounty radar` → Run workflow

## Tuning (`config.json`)

| key | meaning |
|---|---|
| `watch_repos` | curated repos — bypass the star gate, get a longer age window |
| `queries` | raw GitHub issue-search queries (global sweep) |
| `min_amount` / `max_amount` | bounty size band. Cap matters: $2000 issues are big-scope and heavily contested |
| `min_stars` | junk filter for repos *not* in `watch_repos` |
| `max_age_days` | freshness cap for the global sweep |
| `watch_max_age_days` | freshness cap for watched repos (generous, but excludes multi-year zombies) |

Freshness is measured on `updated_at`, not `created_at` — an old issue can get a
bounty attached today.

## Check

```bash
python test_scan.py
```

Covers the money parser and the awarded/claimed classifier.

## Known ceilings

- **Algora never removes the `💎 Bounty` label after payout.** The scanner reads each
  issue's full comment thread and drops ones where the bot posted "has been awarded".
  Ones where someone else is already attempting are kept but dimmed and sorted last.
- **GitHub Actions cron drifts** 5–20 min under load. `*/15` is really "every 15–35 min".
- **Search API is 30 req/min.** With ~50 watched repos a run exceeds that, so
  `search()` backs off and retries rather than silently returning nothing.
- Amounts come from the issue body or bot comments — a bounty announced only in a
  screenshot or external dashboard won't be seen.
