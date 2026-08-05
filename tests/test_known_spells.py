"""
Заклинания, которые персонаж действительно может применить.

До сих пор лист партии считал роли по всему списку класса. Для жреца и друида
это близко к правде — они готовят из полного списка. Для барда и чародея это
враньё: они знают несколько заклинаний из сотни доступных, и «контроль закрыт»
про них означало лишь, что контроль в принципе существует в их классе.

Разделения на «известные» и «подготовленные» нет: для вопроса «чего партии не
хватает» важно только то, что персонаж может применить сегодня.
"""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import parse_spell
from core.models import PartyMember
from core.party_sheet import build_party_sheet

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "spells_sample.json"


@pytest.fixture(scope="module")
def spells():
    return [parse_spell(item) for item in json.loads(FIXTURE.read_text(encoding="utf-8"))]


@pytest.fixture(scope="module")
def keys(spells):
    return {spell.name: spell.key for spell in spells}


def _sheet(class_data, spells, *members):
    return build_party_sheet(members, classes=class_data, spells=spells)


def test_without_a_list_nothing_changes(class_data, spells):
    """Пустой список означает «не знаю», а не «не умеет ничего»."""
    sheet = _sheet(class_data, spells, PartyMember("srd_cleric", 5))
    assert "Cleric" in sheet.roles["healing"]


def test_a_known_list_replaces_the_class_list(class_data, spells, keys):
    """
    Жрец, который взял только Огненный шар... точнее, только контроль — лечить
    он не может, сколько бы лечения ни было в списке его класса.
    """
    sheet = _sheet(
        class_data, spells,
        PartyMember("srd_cleric", 5, spell_keys=frozenset({keys["Hold Person"]})),
    )

    assert sheet.roles["control"] == ("Cleric",)
    assert sheet.roles["healing"] == (), "лечения он не брал"
    assert "healing" in sheet.missing_roles


def test_damage_types_come_from_the_known_list_too(class_data, spells, keys):
    wide = _sheet(class_data, spells, PartyMember("srd_wizard", 9))
    narrow = _sheet(
        class_data, spells,
        PartyMember("srd_wizard", 9, spell_keys=frozenset({keys["Magic Missile"]})),
    )

    assert len(narrow.damage_types) < len(wide.damage_types)
    assert "force" in narrow.damage_types


def test_spells_outside_the_list_are_ignored(class_data, spells, keys):
    """
    Ключ, которого нет в каталоге, не должен ни падать, ни притворяться
    заклинанием: список персонажа мог пережить обновление каталога.
    """
    sheet = _sheet(
        class_data, spells,
        PartyMember(
            "srd_cleric", 5,
            spell_keys=frozenset({keys["Cure Wounds"], "srd_such-spell-does-not-exist"}),
        ),
    )
    assert sheet.roles["healing"] == ("Cleric",)


def test_a_list_beyond_the_reachable_circle_is_still_respected(class_data, spells, keys):
    """
    Если игрок говорит, что заклинание у него есть, спорить не с чем: свитки,
    предметы и хоумбрю мастера в правила круга не укладываются.
    """
    sheet = _sheet(
        class_data, spells,
        PartyMember("srd_cleric", 1, spell_keys=frozenset({keys["Dimension Door"]})),
    )
    assert sheet.members[0].spell_keys
