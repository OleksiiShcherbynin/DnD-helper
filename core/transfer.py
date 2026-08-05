"""
Перенос отряда текстом.

Сайт и бот ведут записи под разными владельцами, и общий код партии связывает
их только пока оба смотрят в одну базу. Слепок переносит отряд туда, где базы
нет: на другую машину, в резервную копию, другому человеку.

Формат — компактный JSON: его можно скопировать одним куском, он переживает
пересылку и по нему видно, что именно переносится. Читаемый построчный формат
был бы приятнее глазу, но копипаста рвёт переносы строк, а восстанавливать
смысл из обрывков хуже, чем отказаться.
"""

import json
from dataclasses import dataclass

from core.models import Stats

#: Версия формата. Слепок из будущей версии лучше отвергнуть, чем разобрать
#: наполовину и молча потерять часть данных.
FORMAT_VERSION = 1


class ParseError(ValueError):
    """Текст не похож на слепок отряда."""


@dataclass(frozen=True)
class _Entry:
    name: str
    class_key: str
    level: int
    subclass_key: str | None
    stats: Stats
    spell_keys: frozenset[str]
    #: True — это персонаж живого игрока, а не заведённый вручную.
    played: bool


def _stats_to_json(stats: Stats) -> dict:
    return {
        "abilities": stats.abilities,
        "ac": stats.ac,
        "hp": stats.hp,
        "attack": stats.attack_bonus,
        "damage": stats.damage_per_round,
    }


def _stats_from_json(data: dict) -> Stats:
    return Stats(
        abilities={str(k): int(v) for k, v in (data.get("abilities") or {}).items()},
        ac=data.get("ac"),
        hp=data.get("hp"),
        attack_bonus=data.get("attack"),
        damage_per_round=data.get("damage"),
    )


def dump_party(storage, owner_id: str) -> str:
    """
    Собрать слепок отряда. Бросает LookupError, если персонажа ещё нет.
    """
    own = storage.get_character(owner_id)
    if own is None:
        raise LookupError("Сначала нужен персонаж: переносить пока нечего.")

    entries = [
        {
            "name": own.name,
            "class": own.class_key,
            "level": own.level,
            "subclass": own.subclass_key,
            "stats": _stats_to_json(own.stats),
            "spells": sorted(own.spell_keys),
            "self": True,
        }
    ]
    for member in storage.party_members(owner_id):
        entries.append(
            {
                "name": member.name,
                "class": member.class_key,
                "level": member.level,
                "subclass": member.subclass_key,
                "stats": _stats_to_json(member.stats),
                "spells": sorted(member.spell_keys),
                # Персонажи живых игроков помечаются, чтобы не ввезти их копией.
                "played": storage.is_played_by_someone(owner_id, member.name),
            }
        )

    return json.dumps(
        {"v": FORMAT_VERSION, "party": entries}, ensure_ascii=False, separators=(",", ":")
    )


def load_party(storage, owner_id: str, text: str) -> list[str]:
    """
    Применить слепок: сделать отряд владельца таким, как в тексте.

    Ввозится только то, чем ввозящий распоряжается — свой персонаж и заведённые
    вручную. Персонажи живых игроков пропускаются и возвращаются списком: ввезти
    их копией значило бы развести двойников и посчитать отряд вдвое больше.

    Повторный ввоз того же текста ничего не удваивает: это «сделай как здесь»,
    а не «добавь ещё раз».
    """
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        raise ParseError("Это не похоже на слепок отряда.") from None

    if not isinstance(data, dict) or data.get("v") != FORMAT_VERSION:
        raise ParseError(
            f"Не тот формат: нужен слепок версии {FORMAT_VERSION}."
        )

    party = data.get("party")
    if not isinstance(party, list) or not party:
        raise ParseError("В слепке нет ни одного персонажа.")

    skipped: list[str] = []
    storage.drop_manual_members(owner_id)

    for entry in party:
        try:
            name = str(entry["name"])
            class_key = str(entry["class"])
            level = int(entry["level"])
        except (KeyError, TypeError, ValueError):
            raise ParseError("В слепке испорчена запись о персонаже.") from None

        subclass = entry.get("subclass")
        stats = _stats_from_json(entry.get("stats") or {})
        spells = {str(key) for key in entry.get("spells") or ()}

        if entry.get("self"):
            storage.save_character(
                owner_id, class_key=class_key, level=level,
                name=name, subclass_key=subclass,
            )
            target = None
        elif entry.get("played"):
            skipped.append(name)
            continue
        else:
            storage.add_member(
                owner_id, name=name, class_key=class_key,
                level=level, subclass_key=subclass,
            )
            target = name

        storage.replace_stats(owner_id, target, stats)
        storage.set_spells(owner_id, target, spells)

    return skipped
