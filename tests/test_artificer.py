"""
Изобретатель — класс, которого нет в SRD.

Он из Tasha's Cauldron of Everything, поэтому каталог о нём не знает ничего:
ни кости хитов, ни спасбросков, и ни одно заклинание не помечено как его.
Механику приходится описывать самим — ровно тот случай, ради которого классы
сделаны таблицей данных, а не ветками кода.

Список заклинаний задаётся явно, ключами, а не фильтром по каталогу. Из 66
заклинаний Изобретателя в SRD есть 57: остальные девять пришли из Tasha's
вместе с классом и в открытый документ не попали.
"""

import pytest

from adapters.open5e_catalog import DEFAULT_SPELLS_PATH, load_spells
from core.advisors.spells import rank_spells
from core.class_profiles import (
    ARTIFICER,
    ARTILLERIST,
    max_spell_level,
    parse_class,
    prepared_or_known_count,
    profile,
)


@pytest.mark.parametrize("text, expected", [
    ("изобретатель", ARTIFICER),
    ("артифайсер", ARTIFICER),
    ("artificer", ARTIFICER),
    ("артиллерист", ARTILLERIST),
    ("artillerist", ARTILLERIST),
])
def test_class_names_are_understood(text, expected):
    assert parse_class(text) == expected


def test_artificer_casts_from_the_first_level():
    """
    Полукастер, но в отличие от следопыта и паладина колдует сразу: это его
    заметная особенность, и потерять её значит занизить персонажа на уровне.
    """
    assert max_spell_level(ARTIFICER, 1) == 1
    assert max_spell_level("srd_ranger", 1) == 0


@pytest.mark.parametrize("level, expected", [
    (1, 1), (4, 1), (5, 2), (9, 3), (13, 4), (17, 5), (20, 5),
])
def test_spell_circles_open_every_four_levels(level, expected):
    assert max_spell_level(ARTIFICER, level) == expected


def test_prepared_count_uses_half_the_level():
    """У Изобретателя это модификатор Интеллекта плюс ПОЛОВИНА уровня."""
    assert prepared_or_known_count(ARTIFICER, level=10, ability_modifier=4) == 9


def test_prepared_count_never_drops_below_one():
    assert prepared_or_known_count(ARTIFICER, level=1, ability_modifier=-1) == 1


def test_artificer_prepares_rather_than_learns():
    assert profile(ARTIFICER).preparation == "prepared"
    assert profile(ARTIFICER).ability == "int"


def test_spell_list_is_explicit_because_the_catalog_has_no_tag():
    """
    Ни одно заклинание в каталоге не помечено как артифайкерское, поэтому
    обычный отбор по списку класса дал бы пустоту.
    """
    assert profile(ARTIFICER).spell_keys, "список обязан быть задан явно"
    assert "srd_cure-wounds" in profile(ARTIFICER).spell_keys


def test_renamed_spells_are_in_the_list_under_srd_names():
    """
    В SRD именные заклинания переименованы: Bigby's Hand стал Arcane Hand.
    По исходному имени он не нашёлся бы, и список молча потерял бы запись.
    """
    assert "srd_arcane-hand" in profile(ARTIFICER).spell_keys
    assert "srd_faithful-hound" in profile(ARTIFICER).spell_keys


def test_artillerist_gets_its_own_spells_on_top():
    """Огненный шар доступен артиллеристу и недоступен обычному изобретателю."""
    assert "srd_fireball" in profile(ARTILLERIST).spell_keys
    assert "srd_fireball" not in profile(ARTIFICER).spell_keys


def test_artillerist_keeps_the_whole_base_list():
    assert profile(ARTIFICER).spell_keys <= profile(ARTILLERIST).spell_keys


# ── Проверки на полном каталоге ───────────────────────────────────────────────

full_catalog = pytest.mark.skipif(
    not DEFAULT_SPELLS_PATH.exists(),
    reason="каталог не загружен: uv run python -m tools.sync_catalog",
)


@full_catalog
@pytest.mark.parametrize("class_key", [ARTIFICER, ARTILLERIST])
def test_every_listed_spell_exists_in_the_catalog(class_key):
    """
    Список набран ключами вручную, и опечатка в слаге ничего не сломает
    заметно: заклинание просто тихо исчезнет из выдачи. Поэтому сверяемся.
    """
    known = {spell.key for spell in load_spells()}
    missing = sorted(profile(class_key).spell_keys - known)
    assert missing == [], f"таких ключей нет в каталоге: {missing}"


@full_catalog
def test_the_list_is_as_complete_as_the_open_document_allows():
    """
    В SRD есть 57 заклинаний Изобретателя из 66. Если число упадёт, значит
    список поредел незаметно, а не потому что источник изменился.
    """
    assert len(profile(ARTIFICER).spell_keys) == 57


@full_catalog
def test_the_advisor_offers_artificer_spells_and_only_them():
    catalog = load_spells()
    offered = {
        item.spell.name
        for item in rank_spells(catalog, class_key=ARTIFICER, character_level=9, party=[])
    }

    assert "Cure Wounds" in offered
    assert "Fly" in offered
    assert "Fireball" not in offered, "огненный шар только у артиллериста"
    assert "Magic Missile" not in offered, "это не его список"


@full_catalog
def test_the_artillerist_advisor_offers_the_subclass_spells():
    catalog = load_spells()
    offered = {
        item.spell.name
        for item in rank_spells(catalog, class_key=ARTILLERIST, character_level=9, party=[])
    }
    assert "Fireball" in offered
    assert "Cure Wounds" in offered
