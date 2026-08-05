"""
Боевая математика 5e.

Чистые функции: ни данных, ни сети, ни модели — всё выводится из правил
бросков. Это то, чего советникам не хватало с самого начала: урон считался в
вакууме, без ответа на вопрос «по кому», и форма со скоростью 60 обгоняла
форму, которая реально попадает.

Две тонкости правил, которые здесь важнее всего:

* у атак единица всегда промахивается, а двадцатка всегда попадает, поэтому
  шанс попасть никогда не выходит за 5–95%;
* у спасбросков такого правила нет, и невозможный спасбросок проваливается
  всегда, а не в 95% случаев.

Перепутать эти два случая — типичная ошибка калькуляторов, и она заметно
искажает оценку заклинаний против высоких DC.
"""

import math

#: Атака: как минимум одна грань промахивается (единица) и одна попадает (двадцатка).
_MIN_ATTACK_FACES = 1
_MAX_ATTACK_FACES = 19

_FACES = 20
#: Крит только на двадцатку.
_CRIT_FACES = 1


def _faces_that_land(attack_bonus: int, target_ac: int) -> int:
    """Сколько граней d20 дают попадание, с учётом автопромаха и автопопадания."""
    needed = target_ac - attack_bonus
    return min(_MAX_ATTACK_FACES, max(_MIN_ATTACK_FACES, _FACES + 1 - needed))


def hit_chance(attack_bonus: int, target_ac: int, advantage: int = 0) -> float:
    """
    Вероятность попасть. advantage: 1 — преимущество, -1 — помеха, 0 — обычный бросок.

    Преимущество это два броска, а не прибавка к бонусу: при базовых 55% выходит
    почти 80%, и подменять его фиксированным «+5» значит врать в расчёте.
    """
    single = _faces_that_land(attack_bonus, target_ac) / _FACES
    if advantage > 0:
        return 1 - (1 - single) ** 2
    if advantage < 0:
        return single**2
    return single


def crit_chance(advantage: int = 0) -> float:
    """Вероятность критического попадания."""
    single = _CRIT_FACES / _FACES
    if advantage > 0:
        return 1 - (1 - single) ** 2
    if advantage < 0:
        return single**2
    return single


def average_roll(dice_count: int, die_size: int) -> float:
    """Средний результат броска костей."""
    return dice_count * (die_size + 1) / 2


def attack_expected_damage(
    *,
    attack_bonus: int,
    dice_count: int,
    die_size: int,
    damage_bonus: int = 0,
    target_ac: int,
    advantage: int = 0,
) -> float:
    """
    Ожидаемый урон одной атаки по конкретной цели.

    При крите бросаются лишние кости, а модификатор не удваивается — удвоить
    всё значит завысить урон тем сильнее, чем больше бонус.
    """
    landed = hit_chance(attack_bonus, target_ac, advantage)
    crit = crit_chance(advantage)
    dice = average_roll(dice_count, die_size)

    ordinary = landed - crit
    return ordinary * (dice + damage_bonus) + crit * (2 * dice + damage_bonus)


def save_fail_chance(save_dc: int, save_bonus: int = 0) -> float:
    """
    Вероятность провалить спасбросок.

    Автоуспеха и автопровала здесь нет: в отличие от атак, двадцатка и единица
    на спасбросках ничего не решают. Поэтому против неподъёмного DC результат
    равен единице, а не 0.95.
    """
    needed = save_dc - save_bonus
    faces_that_save = min(_FACES, max(0, _FACES + 1 - needed))
    return 1 - faces_that_save / _FACES


def expected_round_damage(beast, *, target_ac: int, advantage: int = 0) -> float:
    """
    Ожидаемый урон зверя за раунд по цели с таким AC.

    Это и есть то, чего не хватало ранжированию форм: раньше урон брался как
    «сколько выйдет, если все атаки попадут», и форма с внушительными костями
    обгоняла форму, которая по этой цели действительно попадает.

    Берётся столько лучших атак, сколько существо делает за раунд. У зверей это
    один или два удара, у монстров бывает больше: дракон бьёт укусом и двумя
    когтями. Если разных атак меньше, чем ударов, лучшая повторяется.

    Урон от способностей со спасброском — драконье дыхание и прочее дыхание
    площадью — сюда не входит: это не атака. Для таких существ оценка занижена.
    """
    if not beast.attacks:
        return 0.0

    expected = sorted(
        (
            attack_expected_damage(
                attack_bonus=attack.to_hit,
                dice_count=attack.dice_count,
                die_size=attack.die_size,
                damage_bonus=attack.damage_bonus,
                target_ac=target_ac,
                advantage=advantage,
            )
            # Урон без разбора костей (фиксированный) считаем по среднему из текста.
            if attack.dice_count
            else attack.average * hit_chance(attack.to_hit, target_ac, advantage)
            for attack in beast.attacks
        ),
        reverse=True,
    )

    # Ударов может быть больше, чем разных атак: три удара при укусе и когтях
    # означают, что когтями бьют дважды.
    strikes = max(1, beast.attacks_per_round)
    best = [expected[min(index, len(expected) - 1)] for index in range(strikes)]
    return sum(best)


def rounds_to_defeat(hp: int, damage_per_round: float) -> int | None:
    """
    Сколько раундов нужно, чтобы свалить цель. None — если урона нет вовсе.

    Округление вверх: половины раунда не бывает.
    """
    if damage_per_round <= 0:
        return None
    return math.ceil(hp / damage_per_round)
