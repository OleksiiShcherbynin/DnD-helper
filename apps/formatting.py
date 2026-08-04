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
from core.class_profiles import display_name, parse_class
from core.models import Character, PartyMember

#: Уровни персонажа в D&D 5e.
_MIN_LEVEL, _MAX_LEVEL = 1, 20

_CHARACTER_LINE = re.compile(r"^\s*([^\d\s]+)\s+(\d{1,2})\s*$")


def parse_character(text: str) -> tuple[str, int] | None:
    """
    Разобрать строку вида "друид 6".

    Возвращает None на всё, что не разобралось: пропущенный уровень, уровень
    вне 1-20, неизвестный класс. Бот на это отвечает подсказкой, а не ошибкой.
    """
    match = _CHARACTER_LINE.match(text or "")
    if match is None:
        return None

    class_key = parse_class(match.group(1))
    if class_key is None:
        return None

    level = int(match.group(2))
    if not _MIN_LEVEL <= level <= _MAX_LEVEL:
        return None

    return class_key, level


def format_character(character: Character) -> str:
    lines = [f"<b>{html.escape(display_name(character.class_key))}</b>, {character.level} уровень"]
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
