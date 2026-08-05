"""
Чистые функции правил D&D 5e (SRD 5.1, редакция 2014).

Здесь нет ни сети, ни LLM, ни ввода-вывода — только правила, которые можно
проверить обычным тестом. Всё, что отсюда выходит, гарантированно легально,
поэтому нелегальный вариант физически не может попасть в выдачу советника.

Поддерживается базовый друид (круг земли). Круг луны сознательно не реализован.
"""

# Уровень друида -> максимальный CR зверя для Wild Shape (PHB/SRD, таблица класса).
_CR_CAPS: tuple[tuple[int, float], ...] = (
    (8, 1.0),
    (4, 0.5),
    (2, 0.25),
)

WILD_SHAPE_MIN_LEVEL = 2

# До этих уровней друид не может принимать форму зверя с соответствующей скоростью.
_FLIGHT_MIN_LEVEL = 8
_SWIMMING_MIN_LEVEL = 4


#: Круг Луны: CR 1 со 2 уровня, а с 6-го — уровень делённый на три. Это его
#: определяющая черта, и без неё он неотличим от обычного друида.
MOON_SUBCLASS = "moon"
_MOON_SCALING_FROM_LEVEL = 6
_MOON_LEVEL_DIVISOR = 3


def wild_shape_cr_cap(
    druid_level: int, subclass_key: str | None = None
) -> float | None:
    """
    Максимальный CR зверя, доступного друиду для Wild Shape.

    Возвращает None, если персонаж ещё не умеет превращаться (до 2 уровня).
    """
    if druid_level < WILD_SHAPE_MIN_LEVEL:
        return None

    if subclass_key == MOON_SUBCLASS:
        if druid_level < _MOON_SCALING_FROM_LEVEL:
            return 1.0
        return float(druid_level // _MOON_LEVEL_DIVISOR)

    for min_level, cap in _CR_CAPS:
        if druid_level >= min_level:
            return cap
    return None


def wild_shape_allows_flight(druid_level: int) -> bool:
    """Может ли друид принять форму зверя, у которого есть скорость полёта."""
    return druid_level >= _FLIGHT_MIN_LEVEL


def wild_shape_allows_swimming(druid_level: int) -> bool:
    """Может ли друид принять форму зверя, у которого есть скорость плавания."""
    return druid_level >= _SWIMMING_MIN_LEVEL
