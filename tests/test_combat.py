"""
Боевая математика 5e.

Чистые функции без данных и без сети: всё выводится из правил бросков.
Именно этого движка не хватало советникам — урон считался в вакууме, без
ответа на вопрос «по кому», поэтому форма со скоростью 60 обгоняла форму,
которая реально попадает.
"""

import pytest

from core.combat import (
    attack_expected_damage,
    average_roll,
    crit_chance,
    expected_round_damage,
    hit_chance,
    rounds_to_defeat,
    save_fail_chance,
)


def test_hit_chance_counts_the_faces_that_land():
    """Бонус +5 против AC 15: нужно выбросить 10 и выше, это 11 граней из 20."""
    assert hit_chance(attack_bonus=5, target_ac=15) == pytest.approx(0.55)


def test_natural_one_always_misses():
    """Даже при невозможном перевесе единица промахивается — максимум 95%."""
    assert hit_chance(attack_bonus=30, target_ac=5) == pytest.approx(0.95)


def test_natural_twenty_always_hits():
    """И наоборот: против неподъёмного AC остаётся 5% на двадцатку."""
    assert hit_chance(attack_bonus=0, target_ac=40) == pytest.approx(0.05)


def test_advantage_is_not_a_flat_bonus():
    """
    Преимущество — это два броска, а не прибавка. При базовых 55% выходит
    почти 80%, и подменять это фиксированным бонусом значит врать в расчёте.
    """
    assert hit_chance(attack_bonus=5, target_ac=15, advantage=1) == pytest.approx(0.7975)


def test_disadvantage_squares_the_miss():
    assert hit_chance(attack_bonus=5, target_ac=15, advantage=-1) == pytest.approx(0.3025)


def test_crit_chance_rises_with_advantage():
    assert crit_chance() == pytest.approx(0.05)
    assert crit_chance(advantage=1) == pytest.approx(0.0975)
    assert crit_chance(advantage=-1) == pytest.approx(0.0025)


def test_average_roll_of_dice():
    assert average_roll(2, 6) == pytest.approx(7.0)
    assert average_roll(1, 8) == pytest.approx(4.5)


def test_crits_double_the_dice_but_not_the_modifier():
    """
    Правило 5e: при крите бросаются лишние кости, модификатор не удваивается.
    Удвоить всё — завысить урон тем сильнее, чем больше бонус.
    """
    with_crits = attack_expected_damage(
        attack_bonus=5, dice_count=1, die_size=8, damage_bonus=3, target_ac=15
    )
    # Без учёта критов: 0.55 * (4.5 + 3) = 4.125.
    # Криты добавляют только лишние кости: 0.05 * 4.5 = 0.225.
    assert with_crits == pytest.approx(0.55 * 7.5 + 0.05 * 4.5)


def test_expected_damage_drops_as_armour_rises():
    soft = attack_expected_damage(
        attack_bonus=5, dice_count=1, die_size=8, damage_bonus=3, target_ac=10
    )
    hard = attack_expected_damage(
        attack_bonus=5, dice_count=1, die_size=8, damage_bonus=3, target_ac=20
    )
    assert soft > hard


def test_save_fail_chance_is_the_mirror_of_success():
    """DC 15 против модификатора +3: спасается на 12 и выше, это 9 граней."""
    assert save_fail_chance(save_dc=15, save_bonus=3) == pytest.approx(0.55)


def test_saves_have_no_automatic_success_or_failure():
    """
    В отличие от атак, на спасбросках двадцатка и единица ничего не решают.
    Поэтому невозможный спасбросок проваливается всегда, а не в 95% случаев.
    """
    assert save_fail_chance(save_dc=25, save_bonus=0) == pytest.approx(1.0)
    assert save_fail_chance(save_dc=5, save_bonus=10) == pytest.approx(0.0)


def test_rounds_to_defeat_rounds_up():
    """Половину раунда не бывает: 31 хит при 10 уроне это четыре раунда."""
    assert rounds_to_defeat(hp=30, damage_per_round=10) == 3
    assert rounds_to_defeat(hp=31, damage_per_round=10) == 4


def test_no_damage_means_never():
    assert rounds_to_defeat(hp=30, damage_per_round=0) is None


# ── Урон за раунд против конкретной цели ──────────────────────────────────────


def test_round_damage_falls_as_the_target_gets_harder_to_hit(beasts):
    wolf = next(beast for beast in beasts if beast.name == "Wolf")
    assert expected_round_damage(wolf, target_ac=10) > expected_round_damage(wolf, target_ac=18)


def test_multiattack_counts_two_attacks(beasts):
    """
    У медведя укус и когти, и Multiattack велит бить обоими. Один укус даёт
    заметно меньше, чем связка.
    """
    bear = next(beast for beast in beasts if beast.name == "Brown Bear")
    both = expected_round_damage(bear, target_ac=13)
    best_single = max(
        attack_expected_damage(
            attack_bonus=attack.to_hit,
            dice_count=attack.dice_count,
            die_size=attack.die_size,
            damage_bonus=attack.damage_bonus,
            target_ac=13,
        )
        for attack in bear.attacks
    )
    assert both > best_single * 1.5


def test_single_attack_beast_uses_only_its_best(beasts):
    """У волка одна атака — удваивать её нечем."""
    wolf = next(beast for beast in beasts if beast.name == "Wolf")
    bite = wolf.attacks[0]
    assert expected_round_damage(wolf, target_ac=13) == pytest.approx(
        attack_expected_damage(
            attack_bonus=bite.to_hit,
            dice_count=bite.dice_count,
            die_size=bite.die_size,
            damage_bonus=bite.damage_bonus,
            target_ac=13,
        )
    )


def test_advantage_raises_round_damage(beasts):
    wolf = next(beast for beast in beasts if beast.name == "Wolf")
    assert expected_round_damage(wolf, target_ac=15, advantage=1) > expected_round_damage(
        wolf, target_ac=15
    )
