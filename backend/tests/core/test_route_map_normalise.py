"""Tests for the tile URL template normaliser shared by the renderer and the settings check."""

import pytest

import core.route_map as core_route_map


@pytest.mark.parametrize(
    "template,expected",
    [
        ("https://t.example.com/{z}/{x}/{y}{r}.png", "https://t.example.com/{z}/{x}/{y}.png"),
        ("https://{s}.t.example.com/{z}/{x}/{y}.png", "https://a.t.example.com/{z}/{x}/{y}.png"),
        ("https://t.example.com/{foo}/{z}/{x}/{y}.png", "https://t.example.com/{{foo}}/{z}/{x}/{y}.png"),
    ],
)
def test_templates_become_format_safe(template, expected):
    assert core_route_map.normalise_tile_url(template) == expected
    core_route_map.normalise_tile_url(template).format(z=0, x=0, y=0)
