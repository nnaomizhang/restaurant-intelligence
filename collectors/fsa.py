"""
Food Standards Agency Collector
===============================
Downloads and parses hygiene ratings from the FSA open data portal.

Data source: https://ratings.food.gov.uk/open-data/en-GB
No API key required. Fully open data.

The FSA publishes XML feeds per local authority containing every
rated food establishment. We download, parse, and filter to
restaurant-type businesses within our target postcodes.
"""

import xml.etree.ElementTree as ET
import requests
from pathlib import Path
from config import RAW_DIR
from collectors.base import BaseCollector


class FSACollector(BaseCollector):

    BASE_URL = "https://ratings.food.gov.uk"
    API_URL = "https://api.ratings.food.gov.uk"
    VERSION = "1.0"

    # Business types we care about (FSA classification)
    RESTAURANT_TYPES = {
        "restaurant/cafe/canteen",
        "takeaway/sandwich shop",
        "pub/bar/nightclub",
    }

    def __init__(self):
        super().__init__(
            source_name="fsa",
            raw_dir=RAW_DIR / "fsa",
            method="download",
        )

    def collect(self, area: dict) -> list[dict]:
        """
        Collect FSA hygiene data for a target area.
        Tries the API first, falls back to XML download, then manual data.
        """
        authority = area.get("local_authority", "")
        postcode_prefix = area.get("postcode_prefix", "")
        self.logger.info(
            f"Collecting FSA data for {authority} "
            f"(filtering to {postcode_prefix})"
        )

        # Try API first (more reliable than XML downloads)
        records = self._collect_via_api(authority)

        # Fallback to XML if API fails
        if not records:
            self.logger.info("API returned no results, trying XML download...")
            records = self._collect_via_xml(authority)

        # Fallback to manual data
        if not records:
            self.logger.info("Falling back to manual data...")
            records = self.load_manual_data(area["name"])

        if not records:
            self.logger.warning(f"No FSA data collected for {authority}")
            return []

        # Filter to restaurant types
        restaurants = [
            r for r in records
            if r.get("business_type", "").lower() in self.RESTAURANT_TYPES
        ]
        self.logger.info(
            f"Filtered {len(records)} establishments → "
            f"{len(restaurants)} restaurant-type businesses"
        )

        # Filter to target postcodes
        if postcode_prefix:
            before = len(restaurants)
            restaurants = [
                r for r in restaurants
                if self._postcode_matches(
                    r.get("postcode", ""), postcode_prefix
                )
            ]
            self.logger.info(
                f"Filtered to {postcode_prefix} postcodes: "
                f"{before} → {len(restaurants)}"
            )

        # Add neighbourhood tag
        for r in restaurants:
            r["neighbourhood"] = area["name"]

        if restaurants:
            self.save_raw(restaurants, area["name"])

        return restaurants

    # ------------------------------------------------------------------
    # API collection (preferred method)
    # ------------------------------------------------------------------

    def _collect_via_api(self, authority_name: str) -> list[dict]:
        """
        Collect data using the FSA JSON API.
        Docs: https://api.ratings.food.gov.uk/help
        """
        records = []

        # First, find the authority ID
        authority_id = self._find_authority_id(authority_name)
        if not authority_id:
            return []

        # Fetch all establishments for this authority
        page = 1
        page_size = 200
        while True:
            url = f"{self.API_URL}/Establishments"
            headers = {
                "x-api-version": "2",
                "accept": "application/json",
            }
            params = {
                "localAuthorityId": authority_id,
                "pageNumber": page,
                "pageSize": page_size,
            }

            try:
                response = requests.get(
                    url, headers=headers, params=params, timeout=30
                )
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as e:
                self.logger.error(f"API request failed: {e}")
                break

            establishments = data.get("establishments", [])
            if not establishments:
                break

            for est in establishments:
                scores = est.get("scores", {})
                record = {
                    "fsa_id": str(est.get("FHRSID", "")),
                    "business_name": est.get("BusinessName", ""),
                    "business_type": est.get("BusinessType", ""),
                    "address": ", ".join(
                        filter(None, [
                            est.get("AddressLine1", ""),
                            est.get("AddressLine2", ""),
                            est.get("AddressLine3", ""),
                        ])
                    ),
                    "postcode": est.get("PostCode", ""),
                    "rating_value": self._parse_rating(
                        est.get("RatingValue", "")
                    ),
                    "rating_date": est.get("RatingDate", ""),
                    "local_authority": est.get(
                        "LocalAuthorityName", ""
                    ),
                    "business_type_id": est.get("BusinessTypeID", ""),
                    "score_hygiene": scores.get("Hygiene"),
                    "score_structural": scores.get("Structural"),
                    "score_management": scores.get(
                        "ConfidenceInManagement"
                    ),
                    "latitude": est.get("geocode", {}).get("latitude"),
                    "longitude": est.get("geocode", {}).get("longitude"),
                }
                records.append(record)

            self.logger.info(
                f"  API page {page}: {len(establishments)} establishments"
            )

            # Check if there are more pages
            meta = data.get("meta", {})
            total_pages = meta.get("totalPages", 1)
            if page >= total_pages:
                break
            page += 1
            self.rate_limit(0.5, 0.2)

        self.logger.info(f"API returned {len(records)} total establishments")
        return records

    def _find_authority_id(self, authority_name: str) -> int | None:
        """Find the FSA local authority ID by name."""
        url = f"{self.API_URL}/Authorities/basic"
        headers = {
            "x-api-version": "2",
            "accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            self.logger.error(f"Failed to fetch authority list: {e}")
            return None

        # Search for matching authority (case-insensitive partial match)
        search = authority_name.lower()
        for auth in data.get("authorities", []):
            name = auth.get("Name", "").lower()
            if search in name or name in search:
                auth_id = auth.get("LocalAuthorityId")
                self.logger.info(
                    f"Found authority: {auth['Name']} (ID: {auth_id})"
                )
                return auth_id

        self.logger.warning(f"Authority not found: {authority_name}")
        return None

    # ------------------------------------------------------------------
    # XML download collection (fallback)
    # ------------------------------------------------------------------

    def _collect_via_xml(self, authority_name: str) -> list[dict]:
        """Download and parse the FSA XML feed for a local authority."""
        formatted = authority_name.replace(" ", "%20")
        url = f"{self.BASE_URL}/OpenDataFiles/FHRS{formatted}en-GB.xml"

        self.logger.info(f"Downloading XML: {url}")

        try:
            response = requests.get(url, timeout=60)
            if response.status_code != 200:
                self.logger.warning(
                    f"XML download failed: HTTP {response.status_code}. "
                    f"Try downloading manually from "
                    f"{self.BASE_URL}/open-data/en-GB"
                )
                return []
        except requests.RequestException as e:
            self.logger.error(f"Download error: {e}")
            return []

        # Save raw XML
        xml_path = self.raw_dir / f"{authority_name.lower().replace(' ', '_')}.xml"
        with open(xml_path, "wb") as f:
            f.write(response.content)
        self.logger.info(f"Saved XML to {xml_path}")

        # Parse
        return self._parse_xml(xml_path)

    def _parse_xml(self, xml_path: Path) -> list[dict]:
        """Parse FSA XML into structured records."""
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError as e:
            self.logger.error(f"XML parse error: {e}")
            return []

        root = tree.getroot()
        records = []

        for est in root.findall(".//EstablishmentDetail"):
            record = {
                "fsa_id": self._xml_text(est, "FHRSID"),
                "business_name": self._xml_text(est, "BusinessName"),
                "business_type": self._xml_text(est, "BusinessType"),
                "address": ", ".join(
                    filter(None, [
                        self._xml_text(est, "AddressLine1"),
                        self._xml_text(est, "AddressLine2"),
                        self._xml_text(est, "AddressLine3"),
                    ])
                ),
                "postcode": self._xml_text(est, "PostCode"),
                "rating_value": self._parse_rating(
                    self._xml_text(est, "RatingValue")
                ),
                "rating_date": self._xml_text(est, "RatingDate"),
                "local_authority": self._xml_text(
                    est, "LocalAuthorityName"
                ),
                "score_hygiene": self._xml_text(est, "Scores/Hygiene"),
                "score_structural": self._xml_text(
                    est, "Scores/Structural"
                ),
                "score_management": self._xml_text(
                    est, "Scores/ConfidenceInManagement"
                ),
                "latitude": self._xml_text(est, "Geocode/Latitude"),
                "longitude": self._xml_text(est, "Geocode/Longitude"),
            }
            records.append(record)

        return records

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _xml_text(element: ET.Element, path: str) -> str | None:
        """Safely extract text from an XML element."""
        node = element.find(path)
        return node.text.strip() if node is not None and node.text else None

    @staticmethod
    def _parse_rating(value) -> int | None:
        """Parse rating value — handles 'Exempt', 'AwaitingInspection', etc."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None  # Non-numeric ratings (Exempt, etc.)

    @staticmethod
    def _postcode_matches(postcode: str, prefix: str) -> bool:
        """Check if a postcode starts with the given prefix."""
        if not postcode or not prefix:
            return False
        return postcode.upper().startswith(prefix.upper())


if __name__ == "__main__":
    from config import TARGET_AREAS

    collector = FSACollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(v) for v in results.values())
    print(f"\nDone. Collected {total} restaurant hygiene records.")
