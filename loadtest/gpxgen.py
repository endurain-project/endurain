"""The GPX files the load test uploads, shared by the Locust scenarios and the fault scenarios (faults.py)."""

import math
import random
from datetime import UTC, datetime, timedelta


def gpx(vid: int, n: int, run_index: int, points: int = 600) -> bytes:
    """Build a unique, valid GPX run (a loop of ``points`` trackpoints with heart rate) for one upload.

    The start time is unique per (virtual user, upload), because the server de-duplicates by content.

    Args:
        vid: The virtual user's number.
        n: The virtual user's upload counter.
        run_index: The number of the run within its stack, so runs never repeat a start time.
        points: Trackpoints, one per 5 seconds.

    Returns:
        The file's bytes.
    """
    rng = random.Random(f"{vid}:{n}")
    start = datetime(2012, 1, 1, tzinfo=UTC) + timedelta(minutes=10 * (run_index * 100_000 + vid * 1_000 + n))
    lat0, lon0 = 38.70 + rng.uniform(-0.1, 0.1), -9.15 + rng.uniform(-0.1, 0.1)
    out = [
        (
            '<?xml version="1.0" encoding="UTF-8"?>\n<gpx creator="loadtest" version="1.1" '
            'xmlns="http://www.topografix.com/GPX/1/1" xmlns:ns3="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">'
            f"<metadata><time>{start:%Y-%m-%dT%H:%M:%SZ}</time></metadata><trk><name>Load run {vid}-{n}</name>"
            "<type>running</type><trkseg>"
        )
    ]
    for i in range(points):
        angle = 6.2831853 * i / points
        lat = lat0 + 0.01 * (1 - math.cos(angle))
        lon = lon0 + 0.015 * math.sin(angle)
        stamp = start + timedelta(seconds=5 * i)
        out.append(
            f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"><ele>{20 + 10 * math.sin(angle * 3):.1f}</ele>'
            f"<time>{stamp:%Y-%m-%dT%H:%M:%SZ}</time><extensions><ns3:TrackPointExtension>"
            f"<ns3:hr>{130 + int(25 * abs(math.sin(angle * 2)))}</ns3:hr></ns3:TrackPointExtension>"
            "</extensions></trkpt>"
        )
    out.append("</trkseg></trk></gpx>")
    return "".join(out).encode()
