"""
Оценка столкновения: драться или бежать.

Обычные калькуляторы складывают опыт за головы и сверяются с таблицей порогов.
Отсюда и их дурная слава: «смертельно» на бой, который партия сносит за раунд.
Здесь считается то, что игрока действительно волнует — сколько раундов нужно,
чтобы убить противников, и сколько они продержатся против партии.

Стороны считаются с разной уверенностью, и это показывается явно:

* противники точно, по статблокам SRD — HP, AC и бонусы атаки настоящие;
* партия приблизительно, по классу и уровню, с занижением (см. party_estimate).

Бой считается проигранным не когда общий запас хитов дойдёт до нуля, а когда
партия потеряет половину: враги бьют по одному, и к этому моменту кто-то уже
лежит, а урон партии просел. Считать до последнего хита — самая частая ошибка
такого расчёта, из-за неё бой с драконом выглядит выполнимым.

Ещё одно упрощение: обе стороны предполагаются бьющими каждый раунд, без учёта
инициативы, лечения, контроля и отступлений.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from core.combat import expected_round_damage, hit_chance, rounds_to_defeat
from core.models import ClassData, Creature, PartyMember
from core.party_estimate import estimate_member

#: Отношение «раундов на победу» к «раундам до падения». Меньше единицы —
#: партия успевает раньше.
_VERDICTS = (
    (0.5, "лёгкая"),
    (0.8, "по силам"),
    (1.0, "тяжёлая"),
)
_DEADLY = "смертельно"

#: Доля хитов, после потери которой бой считается проигранным. Враги бьют по
#: одному, поэтому к половине запаса кто-то уже лежит, а урон партии просел.
_BREAKING_POINT = 0.5

_ADVICE = {
    "лёгкая": "Запас большой, можно не тратить ресурсы.",
    "по силам": "Драка ваша, но без глупостей.",
    "тяжёлая": "Кто-то ляжет. Нужны контроль, лечение и отход на случай неудачи.",
    _DEADLY: "В лоб не выйдет. Засада, местность, переговоры или отступление.",
}


@dataclass(frozen=True)
class Side:
    """Сводка по одной стороне боя."""

    hp: int
    armour_class: int
    damage_per_round: float
    #: True — цифры выведены из класса и уровня, а не взяты из статблоков.
    approximate: bool


@dataclass(frozen=True)
class EncounterEstimate:
    party: Side
    enemies: Side
    rounds_to_win: int | None
    rounds_to_fall: int | None
    verdict: str
    advice: str


def _average(values: list[int], default: int) -> int:
    return round(sum(values) / len(values)) if values else default


def _verdict(rounds_to_win: float, rounds_to_fall: float) -> str:
    ratio = rounds_to_win / rounds_to_fall
    for threshold, name in _VERDICTS:
        if ratio < threshold:
            return name
    return _DEADLY


def estimate_encounter(
    party: Iterable[PartyMember],
    enemies: Iterable[tuple[Creature, int]],
    *,
    classes: dict[str, ClassData],
) -> EncounterEstimate:
    """
    Прикинуть исход боя.

    enemies — пары «существо, сколько их».
    """
    estimates = [estimate_member(member, classes=classes) for member in party]
    enemies = [(creature, count) for creature, count in enemies if count > 0]

    party_ac = _average([item.ac for item in estimates], default=14)
    enemy_ac = _average(
        [creature.ac for creature, _ in enemies for _ in range(1)], default=13
    )

    party_hp = sum(item.hp for item in estimates)
    enemy_hp = sum(creature.hp * count for creature, count in enemies)

    # Урон партии: заявленный урон умножается на шанс попасть по этому доспеху.
    party_damage = sum(
        item.damage_per_round * hit_chance(item.attack_bonus, enemy_ac)
        for item in estimates
    )
    enemy_damage = sum(
        expected_round_damage(creature, target_ac=party_ac) * count
        for creature, count in enemies
    )

    breaking_point = party_hp * _BREAKING_POINT

    rounds_to_win = rounds_to_defeat(enemy_hp, party_damage) if enemies else None
    rounds_to_fall = (
        rounds_to_defeat(int(breaking_point), enemy_damage) if estimates else None
    )

    if not enemies:
        verdict = "нет противников"
    elif rounds_to_win is None or rounds_to_fall is None:
        verdict = _DEADLY
    else:
        # Вердикт считается по точным величинам, а не по округлённым раундам:
        # округление вверх на обеих сторонах съедает разницу именно там, где
        # вердикт переключается, и бой 2.1 против 2.5 раундов выглядел бы ничьей.
        verdict = _verdict(enemy_hp / party_damage, breaking_point / enemy_damage)

    advice = _ADVICE.get(verdict, "Считать нечего.")
    if rounds_to_win is not None and rounds_to_fall is not None:
        advice = (
            f"Убить их — примерно {rounds_to_win} раунд(ов), "
            f"продержаться — примерно {rounds_to_fall}. {advice}"
        )

    return EncounterEstimate(
        party=Side(party_hp, party_ac, round(party_damage, 1), approximate=True),
        enemies=Side(enemy_hp, enemy_ac, round(enemy_damage, 1), approximate=False),
        rounds_to_win=rounds_to_win,
        rounds_to_fall=rounds_to_fall,
        verdict=verdict,
        advice=advice,
    )
