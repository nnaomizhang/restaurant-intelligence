"""
Opening Hours Analyser
======================
Parses Google Places opening hours and segments restaurants by
trading pattern to identify target customer demographics.

Segments:
  - breakfast_spot     : opens before 9am
  - lunch_focused      : closes before 5pm
  - dinner_focused     : opens after 5pm
  - late_night         : closes after 11pm
  - weekend_only       : closed Mon-Fri
  - weekday_focused    : closed Sat/Sun
  - all_day            : open 7+ days, 12+ hours/day
  - family_dining      : closes before 9pm, open weekends
  - working_professional: lunch + dinner, Mon-Fri focused
"""

import json
import re
from pathlib import Path
from sqlalchemy import create_engine, text
from config import PROCESSED_DIR, DATABASE_URL


def parse_time(time_str: str) -> int | None:
    """Convert time string like '8:00 AM' to minutes since midnight."""
    if not time_str:
        return None
    time_str = time_str.strip()
    # Remove unicode spaces
    time_str = re.sub(r'[\u202f\u2009\u00a0]', ' ', time_str).strip()

    match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str, re.I)
    if not match:
        return None

    hour, minute, period = int(match.group(1)), int(match.group(2)), match.group(3).upper()

    if period == 'PM' and hour != 12:
        hour += 12
    elif period == 'AM' and hour == 12:
        hour = 0

    return hour * 60 + minute


def parse_hours(opening_hours: list[str]) -> dict:
    """Parse opening hours list into structured dict."""
    days = {}
    day_map = {
        'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
        'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun'
    }

    for entry in opening_hours:
        # Remove unicode spaces
        entry = re.sub(r'[\u202f\u2009\u00a0]', ' ', entry).strip()

        # Split on first colon after day name
        match = re.match(r'(\w+):\s*(.+)', entry)
        if not match:
            continue

        day_name = match.group(1).lower()
        hours_str = match.group(2).strip()
        day_key = day_map.get(day_name)

        if not day_key:
            continue

        if 'closed' in hours_str.lower():
            days[day_key] = None
            continue

        # Handle overnight hours like "11:00 PM – 3:00 AM"
        parts = re.split(r'[–\-]', hours_str)
        if len(parts) == 2:
            open_time = parse_time(parts[0].strip())
            close_time = parse_time(parts[1].strip())
            days[day_key] = {"open": open_time, "close": close_time}
        else:
            days[day_key] = None

    return days


def classify_trading_pattern(hours: dict) -> dict:
    """Classify restaurant by trading pattern and target demographic."""
    if not hours:
        return {"pattern": "unknown", "segments": []}

    open_days = {k: v for k, v in hours.items() if v is not None}
    weekdays = {k: v for k, v in open_days.items() if k in ['mon', 'tue', 'wed', 'thu', 'fri']}
    weekend = {k: v for k, v in open_days.items() if k in ['sat', 'sun']}

    segments = []

    # Opening time analysis
    open_times = [v['open'] for v in open_days.values() if v and v.get('open') is not None]
    close_times = [v['close'] for v in open_days.values() if v and v.get('close') is not None]

    avg_open = sum(open_times) / len(open_times) if open_times else None
    avg_close = sum(close_times) / len(close_times) if close_times else None

    # Breakfast spot — opens before 9am
    if avg_open and avg_open < 9 * 60:
        segments.append("breakfast_spot")

    # Late night — closes after 11pm
    if avg_close and avg_close > 23 * 60:
        segments.append("late_night")

    # Lunch focused — closes before 5pm
    if avg_close and avg_close < 17 * 60:
        segments.append("lunch_focused")

    # Dinner focused — opens after 5pm on average
    if avg_open and avg_open > 17 * 60:
        segments.append("dinner_focused")

    # Weekend only
    if len(weekdays) == 0 and len(weekend) > 0:
        segments.append("weekend_only")

    # Weekday focused
    if len(weekdays) >= 4 and len(weekend) == 0:
        segments.append("weekday_focused")

    # All day — open most days with long hours
    if len(open_days) >= 6:
        long_hours = [
            k for k, v in open_days.items()
            if v and v.get('open') and v.get('close')
            and (v['close'] - v['open']) >= 12 * 60
        ]
        if len(long_hours) >= 4:
            segments.append("all_day")

    # Family dining — closes before 9pm, open weekends
    if avg_close and avg_close <= 21 * 60 and len(weekend) > 0:
        segments.append("family_dining")

    # Working professional — weekday lunch + dinner
    if len(weekdays) >= 4 and avg_open and avg_open <= 12 * 60:
        segments.append("working_professional")

    # Primary pattern
    if "late_night" in segments:
        pattern = "late_night"
    elif "breakfast_spot" in segments and "dinner_focused" not in segments:
        pattern = "breakfast_cafe"
    elif "dinner_focused" in segments:
        pattern = "dinner_restaurant"
    elif "all_day" in segments:
        pattern = "all_day_dining"
    elif "family_dining" in segments:
        pattern = "family_restaurant"
    elif "weekday_focused" in segments:
        pattern = "business_dining"
    else:
        pattern = "standard"

    return {
        "pattern": pattern,
        "segments": segments,
        "days_open": len(open_days),
        "avg_open_time": f"{int(avg_open//60):02d}:{int(avg_open%60):02d}" if avg_open else None,
        "avg_close_time": f"{int(avg_close//60):02d}:{int(avg_close%60):02d}" if avg_close else None,
        "open_weekends": len(weekend) > 0,
        "open_weekdays": len(weekdays) > 0,
    }


