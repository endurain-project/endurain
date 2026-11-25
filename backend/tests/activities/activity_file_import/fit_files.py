"""Build small valid FIT files as bytes, so the parser reads a real file."""

import struct
from datetime import UTC, datetime

#: FIT timestamps count seconds from 1989-12-31T00:00:00Z.
_FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)

_ENUM = 0x00
_SINT8 = 0x01
_UINT8 = 0x02
_UINT16 = 0x84
_SINT32 = 0x85
_UINT32 = 0x86
_STRING = 0x07
_SIZE = {_ENUM: 1, _SINT8: 1, _UINT8: 1, _UINT16: 2, _SINT32: 4, _UINT32: 4}
_FORMAT = {_ENUM: "<B", _SINT8: "<b", _UINT8: "<B", _UINT16: "<H", _SINT32: "<i", _UINT32: "<I"}

#: Message name to (global message number, {field name: (field number, base type, scale, offset)}).
_MESSAGES: dict[str, tuple[int, dict[str, tuple[int, int, float, float]]]] = {
    "file_id": (0, {"type": (0, _ENUM, 1, 0), "manufacturer": (1, _UINT16, 1, 0), "time_created": (4, _UINT32, 1, 0)}),
    "workout": (26, {"wkt_name": (8, _STRING, 1, 0)}),
    "activity": (
        34,
        {
            "timestamp": (253, _UINT32, 1, 0),
            "local_timestamp": (5, _UINT32, 1, 0),
            "total_timer_time": (0, _UINT32, 1000, 0),
            "num_sessions": (1, _UINT16, 1, 0),
            "type": (2, _ENUM, 1, 0),
        },
    ),
    "record": (
        20,
        {
            "timestamp": (253, _UINT32, 1, 0),
            "position_lat": (0, _SINT32, 1, 0),
            "position_long": (1, _SINT32, 1, 0),
            "heart_rate": (3, _UINT8, 1, 0),
            "cadence": (4, _UINT8, 1, 0),
            "power": (7, _UINT16, 1, 0),
            "temperature": (13, _SINT8, 1, 0),
            "enhanced_altitude": (78, _UINT32, 5, 500),
        },
    ),
    "lap": (
        19,
        {
            "timestamp": (253, _UINT32, 1, 0),
            "start_time": (2, _UINT32, 1, 0),
            "total_elapsed_time": (7, _UINT32, 1000, 0),
            "total_timer_time": (8, _UINT32, 1000, 0),
            "total_distance": (9, _UINT32, 100, 0),
        },
    ),
    "session": (
        18,
        {
            "timestamp": (253, _UINT32, 1, 0),
            "start_time": (2, _UINT32, 1, 0),
            "total_elapsed_time": (7, _UINT32, 1000, 0),
            "total_timer_time": (8, _UINT32, 1000, 0),
            "total_distance": (9, _UINT32, 100, 0),
            "sport": (5, _ENUM, 1, 0),
            "sub_sport": (6, _ENUM, 1, 0),
            "total_calories": (11, _UINT16, 1, 0),
            "avg_heart_rate": (16, _UINT8, 1, 0),
            "max_heart_rate": (17, _UINT8, 1, 0),
            "avg_power": (20, _UINT16, 1, 0),
            "max_power": (21, _UINT16, 1, 0),
            "total_ascent": (22, _UINT16, 1, 0),
            "total_descent": (23, _UINT16, 1, 0),
        },
    ),
}

#: Field names that carry a time, given to :func:`message` as a ``datetime``.
_TIME_FIELDS = frozenset({"timestamp", "start_time", "time_created", "local_timestamp"})

#: Field names that carry a position, given to :func:`message` in degrees.
_POSITION_FIELDS = frozenset({"position_lat", "position_long"})


def _crc(data: bytes, crc: int = 0) -> int:
    table = (0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
             0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400)  # fmt: skip
    for byte in data:
        for shift in (0, 4):
            crc = (crc >> 4) ^ table[crc & 0xF] ^ table[(byte >> shift) & 0xF]
    return crc


def message(name: str, local_type: int = 0, **values: object) -> bytes:
    """Encode one data message with its definition.

    Args:
        name: The message name (``record``, ``session``, ``lap``, ``activity``, ``file_id``, ``workout``).
        local_type: The local message type, 0 to 15.
        **values: Field values; times as ``datetime``, positions in degrees, the rest as the field's own unit.

    Returns:
        The definition message followed by the data message.
    """
    number, fields = _MESSAGES[name]
    present = [(key, fields[key]) for key in fields if key in values]
    definition = struct.pack("<BBBHB", 0x40 | local_type, 0, 0, number, len(present))
    data = bytes([local_type])
    for key, (field_number, base_type, scale, offset) in present:
        value = values[key]
        if base_type == _STRING:
            assert isinstance(value, str)
            encoded = value.encode("utf-8") + b"\0"
            definition += struct.pack("<BBB", field_number, len(encoded), base_type)
            data += encoded
            continue
        definition += struct.pack("<BBB", field_number, _SIZE[base_type], base_type)
        if key in _TIME_FIELDS:
            assert isinstance(value, datetime)
            raw = int((value - _FIT_EPOCH).total_seconds())
        elif key in _POSITION_FIELDS:
            assert isinstance(value, int | float)
            raw = round(value * (2**31) / 180)
        else:
            assert isinstance(value, int | float)
            raw = round((value + offset) * scale)
        data += struct.pack(_FORMAT[base_type], raw)
    return definition + data


