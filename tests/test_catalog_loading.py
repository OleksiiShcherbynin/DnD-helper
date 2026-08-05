"""Загрузка сохранённого каталога с диска."""

import json

import pytest

from adapters.open5e_catalog import (
    CatalogMissing,
    load_beasts,
    load_creatures,
    load_spells,
)


def _creature(key, name, type_key):
    return {
        "key": key,
        "name": name,
        "type": {"key": type_key},
        "challenge_rating": 0.25,
        "armor_class": 13,
        "hit_points": 11,
        "speed": {"walk": 40},
        "environments": [{"key": "forest"}],
        "actions": [{"name": "Bite", "desc": "Hit: 7 (2d4 + 2) piercing damage."}],
    }


def _catalog(tmp_path, *creatures):
    path = tmp_path / "creatures.json"
    path.write_text(json.dumps(list(creatures)), encoding="utf-8")
    return path


def test_loads_saved_catalog(tmp_path):
    path = _catalog(tmp_path, _creature("wolf", "Wolf", "beast"))
    assert [creature.name for creature in load_creatures(path)] == ["Wolf"]


def test_wild_shape_candidates_are_beasts_only(tmp_path):
    """
    Каталог общий для форм и для противников, поэтому отбор по типу — не
    оптимизация, а правило: превратиться можно только в зверя, но не в дракона.
    """
    path = _catalog(
        tmp_path,
        _creature("wolf", "Wolf", "beast"),
        _creature("red-dragon", "Adult Red Dragon", "dragon"),
    )

    assert [creature.name for creature in load_beasts(path)] == ["Wolf"]
    assert len(load_creatures(path)) == 2


def test_loads_saved_spells(tmp_path):
    raw = [
        {
            "key": "srd_fireball",
            "name": "Fireball",
            "level": 3,
            "school": {"key": "evocation"},
            "classes": [{"key": "srd_wizard"}],
            "damage_roll": "8d6",
            "desc": "A target takes 8d6 fire damage.",
        }
    ]
    path = tmp_path / "spells.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    spells = load_spells(path)

    assert [spell.name for spell in spells] == ["Fireball"]
    assert spells[0].role == "damage"


def test_missing_catalog_says_how_to_fix_it(tmp_path):
    """
    Приложение, запущенное до синхронизации, обязано сказать что делать,
    а не упасть с невнятным FileNotFoundError.
    """
    with pytest.raises(CatalogMissing, match="sync_catalog"):
        load_beasts(tmp_path / "нет-такого.json")
