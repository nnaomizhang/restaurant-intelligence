"""
Google Places API Collector
===========================
Fetches restaurant listings, details, and reviews for target areas.

API docs: https://developers.google.com/maps/documentation/places/web-service

Endpoints used:
  - Nearby Search:  find restaurants within radius
  - Place Details:  full info + reviews per restaurant

Rate limits: 100 requests/second
"""

import requests
from collectors.config import GOOGLE_PLACES_API_KEY, RAW_DIR
from collectors.base import BaseCollector


class GooglePlacesCollector(BaseCollector):

    BASE_URL = "https://maps.googleapis.com/maps/api/place"
    VERSION = "1.0"

    # Fields to request from Place Details (controls cost per call)
    DETAIL_FIELDS = [
        "place_id",
        "name",
        "formatted_address",
        "geometry",
        "rating",
        "user_ratings_total",
        "price_level",
        "opening_hours",
        "types",
        "reviews",
        "business_status",
        "formatted_phone_number",
        "website",
    ]

    def __init__(self):
        super().__init__(
            source_name="google_places",
            raw_dir=RAW_DIR / "google_places",
            method="api",
        )
        self.api_key = GOOGLE_PLACES_API_KEY
        if not self.api_key:
            self.logger.warning(
                "GOOGLE_PLACES_API_KEY not set. "
                "Set it in .env or collection will fail."
            )

    def collect(self, area: dict) -> list[dict]:
        """Collect restaurant data for one target area."""
        self.logger.info(f"Searching restaurants near {area['name']} "
                         f"({area['lat']}, {area['lng']}) r={area['radius_km']}km")

        # Step 1: Discover restaurants via Nearby Search
        raw_listings = self._nearby_search(
            lat=area["lat"],
            lng=area["lng"],
            radius_km=area["radius_km"],
        )
        self.logger.info(f"Nearby Search found {len(raw_listings)} restaurants")

        # Step 2: Fetch full details + reviews for each
        detailed_restaurants = []
        for i, listing in enumerate(raw_listings):
            place_id = listing.get("place_id")
            name = listing.get("name", "Unknown")
            self.logger.info(
                f"  [{i+1}/{len(raw_listings)}] Fetching details: {name}"
            )

            details = self._place_details(place_id)
            if details:
                details["neighbourhood"] = area["name"]
                detailed_restaurants.append(details)

            # Respect rate limits (0.5s base + jitter)
            self.rate_limit(0.3, 0.2)

        self.logger.info(
            f"Successfully fetched details for "
            f"{len(detailed_restaurants)}/{len(raw_listings)} restaurants"
        )

        # Step 3: Save raw data with lineage
        if detailed_restaurants:
            self.save_raw(detailed_restaurants, area["name"])

        return detailed_restaurants

    # ------------------------------------------------------------------
    # Private API methods
    # ------------------------------------------------------------------

    def _nearby_search(self, lat: float, lng: float, radius_km: float) -> list[dict]:
        """
        Find restaurants near a location using Nearby Search.
        Handles pagination (max 3 pages = 60 results).
        """
        restaurants = []
        radius_m = int(radius_km * 1000)

        url = f"{self.BASE_URL}/nearbysearch/json"
        params = {
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "type": "restaurant",
            "key": self.api_key,
        }

        page = 1
        while True:
            self.logger.info(f"  Nearby Search page {page}...")
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status == "REQUEST_DENIED":
                self.logger.error(
                    f"API request denied: {data.get('error_message', '')}. "
                    f"Check your API key."
                )
                break
            elif status == "ZERO_RESULTS":
                self.logger.warning("No results found for this location/radius.")
                break
            elif status != "OK":
                self.logger.warning(f"Unexpected API status: {status}")
                break

            results = data.get("results", [])
            restaurants.extend(results)
            self.logger.info(f"  Page {page}: {len(results)} results")

            # Handle pagination — Google requires ~2s delay before next page
            next_token = data.get("next_page_token")
            if next_token and page < 3:
                page += 1
                self.rate_limit(2.0, 0.5)  # Google requires delay for page tokens
                params = {"pagetoken": next_token, "key": self.api_key}
            else:
                break

        return restaurants

    def _place_details(self, place_id: str) -> dict | None:
        """
        Fetch full details and reviews for a single restaurant.
        Returns structured dict matching our schema, or None on failure.
        """
        url = f"{self.BASE_URL}/details/json"
        params = {
            "place_id": place_id,
            "fields": ",".join(self.DETAIL_FIELDS),
            "key": self.api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            self.logger.error(f"Request failed for {place_id}: {e}")
            return None

        if data.get("status") != "OK":
            self.logger.warning(
                f"Details failed for {place_id}: {data.get('status')}"
            )
            return None

        result = data["result"]
        location = result.get("geometry", {}).get("location", {})

        # Structure reviews
        reviews = []
        for r in result.get("reviews", []):
            reviews.append({
                "text": r.get("text", ""),
                "rating": r.get("rating"),
                "date": r.get("relative_time_description", ""),
                "time": r.get("time"),  # Unix timestamp
                "author_name": r.get("author_name", "Anonymous"),
                "language": r.get("language", "en"),
            })

        return {
            "google_place_id": result.get("place_id"),
            "name": result.get("name"),
            "address": result.get("formatted_address"),
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
            "rating": result.get("rating"),
            "review_count": result.get("user_ratings_total"),
            "price_level": result.get("price_level"),
            "business_status": result.get("business_status"),
            "phone": result.get("formatted_phone_number"),
            "website": result.get("website"),
            "opening_hours": result.get("opening_hours", {}).get(
                "weekday_text", []
            ),
            "types": result.get("types", []),
            "reviews": reviews,
        }


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------
if __name__ == "__main__":
    from collectors.config import TARGET_AREAS

    collector = GooglePlacesCollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(v) for v in results.values())
    print(f"\nDone. Collected {total} restaurants across {len(results)} areas.")


    