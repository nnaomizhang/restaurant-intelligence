import os
import requests
import json
from dotenv import load_dotenv
from processing.lineage import add_lineage

load_dotenv()

API_KEY = os.getenv("COMPANIES_HOUSE_API_KEY")
BASE_URL = "https://api.company-information.service.gov.uk"

def search_company(restaurant_name: str) -> dict | None:
    url = f"{BASE_URL}/search/companies"
    response = requests.get(
        url,
        params={"q": restaurant_name, "items_per_page": 1},
        auth=(API_KEY, "")
    )

    if response.status_code != 200:
        print(f"Error searching for {restaurant_name}: {response.status_code}")
        return None

    data = response.json()
    items = data.get("items", [])

    if not items:
        return None

    company = items[0]
    record = {
        "restaurant_name": restaurant_name,
        "company_name": company.get("title"),
        "company_number": company.get("company_number"),
        "company_status": company.get("company_status"),
        "date_of_creation": company.get("date_of_creation"),
        "company_type": company.get("company_type"),
        "address": company.get("address", {})
    }

    record = add_lineage(
        record,
        source="companies_house",
        version="1.0",
        raw_file_path=f"data/raw/companies_house_{restaurant_name.lower()}.json"
    )

    return record

def run_from_google_places(neighbourhood: str) -> list[dict]:
    path = f"data/raw/google_places_{neighbourhood.lower()}.json"

    if not os.path.exists(path):
        print(f"File not found: {path} — skipping")
        return []

    with open(path) as f:
        restaurants = json.load(f)

    results = []
    for r in restaurants:
        name = r.get("name")
        print(f"Looking up: {name}")
        company = search_company(name)
        if company:
            results.append(company)

    return results

def save_raw(data: list[dict], neighbourhood: str):
    os.makedirs("data/raw", exist_ok=True)
    path = f"data/raw/companies_house_{neighbourhood.lower()}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} records to {path}")

def run():
    for neighbourhood in ["shoreditch", "peckham", "hackney"]:
        print(f"\nLooking up Companies House data for {neighbourhood}...")
        data = run_from_google_places(neighbourhood)
        save_raw(data, neighbourhood)
        print(f"Found {len(data)} company records for {neighbourhood}")

if __name__ == "__main__":
    run()