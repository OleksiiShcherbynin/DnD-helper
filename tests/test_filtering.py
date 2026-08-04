"""
Отбор легальных форм для Wild Shape.

Это тот самый слой, на котором держится вся гарантия инструмента: если сюда
не просочился нелегальный зверь, то LLM его и не увидит, а значит не сможет
предложить. Поэтому тесты проверяют не "примерно то", а точный состав выдачи.
"""

import pytest

from core.filtering import legal_wild_shape_beasts
from core.rules import wild_shape_cr_cap


def test_druid_below_level_2_gets_nothing(beasts, names):
    assert legal_wild_shape_beasts(beasts, druid_level=1) == []


def test_level_2_excludes_both_flying_and_swimming_beasts(beasts, names):
    """Летучая мышь отсекается по полёту, змея по плаванию, остальные по CR."""
    assert names(legal_wild_shape_beasts(beasts, druid_level=2)) == {"Wolf"}


def test_level_4_unlocks_swimming_but_not_flight(beasts, names):
    assert names(legal_wild_shape_beasts(beasts, druid_level=4)) == {
        "Wolf",
        "Giant Poisonous Snake",
    }


def test_level_8_unlocks_flight_and_cr_1(beasts, names):
    assert names(legal_wild_shape_beasts(beasts, druid_level=8)) == {
        "Wolf",
        "Giant Poisonous Snake",
        "Bat",
        "Brown Bear",
        "Giant Eagle",
        "Giant Octopus",
    }


@pytest.mark.parametrize("level", [2, 3, 4, 5, 6, 7, 8, 12, 20])
def test_cr_cap_is_never_exceeded_at_any_level(beasts, level):
    cap = wild_shape_cr_cap(level)
    assert all(beast.cr <= cap for beast in legal_wild_shape_beasts(beasts, level))
