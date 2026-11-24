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

    def test_leaves_out_a_weak_tag(self):
        assert core_etag.parse_if_match('W/"7"') == set()

    def test_a_list_keeps_its_strong_tags_only(self):
        assert core_etag.parse_if_match('W/"7", "8"') == {"8"}

    def test_a_tag_may_contain_a_comma(self):
        assert core_etag.parse_if_match('"7,8", "9"') == {"7,8", "9"}

    @pytest.mark.parametrize(
        ("header", "tags"), [("", set()), (" ", set()), (",", set()), (' , "7" ,, "8" ,', {"7", "8"})]
    )
    def test_empty_list_elements_are_accepted(self, header, tags):
        """RFC 9110 §5.6.1.2: a recipient accepts empty list elements; an empty list matches no version."""
        assert core_etag.parse_if_match(header) == tags

    def test_a_quoted_asterisk_is_a_tag_not_the_wildcard(self):
        assert core_etag.parse_if_match('"*"') == {"*"}

    @pytest.mark.parametrize(
        "header",
        [
            "7",
            '"7',
            '7"',
            '""7""',
            '"7" "8"',
            '"7", 8',
            "W/7",
            'w/"7"',
            '"a b"',
            '"7";',
            '*, "7"',
            '"7", *',
            "**",
            " " * 8000 + "x",
            ", " * 4000 + "x",
        ],
    )
    def test_a_header_that_is_not_a_list_of_quoted_tags_is_refused(self, header):
        """RFC 9110 §8.8.3: an entity tag is quoted; anything else is a malformed request, not a stale one."""
        with pytest.raises(core_exceptions.InvalidInputError) as refused:
            core_etag.parse_if_match(header)

        assert refused.value.status_code == 400


class TestRequireIfMatch:
    def test_matching_version_passes(self):
        core_etag.require_if_match('"7"', 7, "activity")

    def test_wildcard_passes(self):
        core_etag.require_if_match("*", 7, "activity")

    def test_a_quoted_asterisk_matches_no_version(self):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            core_etag.require_if_match('"*"', 7, "activity")

    def test_an_unquoted_version_is_refused_as_malformed(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            core_etag.require_if_match("7", 7, "activity")

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
