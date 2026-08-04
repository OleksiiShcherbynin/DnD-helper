"""Правила Wild Shape по SRD 5.1 (круг земли, базовый друид)."""

import pytest

from core.rules import (
    wild_shape_allows_flight,
    wild_shape_allows_swimming,
    wild_shape_cr_cap,
)


def test_druid_below_level_2_cannot_wild_shape():
    assert wild_shape_cr_cap(1) is None


@pytest.mark.parametrize("level, expected", [
    (2, 0.25),
    (3, 0.25),
    (4, 0.5),
    (7, 0.5),
    (8, 1.0),
    (20, 1.0),
])
def test_cr_cap_rises_at_levels_4_and_8(level, expected):
    assert wild_shape_cr_cap(level) == expected


@pytest.mark.parametrize("level", [2, 3, 4, 7])
def test_flight_is_forbidden_before_level_8(level):
    assert wild_shape_allows_flight(level) is False


@pytest.mark.parametrize("level", [8, 20])
def test_flight_is_allowed_from_level_8(level):
    assert wild_shape_allows_flight(level) is True


@pytest.mark.parametrize("level", [2, 3])
def test_swimming_is_forbidden_before_level_4(level):
    assert wild_shape_allows_swimming(level) is False


@pytest.mark.parametrize("level", [4, 8])
def test_swimming_is_allowed_from_level_4(level):
    assert wild_shape_allows_swimming(level) is True
