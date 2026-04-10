"""
Deliveroo Collector
===================
Scrapes restaurant listings and menus from Deliveroo using Selenium.
Falls back to manual JSON data if scraping fails.
Cap: 15 restaurants per area.
"""

import json
import re
import time

from config import RAW_DIR, TARGET_AREAS
from collectors.base import BaseCollector

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class DeliverooCollector(BaseCollector):

    BASE_URL = "https://deliveroo.co.uk"
    VERSION = "2.0"
    MAX_RESTAURANTS_PER_AREA = 15

    BANNED_RETAIL_KEYWORDS = [
        "morrisons", "co-op", "coop", "sainsbury", "tesco",
        "waitrose", "aldi", "lidl", "asda", "whole foods",
        "iceland", "marks and spencer", "m&s", "planet organic",
        "holland and barrett", "bp", "spar", "boots", "superdrug",
        "gopuff", "getir", "gorillas", "one stop", "costcutter",
        "premier", "budgens", "nisa", "off licence", "pharmacy",
        "chemist", "foodhall",
    ]

    BANNED_URL_TERMS = [
        "groceries", "grocery", "shopping",
        "convenience", "pharmacy", "alcohol",
    ]

    PROMO_PHRASES = [
        "delivered by", "minimum order", "delivery fee",
        "allergens", "opening times", "add cutlery",
        "restaurant info", "meal deal", "buy one get one",
        "2 for 1", "% off", "entire menu", "free item",
        "selected items", "offers", "promotion", "promo",
        "20% off", "new customers", "off entire",
    ]

    NON_RESTAURANT_PAGE_SIGNALS = [
        "grocery", "groceries", "supermarket", "pharmacy",
        "chemist", "household essentials", "toiletries",
        "cleaning products", "frozen food", "weekly shop",
    ]

    def __init__(self):
        super().__init__(
            source_name="deliveroo",
            raw_dir=RAW_DIR / "deliveroo",
            method="scraping",
        )
        self.driver = None

    # ------------------------------------------------------------------
    # Main collect method
    # ------------------------------------------------------------------

    def collect(self, area: dict) -> list[dict]:
        slug = area.get("deliveroo_slug", "")
        area_name = area["name"]
        area_slug = area_name.lower().replace(" ", "_").replace("-", "_")

        if SELENIUM_AVAILABLE and slug:
            self.logger.info("Attempting Selenium scraping...")
            try:
                restaurants = self._scrape_area(slug, area_name)
                usable = [
                    r for r in restaurants
                    if r.get("name") and r.get("name") != "Unknown"
                ]
                if usable:
                    self.save_raw(usable, area_name)
                    return usable
                self.logger.warning("Scraping returned no usable results.")
            except Exception as e:
                self.logger.warning(f"Scraping failed: {e}")
            finally:
                self._close_driver()
        elif not SELENIUM_AVAILABLE:
            self.logger.warning(
                "Selenium not installed. Run: pip install selenium webdriver-manager"
            )

        self.logger.info("Falling back to manual data...")
        manual = self.load_manual_data(area_name)
        if manual:
            self.save_raw(manual, area_name)
        else:
            self.logger.warning(
                f"No manual data found. Create: "
                f"{self.raw_dir / f'{area_slug}_manual.json'}"
            )
        return manual

    # ------------------------------------------------------------------
    # Driver setup
    # ------------------------------------------------------------------

    def _get_driver(self):
        if self.driver:
            return self.driver

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--window-size=1440,2200")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        except Exception:
            self.driver = webdriver.Chrome(options=options)

        self.driver.set_page_load_timeout(30)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return self.driver

    def _close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    # ------------------------------------------------------------------
    # Area scraping
    # ------------------------------------------------------------------

    def _scrape_area(self, slug: str, area_name: str) -> list[dict]:
        driver = self._get_driver()
        url = f"{self.BASE_URL}/restaurants/{slug}"
        self.logger.info(f"Loading: {url}")

        driver.get(url)
        self.rate_limit(4, 1)

        self._dismiss_cookies(driver)
        self._scroll_page_slowly(driver, max_scrolls=15)

        listings = self._extract_listings(driver)
        self.logger.info(f"Found {len(listings)} listings before filtering")

        filtered = [l for l in listings if self._is_restaurant_listing(l)]
        filtered = filtered[:self.MAX_RESTAURANTS_PER_AREA]
        self.logger.info(f"Kept {len(filtered)} listings after filtering and cap")

        restaurants = []
        for i, listing in enumerate(filtered, start=1):
            # Restart driver every 5 restaurants to prevent crashes
            if i > 1 and (i - 1) % 5 == 0:
                self.logger.info("Restarting driver to prevent memory issues...")
                self._close_driver()
                self.rate_limit(2, 1)
                driver = self._get_driver()

            restaurant_url = listing.get("url", "")
            if not restaurant_url:
                continue

            menu_data = self._scrape_restaurant_page(driver, restaurant_url)

            if menu_data.get("skip_page"):
                self.logger.info(f"Skipped non-restaurant: {listing.get('name')}")
                continue

            if not listing.get("name") and menu_data.get("name"):
                listing["name"] = menu_data["name"]

            display_name = listing.get("name") or "Unknown"
            self.logger.info(
                f"[{i}/{len(filtered)}] Scraped: {display_name} "
                f"— {len(menu_data.get('menu_items', []))} menu items"
            )

            listing.update(menu_data)
            listing["neighbourhood"] = area_name

            if self._is_restaurant_listing(listing):
                restaurants.append(listing)

            self.rate_limit(2, 1)

        return restaurants

    # ------------------------------------------------------------------
    # Page interactions
    # ------------------------------------------------------------------

    def _dismiss_cookies(self, driver):
        xpaths = [
            "//button[contains(text(), 'Accept')]",
            "//button[contains(text(), 'Accept all')]",
            "//button[contains(text(), 'Allow all')]",
            "//button[contains(text(), 'I agree')]",
        ]
        for xpath in xpaths:
            try:
                btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                btn.click()
                self.rate_limit(1, 0.5)
                return
            except Exception:
                continue

    def _scroll_page_slowly(self, driver, max_scrolls: int = 15):
        """Scroll slowly to trigger lazy loading."""
        scroll_step = 400
        current = 0
        for _ in range(max_scrolls):
            driver.execute_script(f"window.scrollTo(0, {current});")
            self.rate_limit(0.8, 0.3)
            current += scroll_step
            total = driver.execute_script("return document.body.scrollHeight")
            if current >= total:
                break
        driver.execute_script("window.scrollTo(0, 0);")
        self.rate_limit(1, 0.3)

    # ------------------------------------------------------------------
    # Listing extraction
    # ------------------------------------------------------------------

    def _extract_listings(self, driver) -> list[dict]:
        listings = []
        seen_urls = set()

        links = driver.find_elements(By.CSS_SELECTOR, 'a[href*="/menu/"]')

        for link in links:
            try:
                href = (link.get_attribute("href") or "").strip()
                if not href or "/menu/" not in href:
                    continue
                href = href.split("?")[0].rstrip("/")
                if href in seen_urls:
                    continue
                if not self._looks_like_valid_restaurant_url(href):
                    continue
                seen_urls.add(href)
                listings.append({
                    "name": None,
                    "url": href,
                    "deliveroo_rating": None,
                    "review_count": None,
                    "cuisine_tags": [],
                })
            except Exception:
                continue

        return listings

    # ------------------------------------------------------------------
    # Restaurant page scraping
    # ------------------------------------------------------------------

    def _scrape_restaurant_page(self, driver, url: str) -> dict:
        result = {
            "name": None,
            "menu_items": [],
            "address": None,
            "postcode": None,
            "delivery_fee": None,
            "min_order": None,
            "estimated_delivery_mins": None,
            "skip_page": False,
        }

        try:
            driver.get(url)
            self.rate_limit(3, 1)

            # Slow scroll to trigger lazy loading
            self._scroll_page_slowly(driver, max_scrolls=12)
            self.rate_limit(2, 0.5)

            # Get page name
            try:
                h1 = driver.find_element(By.TAG_NAME, "h1")
                result["name"] = h1.text.strip()
            except Exception:
                pass

            # Check if grocery/retail
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                if any(s in body_text for s in self.NON_RESTAURANT_PAGE_SIGNALS):
                    result["skip_page"] = True
                    return result
            except Exception:
                body_text = ""

            # Extract menu items
            result["menu_items"] = self._extract_menu_items(driver)

            # Extract postcode
            try:
                postcode_match = re.search(
                r"\b([A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2})\b",
                driver.page_source,
)
                if postcode_match:
                    result["postcode"] = postcode_match.group(1)
            except Exception:
                pass

            # Extract delivery info
            try:
                page_text = driver.find_element(By.TAG_NAME, "body").text

                # Delivery fee — try multiple patterns
                fee_patterns = [
                    r"Delivery fee\s*£(\d+\.?\d*)",
                    r"£(\d+\.?\d*)\s*delivery fee",
                    r"delivery\s*£(\d+\.?\d*)",
                    r"£(0\.\d{2})",
                    r"Delivery\s*·\s*£(\d+\.?\d*)",
                    r"delivery from\s*£(\d+\.?\d*)",
                ]
                for pattern in fee_patterns:
                    fee = re.search(pattern, page_text, re.I)
                    if fee:
                        val = float(fee.group(1))
                        if val <= 5.0:
                            result["delivery_fee"] = val
                            break

                # Free delivery
                if result["delivery_fee"] is None:
                    if re.search(r"free delivery", page_text, re.I):
                        result["delivery_fee"] = 0.0

                # Min order
                min_ord = re.search(
                    r"Min\.?\s*order\s*£(\d+\.?\d*)", page_text, re.I
                )
                if min_ord:
                    result["min_order"] = float(min_ord.group(1))

                # Delivery time — try multiple patterns
                time_patterns = [
                    r"(\d+)\s*[-–]\s*(\d+)\s*min",
                    r"(\d+)\s*to\s*(\d+)\s*min",
                ]
                for pattern in time_patterns:
                    time_match = re.search(pattern, page_text)
                    if time_match:
                        result["estimated_delivery_mins"] = (
                            f"{time_match.group(1)}-{time_match.group(2)}"
                        )
                        break

            except Exception:
                pass

        except (TimeoutException, WebDriverException) as e:
            self.logger.warning(f"Failed to load {url}: {e}")

        return result

    # ------------------------------------------------------------------
    # Menu extraction
    # ------------------------------------------------------------------

    def _extract_menu_items(self, driver) -> list[dict]:
        items = []

        # Try JSON-LD first — most reliable
        json_ld_items = self._extract_menu_from_source(driver.page_source)
        if json_ld_items:
            self.logger.info(f"    JSON-LD extracted {len(json_ld_items)} items")
            return json_ld_items

        # Try CSS selectors
        selectors = [
            '[data-testid="menu-item"]',
            '[data-testid="MenuItem"]',
            '[data-testid*="menuItem"]',
            '[class*="menuItem"]',
            '[class*="MenuItem"]',
            '[class*="menu-item"]',
            '[class*="ItemCard"]',
            'li[class*="item"]',
        ]

        item_elements = []
        for selector in selectors:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                self.logger.info(
                    f"    Selector '{selector}' matched {len(elements)} elements"
                )
                item_elements = elements
                break

        if not item_elements:
            self.logger.info("    No menu elements found with any selector")
            return []

        current_category = "Uncategorised"

        for elem in item_elements:
            try:
                text = (elem.text or "").strip()
                if not text or "£" not in text:
                    continue

                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines or len(lines) > 8:
                    continue

                text_lower = text.lower()

                # Skip promos
                if any(p in text_lower for p in self.PROMO_PHRASES):
                    continue

                name = lines[0].strip()
                if not name or len(name) > 120:
                    continue
                if any(p in name.lower() for p in self.PROMO_PHRASES):
                    continue
                
                # Skip calorie rows
                if re.search(r"^\d+\s*kcal", name, re.I):
                    continue

                # Skip rows where name is just a price
                if re.match(r"^£\d+", name):
                    continue

                # Skip rows where name is a discounted price like "£18.00£20.25"
                if re.match(r"^£[\d.]+£[\d.]+", name):
                    continue

                # Extract price
                price = None
                for line in lines:
                    m = re.search(r"£(\d+(?:\.\d{1,2})?)", line)
                    if m:
                        price = float(m.group(1))
                        break

                if price is None or price == 0:
                    continue

                # Extract description
                description = ""
                for line in lines[1:]:
                    if "£" not in line and len(line) > 3:
                        description = line
                        break

                # Dietary tags
                dietary_tags = []
                if "vegan" in text_lower or "(vg)" in text_lower:
                    dietary_tags.append("vegan")
                if "vegetarian" in text_lower or "(v)" in text_lower:
                    dietary_tags.append("vegetarian")
                if "gluten" in text_lower or "(gf)" in text_lower:
                    dietary_tags.append("gluten-free")
                if "halal" in text_lower:
                    dietary_tags.append("halal")

                items.append({
                    "name": name,
                    "description": description,
                    "price": price,
                    "category": current_category,
                    "is_popular": any(
                        kw in text_lower
                        for kw in ["popular", "top rated", "bestseller"]
                    ),
                    "dietary_tags": dietary_tags,
                })

            except Exception:
                continue

        # Deduplicate
        deduped = []
        seen = set()
        for item in items:
            key = ((item.get("name") or "").lower(), item.get("price"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        
        # Cap at 50 items max per restaurant
        deduped = deduped[:50]

        self.logger.info(f"    CSS extracted {len(deduped)} menu items")
        return deduped

    def _extract_menu_from_source(self, page_source: str) -> list[dict]:
        items = []
        try:
            matches = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                page_source,
                re.DOTALL,
            )
            for match in matches:
                try:
                    data = json.loads(match)
                except json.JSONDecodeError:
                    continue

                if isinstance(data, dict) and "hasMenu" in data:
                    for section in data["hasMenu"].get("hasMenuSection", []):
                        category = section.get("name", "Uncategorised")
                        for item in section.get("hasMenuItem", []):
                            offer = item.get("offers", {})
                            try:
                                price = float(offer.get("price", 0))
                            except (TypeError, ValueError):
                                continue
                            if price == 0:
                                continue
                            items.append({
                                "name": item.get("name", ""),
                                "description": item.get("description", ""),
                                "price": price,
                                "category": category,
                                "is_popular": False,
                                "dietary_tags": [],
                            })
        except Exception:
            pass

        # Deduplicate
        deduped = []
        seen = set()
        for item in items:
            key = ((item.get("name") or "").lower(), item.get("price"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def _normalise_text(self, text: str) -> str:
        text = (text or "").lower()
        text = re.sub(r"[^a-z0-9\s/-]", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _looks_like_valid_restaurant_url(self, url: str) -> bool:
        url = self._normalise_text(url)
        return not any(term in url for term in self.BANNED_URL_TERMS)

    def _is_restaurant_listing(self, record: dict) -> bool:
        name = self._normalise_text(record.get("name") or "")
        url = self._normalise_text(record.get("url") or "")
        text = f"{name} {url}"
        return not any(kw in text for kw in self.BANNED_RETAIL_KEYWORDS)


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

if __name__ == "__main__":
    collector = DeliverooCollector()
    results = collector.collect_all(TARGET_AREAS)
    total = sum(len(v) for v in results.values())
    print(f"\nDone. Collected {total} restaurants across {len(results)} areas.")