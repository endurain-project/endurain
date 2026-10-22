"""Keep a village or hamlet as the activity's settlement.

Nominatim puts a place like Balatonakali in ``address.village`` and leaves
``city`` and ``town`` empty. Jasil only copies those two, so the activity
row kept the country alone. This widens the parsed place before it is stored.
"""

from __future__ import annotations

from jasil.providers import GeocodedPlace

# First inhabited place Nominatim (and the geocode.maps.co copy of it) may use.
# A suburb is a district, not a settlement, so it is not promoted to a city.
_SETTLEMENT_KEYS = ("city", "town", "village", "municipality", "hamlet", "locality")


def _address(service: str, payload: dict) -> dict:
    if service == "photon":
        features = payload.get("features") or []
        if not features:
            return {}
        properties = features[0].get("properties") or {}
        return properties if isinstance(properties, dict) else {}
    address = payload.get("address") or {}
    return address if isinstance(address, dict) else {}


def _settlement(data: dict) -> str | None:
    for key in _SETTLEMENT_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def widen_place(service: str, payload: dict, place: GeocodedPlace | None) -> GeocodedPlace | None:
    """Fill an empty city from a village, hamlet, or municipality.

    A place that already has a city or town is left unchanged. Photon already
    maps its own city and district fields, so this only steps in when both are
    empty.

    Args:
        service: ``nominatim``, ``photon``, or ``geocode``.
        payload: The raw reverse-geocode JSON.
        place: The place Jasil parsed, or None.

    Returns:
        The same place, or one whose city is the settlement. None when nothing
        resolved.
    """
    if place is not None and (place.city or place.town):
        return place
    data = _address(service, payload)
    settlement = _settlement(data)
    if not settlement:
        return place
    country = place.country if place is not None and place.country else None
    if country is None:
        raw_country = data.get("country")
        country = raw_country.strip() if isinstance(raw_country, str) and raw_country.strip() else None
    return GeocodedPlace(city=settlement, town=None, country=country)


def install() -> None:
    """Patch Jasil's HTTP geocoder once per process."""
    from jasil.backends.geocoding_http import HttpGeocoding

    if getattr(HttpGeocoding._parse, "_settlement_widened", False):
        return
    original = HttpGeocoding._parse

    def _parse(self: HttpGeocoding, payload: dict) -> GeocodedPlace | None:
        return widen_place(self._service, payload, original(self, payload))

    _parse._settlement_widened = True  # type: ignore[attr-defined]
    HttpGeocoding._parse = _parse  # type: ignore[method-assign]
