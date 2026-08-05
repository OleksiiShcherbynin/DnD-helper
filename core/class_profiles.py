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

from core.spell_lists import ARTIFICER_SPELLS, ARTILLERIST_EXTRA

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
    #: С какого уровня класс вообще колдует. У следопыта со второго,
    #: у Изобретателя с первого, хотя оба полукастеры.
    spellcasting_from_level: int = 1
    #: На что делить уровень в формуле подготовки. У Изобретателя это половина
    #: уровня, у жреца и друида — полный.
    prepared_level_divisor: int = 1
    #: Явный список заклинаний ключами — для классов, которых каталог не
    #: размечает. Пусто — берём всё, что помечено списком этого класса.
    spell_keys: frozenset[str] | None = None
    #: Класс вне SRD: механика описана нами, а не взята из открытого документа.
    homebrew: bool = False


#: Изобретатель — класс вне SRD (Tasha's). Каталог о нём не знает ничего, ни
#: кости хитов, ни спасбросков, поэтому механика описана здесь, а список
#: заклинаний задан явно в core/spell_lists.py.
ARTIFICER = "hb_artificer"


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
            spellcasting_from_level=2,
        ),
        ClassProfile(
            key=ARTIFICER, name="Изобретатель", caster="half", preparation="prepared",
            ability="int", rituals=True, homebrew=True,
            party_roles=frozenset({"utility", "defense", "damage"}),
            spell_keys=ARTIFICER_SPELLS,
            prepared_level_divisor=2,
            notes="Вне SRD (Tasha's). Готовит Интеллект + половину уровня.",
        ),
    )
}

#: Кость хитов и владения спасбросками для классов вне SRD: каталог их не знает,
#: а листу партии они нужны. У Изобретателя d8, Телосложение и Интеллект.
EXTRA_CLASS_DATA: dict[str, tuple[int, frozenset[str]]] = {
    ARTIFICER: (8, frozenset({"con", "int"})),
}


# ── Подклассы ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Subclass:
    """
    Подкласс всегда принадлежит классу и сам по себе не существует.

    Раньше Артиллерист был заведён отдельным классом — так было дешевле, но
    игроку приходилось вводить подкласс вместо класса, и это враньё в модели.
    """

    key: str
    name: str
    parent: str
    #: Заклинания сверх списка класса.
    extra_spell_keys: frozenset[str] = frozenset()
    notes: str = ""


SUBCLASSES: dict[str, Subclass] = {
    subclass.key: subclass
    for subclass in (
        Subclass(
            key="artillerist", name="Артиллерист", parent=ARTIFICER,
            extra_spell_keys=ARTILLERIST_EXTRA,
            notes="Заклинания подкласса всегда подготовлены.",
        ),
        Subclass(
            key="moon", name="Круг Луны", parent="srd_druid",
            notes="Превращается в куда более крупных зверей: CR 1 со 2 уровня, "
                  "дальше уровень делённый на три.",
        ),
    )
}

_SUBCLASS_ALIASES: dict[str, str] = {
    "артиллерист": "artillerist", "artillerist": "artillerist",
    "круг луны": "moon", "луны": "moon", "луна": "moon", "moon": "moon",
}


def parse_subclass(text: str) -> str | None:
    """Ключ подкласса по названию. Незнакомое слово даёт None, а не догадку."""
    return _SUBCLASS_ALIASES.get((text or "").strip().lower())


def subclass_profile(subclass_key: str) -> Subclass:
    if subclass_key not in SUBCLASSES:
        raise KeyError(f"Неизвестный подкласс: {subclass_key}")
    return SUBCLASSES[subclass_key]


def spell_keys_for(class_key: str, subclass_key: str | None) -> frozenset[str] | None:
    """
    Полный список заклинаний с учётом подкласса.

    None означает, что список берётся из каталога по разметке класса — так
    устроены все классы SRD.

    Подкласс чужого класса — опечатка, а не сборка: принять её молча значит
    выдать персонажу чужой список заклинаний.
    """
    base = profile(class_key).spell_keys

    if subclass_key is None:
        return base

    subclass = subclass_profile(subclass_key)
    if subclass.parent != class_key:
        raise ValueError(
            f"{subclass.name} — подкласс класса "
            f"{display_name(subclass.parent)}, а не {display_name(class_key)}."
        )

    if not subclass.extra_spell_keys:
        return base
    return (base or frozenset()) | subclass.extra_spell_keys

#: Что приносят партии классы без заклинаний. Нужно, чтобы понимать состав,
#: а не чтобы советовать им — заклинаний у них нет.
NON_CASTER_ROLES: dict[str, frozenset[str]] = {
    "fighter": frozenset({"damage", "defense"}),
    "barbarian": frozenset({"damage", "defense"}),
    "rogue": frozenset({"damage", "utility"}),
    "monk": frozenset({"damage", "control"}),
    # Паладин попадает сюда как союзник: список его заклинаний источник не даёт,
    # но в покрытии ролей партии он участвует.
    "paladin": frozenset({"defense", "healing"}),
}

NON_CASTER_NAMES: dict[str, str] = {
    "fighter": "Воин",
    "barbarian": "Варвар",
    "rogue": "Плут",
    "monk": "Монах",
    "paladin": "Паладин",
}


def display_name(class_key: str) -> str:
    """Человеческое название класса для интерфейсов."""
    if class_key in CASTERS:
        return CASTERS[class_key].name
    return NON_CASTER_NAMES.get(class_key.removeprefix("srd_"), class_key)


#: Как игроки называют классы. Английские варианты нужны потому, что каталог
#: английский и половина стола говорит "wizard", а не "волшебник".
_CLASS_ALIASES: dict[str, str] = {
    "друид": "srd_druid", "druid": "srd_druid",
    "волшебник": "srd_wizard", "маг": "srd_wizard", "wizard": "srd_wizard",
    "жрец": "srd_cleric", "клерик": "srd_cleric", "cleric": "srd_cleric",
    "бард": "srd_bard", "bard": "srd_bard",
    "чародей": "srd_sorcerer", "сорк": "srd_sorcerer", "sorcerer": "srd_sorcerer",
    "колдун": "srd_warlock", "варлок": "srd_warlock", "warlock": "srd_warlock",
    "следопыт": "srd_ranger", "рейнджер": "srd_ranger", "ranger": "srd_ranger",
    "воин": "srd_fighter", "файтер": "srd_fighter", "fighter": "srd_fighter",
    "варвар": "srd_barbarian", "barbarian": "srd_barbarian",
    "плут": "srd_rogue", "вор": "srd_rogue", "разбойник": "srd_rogue", "rogue": "srd_rogue",
    "монах": "srd_monk", "monk": "srd_monk",
    "паладин": "srd_paladin", "paladin": "srd_paladin",
    # Вне SRD, но за столом встречается.
    "изобретатель": ARTIFICER, "артифайсер": ARTIFICER, "artificer": ARTIFICER,
}


def parse_class(text: str) -> str | None:
    """
    Ключ класса по названию. Незнакомое слово даёт None, а не догадку.

    Возвращает и кастеров, и остальных: последние нужны как союзники по партии,
    хотя советовать им нечего.
    """
    return _CLASS_ALIASES.get((text or "").strip().lower())

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
    current = profile(class_key)
    kind = current.caster

    if kind == "half":
        # Следопыт начинает со второго уровня, Изобретатель с первого, хотя
        # прогрессия кругов у них одна и та же.
        if character_level < current.spellcasting_from_level:
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

    return max(1, ability_modifier + level // current.prepared_level_divisor)
