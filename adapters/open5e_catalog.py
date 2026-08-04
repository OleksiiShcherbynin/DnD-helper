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

from core.models import Beast, Spell, SpellRole

#: Куда tools/sync_catalog.py кладёт загруженный каталог.
_CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "catalog"
DEFAULT_BEASTS_PATH = _CATALOG_DIR / "beasts.json"
DEFAULT_SPELLS_PATH = _CATALOG_DIR / "spells.json"


class CatalogMissing(FileNotFoundError):
    """Каталог ещё не загружен."""

#: "Hit: 7 (2d4 + 2) piercing damage" -> 7. Первое число и есть средний урон.
_HIT_AVERAGE = re.compile(r"Hit:\s*(\d+)")

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

    has_multiattack = any(
        (action.get("name") or "").lower() == "multiattack" for action in actions or ()
    )
    if has_multiattack:
        return sum(averages[:2])
    return averages[0]


def parse_beast(raw: dict) -> Beast:
    """Собрать доменного зверя из сырого ответа Open5e."""
    speed = raw.get("speed") or {}
    speeds = {
        key: speed[key]
        for key in _SPEED_KEYS
        if isinstance(speed.get(key), int) and speed[key] > 0
    }

    return Beast(
        key=raw["key"],
        name=raw["name"],
        cr=float(raw["challenge_rating"]),
        ac=int(raw["armor_class"]),
        hp=int(raw["hit_points"]),
        speeds=speeds,
        environments=[env["key"] for env in raw.get("environments") or ()],
        damage_per_round=_damage_per_round(raw.get("actions")),
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

#: Состояния из PHB. Их наличие вместе со спасброском означает контроль.
_CONDITIONS = (
    "restrained", "paralyzed", "charmed", "frightened", "prone", "stunned",
    "incapacitated", "blinded", "deafened", "grappled", "unconscious",
    "petrified", "poisoned",
)

#: Признаки защитного заклинания. "base AC becomes" — это Mage Armor, который
#: не даёт бонуса к AC, а задаёт его заново.
_DEFENSIVE = re.compile(
    r"bonus to AC|AC becomes|base AC|armor class becomes|temporary hit points|"
    r"resistance to|half cover|three-quarters cover|immunity to",
    re.I,
)

#: Урон, который получает сам заклинатель. В Dimension Door это цена неудачного
#: приземления, а не боевое применение, причём написано оно как "you and any
#: creature traveling with you each take 4d6" — поэтому шаблон ищет "you" и
#: "take" в пределах одного предложения, а не подряд.
_SELF_DAMAGE = re.compile(r"\byou\b[^.]{0,80}?\btakes?\s+\d+d\d+", re.I)


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

    if _HEALS.search(desc) and not _BLOCKS_HEALING.search(desc):
        return "healing"

    inflicts_condition = any(condition in lowered for condition in _CONDITIONS)
    if inflicts_condition and (lasting or raw.get("saving_throw_ability")):
        return "control"

    dice = _DICE.findall(desc)
    hurts_others = "damage" in lowered and len(dice) > len(_SELF_DAMAGE.findall(desc))
    if raw.get("damage_roll") or hurts_others:
        return "damage"

    if _DEFENSIVE.search(desc):
        return "defense"

    return "utility"


def parse_spell(raw: dict) -> Spell:
    """Собрать доменное заклинание из сырого ответа Open5e."""
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
        role=_classify_role(raw),
        damage_dice=raw.get("damage_roll") or "",
    )


def _load_raw(path: Path) -> list[dict]:
    if not path.exists():
        raise CatalogMissing(
            f"Каталог не найден: {path}. "
            f"Загрузите его один раз: uv run python -m tools.sync_catalog"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_beasts(path: Path | str | None = None) -> list[Beast]:
    """Прочитать сохранённый каталог зверей с диска."""
    return [
        parse_beast(item)
        for item in _load_raw(Path(path) if path is not None else DEFAULT_BEASTS_PATH)
    ]


def load_spells(path: Path | str | None = None) -> list[Spell]:
    """Прочитать сохранённый каталог заклинаний с диска."""
    return [
        parse_spell(item)
        for item in _load_raw(Path(path) if path is not None else DEFAULT_SPELLS_PATH)
    ]
