"""
Подклассы отдельным понятием.

Раньше Артиллерист был заведён как отдельный класс — так было дешевле, но это
враньё в модели: игрок вводил подкласс вместо класса. Круг Луны по той же
причине не поддерживался вовсе.

Подкласс всегда принадлежит классу и может добавлять заклинания или менять
правила. Отдельно от класса он не существует.
"""

import pytest

from core.class_profiles import (
    ARTIFICER,
    SUBCLASSES,
    parse_class,
    parse_subclass,
    spell_keys_for,
    subclass_profile,
)
from core.rules import wild_shape_cr_cap


def test_artillerist_is_a_subclass_not_a_class():
    """Главная претензия: вводить подкласс вместо класса было неправильно."""
    assert parse_class("артиллерист") is None
    assert parse_subclass("артиллерист") == "artillerist"


@pytest.mark.parametrize("text, expected", [
    ("артиллерист", "artillerist"),
    ("Артиллерист", "artillerist"),
    ("artillerist", "artillerist"),
    ("круг луны", "moon"),
    ("луны", "moon"),
    ("moon", "moon"),
])
def test_subclass_names_are_understood(text, expected):
    assert parse_subclass(text) == expected


def test_unknown_subclass_gives_nothing_instead_of_guessing():
    assert parse_subclass("кузнец войны") is None


def test_every_subclass_belongs_to_a_real_class():
    from core.class_profiles import CASTERS

    for current in SUBCLASSES.values():
        assert current.parent in CASTERS or current.parent.startswith("srd_")


def test_subclass_adds_spells_on_top_of_the_class_list():
    base = spell_keys_for(ARTIFICER, None)
    with_subclass = spell_keys_for(ARTIFICER, "artillerist")

    assert base < with_subclass
    assert "srd_fireball" in with_subclass
    assert "srd_fireball" not in base


def test_a_subclass_of_another_class_is_refused():
    """
    Круг Луны у изобретателя — опечатка, а не сборка. Молча принять её значит
    выдать чужой список заклинаний.
    """
    with pytest.raises(ValueError, match="Круг Луны"):
        spell_keys_for(ARTIFICER, "moon")


def test_class_without_an_explicit_list_still_works():
    """У классов SRD список берётся из каталога, и подкласс это не ломает."""
    assert spell_keys_for("srd_wizard", None) is None


def test_subclass_profile_reports_its_name():
    assert subclass_profile("artillerist").name == "Артиллерист"


# ── Круг Луны ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("level, expected", [
    (2, 1.0), (5, 1.0), (6, 2.0), (8, 2.0), (9, 3.0), (12, 4.0), (20, 6.0),
])
def test_moon_druid_turns_into_far_bigger_beasts(level, expected):
    """
    Круг Луны: CR 1 со 2 уровня, а с 6-го — уровень делённый на три. Это его
    определяющая черта, и без неё он выглядит как обычный друид.
    """
    assert wild_shape_cr_cap(level, subclass_key="moon") == expected


@pytest.mark.parametrize("level, expected", [(2, 0.25), (4, 0.5), (8, 1.0)])
def test_land_druid_is_unchanged(level, expected):
    assert wild_shape_cr_cap(level) == expected
    assert wild_shape_cr_cap(level, subclass_key=None) == expected


def test_moon_druid_below_level_two_still_cannot_shift():
    assert wild_shape_cr_cap(1, subclass_key="moon") is None
