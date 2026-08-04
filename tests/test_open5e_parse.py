"""
Разбор сырых данных Open5e в доменную модель.

Тесты гоняются на настоящем срезе API (fixtures/beasts_sample.json), а не на
выдуманных словарях — иначе они не поймают изменения формата и ловушки в данных.
"""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import parse_beast

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "beasts_sample.json"


@pytest.fixture(scope="module")
def raw():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return {c["name"]: c for c in data}


def test_parses_core_stats(raw):
    wolf = parse_beast(raw["Wolf"])
    assert wolf.name == "Wolf"
    assert wolf.cr == 0.25
    assert wolf.ac == 13
    assert wolf.hp == 11


def test_uses_real_speeds_not_derived_ones(raw):
    """
    Open5e отдаёт speed_all с производными значениями: climb и swim там проставлены
    как половина скорости ходьбы почти у всех зверей. Плавать по-настоящему умеют
    25 зверей из 98, а по speed_all их 96.

    Волк обязан оказаться БЕЗ скорости плавания, иначе друид ниже 4 уровня
    потеряет почти всех легальных зверей, и выглядеть это будет не как баг,
    а как "просто нет подходящих вариантов".
    """
    assert parse_beast(raw["Wolf"]).has_swimming is False
    assert parse_beast(raw["Giant Octopus"]).has_swimming is True


def test_detects_real_flight(raw):
    assert parse_beast(raw["Giant Eagle"]).has_flight is True
    assert parse_beast(raw["Wolf"]).has_flight is False


def test_damage_read_from_description_not_from_broken_fields(raw):
    """
    У атак в Open5e damage_bonus = null, а damage_type врёт ("Thunder" для укуса).
    Средний урон берётся из текста статблока: "Hit: 7 (2d4 + 2) piercing damage".
    Посчитанный по структурированным полям укус волка дал бы 5 вместо 7.
    """
    assert parse_beast(raw["Wolf"]).damage_per_round == 7.0


def test_multiattack_sums_two_best_attacks(raw):
    """Бурый медведь: Multiattack из укуса (8) и когтей (11)."""
    assert parse_beast(raw["Brown Bear"]).damage_per_round == 19.0


def test_environments_are_stored_as_keys(raw):
    assert "forest" in parse_beast(raw["Wolf"]).environments
