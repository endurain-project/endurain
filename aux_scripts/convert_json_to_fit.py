#!/usr/bin/env python3
"""
Convert Intervals.icu JSON Activity Files to FIT Format

This script converts orphan JSON activity files (from Runalyzer/Analyzer.com/
Intervals.icu exports) to FIT format so they can be imported into Endurain.

These JSON files often lack FIT equivalents because:
1. They are indoor/non-GPS activities that Runalyzer couldn't export as FIT
2. They are duplicates exported with different activity IDs

The FIT format fully supports non-GPS activities, so this converter creates
valid FIT files from the JSON data including heart rate, cadence, power, etc.

Usage:
    python convert_json_to_fit.py [--dry-run] [--output-dir DIR]

Options:
    --dry-run       Show what would be converted without creating files
    --output-dir    Output directory for FIT files (default: bulk_import folder)
    --input-dir     Input directory with JSON files (default: unsupported_json_format)
"""

import argparse
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend/app to path
script_dir = Path(__file__).parent
backend_app_dir = script_dir.parent / "backend" / "app"
sys.path.insert(0, str(backend_app_dir))

# Default directories
DEFAULT_BULK_IMPORT_DIR = script_dir.parent / "backend" / "app" / "data" / "activity_files" / "bulk_import"
DEFAULT_INPUT_DIR = DEFAULT_BULK_IMPORT_DIR / "unsupported_json_format"

# FIT file constants
FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# Sport type mapping from Intervals.icu to FIT sport enum
SPORT_MAP = {
    "Running": (1, 0),      # sport=running, sub_sport=generic
    "Cycling": (2, 0),      # sport=cycling, sub_sport=generic
    "Swimming": (5, 0),     # sport=swimming, sub_sport=generic
    "Walking": (11, 0),     # sport=walking, sub_sport=generic
    "Hiking": (17, 0),      # sport=hiking, sub_sport=generic
    "Strength training": (4, 20),  # sport=fitness_equipment, sub_sport=strength_training
    "Indoor cycling": (2, 6),      # sport=cycling, sub_sport=indoor_cycling
    "Flexibility training": (4, 15),  # sport=fitness_equipment, sub_sport=flexibility_training
    "Yoga": (4, 43),        # sport=fitness_equipment, sub_sport=yoga
    "Other": (0, 0),        # sport=generic, sub_sport=generic
    "Rowing": (15, 0),      # sport=rowing, sub_sport=generic
    "Kayaking": (41, 0),    # sport=kayaking
    "Sailing": (32, 0),     # sport=sailing
    "Diving": (53, 0),      # sport=diving
}


