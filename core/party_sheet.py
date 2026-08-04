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

from core.class_profiles import CASTERS, max_spell_level, roles_of
from core.models import ABILITIES, ABILITY_NAMES, ClassData, PartyMember, Spell

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


#: Роли, отсутствие которых стоит отметить. Утилита сюда не входит: под неё
#: подпадает больше половины каталога, и «не хватает утилиты» ничего не значит.
_ROLES_WORTH_TRACKING = ("healing", "control", "damage", "defense")

#: Урон оружием. Его приносит любой, кто держит меч, и ценность этого знания
#: обратная: сопротивление немагическому оружию встречается постоянно, и важно
#: понимать, есть ли у партии хоть что-то помимо физического урона.
_PHYSICAL_DAMAGE = frozenset({"bludgeoning", "piercing", "slashing"})


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
    #: Роль -> названия классов, которые её закрывают.
    roles: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: Типы урона, которые партия умеет наносить.
    damage_types: frozenset[str] = field(default_factory=frozenset)

    @property
    def covered_saves(self) -> tuple[str, ...]:
        return tuple(ability for ability in ABILITIES if self.saves[ability])

    @property
    def missing_roles(self) -> tuple[str, ...]:
        return tuple(role for role in _ROLES_WORTH_TRACKING if not self.roles.get(role))

    @property
    def only_physical_damage(self) -> bool:
        """Нечем обойти сопротивление немагическому оружию."""
        return bool(self.damage_types) and self.damage_types <= _PHYSICAL_DAMAGE


def _reachable_spells(member: PartyMember, spells: Iterable[Spell]) -> list[Spell]:
    """Заклинания, до которых персонаж дотягивается на своём уровне."""
    if member.class_key not in CASTERS:
        return []
    cap = max_spell_level(member.class_key, member.level)
    if cap == 0:
        return []
    return [
        spell
        for spell in spells
        if member.class_key in spell.classes and spell.level <= cap
    ]


def _contribution(
    member: PartyMember, class_name: str, spells: Iterable[Spell]
) -> tuple[set[str], set[str]]:
    """
    Что участник приносит партии: роли и типы урона.

    У кастеров считается по заклинаниям, до которых он реально дотягивается,
    а не по таблице классов: волшебник 1 и 5 уровня приносят разное, а таблица
    этой разницы не видела вовсе.

    Кастер без доступных заклинаний — следопыт до 2 уровня — всё равно бьёт
    оружием, поэтому для него берётся роль из профиля класса.
    """
    reachable = _reachable_spells(member, spells)
    if reachable:
        roles = {spell.role for spell in reachable}
        damage = set().union(*(spell.damage_types for spell in reachable))
        return roles, damage

    # Никаких заклинаний: это боец, и урон он наносит оружием.
    return set(roles_of(member.class_key)), set(_PHYSICAL_DAMAGE)


def build_party_sheet(
    members: Iterable[PartyMember],
    *,
    classes: dict[str, ClassData],
    spells: Iterable[Spell] = (),
) -> PartySheet:
    """
    Собрать лист по составу партии.

    Вызывающая сторона передаёт отряд целиком, вместе с собой: это картина
    того, что есть у группы, а не того, чего не хватает одному персонажу.

    Класс, которого нет в каталоге, не роняет лист: остальных всё равно нужно
    посчитать, а неизвестный просто отмечается отдельно.
    """
    members = tuple(members)

    spells = tuple(spells)

    saves: dict[str, list[str]] = {ability: [] for ability in ABILITIES}
    # Отслеживаемые роли заводим заранее: тогда "никто не лечит" читается как
    # пустой список, а не как отсутствующий ключ, и вызывающей стороне не нужно
    # помнить, какие роли вообще бывают.
    roles: dict[str, list[str]] = {role: [] for role in _ROLES_WORTH_TRACKING}
    damage_types: set[str] = set()
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

        member_roles, member_damage = _contribution(member, data.name, spells)
        for role in member_roles:
            holders = roles.setdefault(role, [])
            if data.name not in holders:
                holders.append(data.name)
        damage_types |= member_damage

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
        roles={role: tuple(names) for role, names in roles.items()},
        damage_types=frozenset(damage_types),
    )
