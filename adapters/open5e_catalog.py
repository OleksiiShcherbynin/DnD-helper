"""
Адаптер каталога Open5e: сырой JSON -> доменные модели.

Здесь же лечатся известные дефекты источника, каждый из них закрыт тестом
в tests/test_open5e_parse.py:

1. speed_all содержит производные значения (climb и swim в половину скорости
   ходьбы почти у всех зверей). Настоящие скорости лежат в speed.
2. У атак damage_bonus = null, а damage_type врёт: укус волка помечен как
   "Thunder" при "piercing" в описании. Урон берётся из текста статблока.
"""

import json
from pathlib import Path
import re

from core.models import Attack, Creature, ClassData, Spell, SpellRole

#: Куда tools/sync_catalog.py кладёт загруженный каталог.
_CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "catalog"
#: Один файл на всех существ: и зверей для Wild Shape, и монстров как
#: противников. Отбор по типу дешевле, чем второй файл и вторая загрузка.
DEFAULT_CREATURES_PATH = _CATALOG_DIR / "creatures.json"
DEFAULT_SPELLS_PATH = _CATALOG_DIR / "spells.json"
DEFAULT_CLASSES_PATH = _CATALOG_DIR / "classes.json"

BEAST_TYPE = "beast"


class CatalogMissing(FileNotFoundError):
    """Каталог ещё не загружен."""

#: "Hit: 7 (2d4 + 2) piercing damage" -> 7. Первое число и есть средний урон.
_HIT_AVERAGE = re.compile(r"Hit:\s*(\d+)")

#: Оттуда же кости и прибавка: "(2d4 + 2)". У 101 атаки из 118 они в скобках,
#: у остальных урон фиксированный и скобок нет.
_HIT_DICE = re.compile(r"Hit:\s*\d+\s*\((\d+)d(\d+)(?:\s*([+-])\s*(\d+))?\)")

#: Скорости, которые нас интересуют. Всё остальное (crawl, hover) — служебное.
_SPEED_KEYS = ("walk", "fly", "swim", "climb", "burrow")


def _attack_averages(actions: list[dict]) -> list[float]:
    """Средний урон каждой атакующей акции, взятый из её описания."""
    averages = []
    for action in actions or ():
        match = _HIT_AVERAGE.search(action.get("desc") or "")
        if match:
            averages.append(float(match.group(1)))
    return averages


def _is_multiattack(action: dict) -> bool:
    return (action.get("name") or "").lower() == "multiattack"


def _parse_attacks(actions: list[dict]) -> list[Attack]:
    """
    Разобрать атаки статблока.

    Бонус атаки берётся из структурированного поля: по всем 118 атакам каталога
    оно совпало с текстом, в отличие от damage_bonus и damage_type, которые
    у источника битые. Кости достаются из описания.

    Multiattack пропускается: своего урона у него нет, это указание бить дважды.
    """
    attacks = []
    for action in actions or ():
        desc = action.get("desc") or ""
        average = _HIT_AVERAGE.search(desc)
        if average is None or _is_multiattack(action):
            continue

        structured = (action.get("attacks") or [{}])[0]
        dice = _HIT_DICE.search(desc)
        count, size, bonus = 0, 0, 0
        if dice:
            count, size = int(dice.group(1)), int(dice.group(2))
            bonus = int(dice.group(4) or 0) * (-1 if dice.group(3) == "-" else 1)

        attacks.append(
            Attack(
                name=action.get("name") or "Атака",
                to_hit=int(structured.get("to_hit_mod") or 0),
                dice_count=count,
                die_size=size,
                damage_bonus=bonus,
                average=float(average.group(1)),
            )
        )
    return attacks


def _damage_per_round(actions: list[dict]) -> float:
    """
    Оценка урона за раунд.

    Если у зверя есть Multiattack, берём сумму двух лучших атак — все звери SRD
    с мультиатакой бьют ровно дважды. Иначе берём лучшую одиночную атаку.
    Это приближение: условный урон (яд при провале спасброска) не учитывается.
    """
    averages = sorted(_attack_averages(actions), reverse=True)
    if not averages:
        return 0.0

    has_multiattack = any(_is_multiattack(action) for action in actions or ())
    if has_multiattack:
        return sum(averages[:2])
    return averages[0]


