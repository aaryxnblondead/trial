from __future__ import annotations

import argparse
import json
from pathlib import Path

from etl.pipeline import run_ingestion


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 2 ingestion pipeline.")
    parser.add_argument("--config", required=True, help="Path to source config JSON.")
    parser.add_argument("--data-root", default="data", help="Root directory for artifacts and manifests.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    data_root = Path(args.data_root).resolve()
    rows = run_ingestion(config_path=config_path, data_root=data_root)
    print(json.dumps({"ingested_sources": len(rows), "data_root": str(data_root)}, ensure_ascii=True))


if __name__ == "__main__":
    main()

