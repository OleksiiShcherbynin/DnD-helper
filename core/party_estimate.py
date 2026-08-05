"""
Оценка боевых характеристик персонажа по классу и уровню.

Точных чисел у нас нет: просить у каждого игрока бонус атаки, AC, хиты и урон
оружия — верный способ, чтобы ботом перестали пользоваться. Поэтому всё
выводится из класса и уровня по механикам 5e.

Это приближение, и оно намеренно занижает партию:

* кастеры считаются по заговорам, а не по слотам — реальный волшебник в
  тяжёлом бою потратит Огненный шар и ударит куда сильнее;
* не учитываются магические предметы, баффы, боевые стили и способности
  подклассов, которые почти всегда добавляют, а не убавляют.

Направление ошибки выбрано осознанно: на вопрос «драться или бежать» лучше
ошибиться в сторону осторожности. Монстры при этом считаются точно по
статблокам, и в выводе эта разница показывается явно.
"""

from dataclasses import dataclass

from core.class_profiles import ARTIFICER, display_name, profile
from core.models import ClassData, PartyMember

def ability_modifier(score: int) -> int:
    """Модификатор характеристики: (значение - 10), делённое на два вниз."""
    return (score - 10) // 2


#: Модификатор основной характеристики, когда её не ввели. Обычный путь:
#: начать с +3 и поднимать повышениями характеристик до потолка в +5.
def _primary_modifier(level: int) -> int:
    if level >= 8:
        return 5
    if level >= 4:
        return 4
    return 3


#: Телосложение у большинства персонажей около +2 — на этом держится расчёт хитов.
_CONSTITUTION_MODIFIER = 2


@dataclass(frozen=True)
class Archetype:
    """Как класс дерётся. Это данные, а не ветки кода: добавить класс — строка."""

    ac: int
    style: str
    #: Уровень -> сколько атак. Второй удар на 5 уровне — самый резкий скачок
    #: урона за всю игру, и не заметить его нельзя.
    attacks_by_level: tuple[tuple[int, int], ...] = ((1, 1),)


_ARCHETYPES: dict[str, Archetype] = {
    "srd_fighter": Archetype(ac=18, style="weapon", attacks_by_level=((1, 1), (5, 2), (11, 3), (20, 4))),
    "srd_paladin": Archetype(ac=18, style="weapon", attacks_by_level=((1, 1), (5, 2))),
    "srd_barbarian": Archetype(ac=15, style="weapon", attacks_by_level=((1, 1), (5, 2))),
    "srd_ranger": Archetype(ac=16, style="weapon", attacks_by_level=((1, 1), (5, 2))),
    "srd_monk": Archetype(ac=16, style="monk"),
    "srd_rogue": Archetype(ac=15, style="sneak"),
    # Жрец в тяжёлых доспехах со щитом, друид ограничен немагическим металлом.
    "srd_cleric": Archetype(ac=18, style="caster"),
    "srd_druid": Archetype(ac=15, style="caster"),
    "srd_bard": Archetype(ac=15, style="caster"),
    "srd_warlock": Archetype(ac=14, style="caster"),
    "srd_wizard": Archetype(ac=13, style="caster"),
    "srd_sorcerer": Archetype(ac=13, style="caster"),
    # Изобретатель носит средние доспехи и щит, отсюда AC выше, чем у кастеров.
    ARTIFICER: Archetype(ac=17, style="caster"),
}

#: Неизвестный класс: усреднённый боец. Хоумбрю не должен ронять калькулятор —
#: лучше грубая оценка в расчёте, чем отказ считать столкновение целиком.
_FALLBACK = Archetype(ac=15, style="weapon", attacks_by_level=((1, 1), (5, 2)))
_FALLBACK_HIT_DIE = 8

#: Средний бросок кости оружия (d8) и заговора (d10).
_WEAPON_DIE_AVERAGE = 4.5
_CANTRIP_DIE_AVERAGE = 5.5
_SNEAK_DIE_AVERAGE = 3.5


