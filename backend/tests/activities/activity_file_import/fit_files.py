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
        {"timestamp": (253, _UINT32, 1, 0), "local_timestamp": (5, _UINT32, 1, 0)},
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
