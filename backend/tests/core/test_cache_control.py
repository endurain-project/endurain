"""Tests for core.cache_control."""

from fastapi import Response

import core.cache_control as core_cache_control


def test_set_no_store_sets_both_headers():
    response = Response()

    core_cache_control.set_no_store(response)

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_no_store_headers_match_what_set_no_store_sends():
    response = Response()
    core_cache_control.set_no_store(response)

    assert {k: response.headers[k] for k in core_cache_control.NO_STORE_HEADERS} == core_cache_control.NO_STORE_HEADERS
