#!/usr/bin/env python3
"""
SFO -> Hyderabad business + premium economy fare tracker.

Sweeps a set of candidate departure dates, queries Google Flights via
fast-flights (free, no API key) for each cabin in SEAT_CLASSES, keeps the
cheapest result per date/cabin, appends everything to a running CSV log, and
writes a JSON summary of "deals" (fares at/under each cabin's alert threshold)
for the caller to act on.

Usage:
    venv/bin/python3 check_flights.py

Config lives in the CONFIG block below -- edit dates/thresholds there.
"""
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from fast_flights import FlightData, Passengers, get_flights

# ---------------- CONFIG ----------------
ORIGIN = "SFO"
DEST = "HYD"
SEAT_CLASSES = ["business", "premium-economy"]

# Candidate departure dates to sweep (mid-Nov to mid-Dec 2026 window).
# One query per departure date per cabin; each is a round trip with
# TRIP_LENGTH_DAYS stay. 31 days means the latest departure (Dec 15) returns
# on Jan 15, 2027 -- the latest return date wanted.
DEPARTURE_START = date(2026, 11, 15)
DEPARTURE_END = date(2026, 12, 15)
SWEEP_STEP_DAYS = 3          # check every 3rd day across the window (keeps query count sane)
TRIP_LENGTH_DAYS = 31        # return date = departure + this many days (up to 2027-01-15)

# Alert threshold per cabin: fares at or below this (per person, round trip, USD)
# count as a "deal". Business is grounded in a live sweep on 2026-08-31 ($4,338-$9,621
# observed, cheapest via Cathay Pacific). Premium economy has no observed data yet --
# this is a placeholder guess (typical SFO-int'l premium economy long-haul runs
# well under half of business); tighten it once a few real runs land.
ALERT_THRESHOLD_USD = {
    "business": 4500,
    "premium-economy": 2200,
}

DATA_DIR = Path(__file__).parent / "data"
LOG_CSV = DATA_DIR / "price_history.csv"
DEALS_JSON = DATA_DIR / "latest_deals.json"
# -----------------------------------------


def sweep_dates():
    d = DEPARTURE_START
    while d <= DEPARTURE_END:
        yield d
        d += timedelta(days=SWEEP_STEP_DAYS)


def query_one(depart: date, return_: date, seat: str):
    result = get_flights(
        flight_data=[
            FlightData(date=depart.isoformat(), from_airport=ORIGIN, to_airport=DEST),
            FlightData(date=return_.isoformat(), from_airport=DEST, to_airport=ORIGIN),
        ],
        trip="round-trip",
        seat=seat,
        passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),
        fetch_mode="fallback",
    )
    return result


def parse_price(price_str: str):
    try:
        return int(price_str.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def run_cabin(seat: str, run_timestamp: str):
    rows = []
    deals = []
    errors = []
    threshold = ALERT_THRESHOLD_USD[seat]

    for depart in sweep_dates():
        return_ = depart + timedelta(days=TRIP_LENGTH_DAYS)
        try:
            result = query_one(depart, return_, seat)
        except Exception as e:
            errors.append({"depart": depart.isoformat(), "error": str(e)})
            continue

        priced_flights = [(f, parse_price(f.price)) for f in result.flights]
        priced_flights = [(f, p) for f, p in priced_flights if p is not None]
        if not priced_flights:
            continue

        # Sort by price, then prefer rows with a real airline name (Google occasionally
        # returns a blank name/stops for an otherwise-valid, cheapest-priced row).
        priced_flights.sort(key=lambda fp: (fp[1], not fp[0].name))
        cheapest_flight, cheapest_price = priced_flights[0]

        row = {
            "checked_on": run_timestamp,
            "cabin": seat,
            "depart_date": depart.isoformat(),
            "return_date": return_.isoformat(),
            "cheapest_price_usd": cheapest_price,
            "airline": cheapest_flight.name,
            "stops": cheapest_flight.stops,
            "duration": cheapest_flight.duration,
            "current_price_signal": result.current_price,  # google's "low/typical/high" indicator
        }
        rows.append(row)

        if cheapest_price <= threshold:
            deals.append(row)

    return {
        "cabin": seat,
        "alert_threshold_usd": threshold,
        "dates_checked": len(rows) + len(errors),
        "dates_succeeded": len(rows),
        "dates_errored": len(errors),
        "errors": errors,
        "deals": deals,
        "all_results": rows,
        "cheapest_overall": min(rows, key=lambda r: r["cheapest_price_usd"]) if rows else None,
    }


def main():
    DATA_DIR.mkdir(exist_ok=True)
    is_new_log = not LOG_CSV.exists()
    run_timestamp = date.today().isoformat()

    by_cabin = {seat: run_cabin(seat, run_timestamp) for seat in SEAT_CLASSES}

    # Append every cabin's rows to the running CSV log (shared file, "cabin" column disambiguates)
    all_rows = [row for cabin_summary in by_cabin.values() for row in cabin_summary["all_results"]]
    if all_rows:
        with open(LOG_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            if is_new_log:
                writer.writeheader()
            writer.writerows(all_rows)

    summary = {
        "run_timestamp": run_timestamp,
        "by_cabin": by_cabin,
    }
    with open(DEALS_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    # Print a compact human-readable summary to stdout for the caller (Claude) to read
    any_rows = False
    any_errors = False
    for seat, s in by_cabin.items():
        any_rows = any_rows or bool(s["all_results"])
        any_errors = any_errors or bool(s["errors"])
        print(f"[{seat}] Checked {s['dates_succeeded']}/{s['dates_checked']} dates successfully.")
        if s["cheapest_overall"]:
            c = s["cheapest_overall"]
            print(f"[{seat}] Cheapest overall: ${c['cheapest_price_usd']} on {c['depart_date']} -> {c['return_date']} ({c['airline']}, {c['stops']} stop(s))")
        if s["deals"]:
            print(f"[{seat}] *** {len(s['deals'])} deal(s) at/under ${s['alert_threshold_usd']} ***")
            for d in s["deals"]:
                print(f"  ${d['cheapest_price_usd']} | {d['depart_date']} -> {d['return_date']} | {d['airline']}")
        else:
            print(f"[{seat}] No deals at/under ${s['alert_threshold_usd']} this run.")
        if s["errors"]:
            print(f"[{seat}] {len(s['errors'])} date(s) failed to query.", file=sys.stderr)

    return 0 if not any_errors or any_rows else 1


if __name__ == "__main__":
    sys.exit(main())
