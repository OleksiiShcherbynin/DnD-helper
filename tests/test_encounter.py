"""
Оценка столкновения: драться или бежать.

Считается не по таблицам CR, а по боевой математике — сколько раундов партия
убивает противников и сколько противники убивают партию. Обычные калькуляторы
на это ответить не могут, потому что смотрят только на опыт за головы.

Стороны считаются с разной уверенностью, и это принципиально: монстры точно по
статблокам, партия приблизительно по классу и уровню.
"""

import pytest

from core.encounter import estimate_encounter
from core.models import PartyMember

PARTY = [
    PartyMember("srd_fighter", 5),
    PartyMember("srd_cleric", 5),
    PartyMember("srd_rogue", 5),
    PartyMember("srd_wizard", 5),
]


def _by_name(beasts, name):
    return next(beast for beast in beasts if beast.name == name)


def test_one_weak_enemy_is_no_threat(beasts, class_data):
    result = estimate_encounter(
        PARTY, [(_by_name(beasts, "Wolf"), 1)], classes=class_data
    )
    assert result.rounds_to_win == 1
    assert result.verdict == "лёгкая"


def test_a_horde_of_the_same_enemy_becomes_deadly(beasts, class_data):
    """Один волк — пустяк, тридцать волков — конец: считается именно количество."""
    result = estimate_encounter(
        PARTY, [(_by_name(beasts, "Wolf"), 30)], classes=class_data
    )
    assert result.verdict == "смертельно"
    assert result.rounds_to_fall is not None


def test_more_enemies_never_make_it_easier(beasts, class_data):
    few = estimate_encounter(PARTY, [(_by_name(beasts, "Brown Bear"), 1)], classes=class_data)
    many = estimate_encounter(PARTY, [(_by_name(beasts, "Brown Bear"), 6)], classes=class_data)
    assert many.rounds_to_win > few.rounds_to_win
    assert many.rounds_to_fall <= few.rounds_to_fall


def test_a_bigger_party_holds_out_longer(beasts, class_data):
    """
    Состав тот же, людей вдвое больше: средний AC не меняется, а запас хитов
    растёт, значит и держаться отряд обязан дольше.
    """
    enemies = [(_by_name(beasts, "Brown Bear"), 4)]
    small = estimate_encounter(PARTY, enemies, classes=class_data)
    large = estimate_encounter(PARTY * 2, enemies, classes=class_data)
    assert large.rounds_to_fall > small.rounds_to_fall


def test_party_numbers_are_marked_as_estimates(beasts, class_data):
    """
    Монстры посчитаны по статблокам, партия — по классу и уровню. Показывать
    это с одинаковой уверенностью нельзя, иначе оценке поверят больше, чем она
    заслуживает.
    """
    result = estimate_encounter(PARTY, [(_by_name(beasts, "Wolf"), 1)], classes=class_data)
    assert result.party.approximate is True
    assert result.enemies.approximate is False


def test_no_enemies_is_not_a_fight(beasts, class_data):
    result = estimate_encounter(PARTY, [], classes=class_data)
    assert result.rounds_to_win is None
    assert result.verdict == "нет противников"


def test_empty_party_cannot_win(beasts, class_data):
    result = estimate_encounter([], [(_by_name(beasts, "Wolf"), 1)], classes=class_data)
    assert result.rounds_to_win is None


def test_verdict_explains_itself(beasts, class_data):
    result = estimate_encounter(
        PARTY, [(_by_name(beasts, "Brown Bear"), 8)], classes=class_data
    )
    assert result.advice, "вердикт без объяснения бесполезен"
    assert str(result.rounds_to_win) in result.advice


@pytest.mark.parametrize("count", [1, 3, 10, 30])
def test_rounds_are_whole_numbers(beasts, class_data, count):
    result = estimate_encounter(
        PARTY, [(_by_name(beasts, "Wolf"), count)], classes=class_data
    )
    assert isinstance(result.rounds_to_win, int)
    assert isinstance(result.rounds_to_fall, int)
