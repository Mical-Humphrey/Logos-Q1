from __future__ import annotations

import json
from importlib import resources
from typing import Any, Mapping, Sequence

import jsonschema
from jsonschema import Draft7Validator


class StrategiesIndexValidationError(ValueError):
    """Raised when strategies/index payloads fail schema validation."""


SCHEMA_FILES: dict[str, str] = {
    "v1": "strategies_index_v1.schema.json",
}


def _format_error(error: jsonschema.ValidationError) -> str:
    location = ".".join(str(part) for part in error.absolute_path) or "<root>"
    return f"{location}: {error.message}"


def _format_errors(errors: Sequence[jsonschema.ValidationError]) -> str:
    return "; ".join(_format_error(err) for err in errors)


def load_strategies_index_schema(version: str = "v1") -> dict[str, Any]:
    try:
        filename = SCHEMA_FILES[version]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported strategies index schema version: {version}"
        ) from exc

    with resources.files(__package__).joinpath(filename).open(
        "r", encoding="utf-8"
    ) as handle:
        return json.load(handle)


def validate_strategies_index(data: Mapping[str, Any], version: str = "v1") -> None:
    schema = load_strategies_index_schema(version)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    errors = sorted(
        validator.iter_errors(data), key=lambda err: tuple(err.absolute_path)
    )
    if errors:
        detail = _format_errors(errors)
        raise StrategiesIndexValidationError(
            f"strategies/index payload failed validation: {detail}"
        )


__all__ = [
    "load_strategies_index_schema",
    "validate_strategies_index",
    "StrategiesIndexValidationError",
]
