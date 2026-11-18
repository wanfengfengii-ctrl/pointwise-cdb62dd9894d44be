"""Unsigned bit windows inside one- or two-byte integer containers.

A window is addressed from the least significant bit of the decoded container
value, so the physical byte that holds a given bit depends on the byte order.
Every stage (source reading, handover projection, offline reading, correction)
uses these helpers so a window is interpreted identically everywhere.
"""
from collections.abc import Mapping

from views.integers import validate_integer_format


def has_bit_window(bit_start, bit_length) -> bool:
    return bit_start is not None or bit_length is not None


def normalize_bit_window(
    width: int, byteorder: str, bit_start, bit_length,
) -> tuple[int, int]:
    """Return the effective (start, length) for a container or raise ValueError.

    Both values must be supplied together as plain integers.  ``None`` for both
    keeps the whole-word view, whose window is the complete container.
    """
    validate_integer_format(width, byteorder)
    if bit_start is None and bit_length is None:
        return 0, 8 * width
    if type(bit_start) is not int or type(bit_length) is not int:
        raise ValueError('bit start and bit length must both be integers')
    if bit_start < 0 or bit_length < 1:
        raise ValueError('bit window must start at zero or above and hold at least one bit')
    if bit_start + bit_length > 8 * width:
        raise ValueError('bit window extends outside its integer container')
    return bit_start, bit_length


def window_address_range(width: int, byteorder: str, bit_start, bit_length) -> range:
    """Container address indices, ascending, that carry the requested bits.

    The container is decoded with ``byteorder`` and bits are counted from the
    least significant bit, so a window may straddle the two container bytes.
    """
    start, length = normalize_bit_window(width, byteorder, bit_start, bit_length)
    low_byte = start // 8
    high_byte = (start + length - 1) // 8
    if byteorder == 'big':
        return range(width - 1 - high_byte, width - low_byte)
    return range(low_byte, high_byte + 1)


def bit_address(width: int, byteorder: str, bit: int) -> int:
    """Container address index that owns absolute bit ``bit`` of the value."""
    return width - 1 - bit // 8 if byteorder == 'big' else bit // 8


def decode_address_bytes(
    address_bytes: Mapping[int, int],
    width: int,
    byteorder: str,
    bit_start,
    bit_length,
) -> int:
    """Decode bytes keyed by container address into an unsigned window value."""
    start, length = normalize_bit_window(width, byteorder, bit_start, bit_length)
    container = bytearray(width)
    for address, value in address_bytes.items():
        if type(address) is not int or not 0 <= address < width:
            raise ValueError('byte address outside its integer container')
        if type(value) is not int or not 0 <= value <= 0xFF:
            raise ValueError('container byte is outside the unsigned byte range')
        container[address] = value
    decoded = int.from_bytes(container, byteorder) >> start
    return decoded & ((1 << length) - 1)


def window_value_limit(bit_length: int) -> int:
    if type(bit_length) is not int or bit_length < 1:
        raise ValueError('bit length must be a positive integer')
    return (1 << bit_length) - 1
