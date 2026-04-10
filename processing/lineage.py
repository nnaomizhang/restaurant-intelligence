"""
Data Lineage Tracker
====================
Tracks the provenance of every data record from collection through
processing to final storage. Implements lightweight W3C PROV-style
entity/activity/agent tracking.

Every collector calls lineage.log_collection() after saving data.
Every processing step calls lineage.log_transformation().
The full lineage chain can be queried for any record.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from config import LOGS_DIR


LINEAGE_LOG_PATH = LOGS_DIR / "data_lineage.jsonl"


def _now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def _append_entry(entry: dict):
    """Append a lineage entry to the JSONL log file."""
    with open(LINEAGE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def generate_run_id() -> str:
    """Generate a unique run ID for a collection or processing batch."""
    return str(uuid.uuid4())[:8]


def log_collection(
    run_id: str,
    source_name: str,
    area_name: str,
    records_collected: int,
    output_file: str,
    collector_version: str = "1.0",
    method: str = "api",
    notes: str = "",
) -> dict:
    """
    Log a data collection event.

    Args:
        run_id:             Unique identifier for this collection run.
        source_name:        e.g. 'deliveroo', 'google_places', 'fsa'.
        area_name:          e.g. 'Shoreditch'.
        records_collected:  Number of records saved.
        output_file:        Path to the saved raw data file.
        collector_version:  Version of the collector script.
        method:             'api', 'scraping', 'manual', 'download'.
        notes:              Any additional context.

    Returns:
        The lineage entry dict (also written to the log).
    """
    entry = {
        "event_type": "collection",
        "run_id": run_id,
        "timestamp": _now_iso(),
        "agent": f"collector/{source_name}",
        "agent_version": collector_version,
        "source_system": source_name,
        "collection_method": method,
        "area": area_name,
        "records_collected": records_collected,
        "output_file": str(output_file),
        "notes": notes,
    }
    _append_entry(entry)
    print(f"[Lineage] Logged collection: {source_name}/{area_name} "
          f"— {records_collected} records — run {run_id}")
    return entry


def log_transformation(
    run_id: str,
    source_file: str,
    destination_table: str,
    records_in: int,
    records_out: int,
    transformations: list[str],
    notes: str = "",
) -> dict:
    """
    Log a data transformation/processing event.

    Args:
        run_id:             Links to the original collection run.
        source_file:        Path to the input data file.
        destination_table:  Database table or collection written to.
        records_in:         Records read from source.
        records_out:        Records written to destination.
        transformations:    List of transforms applied,
                            e.g. ['geocoded', 'fuzzy_matched', 'normalised'].
        notes:              Any additional context.
    """
    entry = {
        "event_type": "transformation",
        "run_id": run_id,
        "timestamp": _now_iso(),
        "agent": "processing/pipeline",
        "source_file": str(source_file),
        "destination_table": destination_table,
        "records_in": records_in,
        "records_out": records_out,
        "transformations_applied": transformations,
        "notes": notes,
    }
    _append_entry(entry)
    print(f"[Lineage] Logged transformation: {source_file} → {destination_table} "
          f"— {records_in} in, {records_out} out")
    return entry


def create_record_lineage(
    source_name: str,
    collected_at: str = None,
    collector_version: str = "1.0",
    run_id: str = None,
) -> dict:
    """
    Create a _lineage metadata dict to embed in every raw data record.

    This is attached to individual records (not the batch log).
    Enables tracing any single record back to its source.
    """
    return {
        "source": source_name,
        "collected_at": collected_at or _now_iso(),
        "collector_version": collector_version,
        "run_id": run_id or "unknown",
    }


def get_lineage_for_run(run_id: str) -> list[dict]:
    """Retrieve all lineage entries for a given run ID."""
    entries = []
    if not LINEAGE_LOG_PATH.exists():
        return entries
    with open(LINEAGE_LOG_PATH, "r") as f:
        for line in f:
            entry = json.loads(line.strip())
            if entry.get("run_id") == run_id:
                entries.append(entry)
    return entries


def get_full_lineage() -> list[dict]:
    """Retrieve the complete lineage log."""
    if not LINEAGE_LOG_PATH.exists():
        return []
    with open(LINEAGE_LOG_PATH, "r") as f:
        return [json.loads(line.strip()) for line in f if line.strip()]


def print_lineage_summary():
    """Print a human-readable summary of all lineage events."""
    entries = get_full_lineage()
    if not entries:
        print("[Lineage] No entries found.")
        return

    collections = [e for e in entries if e["event_type"] == "collection"]
    transforms = [e for e in entries if e["event_type"] == "transformation"]

    print(f"\n{'='*60}")
    print(f"DATA LINEAGE SUMMARY")
    print(f"{'='*60}")
    print(f"Total events:        {len(entries)}")
    print(f"Collection events:   {len(collections)}")
    print(f"Transform events:    {len(transforms)}")
    print()

    for c in collections:
        print(f"  [{c['timestamp'][:19]}] COLLECTED {c['records_collected']:>4} records "
              f"from {c['source_system']:<20} area={c['area']}")

    for t in transforms:
        print(f"  [{t['timestamp'][:19]}] TRANSFORMED {t['records_in']:>4} → "
              f"{t['records_out']:>4} records → {t['destination_table']}")
        print(f"    Transforms: {', '.join(t['transformations_applied'])}")

    print(f"{'='*60}\n")
