"""
Planning Portal Collector
=========================
Loads planning application data for restaurant/food-use changes.

This is primarily a manual collection task. Search your local
council's planning portal for Class E (food) applications and
save results as CSV or JSON.

Most councils use Idox or Arcus software for planning search:
  - Tower Hamlets: https://development.towerhamlets.gov.uk/online-applications/
  - Southwark:     https://planning.southwark.gov.uk/online-applications/
  - Stratford:     https://apps.stratford.gov.uk/eplanning/

Search tips:
  - Application type: "Change of Use" or "Full Planning"
  - Keywords: "restaurant", "cafe", "takeaway", "Class E", "food"
  - Date range: last 24 months
  - Filter to your target postcode area
"""

import csv
import json
import re
from pathlib import Path
from config import RAW_DIR
from collectors.base import BaseCollector


class PlanningCollector(BaseCollector):

    VERSION = "1.0"

    def __init__(self):
        super().__init__(
            source_name="planning",
            raw_dir=RAW_DIR / "planning",
            method="manual",
        )

    def collect(self, area: dict) -> list[dict]:
        """Load manually collected planning data for a target area."""
        area_name = area["name"]
        slug = area_name.lower().replace(" ", "_").replace("-", "_")
        self.logger.info(f"Loading planning data for {area_name}")

        # Try loading from multiple file formats
        records = (
            self._load_csv(slug, area_name)
            or self._load_json(slug, area_name)
            or self.load_manual_data(area_name)
        )

        if not records:
            self.logger.warning(
                f"No planning data found for {area_name}. "
                f"Create one of:\n"
                f"  {self.raw_dir / f'{slug}_applications.csv'}\n"
                f"  {self.raw_dir / f'{slug}_applications.json'}\n"
                f"  {self.raw_dir / f'{slug}_manual.json'}"
            )
            self._print_csv_template()
            return []

        # Normalise and validate records
        normalised = []
        for r in records:
            normalised.append(self._normalise_record(r, area_name))

        # Filter to food/restaurant applications
        food_records = [
            r for r in normalised
            if self._is_food_application(r)
        ]
        self.logger.info(
            f"Loaded {len(records)} applications, "
            f"{len(food_records)} food-related"
        )

        if food_records:
            self.save_raw(food_records, area_name)

        return food_records

    # ------------------------------------------------------------------
    # File loaders
    # ------------------------------------------------------------------

    def _load_csv(self, slug: str, area_name: str) -> list[dict] | None:
        """Load from CSV file."""
        path = self.raw_dir / f"{slug}_applications.csv"
        if not path.exists():
            return None

        records = []
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(dict(row))

        self.logger.info(f"Loaded {len(records)} records from {path}")
        return records

    def _load_json(self, slug: str, area_name: str) -> list[dict] | None:
        """Load from JSON file."""
        path = self.raw_dir / f"{slug}_applications.json"
        if not path.exists():
            return None

        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)

        self.logger.info(f"Loaded {len(records)} records from {path}")
        return records

    # ------------------------------------------------------------------
    # Normalisation and filtering
    # ------------------------------------------------------------------

    def _normalise_record(self, raw: dict, area_name: str) -> dict:
        """Normalise a planning record to our standard schema."""
        # Handle various column name formats from different CSV exports
        return {
            "reference": (
                raw.get("reference")
                or raw.get("Reference")
                or raw.get("app_ref")
                or raw.get("Application Reference")
                or ""
            ),
            "date_filed": (
                raw.get("date_filed")
                or raw.get("Date Filed")
                or raw.get("date_received")
                or raw.get("Date Received")
                or ""
            ),
            "address": (
                raw.get("address")
                or raw.get("Address")
                or raw.get("site_address")
                or raw.get("Site Address")
                or ""
            ),
            "postcode": (
                raw.get("postcode")
                or raw.get("Postcode")
                or self._extract_postcode(
                    raw.get("address", "")
                    or raw.get("Address", "")
                    or raw.get("site_address", "")
                )
                or ""
            ),
            "application_type": (
                raw.get("application_type")
                or raw.get("Application Type")
                or raw.get("type")
                or ""
            ),
            "proposed_use": (
                raw.get("proposed_use")
                or raw.get("Proposed Use")
                or raw.get("description")
                or raw.get("Description")
                or raw.get("Proposal")
                or ""
            ),
            "decision_status": (
                raw.get("decision_status")
                or raw.get("Decision")
                or raw.get("status")
                or raw.get("Status")
                or ""
            ),
            "decision_date": (
                raw.get("decision_date")
                or raw.get("Decision Date")
                or ""
            ),
            "neighbourhood": area_name,
        }

    def _is_food_application(self, record: dict) -> bool:
        """Check if a planning application is food/restaurant related."""
        # Combine all text fields for keyword search
        text = " ".join([
            record.get("application_type", ""),
            record.get("proposed_use", ""),
        ]).lower()

        food_keywords = [
            "restaurant", "cafe", "coffee", "takeaway", "food",
            "kitchen", "dining", "bar", "pub", "bistro",
            "class e", "class a3", "a3 use", "e class",
            "hot food", "bakery", "pizza", "sushi", "grill",
        ]

        return any(kw in text for kw in food_keywords)

    @staticmethod
    def _extract_postcode(address: str) -> str:
        """Try to extract a UK postcode from an address string."""
        match = re.search(
            r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})", address.upper()
        )
        return match.group(1) if match else ""

    # ------------------------------------------------------------------
    # Template
    # ------------------------------------------------------------------

    def _print_csv_template(self):
        """Print a CSV template for manual data collection."""
        self.logger.info(
            "CSV template (save with these column headers):\n"
            "reference,date_filed,address,postcode,application_type,"
            "proposed_use,decision_status,decision_date\n"
            'PA/25/001,2025-06-15,"45 High St, E1 6AB",E1 6AB,'
            "Class E change of use,Proposed Japanese restaurant and bar,"
            "Granted,2025-09-20"
        )


if __name__ == "__main__":
    from config import TARGET_AREAS

    collector = PlanningCollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(v) for v in results.values())
    print(f"\nDone. Loaded {total} planning applications.")
