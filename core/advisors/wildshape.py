"""
Советник по Wild Shape: эвристическое ранжирование легальных форм.

Второй слой конвейера. Работает на уже отфильтрованном списке, поэтому здесь
не проверяются правила — сюда нелегальная форма попасть не может.

Оценка нормируется внутри пула кандидатов, а не по абсолютной шкале. Это даёт
осмысленный порядок без магических констант вроде "40 футов = 0.7 балла":
сравнивать имеет смысл только с тем, что реально доступно этому друиду.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from core.models import Beast
from core.situation import Situation

#: Вклад каждой характеристики в зависимости от цели.
#: Несколько целей в одном описании -> веса усредняются.
_WEIGHTS: dict[str, dict[str, float]] = {
    "default": {"damage": 0.35, "durability": 0.35, "mobility": 0.20, "senses": 0.10},
    "chase":   {"damage": 0.20, "durability": 0.20, "mobility": 0.50, "senses": 0.10},
    "escape":  {"damage": 0.10, "durability": 0.25, "mobility": 0.55, "senses": 0.10},
    "tank":    {"damage": 0.25, "durability": 0.55, "mobility": 0.10, "senses": 0.10},
    "damage":  {"damage": 0.55, "durability": 0.25, "mobility": 0.10, "senses": 0.10},
    "scout":   {"damage": 0.15, "durability": 0.15, "mobility": 0.30, "senses": 0.40},
    "swim":    {"damage": 0.20, "durability": 0.20, "mobility": 0.50, "senses": 0.10},
    "climb":   {"damage": 0.20, "durability": 0.20, "mobility": 0.50, "senses": 0.10},
}

#: Прибавка за совпадение местности со средой обитания зверя.
_TERRAIN_BONUS = 0.15


@dataclass(frozen=True)
class ScoredBeast:
    """Форма с оценкой и расшифровкой, посчитанными без обращения к модели."""

    beast: Beast
    score: float
    why: str


def _durability(beast: Beast) -> float:
    """
    Живучесть как условные "эффективные хиты".

    Каждое очко AC сверх 12 считаем примерно за 5% лишних хитов — грубое, но
    устойчивое приближение: точная формула требует знать бонус атаки врага,
    которого мы не знаем.
    """
    return beast.hp * (1 + (beast.ac - 12) * 0.05)


def _mobility(beast: Beast) -> float:
    """Лучшая из доступных скоростей."""
    return float(max(beast.speeds.values(), default=0))


def _senses(beast: Beast) -> float:
    """
    Ценность чувств для разведки.

    Слепое зрение и чувство вибрации работают там, где обычное зрение бесполезно,
    поэтому весят больше тёмного зрения.
    """
    return (
        beast.passive_perception
        + (5 if beast.darkvision else 0)
        + (8 if beast.blindsight else 0)
        + (8 if beast.tremorsense else 0)
    )


_METRICS = {
    "damage": lambda beast: beast.damage_per_round,
    "durability": _durability,
    "mobility": _mobility,
    "senses": _senses,
}


def _weights_for(situation: Situation) -> dict[str, float]:
    """Веса под цели из описания. Целей нет — берём сбалансированные."""
    applicable = [_WEIGHTS[goal] for goal in situation.goals if goal in _WEIGHTS]
    if not applicable:
        return _WEIGHTS["default"]
    return {
        metric: sum(weights[metric] for weights in applicable) / len(applicable)
        for metric in _WEIGHTS["default"]
    }


def _describe(beast: Beast, terrain_matched: bool) -> str:
    parts = [
        f"урон/раунд {beast.damage_per_round:g}",
        f"{beast.hp} HP при AC {beast.ac}",
        f"скорость {_mobility(beast):g}",
    ]
    if beast.has_special_senses:
        parts.append("особые чувства")
    if terrain_matched:
        parts.append("водится в этой местности")
    return ", ".join(parts)


def rank_beasts(beasts: Iterable[Beast], situation: Situation) -> list[ScoredBeast]:
    """Отсортировать легальные формы по пригодности к описанной ситуации."""
    pool = list(beasts)
    if not pool:
        return []

    weights = _weights_for(situation)
    peaks = {
        name: max(metric(beast) for beast in pool) or 1.0
        for name, metric in _METRICS.items()
    }

    scored = []
    for beast in pool:
        score = sum(
            weights[name] * (metric(beast) / peaks[name])
            for name, metric in _METRICS.items()
        )
        terrain_matched = bool(situation.terrains & set(beast.environments))
        if terrain_matched:
            score += _TERRAIN_BONUS
        scored.append(ScoredBeast(beast, round(score, 4), _describe(beast, terrain_matched)))

    return sorted(scored, key=lambda item: (-item.score, item.beast.name))
