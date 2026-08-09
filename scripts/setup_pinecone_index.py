"""One-time setup script for Pinecone integrated inference indexing."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from pinecone import Pinecone

BASE_DIR = Path(__file__).resolve().parents[1] / "backend"
KNOWLEDGE_BASE_PATH = BASE_DIR / "knowledge_base.json"
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "sfcollab-knowledge-base")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "__default__")
PINECONE_MODEL = os.getenv("PINECONE_MODEL", "multilingual-e5-large")


def load_knowledge_base() -> list[dict[str, object]]:
    with KNOWLEDGE_BASE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError("PINECONE_API_KEY is not set")

    pc = Pinecone(api_key=api_key)

    index_list = pc.list_indexes()
    index_exists = any(
        getattr(index_info, "name", None) == PINECONE_INDEX_NAME
        for index_info in index_list
    )

    if not index_exists:
        pc.create_index_for_model(
            name=PINECONE_INDEX_NAME,
            cloud="aws",
            region="us-east-1",
            embed={
                "model": PINECONE_MODEL,
                "field_map": {"text": "text"},
            },
        )

    timeout_seconds = 120
    poll_interval_seconds = 2
    deadline = time.time() + timeout_seconds

    while True:
        index_list = pc.list_indexes()
        index_info = next(
            (
                item
                for item in index_list
                if getattr(item, "name", None) == PINECONE_INDEX_NAME
            ),
            None,
        )
        status = getattr(index_info, "status", None) if index_info is not None else None
        is_ready = bool(getattr(status, "ready", False)) if status is not None else False
        if index_info is not None and is_ready:
            break
        if time.time() >= deadline:
            raise TimeoutError(
                f"Timed out waiting for Pinecone index {PINECONE_INDEX_NAME!r} to become ready"
            )
        time.sleep(poll_interval_seconds)

    index = pc.Index(PINECONE_INDEX_NAME)

    knowledge_base = load_knowledge_base()
    records = [
        {
            "_id": item["id"],
            "text": f"{item['title']} {item['content']}",
            "title": item["title"],
            "content": item["content"],
        }
        for item in knowledge_base
    ]

    index.upsert_records(namespace=PINECONE_NAMESPACE, records=records)
    print(f"Upserted {len(records)} records into {PINECONE_INDEX_NAME!r}.")


if __name__ == "__main__":
    main()
