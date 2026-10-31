"""Device name carried by an imported activity file.

FIT already stores manufacturer and model. GPX and TCX often carry one
combined name (``Fitbit Versa 4``) in the creator field. Software that only
wrote the file, such as FitBridge, is not a watch and is ignored.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

# Matches activities.tracker_manufacturer and activities.tracker_model.
_MAX_NAME_LENGTH = 250

# Exporters, not the wearable that recorded the activity.
_IGNORED_NAMES = frozenset(
    {
        "fitbridge",
        "endurain",
        "strava",
        "garmin connect",
        "tapiriik",
        "runkeeper",
        "komoot",
        "ns",
    }
)


def split_device_name(raw: str | None) -> tuple[str | None, str | None]:
    """Split a combined device name into manufacturer and model.

    Args:
        raw: A creator or device string, or None.

    Returns:
        ``(manufacturer, model)``. A single word is returned as the model.
        An empty or ignored exporter name returns ``(None, None)``.
    """
    if raw is None:
        return None, None
    name = " ".join(raw.split())
    if not name or name.casefold() in _IGNORED_NAMES:
        return None, None
    manufacturer, _, model = name.partition(" ")
    if not model:
        return None, manufacturer[:_MAX_NAME_LENGTH]
    return manufacturer[:_MAX_NAME_LENGTH], model[:_MAX_NAME_LENGTH]


def tcx_creator_name(path: str) -> str | None:
    """Read the first TCX ``Creator/Name``, which is the recording device.

    Args:
        path: Path to the TCX file.

    Returns:
        The creator name, or None when the file has none or cannot be read.
    """
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "Creator":
            continue
        if _creator_type(element) == "application_t":
            continue
        for child in list(element):
            if child.tag.rsplit("}", 1)[-1] == "Name" and child.text and child.text.strip():
                return child.text.strip()
    return None


def _creator_type(element: ET.Element) -> str:
    """The TCX creator ``xsi:type``, such as ``Device_t`` or ``Application_t``."""
    for key, value in element.attrib.items():
        if key.rsplit("}", 1)[-1] == "type" and value and value.strip():
            return value.strip().casefold()
    return ""
