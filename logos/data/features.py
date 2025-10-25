from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from core.io.dirs import ensure_dir

from ..paths import safe_slug
from .contracts import DataContract

__all__ = ["FeatureStore", "FeatureVersion"]


def _stable_json(payload: Mapping[str, Any] | Sequence[Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash_frame(frame: pd.DataFrame) -> str:
    ordered = frame.sort_index()
    if isinstance(ordered.columns, pd.MultiIndex):
        ordered = ordered.copy()
        ordered.columns = ["__".join(map(str, col)) for col in ordered.columns]
    csv = ordered.to_csv(index=True, float_format="%.10f")
    return hashlib.sha256(csv.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FeatureVersion:
    name: str
    version: str
    path: Path
    metadata_path: Path


class FeatureStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else Path("data/features")

    def _target_dir(self, name: str, version: str) -> Path:
        slug = safe_slug(name)
        path = self.root / slug / version
        ensure_dir(path)
        return path

    def register(
        self,
        name: str,
        frame: pd.DataFrame,
        *,
        contract: DataContract | None = None,
        params: Mapping[str, Any] | None = None,
        code_hash: str,
        sources: Iterable[str] | None = None,
    ) -> FeatureVersion:
        if frame.empty:
            raise ValueError("feature frame is empty")
        payload = frame.copy()
        if contract is not None:
            contract.validate(payload)
        data_hash = _hash_frame(payload)
        lineage = {
            "data_hash": data_hash,
            "code_hash": code_hash,
            "params": dict(params or {}),
            "sources": sorted({str(item) for item in sources or []}),
        }
        fingerprint = hashlib.sha256()
        fingerprint.update(data_hash.encode("utf-8"))
        fingerprint.update(code_hash.encode("utf-8"))
        fingerprint.update(_stable_json(lineage["params"]).encode("utf-8"))
        fingerprint.update(_stable_json(lineage["sources"]).encode("utf-8"))
        version = fingerprint.hexdigest()[:16]
        target = self._target_dir(name, version)
        data_path = target / "features.csv"
        meta_path = target / "metadata.json"
        payload.to_csv(data_path, index=True)
        metadata = {
            "name": name,
            "version": version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "rows": int(len(payload)),
            "columns": list(payload.columns),
            **lineage,
        }
        meta_path.write_text(_stable_json(metadata), encoding="utf-8")
        return FeatureVersion(
            name=name, version=version, path=data_path, metadata_path=meta_path
        )

    def load(
        self, name: str, version: str | None = None
    ) -> tuple[pd.DataFrame, dict[str, Any]]:
        target_dir = self._resolve_version_dir(name, version)
        data_path = target_dir / "features.csv"
        meta_path = target_dir / "metadata.json"
        if not data_path.exists() or not meta_path.exists():
            raise FileNotFoundError("feature artefacts missing")
        frame = pd.read_csv(data_path, index_col=0, parse_dates=True)
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        return frame, metadata

    def latest_version(self, name: str) -> FeatureVersion:
        dir_path = self._resolve_version_dir(name, None)
        data_path = dir_path / "features.csv"
        meta_path = dir_path / "metadata.json"
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        return FeatureVersion(
            name=name,
            version=metadata["version"],
            path=data_path,
            metadata_path=meta_path,
        )

    def _resolve_version_dir(self, name: str, version: str | None) -> Path:
        slug = safe_slug(name)
        base = self.root / slug
        if not base.exists() or not any(base.iterdir()):
            raise FileNotFoundError(f"no versions registered for '{name}'")
        if version is not None:
            target = base / version
            if not target.exists():
                raise FileNotFoundError(f"unknown version '{version}' for '{name}'")
            return target
        candidates: list[tuple[datetime, Path]] = []
        for path in base.iterdir():
            if not path.is_dir():
                continue
            meta = path / "metadata.json"
            if not meta.exists():
                continue
            try:
                payload = json.loads(meta.read_text(encoding="utf-8"))
                created = datetime.fromisoformat(payload.get("created_at"))
            except Exception:
                continue
            candidates.append((created, path))
        if not candidates:
            raise FileNotFoundError(f"no valid metadata for '{name}'")
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
