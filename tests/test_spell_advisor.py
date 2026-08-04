"""
Советник по заклинаниям: что взять с учётом того, что уже есть у партии.

Главная мысль — не «какое заклинание лучшее вообще», а «какого умения партии
не хватает». Одно и то же заклинание должно оцениваться по-разному в зависимости
от того, закрыта роль союзниками или нет.
"""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import DEFAULT_SPELLS_PATH, load_spells, parse_spell
from core.advisors.spells import PartyMember, rank_spells

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "spells_sample.json"


@pytest.fixture(scope="module")
def spells():
    return [parse_spell(s) for s in json.loads(FIXTURE.read_text(encoding="utf-8"))]


def _names(scored):
    return [item.spell.name for item in scored]


def test_only_spells_from_the_class_list_are_offered(spells):
    """Fireball есть у волшебника и чародея, но не у жреца."""
    offered = _names(rank_spells(spells, class_key="srd_cleric", character_level=20, party=[]))
    assert "Fireball" not in offered
    assert "Cure Wounds" in offered


def test_spells_above_the_reachable_circle_are_excluded(spells):
    """Волшебник 1 уровня не дотягивается ни до 2, ни до 3 круга."""
    offered = _names(rank_spells(spells, class_key="srd_wizard", character_level=1, party=[]))
    assert "Magic Missile" in offered
    assert "Web" not in offered, "2 круг недоступен"
    assert "Fireball" not in offered, "3 круг недоступен"


def test_ranger_gets_nothing_at_level_1(spells):
    """Следопыт — полукастер, заклинания появляются со 2 уровня."""
    assert rank_spells(spells, class_key="srd_ranger", character_level=1, party=[]) == []


def test_uncovered_role_outranks_a_covered_one(spells):
    """
    Барду в партии без лекаря лечение нужнее, чем в партии, где уже есть жрец
    и друид. Проверяем именно смену порядка, а не абсолютные баллы.
    """
    without_healer = [PartyMember("fighter", 5), PartyMember("rogue", 5)]
    with_healers = [PartyMember("srd_cleric", 5), PartyMember("srd_druid", 5)]

    lonely = _names(rank_spells(spells, class_key="srd_bard", character_level=3, party=without_healer))
    crowded = _names(rank_spells(spells, class_key="srd_bard", character_level=3, party=with_healers))

    assert lonely.index("Cure Wounds") < crowded.index("Cure Wounds")


def test_explanation_names_the_gap_it_closes(spells):
    party = [PartyMember("fighter", 5), PartyMember("rogue", 5)]
    top = rank_spells(spells, class_key="srd_bard", character_level=3, party=party)[0]

    assert top.why, "совет без обоснования бесполезен"
    assert any(word in top.why.lower() for word in ("никто", "закрыт", "роль"))


def test_results_are_sorted_by_score(spells):
    scored = rank_spells(spells, class_key="srd_wizard", character_level=9, party=[])
    assert [item.score for item in scored] == sorted(
        (item.score for item in scored), reverse=True
    )


def test_unknown_class_is_rejected_loudly(spells):
    with pytest.raises(KeyError):
        rank_spells(spells, class_key="srd_dragonrider", character_level=5, party=[])


# ── Проверки на полном каталоге ───────────────────────────────────────────────
# Фикстура из четырнадцати заклинаний слишком мала, чтобы поймать перекос:
# в настоящем каталоге на роль utility приходится больше половины записей.

full_catalog = pytest.mark.skipif(
    not DEFAULT_SPELLS_PATH.exists(),
    reason="каталог не загружен: uv run python -m tools.sync_catalog",
)


@full_catalog
def test_party_composition_actually_changes_the_advice():
    """
    Ради этого советник и существует. Ранняя версия выдавала волшебнику
    одинаковую пятёрку и в отряде из воина с разбойником, и в отряде из трёх
    кастеров, потому что утилита вытесняла всё остальное.
    """
    catalog = load_spells()
    mixed = [PartyMember("fighter"), PartyMember("srd_cleric"), PartyMember("rogue")]
    casters = [PartyMember("srd_bard"), PartyMember("srd_druid"), PartyMember("srd_cleric")]

    with_mixed = _names(rank_spells(catalog, class_key="srd_wizard", character_level=5, party=mixed))[:5]
    with_casters = _names(rank_spells(catalog, class_key="srd_wizard", character_level=5, party=casters))[:5]

    assert with_mixed != with_casters, f"обе партии получили одно и то же: {with_mixed}"


@full_catalog
def test_utility_does_not_crowd_out_the_real_roles():
    """
    Утилита — это остаток классификации, а не роль, которой партии не хватает.
    Отряду без контроля нужен контроль, а не Water Breathing.
    """
    catalog = load_spells()
    party = [PartyMember("fighter"), PartyMember("srd_cleric"), PartyMember("rogue")]

    top = rank_spells(catalog, class_key="srd_wizard", character_level=5, party=party)[:5]

    assert any(item.spell.role != "utility" for item in top), (
        f"вся пятёрка — утилита: {[i.spell.name for i in top]}"
    )
