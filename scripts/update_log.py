#!/usr/bin/env python3
"""
Appends a dated section to data/log.md based on the most recent data/latest_deals.json
(one sub-section per cabin). Run after check_flights.py. Also writes
data/last_notify.json for the read-only notifier routine to consume.
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
LOG_MD = DATA_DIR / "log.md"
DEALS_JSON = DATA_DIR / "latest_deals.json"

CABIN_LABELS = {"business": "Business", "premium-economy": "Premium Economy"}


def get_previous_best(cabin: str):
    if not LOG_MD.exists():
        return None
    text = LOG_MD.read_text()
    # Require an actual "### <Cabin>" heading, not just the word appearing anywhere
    # (e.g. in the page's own H1 title), then the nearest following running-best line.
    heading = re.escape(CABIN_LABELS.get(cabin, cabin))
    pattern = r"^### " + heading + r"\s*\n.*?Running best price so far: \*\*\$([\d,]+)\*\*"
    matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
    if not matches:
        return None
    return int(matches[-1].replace(",", ""))


def main():
    summary = json.loads(DEALS_JSON.read_text())
    today = summary["run_timestamp"]
    by_cabin = summary["by_cabin"]

    lines = [f"\n## {today}"]
    notify_by_cabin = {}
    should_notify_any = False

    for cabin, s in by_cabin.items():
        label = CABIN_LABELS.get(cabin, cabin)
        prev_best = get_previous_best(cabin)
        cheapest = s.get("cheapest_overall")
        this_run_best = cheapest["cheapest_price_usd"] if cheapest else None
        running_best = min(this_run_best, prev_best) if (this_run_best is not None and prev_best) else (this_run_best or prev_best)
        is_new_best = this_run_best is not None and (prev_best is None or this_run_best < prev_best)
        deals = s.get("deals", [])

        lines.append(f"\n### {label}")
        lines.append(
            f"- Swept {s['dates_succeeded']}/{s['dates_checked']} candidate departure dates "
            f"({s['dates_errored']} failed)."
        )
        if cheapest:
            lines.append(
                f"- Cheapest overall: **${cheapest['cheapest_price_usd']:,}** round trip — "
                f"{cheapest['airline'] or 'carrier unconfirmed'}, {cheapest['stops']} stop(s) — "
                f"on {cheapest['depart_date']} -> {cheapest['return_date']}."
            )
        else:
            lines.append("- No fares collected this run (all dates failed).")

        if deals:
            lines.append(f"- **{len(deals)} deal(s) at/under ${s['alert_threshold_usd']:,}:**")
            for d in deals:
                lines.append(
                    f"  - ${d['cheapest_price_usd']:,} | {d['depart_date']} -> {d['return_date']} | {d['airline'] or 'carrier unconfirmed'}"
                )
        else:
            lines.append(f"- No deals at/under ${s['alert_threshold_usd']:,} this run.")

        if running_best is not None:
            marker = " (new low!)" if is_new_best else ""
            lines.append(f"- Running best price so far: **${running_best:,}**{marker}.")

        cabin_should_notify = bool(deals) or is_new_best
        should_notify_any = should_notify_any or cabin_should_notify
        notify_by_cabin[cabin] = {
            "should_notify": cabin_should_notify,
            "is_new_best": is_new_best,
            "running_best_usd": running_best,
            "deals": deals,
            "cheapest_overall": cheapest,
            "alert_threshold_usd": s["alert_threshold_usd"],
        }

    if LOG_MD.exists():
        with open(LOG_MD, "a") as f:
            f.write("\n".join(lines) + "\n")
    else:
        header = "# SFO -> Hyderabad Price Log\n"
        with open(LOG_MD, "w") as f:
            f.write(header + "\n".join(lines) + "\n")

    notify_marker = {
        "checked_on": today,
        "should_notify": should_notify_any,
        "by_cabin": notify_by_cabin,
    }
    (DATA_DIR / "last_notify.json").write_text(json.dumps(notify_marker, indent=2))

    print(f"NOTIFY:{'yes' if should_notify_any else 'no'}")
    for cabin, n in notify_by_cabin.items():
        print(f"[{cabin}] RUNNING_BEST:{n['running_best_usd']} NEW_BEST:{n['is_new_best']}")


if __name__ == "__main__":
    main()
