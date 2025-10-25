from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from core.io import dirs as core_dirs

from logos.paths import safe_slug


@dataclass(slots=True)
class ModelRecord:
    model_id: str
    strategy: str
    symbol: str
    status: str
    created_at: str
    params: Dict[str, Any]
    metrics: Dict[str, float]
    guard_metrics: Dict[str, float]
    stress_metrics: Dict[str, float]
    note: str = ""
    data_hash: str | None = None
    code_hash: str | None = None
    version: int = 1
    lineage: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "strategy": self.strategy,
            "symbol": self.symbol,
            "status": self.status,
            "created_at": self.created_at,
            "params": dict(self.params),
            "metrics": dict(self.metrics),
            "guard_metrics": dict(self.guard_metrics),
            "stress_metrics": dict(self.stress_metrics),
            "note": self.note,
            "data_hash": self.data_hash,
            "code_hash": self.code_hash,
            "version": self.version,
            "lineage": list(self.lineage),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ModelRecord":
        return cls(
            model_id=str(payload.get("model_id")),
            strategy=str(payload.get("strategy")),
            symbol=str(payload.get("symbol")),
            status=str(payload.get("status", "candidate")),
            created_at=str(payload.get("created_at")),
            params=dict(payload.get("params", {})),
            metrics=dict(payload.get("metrics", {})),
            guard_metrics=dict(payload.get("guard_metrics", {})),
            stress_metrics=dict(payload.get("stress_metrics", {})),
            note=str(payload.get("note", "")),
            data_hash=payload.get("data_hash") or None,
            code_hash=payload.get("code_hash") or None,
            version=int(payload.get("version", 1)),
            lineage=list(payload.get("lineage", [])),
        )


class ModelRegistry:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        core_dirs.ensure_dir(self.path.parent)
        self._records: Dict[str, ModelRecord] = {}
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        raw: Any = json.loads(self.path.read_text())
        if isinstance(raw, Mapping) and "models" in raw:
            entries = raw["models"]
        else:
            entries = raw
        if not isinstance(entries, list):
            raise ValueError("Malformed registry file; expected list of models")
        for item in entries:
            if not isinstance(item, Mapping):
                continue
            record = ModelRecord.from_dict(item)
            self._records[record.model_id] = record

    # ------------------------------------------------------------------
    def _write(self) -> None:
        payload: Dict[str, Any] = {
            "models": [record.to_dict() for record in self._records.values()],
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.path.write_text(json.dumps(payload, indent=2))

    # ------------------------------------------------------------------
    def _generate_id(self, strategy: str) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        suffix = uuid.uuid4().hex[:8]
        return f"{ts}_{safe_slug(strategy)}_{suffix}"

    # ------------------------------------------------------------------
    def add_candidate(
        self,
        *,
        strategy: str,
        symbol: str,
        params: Mapping[str, Any],
        metrics: Mapping[str, float],
        guard_metrics: Mapping[str, float],
        stress_metrics: Mapping[str, float],
        note: str = "",
        data_hash: str | None = None,
        code_hash: str | None = None,
        model_id: str | None = None,
    ) -> ModelRecord:
        identifier = model_id or self._generate_id(strategy)
        existing = self._records.get(identifier)
        version = existing.version + 1 if existing else 1
        record = ModelRecord(
            model_id=identifier,
            strategy=strategy,
            symbol=symbol,
            status="candidate",
            created_at=datetime.utcnow().isoformat(),
            params=dict(params),
            metrics=dict(metrics),
            guard_metrics=dict(guard_metrics),
            stress_metrics=dict(stress_metrics),
            note=note,
            data_hash=data_hash,
            code_hash=code_hash,
            version=version,
            lineage=list(existing.lineage) if existing else [],
        )
        self._records[identifier] = record
        self._write()
        return record

    # ------------------------------------------------------------------
    def promote(
        self,
        model_id: str,
        *,
        min_oos_sharpe: float = 0.0,
        max_oos_drawdown: float = -1.0,
    ) -> None:
        record = self._require(model_id)
        sharpe = self._best_metric(record.metrics, ("oos_Sharpe", "Sharpe"))
        drawdown = self._best_metric(record.metrics, ("oos_MaxDD", "MaxDD"))
        if sharpe is None or sharpe < min_oos_sharpe:
            raise ValueError("Model does not satisfy Sharpe promotion threshold")
        if drawdown is None or drawdown < max_oos_drawdown:
            raise ValueError("Model does not satisfy drawdown promotion threshold")

        prior_champions = [
            rec for rec in self._records.values() if rec.status == "champion"
        ]
        for champ in prior_champions:
            champ.status = "archived"
            champ.lineage.append(record.model_id)
        record.status = "champion"
        self._write()

    # ------------------------------------------------------------------
    def champion(self) -> ModelRecord | None:
        for record in self._records.values():
            if record.status == "champion":
                return record
        return None

    # ------------------------------------------------------------------
    def list(self, *, status: str | None = None) -> List[ModelRecord]:
        if status is None:
            return list(self._records.values())
        return [record for record in self._records.values() if record.status == status]

    # ------------------------------------------------------------------
    def _require(self, model_id: str) -> ModelRecord:
        if model_id not in self._records:
            raise KeyError(f"Model '{model_id}' not found in registry")
        return self._records[model_id]

    # ------------------------------------------------------------------
    @staticmethod
    def _best_metric(metrics: Mapping[str, float], keys: Iterable[str]) -> float | None:
        for key in keys:
            if key in metrics:
                return float(metrics[key])
        return None
