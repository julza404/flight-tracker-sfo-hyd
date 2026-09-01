# SFO → Hyderabad Business Class Tracker

Tracks cash business-class fares SFO↔HYD for departures mid-Nov to mid-Dec 2026,
logs history, and flags deals. Built to avoid any paid subscription.

## How it works
- `check_flights.py` queries Google Flights (via the free `fast-flights` library,
  no API key) for round-trip business class fares across a sweep of departure
  dates (every 3 days from 2026-11-15 to 2026-12-15, 21-day trip length).
- Every run appends to `data/price_history.csv` (full history, one row per
  date/run) and overwrites `data/latest_deals.json` (this run's summary).
- A deal is any fare at or below `ALERT_THRESHOLD_USD` (currently **$3,800**
  round trip, per person) — this is a starting guess based on typical
  SFO–HYD business fares of $3,800–6,500; adjust in `check_flights.py` once
  you've seen a few weeks of real data.
- Runs on a recurring Claude Code schedule (daily). Each run: execute the
  script, read `latest_deals.json`, push-notify on any deal or a new
  cheapest-overall price, and note the result in `data/log.md`.

## Capital One points strategy
Two ways to use Capital One miles for this trip, from simplest to highest value:

1. **Purchase Eraser (simple, guaranteed)** — book the cash fare this tracker
   finds, then redeem Capital One miles to erase the charge at **1 cent/mile**
   (Venture/Venture X). A $4,000 fare = 400,000 miles. No availability risk,
   works on any fare. This is what the tracker's "points needed" figure
   assumes.
2. **Transfer to an airline partner for an award seat (higher value, more
   effort)** — Capital One transfers 1:1 (mostly) to Turkish Miles&Smiles,
   Avianca LifeMiles, Air Canada Aeroplan, Singapore KrisFlyer, Etihad Guest,
   Emirates Skywards, and others. A well-priced Star Alliance or partner
   business award SFO–HYD (usually via a connection — HYD has no nonstop from
   SFO) can run 100–150k miles round trip instead of 400k+, sometimes plus
   fuel surcharges depending on program. **This part is not automated** —
   there's no free, reliable API for live award-seat availability (the paid
   options are Seats.aero Pro and ExpertFlyer, which you said to skip). If
   the tracker shows persistently high cash fares, that's your cue to
   manually check award space on united.com (Star Alliance saver seats),
   aircanada.com/aeroplan, or lifemiles.com before defaulting to the
   Purchase Eraser.

## Files
- `check_flights.py` — the checker (edit CONFIG block to change dates/threshold)
- `data/price_history.csv` — full run history
- `data/latest_deals.json` — most recent run's structured output
- `data/log.md` — human-readable running log, updated each scheduled run
- `venv/` — isolated Python env (fast-flights + deps)

## Running manually
```
cd ~/flight-tracker-sfo-hyd
./venv/bin/python3 check_flights.py
```