def parse_creature(raw: dict) -> Creature:
    """Собрать доменного зверя из сырого ответа Open5e."""
    actions = raw.get("actions") or []
    speed = raw.get("speed") or {}
    speeds = {
        key: speed[key]
        for key in _SPEED_KEYS
        if isinstance(speed.get(key), int) and speed[key] > 0
    }

    return Creature(
        key=raw["key"],
        name=raw["name"],
        creature_type=(raw.get("type") or {}).get("key", ""),
        cr=float(raw["challenge_rating"]),
        ac=int(raw["armor_class"]),
        hp=int(raw["hit_points"]),
        speeds=speeds,
        environments=[env["key"] for env in raw.get("environments") or ()],
        damage_per_round=_damage_per_round(actions),
        attacks=_parse_attacks(actions),
        has_multiattack=any(_is_multiattack(action) for action in actions),
        darkvision=raw.get("darkvision_range") or 0,
        blindsight=raw.get("blindsight_range") or 0,
        tremorsense=raw.get("tremorsense_range") or 0,
        passive_perception=raw.get("passive_perception") or 0,
        is_swarm=raw["name"].lower().startswith("swarm of"),
    )


# ── Заклинания ────────────────────────────────────────────────────────────────

#: Кости в тексте: "2d4", "8d6".
_DICE = re.compile(r"\b\d+d\d+\b")

#: Восстановление хитов. Отрицания ловятся отдельно: у Chill Touch в тексте
#: стоит "can't regain hit points", и без этой проверки он стал бы лечением.
_HEALS = re.compile(r"regains?\s+(?:a number of\s+)?hit points|\bhealing\b", re.I)
_BLOCKS_HEALING = re.compile(
    r"(?:can'?t|cannot|unable to|prevented from)\s+regain(?:ing)?", re.I
)

#: Состояния из PHB.
_CONDITIONS = (
    "restrained", "paralyzed", "charmed", "frightened", "prone", "stunned",
    "incapacitated", "blinded", "deafened", "grappled", "unconscious",
    "petrified", "poisoned",
)

#: Обороты, после которых состояние означает защиту от него, а не наложение:
#: "can't be charmed", "against being poisoned", "if it isn't incapacitated".
#: Без этой проверки Magic Circle и Protection from Poison попадали в контроль.
_PROTECTIVE = re.compile(
    r"(?:can'?t be|cannot be|isn'?t|is not|aren'?t|are not|against being|"
    r"immune to|immunity to|no longer|otherwise|ends? the|removes? the|"
    r"if it is|suppress)\b[^.]{0,40}$",
    re.I,
)

#: Насколько далеко назад смотреть в поисках защитного оборота.
_PROTECTIVE_LOOKBACK = 60

#: Признаки защитного заклинания. "base AC becomes" — это Mage Armor, который
#: не даёт бонуса к AC, а задаёт его заново.
_DEFENSIVE = re.compile(
    r"bonus to AC|AC becomes|base AC|armor class becomes|temporary hit points|"
    r"resistance to|half cover|three-quarters cover|immunity to",
    re.I,
)

#: Типы урона из PHB.
DAMAGE_TYPES = (
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
)

_DAMAGE_TYPE_IN_TEXT = re.compile(
    r"\b(" + "|".join(DAMAGE_TYPES) + r")\s+damage", re.I
)

#: Урон, который получает сам заклинатель. В Dimension Door это цена неудачного
#: приземления, а не боевое применение, причём написано оно как "you and any
#: creature traveling with you each take 4d6" — поэтому шаблон ищет "you" и
#: "take" в пределах одного предложения, а не подряд.
_SELF_DAMAGE = re.compile(r"\byou\b[^.]{0,80}?\btakes?\s+\d+d\d+", re.I)


def _inflicts_condition(desc: str, lowered: str) -> bool:
    """
    Накладывает ли заклинание состояние — в отличие от защиты от него.

    Слово состояния само по себе ничего не значит: у Magic Circle стоит
    "can't be charmed, frightened", а у Protection from Poison — "against
    being poisoned". Поэтому каждое вхождение проверяется по тому, что стоит
    перед ним, и контролем заклинание считается только если хотя бы одно
    вхождение не защитное.
    """
    for condition in _CONDITIONS:
        start = 0
        while (found := lowered.find(condition, start)) != -1:
            before = desc[max(0, found - _PROTECTIVE_LOOKBACK):found]
            if not _PROTECTIVE.search(before):
                return True
            start = found + len(condition)
    return False


