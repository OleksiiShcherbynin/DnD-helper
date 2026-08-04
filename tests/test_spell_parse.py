"""
Разбор заклинаний и определение их роли.

Роль — основа совета «чего не хватает партии», поэтому она должна получаться
детерминированно. Структурированные поля источника для этого не годятся:
damage_roll заполнен лишь у 61 заклинания из 319. Поэтому роль выводится из
полей и текста вместе, а тесты собраны из заклинаний, роль которых бесспорна.
"""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import parse_spell

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "spells_sample.json"


@pytest.fixture(scope="module")
def raw():
    return {s["name"]: s for s in json.loads(FIXTURE.read_text(encoding="utf-8"))}


def test_parses_core_fields(raw):
    fireball = parse_spell(raw["Fireball"])
    assert fireball.name == "Fireball"
    assert fireball.level == 3
    assert fireball.school == "evocation"
    assert "srd_wizard" in fireball.classes
    assert fireball.concentration is False


def test_ritual_and_concentration_are_flagged(raw):
    assert parse_spell(raw["Detect Magic"]).ritual is True
    assert parse_spell(raw["Hold Person"]).concentration is True


def test_damage_spell_with_structured_dice(raw):
    assert parse_spell(raw["Fireball"]).role == "damage"


def test_damage_spell_whose_dice_field_is_empty(raw):
    """
    У Acid Splash damage_roll пуст, хотя урон есть. Опираться только на
    структурированное поле значило бы потерять четверть боевых заклинаний.
    """
    assert raw["Acid Splash"]["damage_roll"] == ""
    assert parse_spell(raw["Acid Splash"]).role == "damage"


def test_teleport_is_not_a_damage_spell(raw):
    """
    Ловушка: в тексте Dimension Door есть "4d6 force damage" — урон за неудачное
    приземление. Урон по тексту засчитывается только вместе со спасброском или
    броском атаки, которых здесь нет.
    """
    assert parse_spell(raw["Dimension Door"]).role != "damage"


def test_healing_spells_are_recognised(raw):
    assert parse_spell(raw["Cure Wounds"]).role == "healing"
    assert parse_spell(raw["Healing Word"]).role == "healing"


def test_blocking_healing_is_not_healing(raw):
    """
    Ловушка: Chill Touch мешает цели восстанавливать хиты, и в его тексте
    стоит "can't regain hit points". Это заклинание урона, а не лечения.
    """
    assert parse_spell(raw["Chill Touch"]).role == "damage"


def test_control_spells_are_recognised(raw):
    assert parse_spell(raw["Hold Person"]).role == "control"


def test_control_wins_over_incidental_damage(raw):
    """
    Ловушка: у Web в тексте есть "2d4 fire damage" — урон от подожжённой паутины.
    Партии Web нужен как контроль, и роль обязана это отражать.
    """
    assert parse_spell(raw["Web"]).role == "control"


def test_defensive_spells_are_recognised(raw):
    assert parse_spell(raw["Shield"]).role == "defense"


def test_everything_else_falls_back_to_utility(raw):
    assert parse_spell(raw["Detect Magic"]).role == "utility"


def test_auto_hitting_damage_needs_no_saving_throw(raw):
    """
    Magic Missile попадает автоматически: ни спасброска, ни броска атаки,
    и damage_roll пуст. Требовать спасброска для урона нельзя.
    """
    assert parse_spell(raw["Magic Missile"]).role == "damage"


def test_control_without_a_saving_throw_is_still_control(raw):
    """Sleep не даёт спасброска — он считает хиты, — но это чистый контроль."""
    assert parse_spell(raw["Sleep"]).role == "control"


def test_armor_spells_that_set_ac_are_defensive(raw):
    """У Mage Armor в тексте "base AC becomes", а не "bonus to AC"."""
    assert parse_spell(raw["Mage Armor"]).role == "defense"


def test_damage_that_heals_the_caster_is_still_damage(raw):
    """
    Vampiric Touch лечит заклинателя на половину нанесённого урона. Лечение
    здесь — надбавка к атаке, а не назначение заклинания.
    """
    assert raw["Vampiric Touch"]["damage_roll"] == "3d6"
    assert parse_spell(raw["Vampiric Touch"]).role == "damage"


@pytest.mark.parametrize("name", ["Protection from Poison", "Magic Circle"])
def test_protection_from_a_condition_is_not_control(raw, name):
    """
    Ловушка: у защитных заклинаний слова состояний встречаются в отрицании —
    "against being poisoned", "can't be charmed, frightened". Накладывает
    состояние одно заклинание, защищает от него совсем другое.
    """
    assert parse_spell(raw[name]).role != "control"


def test_removing_conditions_is_not_control(raw):
    """
    Lesser Restoration перечисляет состояния, потому что снимает их.
    Мгновенное действие без длительности — признак снятия, а не наложения.
    """
    assert parse_spell(raw["Lesser Restoration"]).role != "control"
