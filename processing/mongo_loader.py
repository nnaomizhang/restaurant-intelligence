"""
MongoDB Loader
==============
Loads processed data into MongoDB collections.

Collections:
  - google_places    : Google Places records
  - fsa              : FSA hygiene records
  - companies_house  : Companies House records
  - deliveroo        : Deliveroo records
  - ons_census       : ONS census records
  - restaurants      : Master merged records
"""

import json
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient, ASCENDING

from config import DATABASE_URL, MONGO_URL, PROCESSED_DIR
from processing.lineage import log_transformation, generate_run_id


def get_db(uri: str = MONGO_URL, db_name: str = "restaurant_intelligence"):
    client = MongoClient(uri)
    return client[db_name]


def load_processed(source: str, area_name: str) -> list[dict]:
    folder = PROCESSED_DIR / source
    if not folder.exists():
        return []
    slug = area_name.lower().replace(" ", "_").replace("-", "_")
    files = sorted(
        [f for f in folder.glob(f"{slug}*.json")],
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )
    if not files:
        return []
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def upsert_records(collection, records: list[dict], key_field: str) -> dict:
    inserted = 0
    updated = 0

    for record in records:
        record.pop("_id", None)
        key_value = record.get(key_field)

        if not key_value:
            collection.insert_one(record)
            inserted += 1
            continue

        result = collection.update_one(
            {key_field: key_value},
            {"$set": record},
            upsert=True,
        )

        if result.upserted_id:
            inserted += 1
        else:
            updated += 1

    return {"inserted": inserted, "updated": updated}


def create_indexes(collection, key_field: str, extra_fields: list = None):
    """Create indexes without unique constraint conflicts."""
    try:
        if key_field:
            collection.create_index(
                [(key_field, ASCENDING)],
                sparse=True,
                background=True
            )
    except Exception:
        pass

    for field in (extra_fields or []):
        try:
            collection.create_index(
                [(field, ASCENDING)],
                sparse=True,
                background=True
            )
        except Exception:
            pass


def run_mongo_loading(uri: str = MONGO_URL):
    from config import DATABASE_URL, MONGO_URL, TARGET_AREAS

    print(f"\n{'='*60}")
    print(f"  PHASE 4 — STEP 3: MONGODB LOADING")
    print(f"{'='*60}")

    try:
        db = get_db(uri)
        db.command("ping")
        print(f"  Connected to MongoDB\n")
    except Exception as e:
        print(f"  ERROR: Cannot connect to MongoDB: {e}")
        print(f"  Make sure Docker is running: docker-compose up -d mongodb")
        return

    # Drop all existing indexes to avoid conflicts
    for coll_name in ["google_places", "fsa", "companies_house", "deliveroo", "ons_census", "restaurants"]:
        try:
            db[coll_name].drop_indexes()
        except Exception:
            pass

    sources = [
        ("google_places", "google_place_id", ["neighbourhood"]),
        ("fsa", "fsa_id", ["neighbourhood", "postcode"]),
        ("companies_house", "company_number", ["neighbourhood"]),
        ("deliveroo", "name_normalised", ["neighbourhood"]),
        ("ons_census", "lsoa_code", ["neighbourhood"]),
    ]

    total_inserted = 0
    total_updated = 0

    for source, key_field, extra_fields in sources:
        print(f"--- {source} ---")
        collection = db[source]
        create_indexes(collection, key_field, extra_fields)

        for area in TARGET_AREAS:
            run_id = generate_run_id()
            records = load_processed(source, area["name"])

            if not records:
                print(f"  {area['name']}: no data found")
                continue

            result = upsert_records(collection, records, key_field)
            inserted = result["inserted"]
            updated = result["updated"]
            total_inserted += inserted
            total_updated += updated

            print(f"  {area['name']}: {inserted} inserted, {updated} updated")

            log_transformation(
                run_id=run_id,
                source_file=f"processed/{source}/{area['name']}",
                destination_table=f"mongodb/{source}",
                records_in=len(records),
                records_out=inserted + updated,
                transformations=["loaded_to_mongodb"],
            )

    # Load master records
    print(f"\n--- master (restaurants collection) ---")
    collection = db["restaurants"]
    create_indexes(collection, "google_place_id", ["neighbourhood", "postcode"])

    for area in TARGET_AREAS:
        run_id = generate_run_id()
        records = load_processed("master", area["name"])

        if not records:
            print(f"  {area['name']}: no master data found")
            continue

        result = upsert_records(collection, records, "google_place_id")
        inserted = result["inserted"]
        updated = result["updated"]
        total_inserted += inserted
        total_updated += updated

        print(f"  {area['name']}: {inserted} inserted, {updated} updated")

        log_transformation(
            run_id=run_id,
            source_file=f"processed/master/{area['name']}",
            destination_table="mongodb/restaurants",
            records_in=len(records),
            records_out=inserted + updated,
            transformations=["loaded_to_mongodb"],
        )

    print(f"\n{'='*60}")
    print(f"  DONE: {total_inserted} inserted, {total_updated} updated")
    print(f"{'='*60}\n")

    print("  Collection counts:")
    for coll_name in sorted(db.list_collection_names()):
        count = db[coll_name].count_documents({})
        print(f"  {coll_name:<25} {count:>6} documents")


if __name__ == "__main__":
    run_mongo_loading()