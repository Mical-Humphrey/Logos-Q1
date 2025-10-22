from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from core.io.dirs import ensure_dir
from logos.strategies import STRATEGIES

from .validate import validate_strategies_index

DEFAULT_VERSION = "v1"
SIZE_LIMIT_BYTES = 307_200

logger = logging.getLogger(__name__)


def _isoformat_utc(dt: datetime | None = None) -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _annotation_to_text(annotation: Any) -> str:
    if annotation is inspect.Signature.empty:
        return ""
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


def _default_to_json(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _parameter_kind_name(parameter: inspect.Parameter) -> str:
    mapping = {
        inspect.Parameter.POSITIONAL_ONLY: "positional_only",
        inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional_or_keyword",
        inspect.Parameter.VAR_POSITIONAL: "var_positional",
        inspect.Parameter.KEYWORD_ONLY: "keyword_only",
        inspect.Parameter.VAR_KEYWORD: "var_keyword",
    }
    return mapping[parameter.kind]


def _extract_parameters(signature: inspect.Signature) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    for idx, parameter in enumerate(signature.parameters.values()):
        entry: dict[str, Any] = {
            "name": parameter.name,
            "kind": _parameter_kind_name(parameter),
            "position": idx,
        }
        annotation_text = _annotation_to_text(parameter.annotation)
        if annotation_text:
            entry["annotation"] = annotation_text
        if parameter.default is not inspect.Signature.empty:
            entry["default"] = _default_to_json(parameter.default)
        params.append(entry)
    return params


def _extract_summary(function: Callable[..., Any]) -> tuple[str, str]:
    doc = inspect.getdoc(function) or ""
    if not doc:
        return "", ""
    lines = [line.strip() for line in doc.splitlines()]
    summary = ""
    description_lines: list[str] = []

    for line in lines:
        if summary == "" and line:
            summary = line
        else:
            description_lines.append(line)

    description = "\n".join(description_lines).strip()
    return summary, description


@dataclass(frozen=True)
class StrategyDescriptor:
    strategy_id: str
    function: Callable[..., Any]

    def to_contract_entry(self) -> dict[str, Any]:
        signature = inspect.signature(self.function)
        summary, description = _extract_summary(self.function)
        entry = {
            "strategy_id": self.strategy_id,
            "module": self.function.__module__,
            "entrypoint": f"{self.function.__module__}.{self.function.__name__}",
            "parameters": _extract_parameters(signature),
            "summary": summary,
            "description": description,
            "ext": {},
        }
        return entry


def _collect_strategies(
    strategies: Mapping[str, Callable[..., Any]] | None = None
) -> list[StrategyDescriptor]:
    source = strategies or STRATEGIES
    items = [
        StrategyDescriptor(strategy_id=key, function=cast(Callable[..., Any], value))
        for key, value in source.items()
    ]
    items.sort(key=lambda descriptor: descriptor.strategy_id)
    return items


def build_strategies_index(
    *,
    version: str = DEFAULT_VERSION,
    generated_at: datetime | None = None,
    strategies: Mapping[str, Callable[..., Any]] | None = None,
) -> dict[str, Any]:
    """Build the in-memory payload for the strategies index contract."""

    if version != DEFAULT_VERSION:
        raise ValueError(f"Unsupported contract version: {version}")

    descriptors = _collect_strategies(strategies)
    entries = [descriptor.to_contract_entry() for descriptor in descriptors]

    payload: dict[str, Any] = {
        "version": version,
        "generated_at": _isoformat_utc(generated_at),
        "strategies": entries,
        "ext": {},
    }

    return payload


def _serialize_payload(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")


def generate_strategies_index(
    out_path: Path,
    *,
    version: str = DEFAULT_VERSION,
    strategies: Mapping[str, Callable[..., Any]] | None = None,
    size_limit_bytes: int = SIZE_LIMIT_BYTES,
) -> dict[str, Any]:
    payload = build_strategies_index(version=version, strategies=strategies)
    validate_strategies_index(payload, version=version)

    blob = _serialize_payload(payload)
    if len(blob) > size_limit_bytes:
        logger.error(
            "strategies index size guard tripped bytes=%s limit=%s component=contracts",
            len(blob),
            size_limit_bytes,
        )
        raise ValueError(
            f"strategies index exceeds limit bytes={len(blob)} limit={size_limit_bytes}"
        )

    parent = out_path.parent
    if parent != out_path:
        ensure_dir(parent, owned=True)
    out_path.write_bytes(blob)
    return payload


__all__ = [
    "build_strategies_index",
    "generate_strategies_index",
    "SIZE_LIMIT_BYTES",
]