def _classify_role(raw: dict) -> SpellRole:
    """
    Определить роль заклинания.

    Порядок проверок не случаен:

    * лечение первым, но только если текст не про ЗАПРЕТ лечения;
    * контроль раньше урона, потому что у Web в тексте есть "2d4 fire damage"
      от подожжённой паутины, хотя партии он нужен как контроль.

    Спасбросок не может быть условием ни для урона, ни для контроля: Magic
    Missile попадает автоматически, а Sleep считает хиты, и оба остались бы
    неопознанными. Вместо спасброска работают два других признака:

    * контроль накладывает состояние, поэтому длится; мгновенные заклинания
      со словами состояний, наоборот, их снимают (Lesser Restoration);
    * урон отличается от неудачного приземления тем, что его получает не сам
      заклинатель: в Dimension Door урон достаётся "you", и это не боевое
      применение.

    Классификация приближённая: источник ролей не размечает, а по damage_roll
    её не собрать — он заполнен у 61 заклинания из 319.
    """
    desc = raw.get("desc") or ""
    lowered = desc.lower()
    lasting = "instantaneous" not in (raw.get("duration") or "").lower()
    dice = _DICE.findall(desc)
    hurts_others = "damage" in lowered and len(dice) > len(_SELF_DAMAGE.findall(desc))

    # Урон проверяется раньше лечения: Vampiric Touch возвращает заклинателю
    # половину нанесённого, но это надбавка к атаке, а не назначение.
    if raw.get("damage_roll"):
        return "damage"

    if _HEALS.search(desc) and not _BLOCKS_HEALING.search(desc):
        return "healing"

    if _inflicts_condition(desc, lowered) and (lasting or raw.get("saving_throw_ability")):
        return "control"

    if hurts_others:
        return "damage"

    if _DEFENSIVE.search(desc):
        return "defense"

    return "utility"


def _damage_types(raw: dict, role: SpellRole) -> frozenset[str]:
    """
    Типы урона заклинания.

    Структурное поле заполнено у 61 заклинания из 319, вместе с разбором текста
    получается 89 — поэтому берём объединение. Но только у боевых заклинаний:
    в тексте Dimension Door есть "force damage" за неудачное приземление, и без
    этой отсечки партия получила бы умение наносить силовой урон телепортом.
    """
    if role != "damage":
        return frozenset()

    types = {str(name).lower() for name in raw.get("damage_types") or ()}
    types |= {
        match.group(1).lower()
        for match in _DAMAGE_TYPE_IN_TEXT.finditer(raw.get("desc") or "")
    }
    return frozenset(types)


def parse_spell(raw: dict) -> Spell:
    """Собрать доменное заклинание из сырого ответа Open5e."""
    role = _classify_role(raw)
    return Spell(
        key=raw["key"],
        name=raw["name"],
        level=int(raw["level"]),
        school=(raw.get("school") or {}).get("key", ""),
        classes=[cls["key"] for cls in raw.get("classes") or ()],
        concentration=bool(raw.get("concentration")),
        ritual=bool(raw.get("ritual")),
        casting_time=raw.get("casting_time") or "",
        duration=raw.get("duration") or "",
        role=role,
        damage_dice=raw.get("damage_roll") or "",
        damage_types=_damage_types(raw, role),
    )


# ── Классы ────────────────────────────────────────────────────────────────────


def _ability_code(name: str) -> str:
    """"Constitution" -> "con". Источник пишет полностью, внутри удобнее коротко."""
    return name.strip().lower()[:3]


def parse_class_data(raw: dict) -> ClassData:
    """
    Собрать данные о классе.

    Берём только то, чему источник можно верить: кость хитов и владения
    спасбросками — все двенадцать наборов сверены с PHB и совпадают.
    Поле caster_type у него почти везде пустое, поэтому не используется.
    """
    return ClassData(
        key=raw["key"],
        name=raw["name"],
        # В источнике "D12" строкой, а считать по ней придётся числом.
        hit_die=int(str(raw["hit_dice"]).lstrip("Dd")),
        saving_throws=frozenset(
            _ability_code(save["name"]) for save in raw.get("saving_throws") or ()
        ),
    )


def _load_raw(path: Path) -> list[dict]:
    if not path.exists():
        raise CatalogMissing(
            f"Каталог не найден: {path}. "
            f"Загрузите его один раз: uv run python -m tools.sync_catalog"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_creatures(path: Path | str | None = None) -> list[Creature]:
    """Прочитать сохранённый каталог существ с диска."""
    return [
        parse_creature(item)
        for item in _load_raw(Path(path) if path is not None else DEFAULT_CREATURES_PATH)
    ]


def load_beasts(path: Path | str | None = None) -> list[Creature]:
    """Только звери — кандидаты на Wild Shape. Превратиться можно лишь в зверя."""
    return [
        creature
        for creature in load_creatures(path)
        if creature.creature_type == BEAST_TYPE
    ]


def load_spells(path: Path | str | None = None) -> list[Spell]:
    """Прочитать сохранённый каталог заклинаний с диска."""
    return [
        parse_spell(item)
        for item in _load_raw(Path(path) if path is not None else DEFAULT_SPELLS_PATH)
    ]


def load_classes(path: Path | str | None = None) -> dict[str, ClassData]:
    """Данные о классах, по ключу класса."""
    raw = _load_raw(Path(path) if path is not None else DEFAULT_CLASSES_PATH)
    return {item["key"]: parse_class_data(item) for item in raw}
