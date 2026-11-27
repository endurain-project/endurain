"""The ``integer`` id lookup of the UUID conversion helpers, evaluated by PostgreSQL."""

import pytest
import sqlalchemy as sa
from tests._helpers.db import disposable_postgres_url, postgres_test_url

from migrations import uuid_conversion

pytestmark = pytest.mark.postgres


@pytest.mark.skipif(postgres_test_url() is None, reason="TEST_DATABASE_URL is not set")
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("7", 7),
        ("999999999", 999999999),
        ("2147483647", 2147483647),
        ("2147483648", None),
        ("9999999999", None),
        ("12345678901", None),
        ("1.5", None),
        ("-1", None),
        ("abc", None),
    ],
)
def test_integer_id_matches_every_int4_id_and_nothing_else(text: str, expected: int | None) -> None:
    engine = sa.create_engine(disposable_postgres_url())
    try:
        with engine.connect() as connection:
            value = connection.execute(sa.select(uuid_conversion._integer_id(sa.literal(text)))).scalar_one()
    finally:
        engine.dispose()

    assert value == expected
