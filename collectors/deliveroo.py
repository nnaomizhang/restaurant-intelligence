"""
Deliveroo Collector
===================
Scrapes restaurant listings and full menus from Deliveroo.

Approach (in priority order):
  1. Selenium headless browser — renders the React SPA, parses the DOM
  2. Manual JSON fallback — load pre-collected data from *_manual.json

Deliveroo is a React SPA: plain requests/BeautifulSoup won't work because
the content is rendered client-side. Selenium with headless Chrome is the
most reliable automated approach.

Rate limiting: 2-4 seconds between page loads
"""

import json
import re
from pathlib import Path

from config import RAW_DIR
from collectors.base import BaseCollector

# Selenium imports — wrapped in try/except for environments without it
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import (
        TimeoutException,
        NoSuchElementException,
        WebDriverException,
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class DeliverooCollector(BaseCollector):

    BASE_URL = "https://deliveroo.co.uk"
    VERSION = "1.0"

    def __init__(self):
        super().__init__(
            source_name="deliveroo",
            raw_dir=RAW_DIR / "deliveroo",
            method="scraping",
        )
        self.driver = None

    def collect(self, area: dict) -> list[dict]:
        """
        Collect restaurant and menu data for a target area.
        Tries Selenium first, falls back to manual data.
        """
        slug = area.get("deliveroo_slug", "")

        # Try automated scraping first
        if SELENIUM_AVAILABLE and slug:
            self.logger.info("Attempting Selenium scraping...")
            try:
                restaurants = self._scrape_area(slug, area["name"])
                if restaurants:
                    self.save_raw(restaurants, area["name"])
                    return restaurants
                self.logger.warning("Scraping returned no results.")
            except Exception as e:
                self.logger.warning(f"Scraping failed: {e}")
            finally:
                self._close_driver()
        elif not SELENIUM_AVAILABLE:
            self.logger.warning(
                "Selenium not installed. pip install selenium. "
                "Also need Chrome + chromedriver."
            )

        # Fallback to manual data
        self.logger.info("Falling back to manual data...")
        manual = self.load_manual_data(area["name"])
        if manual:
            self.save_raw(manual, area["name"])
        else:
            self.logger.warning(
                f"No manual data found. Create: "
                f"{self.raw_dir / (area['name'].lower() + '_manual.json')}"
            )
            self._print_manual_template()
        return manual

    # ------------------------------------------------------------------
    # Selenium scraping methods
    # ------------------------------------------------------------------

    def _get_driver(self):
        """Create a headless Chrome Selenium driver."""
        if self.driver:
            return self.driver

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self.driver = webdriver.Chrome(options=options)
        self.driver.set_page_load_timeout(30)
        return self.driver

    def _close_driver(self):
        """Safely close the Selenium driver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def _scrape_area(self, slug: str, area_name: str) -> list[dict]:
        """Scrape all restaurant listings for an area, then each menu."""
        driver = self._get_driver()
        url = f"{self.BASE_URL}/restaurants/{slug}"
        self.logger.info(f"Loading: {url}")

        driver.get(url)
        self.rate_limit(3, 1)

        # Handle cookie consent popup if present
        self._dismiss_cookies(driver)

        # Scroll down to load all restaurants (lazy loading)
        self._scroll_to_bottom(driver)

        # Extract restaurant cards from the listing page
        listings = self._extract_listings(driver)
        self.logger.info(f"Found {len(listings)} restaurant listings")

        # Fetch full menu for each restaurant
        restaurants = []
        for i, listing in enumerate(listings):
            restaurant_url = listing.get("url", "")
            if not restaurant_url:
                continue

            self.logger.info(
                f"  [{i+1}/{len(listings)}] Scraping menu: {listing.get('name', '?')}"
            )

            menu_data = self._scrape_restaurant_page(driver, restaurant_url)
            listing.update(menu_data)
            listing["neighbourhood"] = area_name
            restaurants.append(listing)

            self.rate_limit(2, 2)  # 2-4 second delay between pages

        return restaurants

    def _dismiss_cookies(self, driver):
        """Click cookie consent button if present."""
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(text(), 'Accept')]")
                )
            )
            cookie_btn.click()
            self.rate_limit(1, 0.5)
        except (TimeoutException, NoSuchElementException):
            pass  # No cookie popup — continue

    def _scroll_to_bottom(self, driver, max_scrolls: int = 15):
        """Scroll the page to trigger lazy-loading of all restaurant cards."""
        last_height = driver.execute_script("return document.body.scrollHeight")
        for scroll in range(max_scrolls):
            driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            self.rate_limit(1.5, 0.5)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                self.logger.info(f"  Finished scrolling after {scroll+1} scrolls")
                break
            last_height = new_height

    def _extract_listings(self, driver) -> list[dict]:
        """
        Extract restaurant cards from the listings page.

        Note: Deliveroo's HTML structure changes frequently.
        These selectors may need updating. Check the actual DOM
        using browser DevTools (Inspect Element) and update the
        CSS selectors / XPaths accordingly.
        """
        listings = []

        # Try common patterns for restaurant cards
        # Pattern 1: anchor tags with restaurant links
        links = driver.find_elements(
            By.CSS_SELECTOR, 'a[href*="/menu/"]'
        )

        seen_urls = set()
        for link in links:
            try:
                href = link.get_attribute("href") or ""
                if "/menu/" not in href or href in seen_urls:
                    continue
                seen_urls.add(href)

                # Extract text content from the card
                card_text = link.text.strip()
                lines = [l.strip() for l in card_text.split("\n") if l.strip()]

                name = lines[0] if lines else "Unknown"

                # Try to extract rating and other info from card text
                rating = None
                cuisine_tags = []
                for line in lines[1:]:
                    # Look for rating pattern like "4.6"
                    rating_match = re.search(r"(\d\.\d)", line)
                    if rating_match and not rating:
                        rating = float(rating_match.group(1))
                    # Look for cuisine tags (usually comma-separated)
                    elif "," in line and not any(c.isdigit() for c in line[:3]):
                        cuisine_tags = [t.strip() for t in line.split(",")]

                listings.append({
                    "name": name,
                    "url": href,
                    "deliveroo_rating": rating,
                    "cuisine_tags": cuisine_tags,
                })
            except Exception:
                continue

        return listings

    def _scrape_restaurant_page(self, driver, url: str) -> dict:
        """
        Scrape a single restaurant page for menu items and details.
        Returns dict with menu_items, operating_hours, address, etc.
        """
        result = {
            "menu_items": [],
            "address": None,
            "postcode": None,
            "delivery_fee": None,
            "min_order": None,
            "estimated_delivery_mins": None,
            "operating_hours": None,
        }

        try:
            driver.get(url)
            self.rate_limit(2, 1)

            # Extract menu items
            result["menu_items"] = self._extract_menu_items(driver)

            # Try to extract address from page
            try:
                # Look for address in meta tags or structured data
                page_source = driver.page_source
                # Try to find postcode pattern in page source
                postcode_match = re.search(
                    r"([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})", page_source
                )
                if postcode_match:
                    result["postcode"] = postcode_match.group(1)
            except Exception:
                pass

            # Try to extract delivery info
            try:
                page_text = driver.find_element(By.TAG_NAME, "body").text
                fee_match = re.search(r"£(\d+\.?\d*)\s*delivery", page_text, re.I)
                if fee_match:
                    result["delivery_fee"] = float(fee_match.group(1))
                min_match = re.search(r"Min\.?\s*order\s*£(\d+\.?\d*)", page_text, re.I)
                if min_match:
                    result["min_order"] = float(min_match.group(1))
                time_match = re.search(r"(\d+)\s*[-–]\s*(\d+)\s*min", page_text)
                if time_match:
                    result["estimated_delivery_mins"] = (
                        f"{time_match.group(1)}-{time_match.group(2)}"
                    )
            except Exception:
                pass

        except (TimeoutException, WebDriverException) as e:
            self.logger.warning(f"Failed to load {url}: {e}")

        return result

    def _extract_menu_items(self, driver) -> list[dict]:
        """
        Extract menu items from a restaurant page.

        Deliveroo structures menus in sections (Starters, Mains, etc.)
        with items inside each. The DOM structure changes frequently —
        update selectors as needed.
        """
        items = []

        try:
            # Wait for menu content to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "main"))
            )

            # Strategy: find all elements that look like menu item cards
            # Look for price patterns to identify menu items
            page_text = driver.page_source

            # Find menu sections and items using common structural patterns
            # Deliveroo typically uses data-testid attributes
            item_elements = driver.find_elements(
                By.CSS_SELECTOR,
                '[data-testid*="menu-item"], '
                '[class*="MenuItem"], '
                '[class*="menu-item"]'
            )

            if not item_elements:
                # Fallback: parse structured data from page source
                items = self._extract_menu_from_source(page_text)
                return items

            current_category = "Uncategorised"
            for elem in item_elements:
                try:
                    text = elem.text.strip()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]
                    if not lines:
                        continue

                    # Extract price — look for £X.XX pattern
                    price = None
                    name = lines[0]
                    description = ""
                    for line in lines:
                        price_match = re.search(r"£(\d+\.?\d*)", line)
                        if price_match:
                            price = float(price_match.group(1))
                            break

                    if len(lines) > 1:
                        # Second line is usually description
                        desc_line = lines[1]
                        if not re.match(r"^£", desc_line):
                            description = desc_line

                    # Detect popularity badge
                    is_popular = any(
                        kw in text.lower()
                        for kw in ["popular", "top rated", "bestseller"]
                    )

                    # Detect dietary tags
                    dietary_tags = []
                    text_lower = text.lower()
                    if "vegan" in text_lower or "(vg)" in text_lower:
                        dietary_tags.append("vegan")
                    if "vegetarian" in text_lower or "(v)" in text_lower:
                        dietary_tags.append("vegetarian")
                    if "gluten" in text_lower or "(gf)" in text_lower:
                        dietary_tags.append("gluten-free")
                    if "halal" in text_lower:
                        dietary_tags.append("halal")

                    if price is not None:
                        items.append({
                            "name": name,
                            "description": description,
                            "price": price,
                            "category": current_category,
                            "is_popular": is_popular,
                            "dietary_tags": dietary_tags,
                        })
                except Exception:
                    continue

        except TimeoutException:
            self.logger.warning("Menu content didn't load in time")

        self.logger.info(f"    Extracted {len(items)} menu items")
        return items

    def _extract_menu_from_source(self, page_source: str) -> list[dict]:
        """
        Fallback: extract menu data from page source / JSON-LD.
        Deliveroo sometimes embeds menu data in script tags.
        """
        items = []
        try:
            # Look for JSON-LD structured data
            json_ld_match = re.search(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                page_source,
                re.DOTALL,
            )
            if json_ld_match:
                data = json.loads(json_ld_match.group(1))
                if isinstance(data, dict) and "hasMenu" in data:
                    menu = data["hasMenu"]
                    for section in menu.get("hasMenuSection", []):
                        category = section.get("name", "Uncategorised")
                        for item in section.get("hasMenuItem", []):
                            offer = item.get("offers", {})
                            price_str = offer.get("price", "0")
                            items.append({
                                "name": item.get("name", ""),
                                "description": item.get("description", ""),
                                "price": float(price_str),
                                "category": category,
                                "is_popular": False,
                                "dietary_tags": [],
                            })
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

        return items

    # ------------------------------------------------------------------
    # Manual data template
    # ------------------------------------------------------------------

    def _print_manual_template(self):
        """Print a JSON template for manual data collection."""
        template = [
            {
                "name": "Example Restaurant",
                "cuisine_tags": ["Japanese", "Sushi", "Asian"],
                "address": "123 High Street, London E1 6AB",
                "postcode": "E1 6AB",
                "deliveroo_rating": 4.6,
                "review_count": 234,
                "delivery_fee": 1.49,
                "min_order": 10.00,
                "estimated_delivery_mins": "25-35",
                "operating_hours": "11:00-22:30",
                "url": "https://deliveroo.co.uk/menu/london/shoreditch/example",
                "menu_items": [
                    {
                        "name": "Chicken Katsu Curry",
                        "description": "Crispy panko chicken with curry sauce and rice",
                        "price": 12.50,
                        "category": "Mains",
                        "is_popular": True,
                        "dietary_tags": [],
                    },
                    {
                        "name": "Vegetable Gyoza (6 pcs)",
                        "description": "Pan-fried dumplings with dipping sauce",
                        "price": 6.50,
                        "category": "Starters",
                        "is_popular": False,
                        "dietary_tags": ["vegan"],
                    },
                ],
            }
        ]
        self.logger.info(
            "Save your manual data in this format:\n"
            + json.dumps(template, indent=2)
        )


if __name__ == "__main__":
    from config import TARGET_AREAS

    collector = DeliverooCollector()
    results = collector.collect_all(TARGET_AREAS)

    total = sum(len(v) for v in results.values())
    print(f"\nDone. Collected {total} restaurants across {len(results)} areas.")