def run_hours_analysis():
    """Analyse opening hours for all restaurants and update PostgreSQL."""
    print("\n" + "="*60)
    print("  OPENING HOURS ANALYSIS")
    print("="*60)

    engine = create_engine(DATABASE_URL)

    # Add columns if not exist
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE restaurants
                ADD COLUMN IF NOT EXISTS trading_pattern TEXT,
                ADD COLUMN IF NOT EXISTS customer_segments TEXT[],
                ADD COLUMN IF NOT EXISTS days_open INTEGER,
                ADD COLUMN IF NOT EXISTS avg_open_time TEXT,
                ADD COLUMN IF NOT EXISTS avg_close_time TEXT,
                ADD COLUMN IF NOT EXISTS open_weekends BOOLEAN,
                ADD COLUMN IF NOT EXISTS open_weekdays BOOLEAN
            """))
            conn.commit()
            print("  Added opening hours columns to restaurants table")
        except Exception as e:
            conn.rollback()
            print(f"  Columns may already exist: {e}")

    # Load processed Google Places data
    areas = ["Shoreditch", "Peckham", "Hackney"]
    total_analysed = 0
    pattern_counts = {}

    for area in areas:
        folder = PROCESSED_DIR / "google_places"
        slug = area.lower()
        files = sorted(folder.glob(f"{slug}*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            continue

        with open(files[0]) as f:
            records = json.load(f)

        print(f"\n  {area}: {len(records)} restaurants")

        with engine.connect() as conn:
            for r in records:
                place_id = r.get("google_place_id")
                opening_hours = r.get("opening_hours", [])

                if not place_id or not opening_hours:
                    continue

                hours = parse_hours(opening_hours)
                classification = classify_trading_pattern(hours)

                pattern = classification["pattern"]
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

                try:
                    conn.execute(text("""
                        UPDATE restaurants
                        SET trading_pattern = :pattern,
                            customer_segments = :segments,
                            days_open = :days_open,
                            avg_open_time = :avg_open,
                            avg_close_time = :avg_close,
                            open_weekends = :weekends,
                            open_weekdays = :weekdays
                        WHERE google_place_id = :place_id
                    """), {
                        "pattern": pattern,
                        "segments": classification["segments"],
                        "days_open": classification["days_open"],
                        "avg_open": classification["avg_open_time"],
                        "avg_close": classification["avg_close_time"],
                        "weekends": classification["open_weekends"],
                        "weekdays": classification["open_weekdays"],
                        "place_id": place_id,
                    })
                    total_analysed += 1
                except Exception as e:
                    print(f"    Error updating {place_id}: {e}")

            conn.commit()

    print(f"\n  Total analysed: {total_analysed}")
    print(f"\n  Trading patterns:")
    for pattern, count in sorted(pattern_counts.items(), key=lambda x: -x[1]):
        print(f"    {pattern:<25} {count:>4} restaurants")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    run_hours_analysis()