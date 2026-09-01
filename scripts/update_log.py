#!/usr/bin/env python3
"""
Appends a dated section to data/log.md based on the most recent data/latest_deals.json.
Run after check_flights.py. Also prints a one-line machine-readable summary to stdout
(NOTIFY:yes/no) so a caller (e.g. a separate notifier) can decide whether to alert.
"""
import json
import re
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LOG_MD = DATA_DIR / "log.md"
DEALS_JSON = DATA_DIR / "latest_deals.json"


def get_previous_best():
    if not LOG_MD.exists():
        return None
    text = LOG_MD.read_text()
    matches = re.findall(r"Running best price so far: \*\*\$([\d,]+)\*\*", text)
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def main():
    summary = json.loads(DEALS_JSON.read_text())
    today = summary["run_timestamp"]
    prev_best = get_previous_best()

    cheapest = summary.get("cheapest_overall")
    this_run_best = cheapest["cheapest_price_usd"] if cheapest else None

    if this_run_best is not None:
        running_best = min(this_run_best, prev_best) if prev_best else this_run_best
    else:
        running_best = prev_best

    lines = [f"\n## {today}"]
    lines.append(
        f"- Swept {summary['dates_succeeded']}/{summary['dates_checked']} candidate departure dates "
        f"({summary['dates_errored']} failed)."
    )
    if cheapest:
        lines.append(
            f"- Cheapest overall: **${cheapest['cheapest_price_usd']:,}** round trip — "
            f"{cheapest['airline']}, {cheapest['stops']} stop(s) — "
            f"on {cheapest['depart_date']} -> {cheapest['return_date']}."
        )
    else:
        lines.append("- No fares collected this run (all dates failed).")

    deals = summary.get("deals", [])
    if deals:
        lines.append(f"- **{len(deals)} deal(s) at/under ${summary['alert_threshold_usd']:,}:**")
        for d in deals:
            lines.append(
                f"  - ${d['cheapest_price_usd']:,} | {d['depart_date']} -> {d['return_date']} | {d['airline']}"
            )
    else:
        lines.append(f"- No deals at/under ${summary['alert_threshold_usd']:,} this run.")

    is_new_best = this_run_best is not None and (prev_best is None or this_run_best < prev_best)
    if running_best is not None:
        marker = " (new low!)" if is_new_best else ""
        lines.append(f"- Running best price so far: **${running_best:,}**{marker}.")

    if LOG_MD.exists():
        with open(LOG_MD, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        header = "# SFO -> Hyderabad Business Class Price Log\n"
        with open(LOG_MD, "w") as f:
            f.write(header + "\n".join(lines) + "\n")

    should_notify = bool(deals) or is_new_best

    # Machine-readable marker for the read-only notifier (a Claude cloud routine
    # that pulls this repo but never pushes) to consume without re-deriving anything.
    notify_marker = {
        "checked_on": today,
        "should_notify": should_notify,
        "is_new_best": is_new_best,
        "running_best_usd": running_best,
        "deals": deals,
        "cheapest_overall": cheapest,
    }
    (DATA_DIR / "last_notify.json").write_text(json.dumps(notify_marker, indent=2))

    print(f"NOTIFY:{'yes' if should_notify else 'no'}")
    print(f"RUNNING_BEST:{running_best}")
    print(f"NEW_BEST:{is_new_best}")


if __name__ == "__main__":
    main()
