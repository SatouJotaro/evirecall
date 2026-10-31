"""Durable, finite JSON records with explicit crash-tail recovery."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from evirecall.contracts import ContractError


@dataclass(frozen=True)
class ReadResult:
    records: list[dict]
    warnings: list[str]


def _encode(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"Invalid finite JSON: {exc}") from exc


def append_jsonl(path: str | Path, value: Any) -> None:
    """Persist one complete line before returning; caller supplies a single writer."""
    data = (_encode(value) + '\n').encode('utf-8')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('ab') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path: str | Path, value: Any) -> None:
    """Replace JSON atomically using a flushed sibling temporary file."""
    data = (_encode(value) + '\n').encode('utf-8')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _reject_constant(value: str) -> None:
    raise ValueError(f'Non-finite JSON constant: {value}')


def read_jsonl(path: str | Path, *, recover_tail: bool = False) -> ReadResult:
    path = Path(path)
    if not path.exists():
        return ReadResult([], [])
    lines = path.read_bytes().splitlines(keepends=True)
    records, warnings = [], []
    for index, line in enumerate(lines):
        try:
            value = json.loads(line.decode('utf-8'), parse_constant=_reject_constant)
            # A huge JSON exponent can also overflow despite valid JSON syntax.
            _encode(value)
        except (UnicodeDecodeError, ValueError, ContractError) as exc:
            if recover_tail and index == len(lines) - 1 and not line.endswith(b'\n'):
                warnings.append(f'{path}: ignored malformed unterminated final line {index + 1}')
                continue
            raise ContractError(f'{path}: malformed JSON at line {index + 1}') from exc
        if not isinstance(value, dict):
            raise ContractError(f'{path}: expected JSON object at line {index + 1}')
        records.append(value)
        if recover_tail and index == len(lines) - 1 and not line.endswith(b'\n'):
            warnings.append(f'{path}: preserved unterminated final line {index + 1}')
    return ReadResult(records, warnings)
