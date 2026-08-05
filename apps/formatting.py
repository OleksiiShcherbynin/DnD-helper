"""
Текстовый вывод для телеграма и разбор коротких команд.

Вынесено из bot.py отдельно, чтобы проверяться без сети и без токена:
хэндлеры остаются тонкими, а всё, что стоит тестировать, живёт здесь.

Сообщения отправляются в режиме HTML, поэтому любой текст, пришедший от
пользователя или из каталога, экранируется. Иначе название вида "<script>"
или обычный амперсанд ломают разбор на стороне телеграма.
"""

import html
import re

from core.advisor import Advice
from core.class_profiles import (
    display_name,
    parse_class,
    parse_subclass,
    subclass_profile,
)
from core.models import ABILITY_NAMES, ROLE_NAMES, Character, PartyMember
from core.party_sheet import PartySheet

#: Уровни персонажа в D&D 5e.
_MIN_LEVEL, _MAX_LEVEL = 1, 20

def parse_character(text: str) -> tuple[str, int, str | None] | None:
    """
    Разобрать строку вида "друид 6" или "друид 6 круг луны".

    Возвращает None на всё, что не разобралось: пропущенный уровень, уровень
    вне 1-20, неизвестный класс или подкласс чужого класса. Бот на это
    отвечает подсказкой, а не ошибкой.
    """
    parts = (text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        return None

    class_key = parse_class(parts[0])
    if class_key is None:
        return None

    level = int(parts[1])
    if not _MIN_LEVEL <= level <= _MAX_LEVEL:
        return None

    tail = " ".join(parts[2:]).strip()
    if not tail:
        return class_key, level, None

    subclass_key = parse_subclass(tail)
    if subclass_key is None or subclass_profile(subclass_key).parent != class_key:
        return None

    return class_key, level, subclass_key


def parse_member(text: str) -> tuple[str, str, int, str | None] | None:
    """
    Разобрать строку вида "Кузьма изобретатель 5 артиллерист".

    Уровень служит разделителем: имя до класса, подкласс после уровня. Иначе
    многословные имя и подкласс пришлось бы разделять кавычками, а за столом
    их никто не ставит.

    Непонятый подкласс — отказ, а не молчаливый пропуск: посчитать персонажа
    не тем, кто он есть, и никак об этом не сказать хуже, чем переспросить.
    """
    parts = (text or "").split()
    level_at = next(
        (index for index, part in enumerate(parts) if part.isdigit()), None
    )
    if level_at is None or level_at < 2:
        return None

    level = int(parts[level_at])
    if not _MIN_LEVEL <= level <= _MAX_LEVEL:
        return None

    class_key = parse_class(parts[level_at - 1])
    if class_key is None:
        return None

    name = " ".join(parts[: level_at - 1]).strip()
    if not name:
        return None

    tail = " ".join(parts[level_at + 1 :]).strip()
    if not tail:
        return (name, class_key, level, None)

    subclass_key = parse_subclass(tail)
    if subclass_key is None:
        return None
    if subclass_profile(subclass_key).parent != class_key:
        return None

    return (name, class_key, level, subclass_key)


#: "goblin 4", "4 goblin", "goblin x4" — число где угодно, и его может не быть.
_ENEMY_COUNT = re.compile(r"(?:^|\s)x?(\d{1,2})(?:\s|$)")


def parse_enemies(
    text: str, catalog_names: list[str]
) -> tuple[list[tuple[str, int]], list[str]]:
    """
    Разобрать строку вида "goblin 4, ogre" в пары «название, сколько».

    Возвращает разобранное и **отдельно нераспознанное**. Промолчать про
    непонятого противника опаснее, чем не посчитать бой вовсе: игрок решит,
    что дракон учтён, а его в расчёте нет.

    Название ищется по началу слов: за столом никто не печатает
    "Young Red Dragon" целиком. Неоднозначный кусок не угадывается — если под
    "giant" подходит и паук, и орёл, честнее сказать, что не понял.
    """
    resolved: list[tuple[str, int]] = []
    unknown: list[str] = []

    for chunk in (text or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue

        count_match = _ENEMY_COUNT.search(chunk)
        count = int(count_match.group(1)) if count_match else 1
        name_part = _ENEMY_COUNT.sub(" ", chunk).strip().lower()
        if not name_part:
            unknown.append(chunk)
            continue

        matches = [
            name for name in catalog_names if name.lower().startswith(name_part)
        ]
        if len(matches) != 1:
            unknown.append(name_part)
            continue

        resolved.append((matches[0], count))

    return resolved, unknown


def format_character(character: Character) -> str:
    label = display_name(character.class_key)
    if character.subclass_key:
        label += f", {subclass_profile(character.subclass_key).name}"
    lines = [f"<b>{html.escape(label)}</b>, {character.level} уровень"]
    if character.party_code:
        lines.append(f"Партия: <code>{html.escape(character.party_code)}</code>")
    return "\n".join(lines)


def format_party(members: list[PartyMember]) -> str:
    if not members:
        return (
            "В партии пока никого кроме вас.\n"
            "Создайте её командой /party create и передайте код друзьям."
        )
    listing = "\n".join(
        f"• {html.escape(display_name(member.class_key))}, {member.level} уровень"
        for member in members
    )
    return f"<b>Союзники:</b>\n{listing}"


def format_sheet(sheet: PartySheet) -> str:
    """
    Собрать сводку по отряду.

    Предупреждения не выдумываются: если партия всё закрывает, блок про дыры
    просто не появляется. Список из шести пунктов «всё хорошо» обесценил бы
    тот единственный пункт, ради которого лист и читают.
    """
    roster = ", ".join(
        f"{html.escape(display_name(member.class_key))} {member.level}"
        for member in sheet.members
    )
    lines = [f"<b>Лист партии</b>\n{html.escape(roster) if roster else 'Пусто'}"]

    covered = [ABILITY_NAMES[ability] for ability in sheet.covered_saves]
    lines.append(
        "\n<b>Спасброски закрыты:</b> "
        + (html.escape(", ".join(covered)) if covered else "ничего")
    )

    filled = {
        ROLE_NAMES.get(role, role): names
        for role, names in sheet.roles.items()
        if names
    }
    if filled:
        listing = ", ".join(
            f"{html.escape(role)} ({len(names)})" for role, names in filled.items()
        )
        lines.append(f"<b>Умения:</b> {listing}")

    lines.append(f"<b>Типов урона:</b> {len(sheet.damage_types)} из 13")

    warnings = [f"⚠️ {html.escape(gap.text)}" for gap in sheet.gaps]
    if sheet.missing_roles:
        missing = ", ".join(ROLE_NAMES.get(role, role) for role in sheet.missing_roles)
        warnings.append(f"⚠️ Никто не закрывает: {html.escape(missing)}.")
    if sheet.only_physical_damage:
        warnings.append(
            "⚠️ Партия наносит только физический урон: сопротивление немагическому "
            "оружию обойти нечем."
        )
    if sheet.unknown_classes:
        unknown = ", ".join(html.escape(key) for key in sheet.unknown_classes)
        warnings.append(f"⚠️ Не нашёл в справочнике: {unknown}.")

    if warnings:
        lines.append("\n" + "\n".join(warnings))

    return "\n".join(lines)


def format_advice(advice: Advice) -> str:
    """Собрать сообщение с вариантами. Цифры берутся из каталога, не из модели."""
    blocks = [f"<b>{html.escape(advice.title)}</b>"]

    for position, option in enumerate(advice.options, start=1):
        facts = " · ".join(
            f"{html.escape(label)} {html.escape(value)}"
            for label, value in option.facts.items()
        )
        block = f"\n{position}. <b>{html.escape(option.name)}</b>"
        if facts:
            block += f"\n{facts}"
        if option.why:
            block += f"\n<i>{html.escape(option.why)}</i>"
        blocks.append(block)

    if advice.explanation:
        blocks.append(f"\n💬 {html.escape(advice.explanation)}")

    return "\n".join(blocks)
