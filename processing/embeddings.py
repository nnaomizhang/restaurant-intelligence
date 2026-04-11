"""
ChromaDB Embeddings
===================
Generates embeddings from restaurant reviews and descriptions
and loads them into ChromaDB for semantic search.

Used by the agent for: "find restaurants similar to X"
"""

import json
from pathlib import Path
from datetime import datetime

import chromadb
from sentence_transformers import SentenceTransformer

from config import PROCESSED_DIR, CHROMA_DB_DIR, CHROMA_COLLECTION_NAME, EMBEDDING_MODEL
from processing.lineage import log_transformation, generate_run_id


def get_chroma_collection():
    """Get or create ChromaDB collection."""
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    return collection


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


def build_document(restaurant: dict) -> str:
    """
    Build a text document from restaurant data for embedding.
    Combines name, type, reviews and other fields into one string.
    """
    parts = []

    name = restaurant.get("name", "")
    if name:
        parts.append(f"Restaurant: {name}")

    neighbourhood = restaurant.get("neighbourhood", "")
    if neighbourhood:
        parts.append(f"Location: {neighbourhood}")

    business_type = restaurant.get("business_type", "")
    if business_type:
        parts.append(f"Type: {business_type}")

    types = restaurant.get("google_types", [])
    if types:
        parts.append(f"Categories: {', '.join(types[:5])}")

    rating = restaurant.get("google_rating")
    if rating:
        parts.append(f"Rating: {rating}/5")

    price_level = restaurant.get("google_price_level")
    if price_level:
        price_str = "£" * price_level
        parts.append(f"Price: {price_str}")

    hygiene = restaurant.get("hygiene_rating")
    if hygiene is not None:
        parts.append(f"Hygiene rating: {hygiene}/5")

    # Add review text
    reviews = restaurant.get("reviews", [])
    for review in reviews[:3]:
        text = review.get("text", "").strip()
        if text and len(text) > 20:
            parts.append(f"Review: {text[:300]}")

    return " | ".join(parts)


def run_embeddings():
    from config import TARGET_AREAS

    print(f"\n{'='*60}")
    print(f"  PHASE 4 — STEP 5: CHROMADB EMBEDDINGS")
    print(f"{'='*60}")

    print(f"  Loading model: {EMBEDDING_MODEL}")
    model = SentenceTransformer(EMBEDDING_MODEL)
    collection = get_chroma_collection()

    print(f"  ChromaDB collection: {CHROMA_COLLECTION_NAME}")
    print(f"  Storage: {CHROMA_DB_DIR}\n")

    total_embedded = 0

    for area in TARGET_AREAS:
        run_id = generate_run_id()
        records = load_processed("master", area["name"])

        if not records:
            print(f"  {area['name']}: no data found")
            continue

        # Only embed records with meaningful content
        embeddable = [
            r for r in records
            if r.get("name") and (r.get("reviews") or r.get("google_rating"))
        ]

        print(f"--- {area['name']} ---")
        print(f"  Records: {len(records)}, embeddable: {len(embeddable)}")

        if not embeddable:
            continue

        # Build documents
        documents = [build_document(r) for r in embeddable]

        # Generate embeddings in batches
        batch_size = 50
        ids = []
        metadatas = []

        for i, r in enumerate(embeddable):
            record_id = (
                r.get("google_place_id")
                or f"{area['name']}_{i}"
            )
            ids.append(str(record_id))
            metadatas.append({
                "name": r.get("name", ""),
                "neighbourhood": r.get("neighbourhood", ""),
                "google_rating": str(r.get("google_rating", "")),
                "hygiene_rating": str(r.get("hygiene_rating", "")),
                "postcode": r.get("postcode", ""),
                "google_place_id": r.get("google_place_id", ""),
            })

        # Embed in batches
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]

            embeddings = model.encode(batch_docs).tolist()

            # Upsert to ChromaDB
            collection.upsert(
                ids=batch_ids,
                documents=batch_docs,
                embeddings=embeddings,
                metadatas=batch_meta,
            )

            print(f"  Embedded batch {i//batch_size + 1}: {len(batch_docs)} records")

        total_embedded += len(embeddable)

        log_transformation(
            run_id=run_id,
            source_file=f"processed/master/{area['name']}",
            destination_table="chromadb/restaurant_reviews",
            records_in=len(records),
            records_out=len(embeddable),
            transformations=["embedded", "loaded_to_chromadb"],
        )

    print(f"\n{'='*60}")
    print(f"  DONE: {total_embedded} records embedded")
    print(f"  ChromaDB total: {collection.count()} documents")
    print(f"{'='*60}\n")

    # Test semantic search
    print("  Testing semantic search...")
    test_query = "good Indian restaurant with high hygiene rating"
    results = collection.query(
        query_texts=[test_query],
        n_results=3,
    )
    print(f"  Query: '{test_query}'")
    for i, (doc, meta) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0]
    )):
        print(f"  {i+1}. {meta['name']} ({meta['neighbourhood']}) — rating: {meta['google_rating']}")


if __name__ == "__main__":
    run_embeddings()