def datetime_to_fit_timestamp(dt: datetime) -> int:
    """Convert datetime to FIT timestamp (seconds since FIT epoch)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int((dt - FIT_EPOCH).total_seconds())


def unix_to_fit_timestamp(unix_ts: int) -> int:
    """Convert Unix timestamp to FIT timestamp."""
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return datetime_to_fit_timestamp(dt)


class FITWriter:
    """Simple FIT file writer for activity files."""

    def __init__(self):
        self.records = []
        self.data_size = 0

    def _encode_field(self, value, base_type):
        """Encode a field value based on its base type."""
        if value is None:
            # Return invalid value for the type
            if base_type == 0x00:  # enum
                return struct.pack('<B', 0xFF)
            elif base_type == 0x01:  # sint8
                return struct.pack('<b', 0x7F)
            elif base_type == 0x02:  # uint8
                return struct.pack('<B', 0xFF)
            elif base_type == 0x83:  # sint16
                return struct.pack('<h', 0x7FFF)
            elif base_type == 0x84:  # uint16
                return struct.pack('<H', 0xFFFF)
            elif base_type == 0x85:  # sint32
                return struct.pack('<i', 0x7FFFFFFF)
            elif base_type == 0x86:  # uint32
                return struct.pack('<I', 0xFFFFFFFF)
            elif base_type == 0x07:  # string
                return b'\x00'
            elif base_type == 0x88:  # float32
                return struct.pack('<f', float('nan'))
            elif base_type == 0x89:  # float64
                return struct.pack('<d', float('nan'))
            else:
                return struct.pack('<B', 0xFF)

        if base_type == 0x00:  # enum
            return struct.pack('<B', value & 0xFF)
        elif base_type == 0x01:  # sint8
            return struct.pack('<b', value)
        elif base_type == 0x02:  # uint8
            return struct.pack('<B', value & 0xFF)
        elif base_type == 0x83:  # sint16
            return struct.pack('<h', value)
        elif base_type == 0x84:  # uint16
            return struct.pack('<H', value & 0xFFFF)
        elif base_type == 0x85:  # sint32
            return struct.pack('<i', value)
        elif base_type == 0x86:  # uint32
            return struct.pack('<I', value & 0xFFFFFFFF)
        elif base_type == 0x07:  # string
            encoded = value.encode('utf-8') + b'\x00'
            return encoded
        elif base_type == 0x88:  # float32
            return struct.pack('<f', value)
        elif base_type == 0x89:  # float64
            return struct.pack('<d', value)
        else:
            return struct.pack('<B', value & 0xFF)

    def _crc16(self, data):
        """Calculate CRC-16 for FIT file."""
        crc_table = [
            0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
            0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400
        ]
        crc = 0
        for byte in data:
            tmp = crc_table[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ crc_table[byte & 0xF]
            tmp = crc_table[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ crc_table[(byte >> 4) & 0xF]
        return crc

    def add_file_id(self, timestamp: int, manufacturer: int = 1, product: int = 1,
                    serial: int = 12345, file_type: int = 4):
        """Add file_id message (message type 0)."""
        # Definition message for file_id
        definition = bytearray([
            0x40,  # Definition message, local message 0
            0x00,  # Reserved
            0x00,  # Architecture (little endian)
            0x00, 0x00,  # Global message number (0 = file_id)
            0x05,  # Number of fields
            # Fields: field_def_num, size, base_type
            0x00, 0x01, 0x00,  # type (enum)
            0x01, 0x02, 0x84,  # manufacturer (uint16)
            0x02, 0x02, 0x84,  # product (uint16)
            0x03, 0x04, 0x86,  # serial_number (uint32)
            0x04, 0x04, 0x86,  # time_created (uint32)
        ])
        self.records.append(bytes(definition))

        # Data message
        data = bytearray([0x00])  # Data message, local message 0
        data += self._encode_field(file_type, 0x00)  # type = activity
        data += self._encode_field(manufacturer, 0x84)
        data += self._encode_field(product, 0x84)
        data += self._encode_field(serial, 0x86)
        data += self._encode_field(timestamp, 0x86)
        self.records.append(bytes(data))

    def add_event(self, timestamp: int, event: int = 0, event_type: int = 0):
        """Add event message (message type 21)."""
        # Definition message for event
        definition = bytearray([
            0x41,  # Definition message, local message 1
            0x00,  # Reserved
            0x00,  # Architecture (little endian)
            0x15, 0x00,  # Global message number (21 = event)
            0x03,  # Number of fields
            0xFD, 0x04, 0x86,  # timestamp (uint32)
            0x00, 0x01, 0x00,  # event (enum)
            0x01, 0x01, 0x00,  # event_type (enum)
        ])
        self.records.append(bytes(definition))

        # Data message
        data = bytearray([0x01])  # Data message, local message 1
        data += self._encode_field(timestamp, 0x86)
        data += self._encode_field(event, 0x00)
        data += self._encode_field(event_type, 0x00)
        self.records.append(bytes(data))

    def add_record_definition(self, has_hr: bool = True, has_cadence: bool = False,
                               has_power: bool = False, has_temperature: bool = False,
                               has_gps: bool = False):
        """Add record definition message (message type 20)."""
        fields = [
            (0xFD, 0x04, 0x86),  # timestamp (uint32)
        ]

        if has_gps:
            fields.append((0x00, 0x04, 0x85))  # position_lat (sint32)
            fields.append((0x01, 0x04, 0x85))  # position_long (sint32)

        if has_hr:
            fields.append((0x03, 0x01, 0x02))  # heart_rate (uint8)

        if has_cadence:
            fields.append((0x04, 0x01, 0x02))  # cadence (uint8)

        if has_power:
            fields.append((0x07, 0x02, 0x84))  # power (uint16)

        if has_temperature:
            fields.append((0x0D, 0x01, 0x01))  # temperature (sint8)

        definition = bytearray([
            0x42,  # Definition message, local message 2
            0x00,  # Reserved
            0x00,  # Architecture (little endian)
            0x14, 0x00,  # Global message number (20 = record)
            len(fields),  # Number of fields
        ])

        for field_num, size, base_type in fields:
            definition += bytes([field_num, size, base_type])

        self.records.append(bytes(definition))

        return {
            'has_hr': has_hr,
            'has_cadence': has_cadence,
            'has_power': has_power,
            'has_temperature': has_temperature,
            'has_gps': has_gps,
        }

    def add_record(self, timestamp: int, config: dict, heart_rate: int = None,
                   cadence: int = None, power: int = None, temperature: int = None,
                   lat: float = None, lon: float = None):
        """Add a data record."""
        data = bytearray([0x02])  # Data message, local message 2
        data += self._encode_field(timestamp, 0x86)

        if config['has_gps']:
            # Convert lat/lon to semicircles
            lat_semi = int((lat / 180.0) * 2147483648) if lat is not None else None
            lon_semi = int((lon / 180.0) * 2147483648) if lon is not None else None
            data += self._encode_field(lat_semi, 0x85)
            data += self._encode_field(lon_semi, 0x85)

        if config['has_hr']:
            data += self._encode_field(heart_rate, 0x02)

        if config['has_cadence']:
            data += self._encode_field(cadence, 0x02)

        if config['has_power']:
            data += self._encode_field(power, 0x84)

        if config['has_temperature']:
            data += self._encode_field(temperature, 0x01)

        self.records.append(bytes(data))

    def add_session(self, timestamp: int, start_time: int, total_elapsed_time: float,
                    total_timer_time: float, sport: int, sub_sport: int,
                    total_distance: float = None, total_calories: int = None,
                    avg_heart_rate: int = None, max_heart_rate: int = None,
                    avg_cadence: int = None, avg_power: int = None):
        """Add session message (message type 18)."""
        # Definition message for session
        definition = bytearray([
            0x43,  # Definition message, local message 3
            0x00,  # Reserved
            0x00,  # Architecture (little endian)
            0x12, 0x00,  # Global message number (18 = session)
            0x0C,  # Number of fields
            0xFD, 0x04, 0x86,  # timestamp (uint32)
            0x02, 0x04, 0x86,  # start_time (uint32)
            0x07, 0x04, 0x86,  # total_elapsed_time (uint32, scale 1000)
            0x08, 0x04, 0x86,  # total_timer_time (uint32, scale 1000)
            0x05, 0x01, 0x00,  # sport (enum)
            0x06, 0x01, 0x00,  # sub_sport (enum)
            0x09, 0x04, 0x86,  # total_distance (uint32, scale 100)
            0x0B, 0x02, 0x84,  # total_calories (uint16)
            0x10, 0x01, 0x02,  # avg_heart_rate (uint8)
            0x11, 0x01, 0x02,  # max_heart_rate (uint8)
            0x12, 0x01, 0x02,  # avg_cadence (uint8)
            0x14, 0x02, 0x84,  # avg_power (uint16)
        ])
        self.records.append(bytes(definition))

        # Data message
        data = bytearray([0x03])  # Data message, local message 3
        data += self._encode_field(timestamp, 0x86)
        data += self._encode_field(start_time, 0x86)
        data += self._encode_field(int(total_elapsed_time * 1000) if total_elapsed_time else None, 0x86)
        data += self._encode_field(int(total_timer_time * 1000) if total_timer_time else None, 0x86)
        data += self._encode_field(sport, 0x00)
        data += self._encode_field(sub_sport, 0x00)
        data += self._encode_field(int(total_distance * 100) if total_distance else None, 0x86)
        data += self._encode_field(total_calories, 0x84)
        data += self._encode_field(avg_heart_rate, 0x02)
        data += self._encode_field(max_heart_rate, 0x02)
        data += self._encode_field(avg_cadence, 0x02)
        data += self._encode_field(avg_power, 0x84)
        self.records.append(bytes(data))

    def add_activity(self, timestamp: int, total_timer_time: float, num_sessions: int = 1):
        """Add activity message (message type 34)."""
        # Definition message for activity
        definition = bytearray([
            0x44,  # Definition message, local message 4
            0x00,  # Reserved
            0x00,  # Architecture (little endian)
            0x22, 0x00,  # Global message number (34 = activity)
            0x04,  # Number of fields
            0xFD, 0x04, 0x86,  # timestamp (uint32)
            0x00, 0x04, 0x86,  # total_timer_time (uint32, scale 1000)
            0x01, 0x02, 0x84,  # num_sessions (uint16)
            0x02, 0x01, 0x00,  # type (enum)
        ])
        self.records.append(bytes(definition))

        # Data message
        data = bytearray([0x04])  # Data message, local message 4
        data += self._encode_field(timestamp, 0x86)
        data += self._encode_field(int(total_timer_time * 1000) if total_timer_time else None, 0x86)
        data += self._encode_field(num_sessions, 0x84)
        data += self._encode_field(0, 0x00)  # type = manual
        self.records.append(bytes(data))

    def write(self, filepath: Path):
        """Write the FIT file to disk."""
        # Combine all records
        data_records = b''.join(self.records)
        data_size = len(data_records)

        # File header (14 bytes for FIT 2.0)
        header = bytearray([
            14,  # Header size
            0x20,  # Protocol version (2.0)
            0x08, 0x08,  # Profile version (little endian, 2056 = 8.8)
            data_size & 0xFF, (data_size >> 8) & 0xFF,
            (data_size >> 16) & 0xFF, (data_size >> 24) & 0xFF,
            ord('.'), ord('F'), ord('I'), ord('T'),  # ".FIT"
        ])

        # Header CRC
        header_crc = self._crc16(header)
        header += bytes([header_crc & 0xFF, (header_crc >> 8) & 0xFF])

        # Data CRC
        data_crc = self._crc16(data_records)

        # Write file
        with open(filepath, 'wb') as f:
            f.write(bytes(header))
            f.write(data_records)
            f.write(bytes([data_crc & 0xFF, (data_crc >> 8) & 0xFF]))


def geohash_to_latlon(geohash: str) -> tuple[float, float]:
    """Decode a geohash string to latitude and longitude."""
    base32 = '0123456789bcdefghjkmnpqrstuvwxyz'

    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    is_lon = True

    for char in geohash.lower():
        if char not in base32:
            continue
        val = base32.index(char)
        for i in range(4, -1, -1):
            bit = (val >> i) & 1
            if is_lon:
                mid = (lon_range[0] + lon_range[1]) / 2
                if bit:
                    lon_range[0] = mid
                else:
                    lon_range[1] = mid
            else:
                mid = (lat_range[0] + lat_range[1]) / 2
                if bit:
                    lat_range[0] = mid
                else:
                    lat_range[1] = mid
            is_lon = not is_lon

    lat = (lat_range[0] + lat_range[1]) / 2
    lon = (lon_range[0] + lon_range[1]) / 2
    return lat, lon


def convert_json_to_fit(json_path: Path, output_path: Path, dry_run: bool = False) -> bool:
    """Convert an Intervals.icu JSON file to FIT format."""
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        # Extract basic info
        unix_timestamp = data.get('time')
        if not unix_timestamp:
            print(f"  Skipping {json_path.name}: No timestamp found")
            return False

        start_time = unix_to_fit_timestamp(unix_timestamp)
        sport_name = data.get('sport', 'Other')
        sport, sub_sport = SPORT_MAP.get(sport_name, (0, 0))

        # Get stream data first (needed for duration calculation)
        stream = data.get('stream', [{}])
        if stream and len(stream) > 0:
            stream_data = stream[0]
        else:
            stream_data = {}

        # Get duration from stream if not at top level
        duration_data = stream_data.get('Duration', [])
        duration = data.get('duration') or data.get('elapsedTime')
        if not duration and duration_data:
            # Calculate from max stream duration value
            valid_durations = [d for d in duration_data if d is not None]
            if valid_durations:
                duration = max(valid_durations)

        distance = data.get('distance')
        calories = data.get('kcal')
        avg_hr = data.get('hrAvg')
        max_hr = data.get('hrMax')
        avg_cadence = data.get('cadence')
        avg_power = data.get('power')

        hr_data = stream_data.get('HeartRate', [])
        cadence_data = stream_data.get('Cadence', [])
        power_data = stream_data.get('PowerOriginal', []) or stream_data.get('PowerCalculated', [])
        temp_data = stream_data.get('Temperature', [])
        geohash_data = stream_data.get('Geohashes', [])

        # Determine what data we have
        has_hr = bool(hr_data and any(v is not None for v in hr_data))
        has_cadence = bool(cadence_data and any(v is not None for v in cadence_data))
        has_power = bool(power_data and any(v is not None for v in power_data))
        has_temperature = bool(temp_data and any(v is not None for v in temp_data))
        has_gps = bool(geohash_data and any(v for v in geohash_data))

        num_records = len(duration_data) if duration_data else 0

        print(f"  {json_path.name}:")
        print(f"    Sport: {sport_name}, Duration: {duration}s, Records: {num_records}")
        print(f"    Data: HR={has_hr}, Cadence={has_cadence}, Power={has_power}, GPS={has_gps}")

        if dry_run:
            print(f"    Would create: {output_path.name}")
            return True

        # Create FIT file
        writer = FITWriter()

        # Add file ID
        writer.add_file_id(start_time)

        # Add start event
        writer.add_event(start_time, event=0, event_type=0)  # timer start

        # Add records if we have stream data
        if num_records > 0:
            config = writer.add_record_definition(
                has_hr=has_hr,
                has_cadence=has_cadence,
                has_power=has_power,
                has_temperature=has_temperature,
                has_gps=has_gps
            )

            for i in range(num_records):
                # Calculate timestamp for this record
                if duration_data and i < len(duration_data) and duration_data[i] is not None:
                    record_time = start_time + int(duration_data[i])
                else:
                    record_time = start_time + i

                hr = int(hr_data[i]) if has_hr and i < len(hr_data) and hr_data[i] is not None else None
                cad = int(cadence_data[i]) if has_cadence and i < len(cadence_data) and cadence_data[i] is not None else None
                pwr = int(power_data[i]) if has_power and i < len(power_data) and power_data[i] is not None else None
                temp = int(temp_data[i]) if has_temperature and i < len(temp_data) and temp_data[i] is not None else None

                lat, lon = None, None
                if has_gps and i < len(geohash_data) and geohash_data[i]:
                    lat, lon = geohash_to_latlon(geohash_data[i])

                writer.add_record(
                    record_time, config,
                    heart_rate=hr, cadence=cad, power=pwr, temperature=temp,
                    lat=lat, lon=lon
                )

        # Calculate end time
        if duration:
            end_time = start_time + int(duration)
        elif num_records > 0 and duration_data:
            end_time = start_time + int(max(d for d in duration_data if d is not None))
        else:
            end_time = start_time

        # Add stop event
        writer.add_event(end_time, event=0, event_type=4)  # timer stop

        # Add session
        total_time = duration if duration else (end_time - start_time)
        writer.add_session(
            end_time, start_time,
            total_elapsed_time=total_time,
            total_timer_time=total_time,
            sport=sport, sub_sport=sub_sport,
            total_distance=distance,
            total_calories=int(calories) if calories else None,
            avg_heart_rate=int(avg_hr) if avg_hr else None,
            max_heart_rate=int(max_hr) if max_hr else None,
            avg_cadence=int(avg_cadence) if avg_cadence else None,
            avg_power=int(avg_power) if avg_power else None
        )

        # Add activity
        writer.add_activity(end_time, total_time)

        # Write file
        writer.write(output_path)
        print(f"    Created: {output_path.name}")
        return True

    except Exception as e:
        print(f"  Error converting {json_path.name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Convert Intervals.icu JSON files to FIT format")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be converted without creating files")
    parser.add_argument("--input-dir", type=str, default=None,
                        help="Input directory with JSON files (default: unsupported_json_format)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for FIT files (default: bulk_import folder)")

    args = parser.parse_args()

    input_dir = Path(args.input_dir) if args.input_dir else DEFAULT_INPUT_DIR
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_BULK_IMPORT_DIR

    if not input_dir.exists():
        print(f"Error: Input directory not found: {input_dir}")
        print("Run clean_duplicates.py first to move orphan JSON files to unsupported_json_format/")
        sys.exit(1)

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        sys.exit(1)

    print(f"Input directory:  {input_dir}")
    print(f"Output directory: {output_dir}")
    if args.dry_run:
        print("Mode: DRY RUN (no files will be created)")
    print()

    # Find JSON files (exclude README and summarizedActivities metadata files)
    json_files = list(input_dir.glob("*.json"))
    json_files = [f for f in json_files
                  if not f.name.startswith("README")
                  and "summarizedActivities" not in f.name]

    if not json_files:
        print("No JSON files found in input directory.")
        sys.exit(0)

    print(f"Found {len(json_files)} JSON files to convert.\n")

    success_count = 0
    fail_count = 0

    for json_path in sorted(json_files):
        # Create output filename
        output_name = json_path.stem + ".fit"
        output_path = output_dir / output_name

        if convert_json_to_fit(json_path, output_path, args.dry_run):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Successfully converted: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"{'='*60}")

    if not args.dry_run and success_count > 0:
        print(f"\nFIT files created in: {output_dir}")
        print("You can now import these files into Endurain.")


if __name__ == "__main__":
    main()
