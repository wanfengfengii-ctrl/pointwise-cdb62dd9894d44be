from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class RecordingBank:
    name: str
    data: bytes


def normalize_banks(
    banks: Mapping[str, bytes] | Iterable[tuple[str, bytes]],
) -> tuple[RecordingBank, ...]:
    entries = banks.items() if isinstance(banks, Mapping) else banks
    normalized = {}
    try:
        for name, data in entries:
            if not isinstance(name, str) or not name.strip():
                raise ValueError('bank name must be a nonempty string')
            name.encode('utf-8')
            if name in normalized:
                raise ValueError(f'duplicate bank {name!r}')
            if not isinstance(data, (bytes, bytearray, memoryview)):
                raise ValueError(f'bank {name!r} must contain raw bytes')
            data = bytes(data)
            if not data:
                raise ValueError(f'bank {name!r} is empty')
            normalized[name] = RecordingBank(name, data)
    except TypeError as error:
        raise ValueError('banks must be a mapping or iterable of name and byte pairs') from error
    if not normalized:
        raise ValueError('recording must contain at least one bank')
    return tuple(normalized[name] for name in sorted(normalized))


def bank_lengths(banks: Iterable[RecordingBank]) -> dict[str, int]:
    return {bank.name: len(bank.data) for bank in banks}


def read_bank(banks: Iterable[RecordingBank], name: str) -> bytes:
    for bank in banks:
        if bank.name == name:
            return bank.data
    raise KeyError(name)
