# SFO → Hyderabad Fare Tracker

Tracks cash business-class and premium-economy fares SFO↔HYD for departures
mid-Nov to mid-Dec 2026, returns as late as mid-Jan 2027, logs history, and
flags deals. Built to avoid any paid subscription.

## How it works
- `check_flights.py` queries Google Flights (via the free `fast-flights` library,
  pinned to `fast-flights==2.2` -- 3.x has a breaking API change) for round-trip
  fares in **both `business` and `premium-economy`** across a sweep of departure
  dates (every 3 days from 2026-11-15 to 2026-12-15). Trip length is fixed at
  31 days, so the latest departure (Dec 15) returns on the latest date wanted
  (Jan 15, 2027) -- earlier departures get correspondingly earlier returns.
- **The actual scraping runs in GitHub Actions** (`.github/workflows/check-flights.yml`,
  daily at 14:07 UTC / ~6-7am Pacific depending on DST), not in a Claude cloud
  routine -- Claude's cloud sandbox blocks outbound requests to google.com at
  its own egress proxy, so the scrape has to happen somewhere with real internet
  access. GitHub's hosted runners have that; free for a repo like this.
- Each GitHub Actions run: installs pinned deps, runs `check_flights.py`
  (appends to `data/price_history.csv`, overwrites `data/latest_deals.json`),
  runs `scripts/update_log.py` (appends a dated section to `data/log.md` and
  writes `data/last_notify.json`), then commits and pushes all of it back to
  the repo with the built-in `GITHUB_TOKEN`.
- A deal is any fare at or below that cabin's threshold in
  `ALERT_THRESHOLD_USD` (a dict in `check_flights.py`): **business $4,500**
  (set after a live sweep on 2026-08-31 found real fares ranging
  $4,338-$9,621, cheapest via Cathay Pacific); **premium economy $2,200** is
  an unverified placeholder -- no real premium-economy data has landed yet,
  tighten it once a few runs come in.
- Every fare gets a `booking_url` -- the same tfs-encoded Google Flights
  search URL the scraper itself queries, so a result links straight to a
  live, bookable search rather than just a number. The dashboard surfaces it
  as a "Book this fare" link on the hero card and a "Book →" link per row.
- The scraper's underlying HTML parser occasionally mis-extracts a
  multi-airline/codeshare row as blank name + blank duration (a DOM-selector
  quirk in `fast_flights`, not a real distinct fare). `check_flights.py`
  filters those out in favor of a confirmed-carrier row whenever one exists
  for that date, so "carrier unconfirmed" should now be rare, not routine.
- **Notification is a separate, read-only Claude cloud routine** ("SFO-HYD
  Business Class Tracker", daily, offset after the GitHub Actions run) that
  just clones this repo, reads `data/last_notify.json`, and sends a push
  notification if either cabin's `should_notify` is true (a deal, or a new
  all-time-low price, tracked separately per cabin so a cheap premium-economy
  fare never masks a business-class deal or vice versa). It never pushes back
  to the repo, which sidesteps a separate permission gap (Claude's GitHub
  connector needed extra scoping just to read the repo, and a full write
  grant wasn't reliably available).

## Capital One points strategy
Two ways to use Capital One miles for this trip, from simplest to highest value:

1. **Purchase Eraser (simple, guaranteed)** — book the cash fare this tracker
   finds, then redeem Capital One miles to erase the charge at **1 cent/mile**
   (Venture/Venture X). A $4,000 fare = 400,000 miles. No availability risk,
   works on any fare. This is what the tracker's "points needed" figure
   assumes.
2. **Transfer to an airline partner for an award seat (higher value, more
   effort)** — Capital One transfers 1:1 (mostly) to Cathay Pacific Asia
   Miles, Turkish Miles&Smiles, Avianca LifeMiles, Air Canada Aeroplan,
   Singapore KrisFlyer, Etihad Guest, Emirates Skywards, and others. Cathay
   Pacific is worth calling out specifically: it's the single most frequent
   carrier this tracker finds on SFO–HYD, and a direct Capital One transfer
   partner, so a business-class award through Asia Miles is the most
   plausible higher-value path here. A well-priced award can run well under
   half of the ~400k+ miles Purchase Eraser implies, sometimes plus fuel
   surcharges depending on program. **This part is not automated and shows
   no "points deals" in the tracker** — there's no free, reliable API for
   live award-seat availability (the paid options are Seats.aero Pro and
   ExpertFlyer, which you said to skip), so award space has to be checked by
   hand. The dashboard links directly to Cathay's award search
   (cathaypacific.com/redeem-flight-awards) for a quick manual check; also
   worth trying aircanada.com/aeroplan and lifemiles.com if cash fares stay
   persistently high on other carriers.

## Files
- `check_flights.py` — the checker (edit CONFIG block to change dates/threshold)
- `scripts/update_log.py` — appends to `data/log.md`, writes `data/last_notify.json`
- `.github/workflows/check-flights.yml` — the daily GitHub Actions job
- `requirements.txt` — pinned deps (`fast-flights==2.2`)
- `data/price_history.csv` — full run history
- `data/latest_deals.json` — most recent run's structured output
- `data/last_notify.json` — small marker the notifier routine reads
- `data/log.md` — human-readable running log, updated each scheduled run
- `venv/` — local-only isolated Python env, not used by CI (gitignored)

## Running manually
```
cd ~/flight-tracker-sfo-hyd
./venv/bin/python3 check_flights.py
./venv/bin/python3 scripts/update_log.py
```
Or trigger the GitHub Actions run directly: `gh workflow run check-flights.yml -R julza404/flight-tracker-sfo-hyd`
