import xml.etree.ElementTree as ET
import json
import os
from processing.lineage import add_lineage

VALID_TYPES = [
    "Restaurant/Cafe/Canteen",
    "Takeaway/sandwich shop"
]

def parse_fsa_xml(filepath: str, neighbourhood: str) -> list[dict]:
    tree = ET.parse(filepath)
    root = tree.getroot()

    restaurants = []
    skipped = 0

    for est in root.findall(".//EstablishmentDetail"):
        business_type = est.findtext("BusinessType")

        if business_type not in VALID_TYPES:
            skipped += 1
            continue

        record = {
            "name": est.findtext("BusinessName"),
            "address": est.findtext("AddressLine1"),
            "postcode": est.findtext("PostCode"),
            "hygiene_rating": est.findtext("RatingValue"),
            "rating_date": est.findtext("RatingDate"),
            "business_type": business_type,
            "neighbourhood": neighbourhood
        }
        record = add_lineage(
            record,
            source="fsa",
            version="1.0",
            raw_file_path=filepath
        )
        restaurants.append(record)

    print(f"Kept {len(restaurants)} records, skipped {skipped} non-food businesses")
    return restaurants

def save_raw(data: list[dict], neighbourhood: str):
    os.makedirs("data/raw", exist_ok=True)
    path = f"data/raw/fsa_{neighbourhood.lower()}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} records to {path}")

def run():
    sources = [
        ("data/raw/hackney.xml", "Hackney"),
        ("data/raw/tower_hamlets.xml", "Shoreditch"),
        ("data/raw/southwark.xml", "Peckham")
    ]

    for filepath, neighbourhood in sources:
        if not os.path.exists(filepath):
            print(f"File not found: {filepath} — skipping")
            continue
        print(f"Parsing FSA data for {neighbourhood}...")
        data = parse_fsa_xml(filepath, neighbourhood)
        save_raw(data, neighbourhood)
        print(f"Found {len(data)} establishments in {neighbourhood}")

if __name__ == "__main__":
    run()