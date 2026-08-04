"""
Классы как данные, а не как код.

Разница между жрецом (готовит список каждый день), бардом (учит навсегда)
и волшебником (пишет в книгу, готовит из неё) — это разные значения полей
в одной таблице. Добавить класс или хоумбрю должно быть добавлением строки.
"""

import pytest

from core.class_profiles import (
    CASTERS,
    max_spell_level,
    prepared_or_known_count,
    profile,
)


def test_every_caster_in_the_table_matches_the_catalog_key_convention():
    """Ключ srd_wizard работает, а wizard молча возвращает пустоту."""
    assert all(key.startswith("srd_") for key in CASTERS)


def test_paladin_is_absent_because_the_source_does_not_tag_it():
    """
    В данных Open5e паладинские заклинания не размечены: Divine Favor помечен
    жреческим, а Branding Smite не имеет классов вовсе. Обещать поддержку
    паладина, не имея его списка, значит выдавать неверные советы.
    """
    assert "srd_paladin" not in CASTERS


@pytest.mark.parametrize("level, expected", [
    (1, 1), (2, 1), (3, 2), (5, 3), (9, 5), (17, 9), (20, 9),
])
def test_full_casters_gain_a_spell_level_every_two_levels(level, expected):
    assert max_spell_level("srd_wizard", level) == expected


@pytest.mark.parametrize("level, expected", [
    (1, 0), (2, 1), (4, 1), (5, 2), (9, 3), (13, 4), (17, 5), (20, 5),
])
def test_ranger_is_a_half_caster_starting_at_level_2(level, expected):
    assert max_spell_level("srd_ranger", level) == expected


@pytest.mark.parametrize("level, expected", [(1, 1), (5, 3), (9, 5), (20, 5)])
def test_warlock_pact_magic_stops_at_fifth_level_slots(level, expected):
    assert max_spell_level("srd_warlock", level) == expected


def test_prepared_caster_counts_from_ability_and_level():
    """Жрец готовит модификатор Мудрости + уровень жреца, минимум одно."""
    assert prepared_or_known_count("srd_cleric", level=5, ability_modifier=3) == 8


def test_prepared_count_never_drops_below_one():
    assert prepared_or_known_count("srd_cleric", level=1, ability_modifier=-2) == 1


def test_known_caster_uses_a_table_and_ignores_the_ability_modifier():
    """У барда число известных заклинаний не зависит от Харизмы."""
    low = prepared_or_known_count("srd_bard", level=5, ability_modifier=0)
    high = prepared_or_known_count("srd_bard", level=5, ability_modifier=5)
    assert low == high


def test_profiles_say_how_the_class_learns_spells():
    assert profile("srd_cleric").preparation == "prepared"
    assert profile("srd_bard").preparation == "known"
    assert profile("srd_wizard").preparation == "spellbook"


def test_unknown_class_is_rejected_loudly():
    with pytest.raises(KeyError):
        profile("srd_dragonrider")
