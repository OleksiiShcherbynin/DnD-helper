"""
Запрос к советнику.

Один и тот же тип для всех советников: у вайлдшейпа он берёт уровень и описание
ситуации, у заклинаний — класс и состав партии. Общая форма запроса и есть то,
что позволяет интерфейсам перебирать реестр, ничего не зная про конкретные
советники.
"""

from dataclasses import dataclass, field

from core.models import PartyMember


@dataclass(frozen=True)
class AdviceRequest:
    """Кто спрашивает, в какой обстановке и с какой партией."""

    class_key: str
    level: int
    #: Подкласс: меняет и список заклинаний, и правила превращения.
    subclass_key: str | None = None
    situation_text: str = ""
    party: tuple[PartyMember, ...] = field(default_factory=tuple)
    top_n: int = 3
    allow_swarms: bool = False
    #: Доспех противника, если игрок может его прикинуть. Без него урон
    #: считается по костям, а не по попаданиям.
    target_ac: int | None = None
