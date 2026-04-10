"""
Run All Collectors
==================
Runs data collectors for all target areas.
Skips sources that already have data unless --force is used.

Usage:
  python run_collectors.py                    # Run missing only
  python run_collectors.py --force            # Force rerun all
  python run_collectors.py --source fsa       # Run one source
  python run_collectors.py --source deliveroo --force  # Force one source
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from config import TARGET_AREAS, RAW_DIR
from processing.lineage import print_lineage_summary


SOURCES = [
    "google_places",
    "fsa",
    "companies_house",
    "deliveroo",
    "ons_census",
]


def already_collected(source: str, area_name: str) -> bool:
    """Check if data already exists for this source/area."""
    folder = RAW_DIR / source
    if not folder.exists():
        return False
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = list(folder.glob(f"{slug}*.json"))
    return len(files) > 0


def get_missing_areas(source: str) -> list[dict]:
    """Return areas that have not yet been collected for a source."""
    return [a for a in TARGET_AREAS if not already_collected(source, a["name"])]


def get_all_areas(source: str) -> list[dict]:
    """Return all areas regardless of existing data."""
    return TARGET_AREAS


def print_status():
    """Print current collection status for all sources and areas."""
    print(f"\n{'─'*50}")
    print(f"  COLLECTION STATUS")
    print(f"{'─'*50}")
    for source in SOURCES:
        for area in TARGET_AREAS:
            folder = RAW_DIR / source
            slug = area["name"].lower().replace(" ", "_")
            files = list(folder.glob(f"{slug}*.json")) if folder.exists() else []
            status = f"✓ {len(files)} file(s)" if files else "✗ missing"
            print(f"  {source:<20} {area['name']:<12} {status}")
    print(f"{'─'*50}\n")


def run_google_places(areas):
    from collectors.google_places import GooglePlacesCollector
    collector = GooglePlacesCollector()
    return collector.collect_all(areas)


def run_fsa(areas):
    from collectors.fsa import FSACollector
    collector = FSACollector()
    return collector.collect_all(areas)


def run_companies_house(areas):
    from collectors.companies_house import CompaniesHouseCollector
    collector = CompaniesHouseCollector()
    return collector.collect_all(areas)


def run_deliveroo(areas):
    from collectors.deliveroo import DeliverooCollector
    collector = DeliverooCollector()
    return collector.collect_all(areas)


def run_ons_census(areas):
    from collectors.ons_census import ONSCensusCollector
    collector = ONSCensusCollector()
    return collector.collect_all(areas)


RUNNERS = {
    "google_places": run_google_places,
    "fsa": run_fsa,
    "companies_house": run_companies_house,
    "deliveroo": run_deliveroo,
    "ons_census": run_ons_census,
}


def run_all(sources=None, force=False):
    start = datetime.now()

    print(f"\n{'='*60}")
    print(f"  RESTAURANT INTELLIGENCE — DATA COLLECTION")
    print(f"  Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {'FORCE RERUN' if force else 'SKIP EXISTING'}")
    print(f"{'='*60}")

    print_status()

    sources = sources or SOURCES
    results = {}
    total = 0

    for source in sources:
        print(f"\n--- {source} ---")

        areas = get_all_areas(source) if force else get_missing_areas(source)

        if not areas:
            print(f"  All areas already collected — skipping")
            print(f"  Use --force to rerun")
            continue

        skipped = [
            a["name"] for a in TARGET_AREAS
            if a not in areas
        ]
        if skipped:
            print(f"  Skipping (already collected): {skipped}")
        print(f"  Collecting for: {[a['name'] for a in areas]}")

        runner = RUNNERS[source]
        area_results = runner(areas)
        results[source] = area_results

        count = sum(len(v) for v in area_results.values())
        total += count
        print(f"  Done: {count} records")

    # Summary
    end = datetime.now()
    duration = (end - start).seconds

    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE — {duration}s")
    print(f"{'='*60}")

    for source, area_results in results.items():
        count = sum(len(v) for v in area_results.values())
        print(f"  {source:<20} {count:>4} records")

    if results:
        print(f"  {'─'*30}")
        print(f"  {'New records':<20} {total:>4}")

    print(f"{'='*60}\n")

    print_status()
    print_lineage_summary()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data collectors")
    parser.add_argument(
        "--source", "-s",
        choices=SOURCES,
        help="Run only this collector"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force rerun even if data already exists"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show collection status and exit"
    )
    args = parser.parse_args()

    if args.status:
        print_status()
        sys.exit(0)

    sources = [args.source] if args.source else None
    run_all(sources=sources, force=args.force)