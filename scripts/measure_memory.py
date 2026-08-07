"""Measure peak memory for the standalone Chroma + fastembed retriever."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

from backend import retrieval_chroma


def _rss_mb() -> float:
    if psutil is not None:
        return psutil.Process().memory_info().rss / (1024 * 1024)

    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


def main() -> None:
    before = _rss_mb()
    print(f"RSS_BEFORE_LOAD_MB={before}")

    _ = retrieval_chroma.load_embedder()
    _ = retrieval_chroma._build_collection()
    after_load = _rss_mb()
    print(f"RSS_AFTER_LOAD_MB={after_load}")

    _ = retrieval_chroma.retrieve("How do I update my profile picture?")
    after_query = _rss_mb()
    print(f"RSS_AFTER_QUERY_MB={after_query}")

    print(f"PEAK_RSS_MB={max(before, after_load, after_query)}")


if __name__ == "__main__":
    main()
