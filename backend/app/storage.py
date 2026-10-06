from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import UploadedFileRecord

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class FileRegistry:
    """Small local upload registry. Replace with durable storage for multi-instance deployment."""

    def __init__(self, upload_dir: Path, manifest_path: Path) -> None:
        self.upload_dir = upload_dir
        self.manifest_path = manifest_path
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._atomic_write({})

    def register(self, original_name: str, content: bytes, sha256: str) -> UploadedFileRecord:
        upload_id = uuid4().hex
        safe_original = safe_filename(original_name, fallback="reference.pdf")
        stored_name = f"{upload_id}-{safe_original}"
        destination = self.upload_dir / stored_name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(content)
        os.replace(temporary, destination)

        record = UploadedFileRecord(
            upload_id=upload_id,
            original_name=safe_original,
            stored_path=str(destination),
            sha256=sha256,
            size_bytes=len(content),
            uploaded_at=datetime.now(timezone.utc),
        )
        manifest = self._read()
        manifest[upload_id] = record.model_dump(mode="json")
        self._atomic_write(manifest)
        return record

    def get(self, upload_id: str) -> UploadedFileRecord:
        payload = self._read().get(upload_id)
        if payload is None:
            raise KeyError(f"Unknown upload_id: {upload_id}")
        record = UploadedFileRecord.model_validate(payload)
        path = Path(record.stored_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Uploaded PDF is missing: {record.original_name}")
        return record

    def _read(self) -> dict[str, dict]:
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Cannot read upload registry: {self.manifest_path}") from exc

    def _atomic_write(self, payload: dict) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.manifest_path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self.manifest_path)


def safe_filename(value: str, fallback: str = "file") -> str:
    name = Path(value).name.strip()
    name = _SAFE_NAME.sub("-", name).strip(".-")
    return (name or fallback)[:180]
