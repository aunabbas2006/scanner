# Bounty Radar

Watches GitHub for new bounty-labeled issues, pushes a phone notification, serves a dashboard.
Runs entirely on GitHub's servers — your laptop is irrelevant.

## Setup (~10 min, $0)

1. **Push this to a public GitHub repo.** Public = unlimited free Actions minutes.

2. **Enable Pages:** Settings → Pages → Source: `Deploy from a branch`, branch `main`, folder `/docs`.
   Dashboard lands at `https://<you>.github.io/<repo>/`.

3. **Allow the workflow to commit:** Settings → Actions → General → Workflow permissions →
   *Read and write permissions*.

4. **Phone alerts (optional):** install the [ntfy](https://ntfy.sh) app, subscribe to a
   random topic name, then add it as a repo secret named `NTFY_TOPIC`.
   Pick something unguessable — anyone who knows the topic can read it.

5. **Kick it off:** Actions tab → `bounty radar` → Run workflow.

## Tuning

Everything lives in `config.json`:

| key | meaning |
|---|---|
| `watch_repos` | your specialized repos — these **bypass the star gate** |
| `queries` | raw GitHub issue-search queries |
| `min_amount` | ignore bounties below this |
| `min_stars` | junk filter for unwatched repos |
| `max_age_days` | ignore stale issues |

## Check

```bash
python test_scan.py
```

Covers the money parser — the only non-trivial logic. Run it if you touch the regex.

## Known ceilings

- **GitHub Actions cron drifts** 5–20 min under load. `*/15` is really "every 15–35 min."
  Fine for this; if you need true 15-min latency you need a VPS, which costs money.
- **Global label search is mostly spam.** See below.
- Amounts come from the issue body or bot comments. A bounty announced only in a
  screenshot or an external dashboard won't be seen.
