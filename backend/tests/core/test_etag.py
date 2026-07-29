"""Tests for ETag / If-Match optimistic concurrency."""

import pytest

import core.etag as core_etag
import core.exceptions as core_exceptions


class TestFormatEtag:
    def test_is_a_quoted_strong_tag(self):
        assert core_etag.format_etag(7) == '"7"'


class TestParseIfMatch:
    def test_single_tag(self):
        assert core_etag.parse_if_match('"7"') == {"7"}

    def test_a_list_of_tags(self):
        assert core_etag.parse_if_match('"7", "8"') == {"7", "8"}

    def test_strips_the_weak_prefix(self):
        assert core_etag.parse_if_match('W/"7"') == {"7"}


class TestRequireIfMatch:
    def test_absent_header_is_allowed(self):
        """Requiring it would break every existing client at once."""
        core_etag.require_if_match(None, 7)

    def test_matching_version_passes(self):
        core_etag.require_if_match('"7"', 7)

    def test_wildcard_passes(self):
        core_etag.require_if_match("*", 7)

    def test_stale_version_is_refused(self):
        """The whole point: the caller is editing something it has not seen."""
        with pytest.raises(core_exceptions.PreconditionFailedError):
            core_etag.require_if_match('"6"', 7)

    def test_unknown_current_version_is_refused(self):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            core_etag.require_if_match('"6"', None)

    def test_refusal_maps_to_412(self):
        with pytest.raises(core_exceptions.PreconditionFailedError) as exc:
            core_etag.require_if_match('"6"', 7)

        assert exc.value.status_code == 412
        assert exc.value.code == "precondition-failed"
