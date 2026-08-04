"""
Адаптер каталога Open5e: сырой JSON -> доменные модели.

Здесь же лечатся известные дефекты источника, каждый из них закрыт тестом
в tests/test_open5e_parse.py:

1. speed_all содержит производные значения (climb и swim в половину скорости
   ходьбы почти у всех зверей). Настоящие скорости лежат в speed.
2. У атак damage_bonus = null, а damage_type врёт: укус волка помечен как
   "Thunder" при "piercing" в описании. Урон берётся из текста статблока.
"""

import re

from core.models import Beast

#: "Hit: 7 (2d4 + 2) piercing damage" -> 7. Первое число и есть средний урон.
_HIT_AVERAGE = re.compile(r"Hit:\s*(\d+)")

#: Скорости, которые нас интересуют. Всё остальное (crawl, hover) — служебное.
_SPEED_KEYS = ("walk", "fly", "swim", "climb", "burrow")


def _attack_averages(actions: list[dict]) -> list[float]:
    """Средний урон каждой атакующей акции, взятый из её описания."""
    averages = []
    for action in actions or ():
        match = _HIT_AVERAGE.search(action.get("desc") or "")
        if match:
            averages.append(float(match.group(1)))
    return averages


def _damage_per_round(actions: list[dict]) -> float:
    """
    Оценка урона за раунд.

    Если у зверя есть Multiattack, берём сумму двух лучших атак — все звери SRD
    с мультиатакой бьют ровно дважды. Иначе берём лучшую одиночную атаку.
    Это приближение: условный урон (яд при провале спасброска) не учитывается.
    """
    averages = sorted(_attack_averages(actions), reverse=True)
    if not averages:
        return 0.0

    has_multiattack = any(
        (action.get("name") or "").lower() == "multiattack" for action in actions or ()
    )
    if has_multiattack:
        return sum(averages[:2])
    return averages[0]


def parse_beast(raw: dict) -> Beast:
    """Собрать доменного зверя из сырого ответа Open5e."""
    speed = raw.get("speed") or {}
    speeds = {
        key: speed[key]
        for key in _SPEED_KEYS
        if isinstance(speed.get(key), int) and speed[key] > 0
    }

    return Beast(
        key=raw["key"],
        name=raw["name"],
        cr=float(raw["challenge_rating"]),
        ac=int(raw["armor_class"]),
        hp=int(raw["hit_points"]),
        speeds=speeds,
        environments=[env["key"] for env in raw.get("environments") or ()],
        damage_per_round=_damage_per_round(raw.get("actions")),
        darkvision=raw.get("darkvision_range") or 0,
        blindsight=raw.get("blindsight_range") or 0,
        tremorsense=raw.get("tremorsense_range") or 0,
        passive_perception=raw.get("passive_perception") or 0,
    )
