"""
Разбор данных о классах из каталога.

Спасброски и кость хитов приходят из SRD, а не пишутся руками: это единственное,
что источник даёт по классам надёжно — все 12 наборов спасбросков сверены с PHB
и совпадают. Прогрессию слотов и формулы подготовки он по-прежнему не даёт,
они остаются в core/class_profiles.py.
"""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import parse_class_data

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "classes_sample.json"


@pytest.fixture(scope="module")
def raw():
    return {c["name"]: c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))}


def test_parses_key_and_hit_die(raw):
    barbarian = parse_class_data(raw["Barbarian"])
    assert barbarian.key == "srd_barbarian"
    assert barbarian.hit_die == 12


def test_hit_die_is_a_number_not_a_string(raw):
    """В источнике "D12" строкой, а считать по ней придётся числом."""
    assert parse_class_data(raw["Wizard"]).hit_die == 6


def test_saving_throws_become_short_ability_codes(raw):
    """
    Источник пишет "Constitution", а внутри удобнее "con": так они сравниваются
    со спасбросками, которые требуют заклинания.
    """
    assert parse_class_data(raw["Barbarian"]).saving_throws == frozenset({"str", "con"})
    assert parse_class_data(raw["Cleric"]).saving_throws == frozenset({"wis", "cha"})
    assert parse_class_data(raw["Rogue"]).saving_throws == frozenset({"dex", "int"})


def test_every_class_has_exactly_two_saving_throws(raw):
    """Правило 5e: у каждого класса ровно два владения спасбросками."""
    for name in raw:
        assert len(parse_class_data(raw[name]).saving_throws) == 2, name
