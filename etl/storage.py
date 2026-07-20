from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def write_artifact(raw_root: Path, source_id: str, payload: bytes, extension: str = ".bin") -> Dict[str, Any]:
    retrieved_at = utc_now_iso()
    digest = sha256_bytes(payload)
    date_part = retrieved_at[:10]

    artifact_dir = raw_root / source_id / date_part
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{digest}{extension}"
    artifact_path.write_bytes(payload)

    return {
        "retrieved_at_utc": retrieved_at,
        "sha256": digest,
        "bytes_size": len(payload),
        "artifact_path": str(artifact_path),
    }


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(row, ensure_ascii=True) + "\n")

