from collections.abc import Iterable
from hashlib import sha256

from capture.banks import RecordingBank


def fingerprint_banks(banks: Iterable[RecordingBank]) -> str:
    digest = sha256()
    for bank in sorted(banks, key=lambda bank: bank.name):
        for field in (bank.name.encode('utf-8'), bank.data):
            digest.update(len(field).to_bytes(8, 'big'))
            digest.update(field)
    return digest.hexdigest()


def same_named_banks(
    left: Iterable[RecordingBank], right: Iterable[RecordingBank],
) -> bool:
    return {bank.name: bank.data for bank in left} == {
        bank.name: bank.data for bank in right
    }
