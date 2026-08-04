"""
Классы как данные.

Первый из двух механизмов расширения: разница между «подготавливающими»,
«знающими» и волшебником с книгой — это разные значения полей одной строки,
а не разные ветки кода. Добавить класс, подкласс или хоумбрю = добавить строку.

Механики классов берутся отсюда, а не из каталога: Open5e даёт только
принадлежность заклинания списку класса, а прогрессию слотов и формулы
подготовки не даёт вовсе.

Паладина здесь нет намеренно. В данных SRD его заклинания не размечены:
Divine Favor помечен жреческим, а Branding Smite не имеет классов вообще.
Советовать паладину, не имея его списка, значит выдавать неверные советы.
"""

from dataclasses import dataclass, field
from typing import Literal

CasterKind = Literal["full", "half", "pact"]
Preparation = Literal["prepared", "known", "spellbook"]

#: Сколько заклинаний знает бард/чародей/колдун/следопыт на каждом уровне.
#: Таблицы из PHB; у «знающих» число не зависит от характеристики.
_BARD_KNOWN = (4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 15, 16, 18, 19, 19, 20, 22, 22, 22)
_SORCERER_KNOWN = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 12, 13, 13, 14, 14, 15, 15, 15, 15)
_WARLOCK_KNOWN = (2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 11, 11, 12, 12, 13, 13, 14, 14, 15, 15)
_RANGER_KNOWN = (0, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11)


@dataclass(frozen=True)
class ClassProfile:
    """Всё, что нужно знать о классе, чтобы советовать ему заклинания."""

    key: str
    name: str
    caster: CasterKind
    preparation: Preparation
    ability: Literal["int", "wis", "cha"]
    #: Что класс приносит партии. Используется, чтобы искать дыры в составе.
    party_roles: frozenset[str]
    #: Для «знающих» — таблица по уровням. Для остальных None.
    known_table: tuple[int, ...] | None = None
    rituals: bool = False
    notes: str = ""


CASTERS: dict[str, ClassProfile] = {
    profile.key: profile
    for profile in (
        ClassProfile(
            key="srd_wizard", name="Волшебник", caster="full", preparation="spellbook",
            ability="int", rituals=True,
            party_roles=frozenset({"damage", "control", "utility"}),
            notes="Готовит из книги: модификатор Интеллекта + уровень волшебника.",
        ),
        ClassProfile(
            key="srd_cleric", name="Жрец", caster="full", preparation="prepared",
            ability="wis", rituals=True,
            party_roles=frozenset({"healing", "defense", "control"}),
        ),
        ClassProfile(
            key="srd_druid", name="Друид", caster="full", preparation="prepared",
            ability="wis", rituals=True,
            party_roles=frozenset({"control", "healing", "damage"}),
        ),
        ClassProfile(
            key="srd_bard", name="Бард", caster="full", preparation="known",
            ability="cha", rituals=True, known_table=_BARD_KNOWN,
            party_roles=frozenset({"control", "utility", "healing"}),
        ),
        ClassProfile(
            key="srd_sorcerer", name="Чародей", caster="full", preparation="known",
            ability="cha", known_table=_SORCERER_KNOWN,
            party_roles=frozenset({"damage"}),
        ),
        ClassProfile(
            key="srd_warlock", name="Колдун", caster="pact", preparation="known",
            ability="cha", known_table=_WARLOCK_KNOWN,
            party_roles=frozenset({"damage", "utility"}),
            notes="Ячейки Договора восстанавливаются на коротком отдыхе.",
        ),
        ClassProfile(
            key="srd_ranger", name="Следопыт", caster="half", preparation="known",
            ability="wis", known_table=_RANGER_KNOWN,
            party_roles=frozenset({"utility", "damage"}),
        ),
    )
}

#: Что приносят партии классы без заклинаний. Нужно, чтобы понимать состав,
#: а не чтобы советовать им — заклинаний у них нет.
NON_CASTER_ROLES: dict[str, frozenset[str]] = {
    "fighter": frozenset({"damage", "defense"}),
    "barbarian": frozenset({"damage", "defense"}),
    "rogue": frozenset({"damage", "utility"}),
    "monk": frozenset({"damage", "control"}),
    "paladin": frozenset({"defense", "healing"}),
}

#: Колдун получает Таинственный арканум 6-9 круга отдельно от ячеек Договора,
#: здесь он не учитывается.
_PACT_MAX_SPELL_LEVEL = 5
_HALF_CASTER_MIN_LEVEL = 2


def roles_of(class_key: str) -> frozenset[str]:
    """
    Что класс приносит партии.

    Понимает и кастеров, и остальных: в партии сидит воин и разбойник, и без
    них картина покрытия ролей была бы неполной.
    """
    if class_key in CASTERS:
        return CASTERS[class_key].party_roles
    return NON_CASTER_ROLES.get(class_key.removeprefix("srd_"), frozenset())


def profile(class_key: str) -> ClassProfile:
    """Профиль класса. Неизвестный класс — ошибка, а не молчаливый пропуск."""
    if class_key not in CASTERS:
        raise KeyError(
            f"Неизвестный класс: {class_key}. Известные: {sorted(CASTERS)}"
        )
    return CASTERS[class_key]


def max_spell_level(class_key: str, character_level: int) -> int:
    """Максимальный круг заклинаний, доступный персонажу. 0 — заклинаний ещё нет."""
    kind = profile(class_key).caster

    if kind == "half":
        if character_level < _HALF_CASTER_MIN_LEVEL:
            return 0
        return min(5, (character_level + 3) // 4)

    if character_level < 1:
        return 0

    by_level = min(9, (character_level + 1) // 2)
    if kind == "pact":
        return min(_PACT_MAX_SPELL_LEVEL, by_level)
    return by_level


def prepared_or_known_count(
    class_key: str, level: int, ability_modifier: int
) -> int:
    """
    Сколько заклинаний персонаж держит наготове.

    У «подготавливающих» это модификатор характеристики плюс уровень, и список
    можно менять после долгого отдыха. У «знающих» — фиксированная таблица,
    и выбор постоянный, поэтому цена ошибки у них выше.
    """
    current = profile(class_key)

    if current.known_table is not None:
        index = max(0, min(level, len(current.known_table)) - 1)
        return current.known_table[index]

    return max(1, ability_modifier + level)
