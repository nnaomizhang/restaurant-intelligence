"""
Companies House API Collector
=============================
Fetches company data for restaurant businesses in target areas.

API docs: https://developer.company-information.service.gov.uk/
Auth:     HTTP Basic (API key as username, empty password)
Rate:     600 requests / 5 minutes

Key endpoints:
  - /advanced-search/companies — find companies by SIC code + location
  - /company/{number}          — full company profile
  - /company/{number}/filing-history  — detect late filings
  - /company/{number}/officers — detect director turnover
"""

import requests
from requests.auth import HTTPBasicAuth
from config import COMPANIES_HOUSE_API_KEY, RAW_DIR
from collectors.base import BaseCollector


class CompaniesHouseCollector(BaseCollector):

    BASE_URL = "https://api.company-information.service.gov.uk"
    VERSION = "1.0"

    # Keep request volume under control
    MAX_CANDIDATES_PER_AREA = 30
    MIN_RESULTS_BEFORE_SKIP_FALLBACK = 15

    # Restaurant-related SIC codes
    SIC_CODES = {
        "56101": "Licensed restaurants",
        "56102": "Unlicensed restaurants and cafes",
        "56103": "Take-away food shops and mobile food stands",
        "56210": "Event catering activities",
        "56301": "Licensed clubs",
        "56302": "Public houses and bars",
    }

    def __init__(self):
        super().__init__(
            source_name="companies_house",
            raw_dir=RAW_DIR / "companies_house",
            method="api",
        )
        self.auth = HTTPBasicAuth(COMPANIES_HOUSE_API_KEY, "")
        if not COMPANIES_HOUSE_API_KEY:
            self.logger.warning(
                "COMPANIES_HOUSE_API_KEY not set. "
                "Register at developer.company-information.service.gov.uk"
            )

    def collect(self, area: dict) -> list[dict]:
        """Collect company data for restaurant businesses in a target area."""
        self.logger.info(f"Searching restaurant companies near {area['name']}")

        # Step 1: Search for restaurant companies
        companies = self._search_companies(area)
        self.logger.info(f"Found {len(companies)} candidate companies before capping")

        # Cap detail fetching to stay within API budget
        companies = companies[:self.MAX_CANDIDATES_PER_AREA]
        self.logger.info(f"Fetching details for {len(companies)} companies")

        # Step 2: Fetch detailed profiles
        detailed = []
        for i, company in enumerate(companies):
            number = company.get("company_number", "")
            name = company.get("title", company.get("company_name", "?"))
            self.logger.info(f"  [{i+1}/{len(companies)}] {name} ({number})")

            profile = self._get_profile(number)
            if not profile:
                continue

            profile["filing_summary"] = self._get_filing_history(number)
            profile["officers"] = self._get_officers(number)
            profile["neighbourhood"] = area["name"]

            # Calculate distress signals
            profile["distress_signals"] = self._calculate_distress(profile)

            detailed.append(profile)

            # 3 detail requests per company total; keep modest pace
            self.rate_limit(0.5, 0.3)

        self.logger.info(
            f"Fetched details for {len(detailed)}/{len(companies)} companies"
        )

        if detailed:
            self.save_raw(detailed, area["name"])

        return detailed

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    def _search_companies(self, area: dict) -> list[dict]:
        """
        Search for restaurant companies near a target area.

        Strategy:
          1. Advanced search by SIC code and a sequence of broad locations
          2. Filter results locally to the target area
          3. Only use keyword fallback if advanced search is too weak
        """
        companies = []
        seen_numbers = set()

        search_locations = [
            area["name"],
            area.get("local_authority", ""),
            "London",
        ]

        # Strategy 1: advanced search
        for location in search_locations:
            if not location:
                continue

            self.logger.info(f"Trying advanced search location: {location}")

            for sic_code, sic_desc in self.SIC_CODES.items():
                self.logger.info(f"  Searching SIC {sic_code} ({sic_desc}) in {location}...")
                results = self._advanced_search(
                    sic_code=sic_code,
                    location=location,
                )

                for r in results:
                    num = r.get("company_number")
                    if not num or num in seen_numbers:
                        continue

                    if self._address_matches_area(r, area):
                        seen_numbers.add(num)
                        companies.append(r)

                self.rate_limit(0.5, 0.2)

                # Stop early if we already have enough
                if len(companies) >= self.MAX_CANDIDATES_PER_AREA:
                    return companies

            # If advanced search is already good enough, skip fallbacks
            if len(companies) >= self.MIN_RESULTS_BEFORE_SKIP_FALLBACK:
                return companies

        # Strategy 2: keyword search fallback only if needed
        if len(companies) < self.MIN_RESULTS_BEFORE_SKIP_FALLBACK:
            keywords = [
                f"restaurant {area['name']}",
                f"cafe {area['name']}",
                f"food {area['name']}",
                f"restaurant {area.get('local_authority', '')}".strip(),
                "restaurant london",
            ]

            for keyword in keywords:
                if not keyword:
                    continue

                self.logger.info(f"  Keyword search: '{keyword}'")
                results = self._keyword_search(keyword)

                for r in results:
                    num = r.get("company_number")
                    if not num or num in seen_numbers:
                        continue

                    sic = r.get("sic_codes") or []
                    has_restaurant_sic = (not sic) or any(
                        s in self.SIC_CODES for s in sic
                    )

                    if has_restaurant_sic and self._address_matches_area(r, area):
                        seen_numbers.add(num)
                        companies.append(r)

                self.rate_limit(0.5, 0.2)

                if len(companies) >= self.MAX_CANDIDATES_PER_AREA:
                    return companies

        return companies

    def _advanced_search(self, sic_code: str, location: str) -> list[dict]:
        """Search companies by SIC code and location."""
        url = f"{self.BASE_URL}/advanced-search/companies"
        params = {
            "sic_codes": sic_code,
            "location": location,
            "size": 100,
            "status": "active",
        }

        try:
            response = requests.get(
                url, params=params, auth=self.auth, timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("items", [])
            elif response.status_code == 416:
                return []
            else:
                self.logger.warning(
                    f"Advanced search HTTP {response.status_code} for location={location}, sic={sic_code}"
                )
                return []
        except requests.RequestException as e:
            self.logger.error(f"Advanced search failed: {e}")
            return []

    def _keyword_search(self, query: str) -> list[dict]:
        """Search companies by keyword."""
        url = f"{self.BASE_URL}/search/companies"
        params = {"q": query, "items_per_page": 50}

        try:
            response = requests.get(
                url, params=params, auth=self.auth, timeout=15
            )
            if response.status_code == 200:
                return response.json().get("items", [])
            self.logger.warning(f"Keyword search HTTP {response.status_code} for query='{query}'")
            return []
        except requests.RequestException as e:
            self.logger.error(f"Keyword search failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Detail fetching methods
    # ------------------------------------------------------------------

    def _get_profile(self, company_number: str) -> dict | None:
        """Fetch full company profile."""
        url = f"{self.BASE_URL}/company/{company_number}"

        try:
            response = requests.get(url, auth=self.auth, timeout=15)
            if response.status_code != 200:
                return None
            data = response.json()
        except (requests.RequestException, ValueError):
            return None

        accounts = data.get("accounts", {})
        confirmation = data.get("confirmation_statement", {})

        return {
            "company_number": data.get("company_number"),
            "company_name": data.get("company_name"),
            "status": data.get("company_status"),
            "incorporation_date": data.get("date_of_creation"),
            "dissolution_date": data.get("date_of_cessation"),
            "registered_address": self._format_address(
                data.get("registered_office_address", {})
            ),
            "sic_codes": data.get("sic_codes", []),
            "type": data.get("type"),
            "accounts_overdue": accounts.get("overdue", False),
            "accounts_next_due": accounts.get("next_due"),
            "last_accounts_date": accounts.get("last_accounts", {}).get(
                "made_up_to"
            ),
            "confirmation_overdue": confirmation.get("overdue", False),
            "confirmation_next_due": confirmation.get("next_due"),
        }

    def _get_filing_history(self, company_number: str) -> dict:
        """Fetch recent filing history to detect late/missing filings."""
        url = f"{self.BASE_URL}/company/{company_number}/filing-history"
        params = {"items_per_page": 15}

        try:
            response = requests.get(
                url, params=params, auth=self.auth, timeout=15
            )
            if response.status_code != 200:
                return {"total_filings": 0, "recent_filings": []}
            data = response.json()
        except (requests.RequestException, ValueError):
            return {"total_filings": 0, "recent_filings": []}

        filings = [
            {
                "date": item.get("date"),
                "type": item.get("type"),
                "description": item.get("description"),
                "category": item.get("category"),
            }
            for item in data.get("items", [])[:10]
        ]

        return {
            "total_filings": data.get("total_count", 0),
            "recent_filings": filings,
        }

    def _get_officers(self, company_number: str) -> list[dict]:
        """Fetch current and recent officers to detect turnover."""
        url = f"{self.BASE_URL}/company/{company_number}/officers"

        try:
            response = requests.get(url, auth=self.auth, timeout=15)
            if response.status_code != 200:
                return []
            data = response.json()
        except (requests.RequestException, ValueError):
            return []

        return [
            {
                "name": item.get("name"),
                "role": item.get("officer_role"),
                "appointed_on": item.get("appointed_on"),
                "resigned_on": item.get("resigned_on"),
                "nationality": item.get("nationality"),
            }
            for item in data.get("items", [])
        ]

    # ------------------------------------------------------------------
    # Distress signal calculation
    # ------------------------------------------------------------------

    def _calculate_distress(self, profile: dict) -> list[str]:
        """
        Calculate distress signals from company data.
        Returns a list of signal descriptions.
        """
        signals = []

        if profile.get("accounts_overdue"):
            signals.append("Accounts overdue")

        if profile.get("confirmation_overdue"):
            signals.append("Confirmation statement overdue")

        status = (profile.get("status") or "").lower()
        if status in ("dissolved", "liquidation", "administration"):
            signals.append(f"Company status: {status}")

        officers = profile.get("officers", [])
        recent_resignations = sum(1 for o in officers if o.get("resigned_on"))
        if recent_resignations > 2:
            signals.append(
                f"High officer turnover ({recent_resignations} resignations)"
            )

        total_filings = profile.get("filing_summary", {}).get("total_filings", 0)
        if total_filings < 3:
            signals.append(f"Very few filings ({total_filings} total)")

        return signals

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _address_matches_area(self, company: dict, area: dict) -> bool:
        """
        Filter broad search results back down to the target area.
        Uses postcode prefix, area name, and local authority.
        """
        text = " ".join([
            company.get("address_snippet", ""),
            company.get("description", ""),
            company.get("title", ""),
        ]).lower()

        postcode_prefix = area.get("postcode_prefix", "").lower()
        area_name = area.get("name", "").lower()
        local_authority = area.get("local_authority", "").lower()

        return any([
            postcode_prefix and postcode_prefix in text,
            area_name and area_name in text,
            local_authority and local_authority in text,
        ])

    @staticmethod
    def _format_address(addr: dict) -> str:
        """Format a Companies House address dict into a string."""
        parts = [
            addr.get("address_line_1", ""),
            addr.get("address_line_2", ""),
            addr.get("locality", ""),
            addr.get("region", ""),
            addr.get("postal_code", ""),
        ]
        return ", ".join(p for p in parts if p)


if __name__ == "__main__":
    from config import TARGET_AREAS

    collector = CompaniesHouseCollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(v) for v in results.values())
    distressed = sum(
        1
        for area_results in results.values()
        for c in area_results
        if c.get("distress_signals")
    )
    print(f"\nDone. {total} companies, {distressed} with distress signals.")