"""Chunked CSV readers with guard rails for large or malformed inputs."""

from __future__ import annotations

import csv
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, Mapping

try:
    import jsonschema
except Exception:  # pragma: no cover - optional dependency
    jsonschema = None  # type: ignore[assignment]


class ReaderLimitError(RuntimeError):
    """Raised when a configured limit is exceeded during streaming read."""


class SchemaValidationError(RuntimeError):
    """Raised when a row fails validation against a supplied schema."""


@dataclass(slots=True)
class Sample:
    lines: list[str]
    sha256: str = ""


@dataclass(slots=True)
class ReaderMetadata:
    sample: Sample
    rows: int = 0
    bytes_read: int = 0


class ChunkedCSVIterator(Iterator[Dict[str, str]]):
    def __init__(
        self, iterator: Iterator[Dict[str, str]], metadata: ReaderMetadata
    ) -> None:
        self._iterator = iterator
        self.metadata = metadata

    def __iter__(self) -> "ChunkedCSVIterator":
        return self

    def __next__(self) -> Dict[str, str]:
        return next(self._iterator)


def _sample_lines(path: Path, limit: int) -> list[str]:
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for _ in range(limit):
            line = fh.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))
    return lines


def read_csv_chunked(
    path: Path,
    *,
    max_rows: int | None = None,
    max_bytes: int | None = None,
    max_seconds: float | None = None,
    schema: Mapping[str, object] | None = None,
    sample_lines: int = 5,
) -> ChunkedCSVIterator:
    """Yield CSV rows as dictionaries enforcing configured guard rails.

    The returned generator exposes ``sample`` (Sample) and ``bytes_read`` attributes for
    callers needing inspection when quarantining a file after an error.
    """

    start = time.monotonic()
    sha = hashlib.sha256()
    sample = Sample(lines=_sample_lines(path, sample_lines))
    metadata = ReaderMetadata(sample=sample)

    def _iter() -> Iterator[Dict[str, str]]:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None:
                return
            header_serialised = ",".join(reader.fieldnames)
            metadata.bytes_read += len(header_serialised)
            sha.update((header_serialised + "\n").encode("utf-8"))

            try:
                for row in reader:
                    metadata.rows += 1
                    row_serialised = ",".join(
                        row.get(key, "") or "" for key in reader.fieldnames
                    )
                    metadata.bytes_read += len(row_serialised)
                    sha.update((row_serialised + "\n").encode("utf-8"))

                    if max_rows is not None and metadata.rows > max_rows:
                        raise ReaderLimitError("row limit exceeded")
                    if max_bytes is not None and metadata.bytes_read > max_bytes:
                        raise ReaderLimitError("byte limit exceeded")
                    if (
                        max_seconds is not None
                        and (time.monotonic() - start) > max_seconds
                    ):
                        raise ReaderLimitError("time limit exceeded")
                    if schema is not None:
                        if jsonschema is None:
                            raise SchemaValidationError("jsonschema not installed")
                        try:
                            jsonschema.validate(instance=row, schema=schema)
                        except Exception as exc:  # pragma: no cover - passthrough
                            raise SchemaValidationError(str(exc)) from exc
                    yield row
            finally:
                metadata.sample.sha256 = sha.hexdigest()

    return ChunkedCSVIterator(_iter(), metadata)


__all__ = [
    "read_csv_chunked",
    "ReaderLimitError",
    "SchemaValidationError",
    "Sample",
    "ReaderMetadata",
    "ChunkedCSVIterator",
]