@dataclass(frozen=True)
class MemberEstimate:
    """Прикидка по одному персонажу. Всегда приблизительная — см. модуль."""

    name: str
    level: int
    ac: int
    hp: int
    attack_bonus: int
    damage_per_round: float
    approximate: bool = True


def proficiency_bonus(level: int) -> int:
    """Бонус мастерства: +2 на 1 уровне и по единице каждые четыре уровня."""
    return 2 + (max(1, level) - 1) // 4


def _attacks_at(archetype: Archetype, level: int) -> int:
    count = 1
    for threshold, attacks in archetype.attacks_by_level:
        if level >= threshold:
            count = attacks
    return count


def _cantrip_dice(level: int) -> int:
    """Заговоры усиливаются на 5, 11 и 17 уровнях."""
    if level >= 17:
        return 4
    if level >= 11:
        return 3
    if level >= 5:
        return 2
    return 1


def _damage_per_round(archetype: Archetype, level: int, modifier: int) -> float:
    if archetype.style == "sneak":
        # Одна атака плюс скрытая атака: по кости d6 на каждый нечётный уровень.
        sneak = ((level + 1) // 2) * _SNEAK_DIE_AVERAGE
        return _WEAPON_DIE_AVERAGE + modifier + sneak

    if archetype.style == "monk":
        # Удар оружием, безоружный удар и ещё один бонусным действием.
        return 3 * (_WEAPON_DIE_AVERAGE + modifier)

    if archetype.style == "caster":
        # Только заговор, и без модификатора характеристики: Fire Bolt и Sacred
        # Flame его не добавляют, это умеет лишь Eldritch Blast с инвокацией.
        # Слоты сюда тоже не входят, и оценка от этого занижена.
        return _cantrip_dice(level) * _CANTRIP_DIE_AVERAGE

    return _attacks_at(archetype, level) * (_WEAPON_DIE_AVERAGE + modifier)


def _casting_ability(class_key: str) -> str | None:
    """Какая характеристика у класса основная. У неизвестных — ничего."""
    try:
        return profile(class_key).ability
    except KeyError:
        return None


def estimate_member(
    member: PartyMember, *, classes: dict[str, ClassData]
) -> MemberEstimate:
    """
    Собрать боевые числа персонажа.

    Каждое берётся по цепочке: явно введённое, потом выведенное из
    характеристик, потом оценка по классу и уровню. Это единственное место,
    где решается «откуда взялась цифра».

    AC из характеристик не выводится: он зависит от доспеха, которого мы не
    знаем, и Ловкость 20 у латника не значит ничего. Его либо вводят, либо
    берётся типичный для класса.
    """
    archetype = _ARCHETYPES.get(member.class_key, _FALLBACK)
    data = classes.get(member.class_key)
    hit_die = data.hit_die if data else _FALLBACK_HIT_DIE
    level = max(1, member.level)
    sheet = member.stats

    primary = _casting_ability(member.class_key)
    modifier = (
        ability_modifier(sheet.abilities[primary])
        if primary and primary in sheet.abilities
        else _primary_modifier(level)
    )
    constitution = (
        ability_modifier(sheet.abilities["con"])
        if "con" in sheet.abilities
        else _CONSTITUTION_MODIFIER
    )

    # Хиты: полная кость на первом уровне, среднее на остальных, плюс Телосложение.
    average_per_level = hit_die / 2 + 1
    hp = int(hit_die + (level - 1) * average_per_level + constitution * level)

    return MemberEstimate(
        name=data.name if data else display_name(member.class_key),
        level=level,
        ac=sheet.ac if sheet.ac is not None else archetype.ac,
        hp=sheet.hp if sheet.hp is not None else hp,
        attack_bonus=(
            sheet.attack_bonus
            if sheet.attack_bonus is not None
            else proficiency_bonus(level) + modifier
        ),
        damage_per_round=(
            sheet.damage_per_round
            if sheet.damage_per_round is not None
            else round(_damage_per_round(archetype, level, modifier), 1)
        ),
        approximate=not sheet.combat_is_complete,
    )
