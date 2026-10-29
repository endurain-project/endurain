"""Tests for ETag / If-Match optimistic concurrency."""

import pytest
from fastapi import Response

import core.etag as core_etag
import core.exceptions as core_exceptions


class TestFormatEtag:
    def test_is_a_quoted_strong_tag(self):
        assert core_etag.format_etag(7) == '"7"'


class TestSetEtag:
    def test_sends_the_version_as_the_etag_header(self):
        response = Response()

        core_etag.set_etag(response, 7)

        assert response.headers["ETag"] == '"7"'


class TestParseIfMatch:
    def test_single_tag(self):
        assert core_etag.parse_if_match('"7"') == {"7"}

    def test_a_list_of_tags(self):
        assert core_etag.parse_if_match('"7", "8"') == {"7", "8"}

    def test_strips_the_weak_prefix(self):
        assert core_etag.parse_if_match('W/"7"') == set()


class TestRequireIfMatch:
    def test_matching_version_passes(self):
        core_etag.require_if_match('"7"', 7, "activity")

    def test_wildcard_passes(self):
        core_etag.require_if_match("*", 7, "activity")

    def test_stale_version_is_refused(self):
        """The whole point: the caller is editing something it has not seen."""
        with pytest.raises(core_exceptions.PreconditionFailedError):
            core_etag.require_if_match('"6"', 7, "activity")

    def test_unknown_current_version_is_refused(self):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            core_etag.require_if_match('"6"', None, "activity")

    def test_refusal_maps_to_412(self):
        with pytest.raises(core_exceptions.PreconditionFailedError) as exc:
            core_etag.require_if_match('"6"', 7, "activity")

        assert exc.value.status_code == 412
        assert exc.value.code == "precondition-failed"
