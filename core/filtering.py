"""
Отбор легальных кандидатов — первый из трёх слоёв советника.

Всё, что этот слой отсеял, дальше не существует: ни эвристика, ни LLM его уже
не увидят. Поэтому модель физически не может предложить нелегальную форму —
не потому что ей запретили, а потому что такого варианта нет во входных данных.
"""

from collections.abc import Iterable

from core.models import Creature
from core.rules import (
    wild_shape_allows_flight,
    wild_shape_allows_swimming,
    wild_shape_cr_cap,
)


def legal_wild_shape_beasts(
    beasts: Iterable[Creature], druid_level: int, *, allow_swarms: bool = False
) -> list[Creature]:
    """
    Звери, в которых друид указанного уровня имеет право превратиться.

    Рои по умолчанию отсекаются. Формально они проходят и по типу, и по CR,
    но превращение в рой большинство мастеров не разрешает, а в выдаче рои
    ещё и вытесняют осмысленные варианты несколькими почти одинаковыми
    строками. Решение спорное, поэтому оставлено переключателем, а не зашито.
    """
    cap = wild_shape_cr_cap(druid_level)
    if cap is None:
        return []

    flight_ok = wild_shape_allows_flight(druid_level)
    swimming_ok = wild_shape_allows_swimming(druid_level)

    return [
        beast
        for beast in beasts
        if beast.cr <= cap
        and (flight_ok or not beast.has_flight)
        and (swimming_ok or not beast.has_swimming)
        and (allow_swarms or not beast.is_swarm)
    ]
