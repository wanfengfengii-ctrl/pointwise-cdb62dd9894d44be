def validate_integer_format(width: int, byteorder: str) -> None:
    if type(width) is not int or width not in (1, 2):
        raise ValueError('integer width must be one or two bytes')
    if byteorder not in ('little', 'big'):
        raise ValueError('byte order must be little or big')


def unsigned_limit(width: int) -> int:
    validate_integer_format(width, 'little')
    return (1 << (8 * width)) - 1


def decode_unsigned(data: bytes, width: int, byteorder: str) -> int:
    validate_integer_format(width, byteorder)
    if len(data) != width:
        raise ValueError('integer byte count differs from width')
    return int.from_bytes(data, byteorder, signed=False)


def encode_unsigned(value: int, width: int, byteorder: str) -> bytes:
    validate_integer_format(width, byteorder)
    if type(value) is not int or not 0 <= value <= unsigned_limit(width):
        raise ValueError(f'unsigned integer is outside the {width}-byte range')
    return value.to_bytes(width, byteorder, signed=False)
