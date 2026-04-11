"""
Agent Logger
============
Logs all agent queries, responses, tool calls and latency.
"""

import logging
import json
from datetime import datetime, timezone
from pathlib import Path

from config import LOGS_DIR

LOGS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOGS_DIR / "agent.log"),
        logging.StreamHandler(),
    ]
)

logger = logging.getLogger("agent")
query_log_path = LOGS_DIR / "queries.jsonl"


def log_query(
    query: str,
    answer: str,
    latency_ms: int,
    validation: dict = None,
    tools_used: list = None,
):
    """Log a query and its response to the query log file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "answer": answer[:500],
        "latency_ms": latency_ms,
        "validation": validation or {},
        "tools_used": tools_used or [],
    }

    with open(query_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    logger.info(f"Query logged: {query[:80]}... ({latency_ms}ms)")