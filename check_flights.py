#!/usr/bin/env python3
"""
SFO -> Hyderabad business class fare tracker.

Sweeps a set of candidate departure dates (round trip, ~21 day stay by default),
queries Google Flights via fast-flights (free, no API key), keeps the cheapest
result per date, appends everything to a running CSV log, and writes a JSON
summary of "deals" (fares at/under the alert threshold) for the caller to act on.

Usage:
    venv/bin/python3 check_flights.py

Config lives in the CONFIG block below -- edit dates/threshold there.
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
SEAT = "business"

# Candidate departure dates to sweep (mid-Nov to mid-Dec 2026 window).
# One query per departure date; each is a round trip with TRIP_LENGTH_DAYS stay.
DEPARTURE_START = date(2026, 11, 15)
DEPARTURE_END = date(2026, 12, 15)
SWEEP_STEP_DAYS = 3          # check every 3rd day across the window (keeps query count sane)
TRIP_LENGTH_DAYS = 21        # return date = departure + this many days

# Alert threshold: fares at or below this (per person, round trip, USD) count as a "deal".
# Based on a live sweep on 2026-08-31: observed range was $4,338-$9,621, with the
# cheapest ($4,338, Cathay Pacific 1-stop) on Nov 24 and Nov 30 departures.
# Set just above that so we get notified as soon as it matches or beats the best seen so far.
ALERT_THRESHOLD_USD = 4500

DATA_DIR = Path(__file__).parent / "data"
LOG_CSV = DATA_DIR / "price_history.csv"
DEALS_JSON = DATA_DIR / "latest_deals.json"
# -----------------------------------------


def sweep_dates():
    d = DEPARTURE_START
    while d <= DEPARTURE_END:
        yield d
        d += timedelta(days=SWEEP_STEP_DAYS)


def query_one(depart: date, return_: date):
    result = get_flights(
        flight_data=[
            FlightData(date=depart.isoformat(), from_airport=ORIGIN, to_airport=DEST),
            FlightData(date=return_.isoformat(), from_airport=DEST, to_airport=ORIGIN),
        ],
        trip="round-trip",
        seat=SEAT,
        passengers=Passengers(adults=1, children=0, infants_in_seat=0, infants_on_lap=0),
        fetch_mode="fallback",
    )
    return result


def parse_price(price_str: str):
    try:
        return int(price_str.replace("$", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def main():
    DATA_DIR.mkdir(exist_ok=True)
    is_new_log = not LOG_CSV.exists()

    run_timestamp = date.today().isoformat()
    rows = []
    deals = []
    errors = []

    for depart in sweep_dates():
        return_ = depart + timedelta(days=TRIP_LENGTH_DAYS)
        try:
            result = query_one(depart, return_)
        except Exception as e:
            errors.append({"depart": depart.isoformat(), "error": str(e)})
            continue

        priced_flights = [
            (f, parse_price(f.price)) for f in result.flights
        ]
        priced_flights = [(f, p) for f, p in priced_flights if p is not None]
        if not priced_flights:
            continue

        priced_flights.sort(key=lambda fp: fp[1])
        cheapest_flight, cheapest_price = priced_flights[0]

        row = {
            "checked_on": run_timestamp,
            "depart_date": depart.isoformat(),
            "return_date": return_.isoformat(),
            "cheapest_price_usd": cheapest_price,
            "airline": cheapest_flight.name,
            "stops": cheapest_flight.stops,
            "duration": cheapest_flight.duration,
            "current_price_signal": result.current_price,  # google's "low/typical/high" indicator
        }
        rows.append(row)

        if cheapest_price <= ALERT_THRESHOLD_USD:
            deals.append(row)

    # Append to running CSV log
    if rows:
        with open(LOG_CSV, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            if is_new_log:
                writer.writeheader()
            writer.writerows(rows)

    # Write latest deals + full run summary as JSON for the caller
    summary = {
        "run_timestamp": run_timestamp,
        "dates_checked": len(rows) + len(errors),
        "dates_succeeded": len(rows),
        "dates_errored": len(errors),
        "errors": errors,
        "alert_threshold_usd": ALERT_THRESHOLD_USD,
        "deals": deals,
        "all_results": rows,
        "cheapest_overall": min(rows, key=lambda r: r["cheapest_price_usd"]) if rows else None,
    }
    with open(DEALS_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    # Print a compact human-readable summary to stdout for the caller (Claude) to read
    print(f"Checked {len(rows)}/{len(rows)+len(errors)} dates successfully.")
    if summary["cheapest_overall"]:
        c = summary["cheapest_overall"]
        print(f"Cheapest overall: ${c['cheapest_price_usd']} on {c['depart_date']} -> {c['return_date']} ({c['airline']}, {c['stops']} stop(s))")
    if deals:
        print(f"*** {len(deals)} deal(s) at/under ${ALERT_THRESHOLD_USD} ***")
        for d in deals:
            print(f"  ${d['cheapest_price_usd']} | {d['depart_date']} -> {d['return_date']} | {d['airline']}")
    else:
        print(f"No deals at/under ${ALERT_THRESHOLD_USD} this run.")
    if errors:
        print(f"{len(errors)} date(s) failed to query.", file=sys.stderr)

    return 0 if not errors or rows else 1


if __name__ == "__main__":
    sys.exit(main())
