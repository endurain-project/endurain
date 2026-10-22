"""Settlement widening for reverse-geocode answers."""

from jasil.providers import GeocodedPlace

from core.geocoding_place import widen_place


def test_village_becomes_the_city_when_nominatim_has_no_city() -> None:
    place = widen_place(
        "nominatim",
        {"address": {"village": "Balatonakali", "state": "Transdanubia", "country": "Magyarország"}},
        GeocodedPlace(city=None, town=None, country="Magyarország"),
    )

    assert place == GeocodedPlace(city="Balatonakali", town=None, country="Magyarország")


def test_an_existing_city_is_kept() -> None:
    original = GeocodedPlace(city="Lisboa", town="Alvalade", country="Portugal")

    assert widen_place("nominatim", {"address": {"village": "Ignored"}}, original) is original
