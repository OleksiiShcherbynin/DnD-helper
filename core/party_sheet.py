"""
Лист партии: что отряд умеет и чего ему не хватает.

Главное здесь — спасброски. В 5e они решают, кого выключают из боя одним
заклинанием, и дыра в них дорога: партия без владения Мудростью ложится от
Hold Person целиком. Заметить это при подготовке дешевле, чем на игре.

В отличие от списка союзников, лист считает партию целиком, включая того, кто
спрашивает: это картина отряда, а не дыры вокруг одного персонажа.

Данные о владениях берутся из каталога SRD, а не пишутся руками: все двенадцать
наборов сверены с PHB и совпадают.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field

from core.models import ABILITIES, ABILITY_NAMES, ClassData, PartyMember

#: Чем грозит отсутствие владения и насколько часто это встречается в бою.
#: Порядок внутри словаря задаёт порядок вывода дыр: Мудрость и Ловкость
#: случаются постоянно, Интеллект и Харизма почти никогда, и показывать их
#: с одинаковой тревожностью значит обесценить обе.
_SAVE_THREATS: dict[str, str] = {
    "wis": "Hold Person, Fear, Dominate Person — самые частые и самые болезненные эффекты",
    "dex": "Fireball, Lightning Bolt, драконье дыхание — урон по площади",
    "con": "удержание концентрации, яды, Thunderwave",
    "str": "захваты, Web, принудительное перемещение",
    "int": "Feeblemind и псионика — встречается редко",
    "cha": "Banishment и планарные эффекты — встречается редко",
}


@dataclass(frozen=True)
class SaveGap:
    """Спасбросок, которым не владеет никто в партии."""

    ability: str
    text: str


@dataclass(frozen=True)
class PartySheet:
    """Сводка по отряду."""

    members: tuple[PartyMember, ...]
    #: Характеристика -> названия классов, владеющих спасброском.
    saves: dict[str, tuple[str, ...]]
    #: Название класса -> размер кости хитов.
    hit_dice: dict[str, int]
    gaps: tuple[SaveGap, ...] = ()
    #: Классы, которых не нашлось в каталоге: хоумбрю или опечатка.
    unknown_classes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def covered_saves(self) -> tuple[str, ...]:
        return tuple(ability for ability in ABILITIES if self.saves[ability])


def build_party_sheet(
    members: Iterable[PartyMember], *, classes: dict[str, ClassData]
) -> PartySheet:
    """
    Собрать лист по составу партии.

    Вызывающая сторона передаёт отряд целиком, вместе с собой: это картина
    того, что есть у группы, а не того, чего не хватает одному персонажу.

    Класс, которого нет в каталоге, не роняет лист: остальных всё равно нужно
    посчитать, а неизвестный просто отмечается отдельно.
    """
    members = tuple(members)

    saves: dict[str, list[str]] = {ability: [] for ability in ABILITIES}
    hit_dice: dict[str, int] = {}
    unknown: list[str] = []

    for member in members:
        data = classes.get(member.class_key)
        if data is None:
            unknown.append(member.class_key)
            continue
        hit_dice[data.name] = data.hit_die
        for ability in data.saving_throws:
            if data.name not in saves[ability]:
                saves[ability].append(data.name)

    gaps = tuple(
        SaveGap(
            ability=ability,
            text=f"Спасброски {ABILITY_NAMES[ability]} не тянет никто: {threat}.",
        )
        for ability, threat in _SAVE_THREATS.items()
        if not saves[ability]
    )

    return PartySheet(
        members=members,
        saves={ability: tuple(names) for ability, names in saves.items()},
        hit_dice=hit_dice,
        gaps=gaps,
        unknown_classes=tuple(unknown),
    )
