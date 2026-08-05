"""
Лист партии: что отряд умеет и чего ему не хватает.

Самая полезная часть — спасброски. В 5e именно они решают, кто выключается из
боя одним заклинанием: партия без владения Мудростью ложится от Hold Person,
и заметить это заранее гораздо дешевле, чем на игре.

В отличие от списка союзников, лист считает партию целиком, включая того, кто
спрашивает: это картина отряда, а не дыры вокруг одного персонажа.
"""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import parse_class_data
from core.models import PartyMember
from core.party_sheet import build_party_sheet

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "classes_sample.json"


@pytest.fixture(scope="module")
def classes():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {item["key"]: parse_class_data(item) for item in raw}


def _sheet(classes, *class_keys):
    return build_party_sheet(
        [PartyMember(key, 5) for key in class_keys], classes=classes
    )


def test_sheet_covers_all_six_abilities(classes):
    sheet = _sheet(classes, "srd_barbarian")
    assert set(sheet.saves) == {"str", "dex", "con", "int", "wis", "cha"}


def test_saves_list_who_covers_them(classes):
    sheet = _sheet(classes, "srd_barbarian", "srd_rogue")
    assert sheet.saves["str"] == ("Barbarian",)
    assert sheet.saves["dex"] == ("Rogue",)


def test_uncovered_save_is_reported_as_a_gap(classes):
    """У варвара и плута нет владения Мудростью — это дыра, и опасная."""
    sheet = _sheet(classes, "srd_barbarian", "srd_rogue")
    assert sheet.saves["wis"] == ()
    assert any("Мудрост" in gap.text for gap in sheet.gaps)


def test_covered_save_is_not_a_gap(classes):
    """Жрец закрывает Мудрость — жаловаться больше не на что."""
    sheet = _sheet(classes, "srd_barbarian", "srd_cleric")
    assert sheet.saves["wis"] == ("Cleric",)
    assert not any(gap.ability == "wis" for gap in sheet.gaps)


def test_dangerous_gaps_come_before_rare_ones(classes):
    """
    Мудрость и Ловкость встречаются в бою постоянно, Интеллект и Харизма почти
    никогда. Список дыр без такого порядка одинаково пугал бы и там, и там.
    """
    sheet = _sheet(classes, "srd_barbarian")
    abilities = [gap.ability for gap in sheet.gaps]
    assert abilities.index("wis") < abilities.index("cha")
    assert abilities.index("dex") < abilities.index("int")


def test_gap_explains_what_it_costs(classes):
    """Дыра без объяснения последствий — просто буква, по ней не решишь."""
    sheet = _sheet(classes, "srd_barbarian")
    wis = next(gap for gap in sheet.gaps if gap.ability == "wis")
    assert "Hold Person" in wis.text


def test_a_gap_names_the_classes_that_close_it(classes):
    """
    Дыру в спасбросках закрывает класс, а не заклинание. Без этого игрок
    ищет решение там, где его нет — и учит заклинание, которое не поможет.
    """
    sheet = _sheet(classes, "srd_barbarian")
    dex = next(gap for gap in sheet.gaps if gap.ability == "dex")

    assert "Rogue" in dex.covered_by_classes
    assert "Ranger" in dex.covered_by_classes
    assert "Barbarian" not in dex.covered_by_classes


def test_the_threat_text_does_not_name_a_spell_you_can_own(classes):
    """
    В подсказке про Ловкость стояло «драконье дыхание» — дыхание монстра.
    Читалось как заклинание Dragon's Breath, и игрок решил, что выучив его
    закроет дыру. Название, совпадающее с заклинанием, тут неуместно.
    """
    sheet = _sheet(classes, "srd_barbarian")
    dex = next(gap for gap in sheet.gaps if gap.ability == "dex")

    assert "дыхание" not in dex.text.lower()


def test_hit_dice_are_collected_for_durability(classes):
    sheet = _sheet(classes, "srd_barbarian", "srd_wizard")
    assert sheet.hit_dice == {"Barbarian": 12, "Wizard": 6}


def test_unknown_class_does_not_break_the_sheet(classes):
    """
    В партии может оказаться класс, которого нет в каталоге — хоумбрю или
    опечатка. Лист обязан посчитать остальных, а не упасть целиком.
    """
    sheet = build_party_sheet(
        [PartyMember("srd_cleric", 5), PartyMember("srd_dragonrider", 5)],
        classes=classes,
    )
    assert sheet.saves["wis"] == ("Cleric",)
    assert "srd_dragonrider" in sheet.unknown_classes


def test_empty_party_is_all_gaps(classes):
    sheet = build_party_sheet([], classes=classes)
    assert len(sheet.gaps) == 6


# ── Умения партии, посчитанные по спискам заклинаний ──────────────────────────
# Раньше роли брались из таблицы "класс -> что приносит", написанной руками.
# Она не различала волшебника 1 и 17 уровня, хотя это совершенно разные партии.


def _capabilities(classes, spells, *pairs):
    return build_party_sheet(
        [PartyMember(key, level) for key, level in pairs],
        classes=classes,
        spells=spells,
    )


def test_roles_come_from_spells_the_character_can_actually_reach(classes, spells_fixture):
    sheet = _capabilities(classes, spells_fixture, ("srd_cleric", 5))
    assert "Cleric" in sheet.roles["healing"]


def test_martials_have_no_healing_and_it_shows(classes, spells_fixture):
    sheet = _capabilities(
        classes, spells_fixture, ("srd_barbarian", 5), ("srd_rogue", 5)
    )
    assert sheet.roles["healing"] == ()
    assert "healing" in sheet.missing_roles


def test_a_higher_level_caster_brings_damage_types_a_lower_one_cannot(
    classes, spells_fixture
):
    """
    Огненный шар это 3 круг, и волшебнику 1 уровня он недоступен. Таблица
    классов эту разницу не видела вовсе, а она решает: против существа с
    сопротивлением огню важно знать, есть ли у партии что-то ещё.
    """
    junior = _capabilities(classes, spells_fixture, ("srd_wizard", 1))
    senior = _capabilities(classes, spells_fixture, ("srd_wizard", 5))

    assert "fire" not in junior.damage_types
    assert "fire" in senior.damage_types


def test_a_party_of_martials_deals_only_physical_damage(classes, spells_fixture):
    """
    Самый ценный вывод здесь отрицательный: сопротивление немагическому оружию
    встречается постоянно, и партии полезно знать, что обойти его нечем.
    """
    sheet = _capabilities(
        classes, spells_fixture, ("srd_barbarian", 5), ("srd_rogue", 5)
    )
    assert sheet.damage_types <= {"bludgeoning", "piercing", "slashing"}
    assert sheet.only_physical_damage is True


def test_a_caster_gives_the_party_a_way_around_physical_resistance(
    classes, spells_fixture
):
    sheet = _capabilities(
        classes, spells_fixture, ("srd_barbarian", 5), ("srd_wizard", 5)
    )
    assert sheet.only_physical_damage is False


def test_a_caster_without_spells_yet_still_counts_as_a_fighter(classes, spells_fixture):
    """Следопыт 1 уровня заклинаний не имеет, но урон партии приносит."""
    sheet = _capabilities(classes, spells_fixture, ("srd_ranger", 1))
    assert "Ranger" in sheet.roles["damage"]