def fit_file(*messages: bytes) -> bytes:
    """Wrap encoded messages in a FIT file header and CRC.

    Args:
        *messages: Encoded messages from :func:`message`.

    Returns:
        The bytes of a valid FIT file.
    """
    body = b"".join(messages)
    header = struct.pack("<BBHI4s", 14, 0x20, 2140, len(body), b".FIT")
    header += struct.pack("<H", _crc(header))
    return header + body + struct.pack("<H", _crc(header + body))


#: Base type byte to (struct character, size, the value the FIT protocol reserves for "invalid").
_BASE_TYPES: dict[int, tuple[str, int, object]] = {
    0x00: ("B", 1, 0xFF),  # enum
    0x01: ("b", 1, 0x7F),  # sint8
    0x02: ("B", 1, 0xFF),  # uint8
    0x83: ("h", 2, 0x7FFF),  # sint16
    0x84: ("H", 2, 0xFFFF),  # uint16
    0x85: ("i", 4, 0x7FFFFFFF),  # sint32
    0x86: ("I", 4, 0xFFFFFFFF),  # uint32
    0x88: ("f", 4, float("nan")),  # float32
    0x0A: ("B", 1, 0),  # uint8z
    0x0D: ("B", 1, 0xFF),  # byte
    0x8B: ("H", 2, 0),  # uint16z
    0x8C: ("I", 4, 0),  # uint32z
}

#: A field of :func:`raw_message`: (field number, base type byte, value); a value of ``None`` is the base type's
#: invalid sentinel, a ``tuple`` is an array, a ``str`` is a string.
type RawField = tuple[int, int, object]


def raw_message(
    global_number: int,
    fields: list[RawField],
    *,
    local_type: int = 0,
    big_endian: bool = False,
    with_definition: bool = True,
    time_offset: int | None = None,
    developer_fields: list[tuple[int, int, bytes]] | None = None,
) -> bytes:
    """Encode one message of any global number, field by field, in raw FIT values.

    Unlike :func:`message`, nothing is scaled: each value is what goes on the wire.

    Args:
        global_number: The global message number.
        fields: The fields in wire order.
        local_type: The local message type; 0 to 3 when ``time_offset`` is given.
        big_endian: Whether the definition declares big-endian architecture.
        with_definition: Whether to emit the definition before the data (False reuses an earlier one).
        time_offset: A 5-bit time offset; when given the data record carries a compressed timestamp header.
        developer_fields: Developer fields as (field number, developer data index, value bytes).

    Returns:
        The definition (when asked for) followed by the data message.
    """
    endian = ">" if big_endian else "<"
    flags = 0x40 | 0x20 if developer_fields else 0x40
    definition = struct.pack(f"{endian}BBBHB", flags | local_type, 0, int(big_endian), global_number, len(fields))
    data = bytes([0x80 | (local_type << 5) | time_offset]) if time_offset is not None else bytes([local_type])
    for field_number, base_type, value in fields:
        char, size, invalid = _BASE_TYPES.get(base_type, ("", 0, None))
        if base_type == _STRING:
            assert isinstance(value, str)
            encoded = value.encode("utf-8") + b"\0"
            definition += struct.pack("<BBB", field_number, len(encoded), base_type)
            data += encoded
            continue
        values = list(value) if isinstance(value, tuple) else [invalid if value is None else value]
        definition += struct.pack("<BBB", field_number, size * len(values), base_type)
        for item in values:
            data += struct.pack(f"{endian}{char}", item)
    if developer_fields:
        definition += bytes([len(developer_fields)])
        for field_number, index, value in developer_fields:
            definition += struct.pack("<BBB", field_number, len(value), index)
            data += value
    return (definition if with_definition else b"") + data


def damaged_fit_file(*messages: bytes, corrupt_crc: bool = False, truncate: int = 0) -> bytes:
    """Wrap messages in a FIT file and damage it.

    Args:
        *messages: Encoded messages.
        corrupt_crc: Whether to write a wrong trailing CRC.
        truncate: How many trailing bytes to cut off.

    Returns:
        The file bytes.
    """
    content = fit_file(*messages)
    if corrupt_crc:
        content = content[:-2] + struct.pack("<H", struct.unpack("<H", content[-2:])[0] ^ 0xFFFF)
    return content[: len(content) - truncate]
