"""
Base Collector
==============
Abstract base class for all data source collectors.
Handles: rate limiting, raw data saving, lineage tracking, and logging.
All six collectors inherit from this.
"""

import json
import time
import random
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime, timezone

from processing.lineage import (
    generate_run_id,
    log_collection,
    create_record_lineage,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    VERSION = "1.0"

    def __init__(self, source_name: str, raw_dir: Path, method: str = "api"):
        self.source_name = source_name
        self.raw_dir = raw_dir
        self.method = method
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(source_name)
        self.run_id = generate_run_id()

    @abstractmethod
    def collect(self, area: dict) -> list[dict]:
        """
        Collect data for a given target area.

        Args:
            area: dict from TARGET_AREAS with keys:
                  name, postcode_prefix, lat, lng, radius_km,
                  local_authority, deliveroo_slug

        Returns:
            List of collected records as dicts.
        """
        pass

    def save_raw(self, data: list[dict], area_name: str) -> Path:
        """
        Save raw collected data as timestamped JSON.
        Attaches lineage metadata to every record and logs the collection event.
        """
        # Attach lineage metadata to each record
        collected_at = datetime.now(timezone.utc).isoformat()
        for record in data:
            record["_lineage"] = create_record_lineage(
                source_name=self.source_name,
                collected_at=collected_at,
                collector_version=self.VERSION,
                run_id=self.run_id,
            )

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = area_name.lower().replace(" ", "_").replace("-", "_")
        filename = f"{slug}_{timestamp}.json"
        filepath = self.raw_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

        # Log lineage event
        log_collection(
            run_id=self.run_id,
            source_name=self.source_name,
            area_name=area_name,
            records_collected=len(data),
            output_file=filepath,
            collector_version=self.VERSION,
            method=self.method,
        )

        self.logger.info(f"Saved {len(data)} records to {filepath}")
        return filepath

    def load_manual_data(self, area_name: str) -> list[dict]:
        """
        Load manually collected data from a _manual.json file.
        Fallback when automated collection isn't possible.
        """
        slug = area_name.lower().replace(" ", "_").replace("-", "_")
        manual_file = self.raw_dir / f"{slug}_manual.json"
        if manual_file.exists():
            with open(manual_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.logger.info(f"Loaded {len(data)} records from manual data: {manual_file}")
            return data
        self.logger.warning(f"No manual data at {manual_file}")
        return []

    def rate_limit(self, base_seconds: float = 1.0, jitter: float = 0.5):
        """Sleep with random jitter to avoid detection and respect rate limits."""
        delay = base_seconds + random.uniform(0, jitter)
        time.sleep(delay)

    def collect_all(self, areas: list[dict]) -> dict[str, list[dict]]:
        """Collect data for all target areas. Returns {area_name: records}."""
        results = {}
        for area in areas:
            self.run_id = generate_run_id()  # fresh run_id per area
            self.logger.info(f"{'='*50}")
            self.logger.info(f"Starting collection for {area['name']}")
            self.logger.info(f"Run ID: {self.run_id}")
            self.logger.info(f"{'='*50}")
            try:
                records = self.collect(area)
                results[area["name"]] = records
                self.logger.info(
                    f"Completed {area['name']}: {len(records)} records"
                )
            except Exception as e:
                self.logger.error(f"Failed for {area['name']}: {e}", exc_info=True)
                results[area["name"]] = []
        return results
