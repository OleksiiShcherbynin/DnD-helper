"""
Отбор легальных кандидатов — первый из трёх слоёв советника.

Всё, что этот слой отсеял, дальше не существует: ни эвристика, ни LLM его уже
не увидят. Поэтому модель физически не может предложить нелегальную форму —
не потому что ей запретили, а потому что такого варианта нет во входных данных.
"""

from collections.abc import Iterable

from core.models import Beast
from core.rules import (
    wild_shape_allows_flight,
    wild_shape_allows_swimming,
    wild_shape_cr_cap,
)


def legal_wild_shape_beasts(beasts: Iterable[Beast], druid_level: int) -> list[Beast]:
    """Звери, в которых друид указанного уровня имеет право превратиться."""
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
    ]
