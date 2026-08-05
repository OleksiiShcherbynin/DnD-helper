"""
Введённые вручную числа и цепочка отката.

Каждое число персонажа берётся по порядку: явно введённое, потом выведенное
из характеристик, потом оценка по классу и уровню. Заполнять можно сколько
угодно и в любом порядке — незаполненное продолжает считаться как раньше.

Это единственное место, где решается «откуда взялась цифра». Проверки «если
задано» по всему проекту были бы тем же самым, только рассыпанным.
"""

import pytest

from core.models import PartyMember, Stats
from core.party_estimate import ability_modifier, estimate_member


@pytest.mark.parametrize("score, expected", [
    (1, -5), (8, -1), (10, 0), (11, 0), (14, 2), (16, 3), (20, 5), (30, 10),
])
def test_ability_modifier_follows_the_rules(score, expected):
    assert ability_modifier(score) == expected


def test_nothing_entered_behaves_exactly_as_before(class_data):
    """Главное требование: пустой лист не должен ничего менять."""
    plain = estimate_member(PartyMember("srd_wizard", 5), classes=class_data)
    empty = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats()), classes=class_data
    )
    assert plain == empty


def test_entered_numbers_win_over_everything(class_data):
    sheet = Stats(ac=21, hp=99, attack_bonus=11, damage_per_round=42.0)
    estimate = estimate_member(
        PartyMember("srd_wizard", 5, stats=sheet), classes=class_data
    )

    assert (estimate.ac, estimate.hp) == (21, 99)
    assert estimate.attack_bonus == 11
    assert estimate.damage_per_round == 42.0


def test_a_single_entered_number_does_not_disturb_the_rest(class_data):
    """Заполнить одно поле должно быть безопасно."""
    default = estimate_member(PartyMember("srd_wizard", 5), classes=class_data)
    with_ac = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(ac=18)), classes=class_data
    )

    assert with_ac.ac == 18
    assert with_ac.hp == default.hp
    assert with_ac.damage_per_round == default.damage_per_round


def test_constitution_changes_hit_points(class_data):
    """Оценка исходила из Телосложения +2 — настоящее значение её уточняет."""
    tough = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(abilities={"con": 18})),
        classes=class_data,
    )
    frail = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(abilities={"con": 8})),
        classes=class_data,
    )
    assert tough.hp > frail.hp


def test_the_casting_ability_changes_the_attack_bonus(class_data):
    """У волшебника это Интеллект, и подставлять надо именно его."""
    smart = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(abilities={"int": 20})),
        classes=class_data,
    )
    average = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(abilities={"int": 10})),
        classes=class_data,
    )
    assert smart.attack_bonus - average.attack_bonus == 5


def test_an_unrelated_ability_leaves_the_attack_bonus_alone(class_data):
    """Харизма волшебнику к попаданию ничего не даёт."""
    default = estimate_member(PartyMember("srd_wizard", 5), classes=class_data)
    charming = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(abilities={"cha": 20})),
        classes=class_data,
    )
    assert charming.attack_bonus == default.attack_bonus


def test_the_estimate_says_how_much_of_it_was_entered(class_data):
    """
    Показывать выведенное и введённое с одинаковой уверенностью нельзя:
    иначе оценке поверят больше, чем она заслуживает.
    """
    guessed = estimate_member(PartyMember("srd_wizard", 5), classes=class_data)
    assert guessed.approximate is True

    known = estimate_member(
        PartyMember(
            "srd_wizard", 5,
            stats=Stats(ac=18, hp=40, attack_bonus=7, damage_per_round=20.0),
        ),
        classes=class_data,
    )
    assert known.approximate is False


def test_partly_filled_is_still_an_estimate(class_data):
    partial = estimate_member(
        PartyMember("srd_wizard", 5, stats=Stats(ac=18)), classes=class_data
    )
    assert partial.approximate is True
