"""
Lineage tracking for the Restaurant Intelligence Platform.
Handles run IDs, record-level lineage, and collection event logging.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_run_id() -> str:
    """Generate a unique run ID for each collection run."""
    return str(uuid.uuid4())


def create_record_lineage(
    source_name: str,
    collected_at: str,
    collector_version: str,
    run_id: str,
) -> dict:
    """Attach lineage metadata to a single record."""
    return {
        "source_name": source_name,
        "collected_at": collected_at,
        "collector_version": collector_version,
        "run_id": run_id,
    }


def log_collection(
    run_id: str,
    source_name: str,
    area_name: str,
    records_collected: int,
    output_file: Path,
    collector_version: str,
    method: str,
) -> None:
    """Log a collection event to the lineage log file."""
    from collectors.config import LOGS_DIR

    log_entry = {
        "run_id": run_id,
        "source_name": source_name,
        "area_name": area_name,
        "records_collected": records_collected,
        "output_file": str(output_file),
        "collector_version": collector_version,
        "method": method,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log_path = LOGS_DIR / "lineage_log.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    logger.info(f"Lineage logged: {source_name} / {area_name} / {records_collected} records")


def add_lineage(record: dict, source: str, version: str, raw_file_path: str = "") -> dict:
    """Legacy function — kept for backwards compatibility."""
    return {
        **record,
        "lineage": {
            "source_name": source,
            "collection_timestamp": datetime.now(timezone.utc).isoformat(),
            "collector_version": version,
            "raw_file_path": raw_file_path,
        }
    }