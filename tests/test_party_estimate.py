"""
Оценка боевых характеристик персонажа по классу и уровню.

Точных чисел у нас нет и не будет: просить у каждого игрока бонус атаки, AC и
урон оружия — верный способ, чтобы ботом перестали пользоваться. Поэтому всё
выводится из класса и уровня по механикам 5e, и это приближение.

Оценка намеренно занижает партию: кастеры считаются по заговорам, а не по
слотам. Вердикт «потянем» из-за этого ошибается в сторону осторожности, и это
правильное направление ошибки для вопроса «бежать или драться».
"""

import pytest

from core.party_estimate import estimate_member, proficiency_bonus
from core.models import PartyMember


@pytest.mark.parametrize("level, expected", [
    (1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (17, 6), (20, 6),
])
def test_proficiency_grows_every_four_levels(level, expected):
    assert proficiency_bonus(level) == expected


def test_hit_points_grow_with_level_and_hit_die(class_data):
    small = estimate_member(PartyMember("srd_wizard", 5), classes=class_data)
    large = estimate_member(PartyMember("srd_barbarian", 5), classes=class_data)

    assert large.hp > small.hp, "d12 держит больше, чем d6"

    junior = estimate_member(PartyMember("srd_wizard", 1), classes=class_data)
    assert small.hp > junior.hp


def test_armoured_classes_are_harder_to_hit(class_data):
    wizard = estimate_member(PartyMember("srd_wizard", 5), classes=class_data)
    barbarian = estimate_member(PartyMember("srd_barbarian", 5), classes=class_data)
    assert barbarian.ac > wizard.ac


def test_extra_attack_shows_up_at_level_five(class_data):
    """
    Второй удар на 5 уровне — самый резкий скачок урона у бойцов, и оценка
    обязана его видеть: без него партия пятого уровня выглядит вдвое слабее.
    """
    before = estimate_member(PartyMember("srd_barbarian", 4), classes=class_data)
    after = estimate_member(PartyMember("srd_barbarian", 5), classes=class_data)

    assert after.damage_per_round > before.damage_per_round * 1.6


def test_rogue_damage_grows_with_sneak_attack(class_data):
    junior = estimate_member(PartyMember("srd_rogue", 1), classes=class_data)
    senior = estimate_member(PartyMember("srd_rogue", 11), classes=class_data)
    assert senior.damage_per_round > junior.damage_per_round * 2


def test_attack_bonus_includes_proficiency(class_data):
    junior = estimate_member(PartyMember("srd_barbarian", 4), classes=class_data)
    senior = estimate_member(PartyMember("srd_barbarian", 5), classes=class_data)
    assert senior.attack_bonus > junior.attack_bonus


def test_unknown_class_still_gets_an_estimate(class_data):
    """
    Хоумбрю не должен ронять калькулятор: лучше усреднённый боец в расчёте,
    чем отказ считать столкновение целиком.
    """
    estimate = estimate_member(PartyMember("srd_dragonrider", 5), classes=class_data)
    assert estimate.hp > 0
    assert estimate.damage_per_round > 0
    assert estimate.approximate is True


def test_estimate_is_marked_as_an_estimate(class_data):
    """Цифры партии и цифры монстров нельзя показывать с одинаковой уверенностью."""
    assert estimate_member(PartyMember("srd_wizard", 5), classes=class_data).approximate