from datetime import datetime, timezone

def add_lineage(record: dict, source: str, version: str, raw_file_path: str = "") -> dict:
    return {
        **record,
        "lineage": {
            "source_name": source,
            "collection_timestamp": datetime.now(timezone.utc).isoformat(),
            "collector_version": version,
            "raw_file_path": raw_file_path
        }
    }