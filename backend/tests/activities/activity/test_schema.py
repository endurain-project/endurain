"""Tests for activity schema validators."""

import modules.activities.activity.schema as activity_schema


class TestTimezoneCanonicalization:
    """Legacy timezone aliases are stored under their canonical name."""

    def _activity(self, timezone):
        return activity_schema.ActivityBase(distance=0, name="Run", activity_type=1, timezone=timezone)

    def test_legacy_alias_is_canonicalized(self):
        assert self._activity("GB-Eire").timezone == "Europe/London"

    def test_canonical_name_is_kept(self):
        assert self._activity("Europe/Lisbon").timezone == "Europe/Lisbon"

    def test_none_is_kept(self):
        assert self._activity(None).timezone is None
