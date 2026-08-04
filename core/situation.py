"""
Свободное описание ситуации -> набор тегов. Без обращения к LLM.

Зачем не отдать разбор модели: теги входят в ключ кэша, поэтому разбор обязан
быть детерминированным и бесплатным. Если бы ситуацию размечала модель, то
за разметку уже пришлось бы платить запросом — и кэш терял бы смысл.

Сопоставление идёт по началу слова, а не по подстроке. Это принципиально:
поиск подстроки находит "лед" внутри "следам" и отправляет друида в тундру
посреди леса, а "гор" внутри "город" — в горы посреди города.
"""

import re
from dataclasses import dataclass

#: Ключи местностей взяты из реальных данных Open5e (v2/creatures, srd-2014),
#: а не придуманы: forest, grassland, hills, desert, swamp, urban, ocean,
#: mountain, caves, ruins, underworld, coast, arctic, sewer, lake.
_TERRAIN_STEMS: dict[str, tuple[str, ...]] = {
    "forest": ("лес", "лесн", "чащ", "джунгл", "forest", "jungle", "wood"),
    "swamp": ("болот", "трясин", "swamp", "marsh", "bog"),
    "grassland": ("степ", "равнин", "луг", "поле", "поля", "полян", "grassland", "plain", "meadow"),
    "hills": ("холм", "hill"),
    "mountain": ("гора", "горы", "горах", "горн", "скал", "mountain", "cliff"),
    "desert": ("пустын", "барх", "desert", "dune"),
    "arctic": ("тундр", "снег", "снеж", "лед", "льд", "мороз", "arctic", "tundra", "snow", "ice"),
    "coast": ("побереж", "берег", "coast", "shore", "beach"),
    "ocean": ("океан", "море", "моря", "морск", "ocean", "sea"),
    "lake": ("озер", "река", "реки", "реке", "речн", "lake", "river"),
    "caves": ("пещер", "cave", "grotto"),
    "underworld": ("подземел", "подземн", "катакомб", "underdark", "dungeon", "underworld"),
    "urban": ("город", "улиц", "urban", "city", "town", "street"),
    "sewer": ("канализ", "sewer"),
    "ruins": ("руин", "развалин", "ruin"),
}

_GOAL_STEMS: dict[str, tuple[str, ...]] = {
    "chase": ("догна", "догон", "преслед", "убега", "погон", "chas", "pursu", "flee", "catch"),
    "escape": ("сбежа", "отступ", "удра", "спаст", "escape", "retreat", "disengage"),
    "scout": ("развед", "подкрад", "осмотр", "разгляд", "scout", "sneak", "stealth", "spy"),
    "tank": ("держ", "оборон", "прикры", "танк", "защит", "tank", "block", "defend"),
    "damage": ("урон", "убить", "атак", "драк", "damage", "kill", "fight", "burst"),
    "swim": ("плыть", "плыв", "плава", "подвод", "swim", "underwater", "dive"),
    "climb": ("взобра", "залез", "вскара", "climb", "scale"),
}

_WORD = re.compile(r"[a-zа-я]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower().replace("ё", "е"))


def _match(words: list[str], stems: dict[str, tuple[str, ...]]) -> set[str]:
    return {
        tag
        for tag, variants in stems.items()
        if any(word.startswith(variant) for word in words for variant in variants)
    }


@dataclass(frozen=True)
class Situation:
    """Размеченная ситуация: что вокруг и чего мы хотим добиться."""

    raw: str
    terrains: frozenset[str]
    goals: frozenset[str]

    def cache_key(self) -> str:
        """
        Стабильный ключ для кэша ответов LLM.

        Строится только из тегов, поэтому не зависит от регистра, лишних
        пробелов и порядка слов: два описания одного и того же расклада
        дают одно попадание в кэш вместо двух запросов к модели.
        """
        return "t:{};g:{}".format(
            ",".join(sorted(self.terrains)),
            ",".join(sorted(self.goals)),
        )


def parse_situation(text: str) -> Situation:
    """Разметить описание ситуации. Незнакомый текст даёт пустые теги, а не догадки."""
    words = _words(text or "")
    return Situation(
        raw=text or "",
        terrains=frozenset(_match(words, _TERRAIN_STEMS)),
        goals=frozenset(_match(words, _GOAL_STEMS)),
    )
