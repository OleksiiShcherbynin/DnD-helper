"""Загрузка сохранённого каталога с диска."""

import json

import pytest

from adapters.open5e_catalog import (
    DEFAULT_SPELLS_PATH,
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

    spells = {spell.name: spell for spell in load_spells(path)}

    assert "Fireball" in spells
    assert spells["Fireball"].role == "damage"


def test_spells_outside_the_srd_are_added_to_the_catalog(tmp_path):
    """
    В открытом документе 319 заклинаний из примерно 360 в PHB. Привычные за
    столом Thorn Whip и Hex в него не попали, и без них список персонажа
    пришлось бы вести не полностью.
    """
    path = tmp_path / "spells.json"
    path.write_text("[]", encoding="utf-8")

    names = {spell.name for spell in load_spells(path)}

    assert "Thorn Whip" in names
    assert "Hex" in names


@pytest.mark.skipif(
    not DEFAULT_SPELLS_PATH.exists(),
    reason="каталог не загружен: uv run python -m tools.sync_catalog",
)
def test_every_rename_points_at_something_real():
    """
    Таблица переименований набрана вручную. Опечатка в ней не падает —
    заклинание просто перестаёт находиться, как будто его нет.
    """
    from core.spell_lists import SRD_RENAMES

    known = {spell.name for spell in load_spells()}
    missing = sorted(target for target in SRD_RENAMES.values() if target not in known)
    assert missing == [], f"переименования ведут в пустоту: {missing}"


@pytest.mark.skipif(
    not DEFAULT_SPELLS_PATH.exists(),
    reason="каталог не загружен: uv run python -m tools.sync_catalog",
)
def test_added_spells_do_not_shadow_catalog_ones():
    """
    Если заклинание уже есть в SRD, добавлять его вручную не нужно: две записи
    с одним именем сделают ввод неоднозначным и сломают то, что работало.
    """
    from core.spell_lists import EXTRA_SPELLS

    names = [spell.name for spell in load_spells()]
    for extra in EXTRA_SPELLS:
        assert names.count(extra.name) == 1, f"{extra.name} задвоился"


def test_missing_catalog_says_how_to_fix_it(tmp_path):
    """
    Приложение, запущенное до синхронизации, обязано сказать что делать,
    а не упасть с невнятным FileNotFoundError.
    """
    with pytest.raises(CatalogMissing, match="sync_catalog"):
        load_beasts(tmp_path / "нет-такого.json")
