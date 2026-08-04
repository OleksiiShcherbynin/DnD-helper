"""Загрузка сохранённого каталога с диска."""

import json

import pytest

from adapters.open5e_catalog import CatalogMissing, load_beasts


def test_loads_saved_catalog(tmp_path):
    raw = [
        {
            "key": "wolf",
            "name": "Wolf",
            "challenge_rating": 0.25,
            "armor_class": 13,
            "hit_points": 11,
            "speed": {"walk": 40},
            "environments": [{"key": "forest"}],
            "actions": [{"name": "Bite", "desc": "Hit: 7 (2d4 + 2) piercing damage."}],
        }
    ]
    path = tmp_path / "beasts.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    beasts = load_beasts(path)

    assert [beast.name for beast in beasts] == ["Wolf"]


def test_missing_catalog_says_how_to_fix_it(tmp_path):
    """
    Приложение, запущенное до синхронизации, обязано сказать что делать,
    а не упасть с невнятным FileNotFoundError.
    """
    with pytest.raises(CatalogMissing, match="sync_catalog"):
        load_beasts(tmp_path / "нет-такого.json")
