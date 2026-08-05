"""
Telegram-бот.

Второй тонкий адаптер над тем же ядром: советники, кэш и бюджет общие с
веб-интерфейсом, поэтому оба советника доехали сюда без единой правки в них.

Работает через long polling — публичный адрес, вебхуки и туннели не нужны,
бот запускается прямо с ноутбука.

    uv sync --extra bot
    # TELEGRAM_BOT_TOKEN в .env
    uv run python -m apps.bot
"""

import html
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from adapters.gemini_explainer import explainer_from_env
from adapters.llm_cache import LlmCache
from adapters.open5e_catalog import (
    BEAST_TYPE,
    CatalogMissing,
    load_classes,
    load_creatures,
    load_spells,
)
from adapters.sqlite_storage import Storage, StorageTooNew
from apps.formatting import (
    format_advice,
    format_character,
    format_party,
    format_sheet,
    parse_character,
    parse_enemies,
    parse_member,
)
from core.advisor import ADVISORS, advise
from core.class_profiles import display_name
from core.encounter import estimate_encounter
from core.party_sheet import build_party_sheet
from core.request import AdviceRequest

load_dotenv()

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATALOG_FOR = {"wildshape": "beasts", "spells": "spells"}

HELP = (
    "Я подсказываю по D&D 5e: во что превратиться друиду и какие заклинания взять.\n\n"
    "<b>Как начать</b>\n"
    "/me друид 6 — задать своего персонажа\n"
    "/member Гарет воин 5 — добавить того, кто ботом не пользуется\n"
    "/member remove Гарет — убрать его\n"
    "/party create — создать партию и получить код\n"
    "/party join КОД — вступить в чужую партию\n\n"
    "<b>Как спрашивать</b>\n"
    "Просто напишите обстановку: <i>болото, преследуем убегающего</i>\n"
    "/spells — что взять из заклинаний\n"
    "/fight goblin 4, ogre — драться или бежать\n\n"
    "Поиск вариантов бесплатный. Кнопка «Объяснить» тратит один запрос к модели."
)


class Deps:
    """Общие для всех хэндлеров ресурсы. Собираются один раз при старте."""

    def __init__(self) -> None:
        creatures = load_creatures()
        self.catalogs = {
            "beasts": [c for c in creatures if c.creature_type == BEAST_TYPE],
            "spells": load_spells(),
            "creatures": creatures,
        }
        self.classes = load_classes()
        self.storage = Storage(DATA_DIR / "copilot.db")
        self.cache = LlmCache(
            DATA_DIR / "copilot.db",
            daily_budget=int(os.getenv("LLM_DAILY_BUDGET", "200")),
            user_daily_budget=int(os.getenv("LLM_USER_DAILY_BUDGET", "30")),
        )
        self.explainer = explainer_from_env()


def _deps(context: ContextTypes.DEFAULT_TYPE) -> Deps:
    return context.application.bot_data["deps"]


def _user_id(update: Update) -> str:
    return str(update.effective_user.id)


def build_request(deps: Deps, user_id: str, situation_text: str = "") -> AdviceRequest | None:
    """Собрать запрос из сохранённого персонажа и его партии."""
    character = deps.storage.get_character(user_id)
    if character is None:
        return None
    return AdviceRequest(
        class_key=character.class_key,
        level=character.level,
        situation_text=situation_text,
        party=tuple(deps.storage.party_members(user_id)),
    )


def choose_advisor(request: AdviceRequest, preferred: str | None = None):
    """
    Какой советник отвечает на это сообщение.

    Свободный текст — это описание обстановки, поэтому у друида он идёт в
    советник по формам. Заклинания вызываются командой явно.
    """
    applicable = [a for a in ADVISORS.values() if a.applies_to(request)]
    if not applicable:
        return None
    if preferred:
        return next((a for a in applicable if a.key == preferred), None)
    return next((a for a in applicable if a.key == "wildshape"), applicable[0])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(HELP)


async def me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps, user_id = _deps(context), _user_id(update)
    raw = " ".join(context.args)

    if not raw:
        character = deps.storage.get_character(user_id)
        if character is None:
            await update.message.reply_html(
                "Персонаж не задан. Напишите, например: <code>/me друид 6</code>"
            )
        else:
            await update.message.reply_html(format_character(character))
        return

    parsed = parse_character(raw)
    if parsed is None:
        await update.message.reply_html(
            "Не разобрал. Нужно класс и уровень: <code>/me друид 6</code>"
        )
        return

    class_key, level = parsed
    deps.storage.save_character(user_id, class_key=class_key, level=level)
    await update.message.reply_html(
        "Записал.\n" + format_character(deps.storage.get_character(user_id))
    )


async def party(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    deps, user_id = _deps(context), _user_id(update)
    action = (context.args[0].lower() if context.args else "")

    if action == "create":
        try:
            code = deps.storage.create_party(user_id)
        except LookupError as error:
            await update.message.reply_html(html.escape(str(error)))
            return
        await update.message.reply_html(
            f"Партия создана. Код для друзей: <code>{code}</code>\n"
            f"Они вступают командой <code>/party join {code}</code>"
        )
        return

    if action == "join":
        if len(context.args) < 2:
            await update.message.reply_html("Нужен код: <code>/party join ABC123</code>")
            return
        if deps.storage.get_character(user_id) is None:
            await update.message.reply_html(
                "Сначала задайте персонажа: <code>/me друид 6</code>"
            )
            return
        if deps.storage.join_party(user_id, context.args[1]):
            await update.message.reply_html("Вы в партии.\n" + format_party(deps.storage.party_members(user_id)))
        else:
            await update.message.reply_html("Такого кода нет. Проверьте написание.")
        return

    if action == "leave":
        deps.storage.leave_party(user_id)
        await update.message.reply_html("Вышли из партии.")
        return

    # Без аргументов показываем сводку по отряду. Лист считает партию целиком,
    # включая спрашивающего: это картина группы, а не дыры вокруг одного.
    character = deps.storage.get_character(user_id)
    if character is None:
        await update.message.reply_html(
            "Сначала задайте персонажа: <code>/me друид 6</code>"
        )
        return

    allies = deps.storage.party_members(user_id)
    if not allies:
        await update.message.reply_html(format_party(allies))
        return

    sheet = build_party_sheet(
        deps.storage.full_party(user_id),
        classes=deps.classes,
        spells=deps.catalogs["spells"],
    )
    text = format_sheet(sheet)
    if character.party_code:
        text += f"\n\nКод партии: <code>{character.party_code}</code>"
    await update.message.reply_html(text)


async def member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Завести или убрать участника, который ботом не пользуется.

        /member Гарет воин 5
        /member remove Гарет
    """
    deps, user_id = _deps(context), _user_id(update)
    raw = " ".join(context.args)

    if deps.storage.get_character(user_id) is None:
        await update.message.reply_html(
            "Сначала задайте своего персонажа: <code>/me друид 6</code>"
        )
        return

    action = context.args[0].lower() if context.args else ""
    if action in ("remove", "убрать", "del"):
        name = " ".join(context.args[1:]).strip()
        if not name:
            await update.message.reply_html("Кого убрать? <code>/member remove Гарет</code>")
        elif deps.storage.remove_member(user_id, name):
            await update.message.reply_html(f"Убрал {html.escape(name)}.")
        else:
            await update.message.reply_html(
                f"Не нашёл {html.escape(name)} среди тех, кого вы заводили."
            )
        return

    parsed = parse_member(raw)
    if parsed is None:
        await update.message.reply_html(
            "Нужно имя, класс и уровень: <code>/member Гарет воин 5</code>\n"
            "Убрать: <code>/member remove Гарет</code>"
        )
        return

    name, class_key, level = parsed
    deps.storage.add_member(user_id, name=name, class_key=class_key, level=level)
    await update.message.reply_html(
        f"Добавил: <b>{html.escape(name)}</b>, "
        f"{html.escape(display_name(class_key))} {level} уровня.\n"
        + format_party(deps.storage.party_members(user_id))
    )


async def _answer(update: Update, context: ContextTypes.DEFAULT_TYPE, *, preferred: str | None) -> None:
    deps, user_id = _deps(context), _user_id(update)
    situation_text = "" if preferred == "spells" else (update.message.text or "")

    request = build_request(deps, user_id, situation_text)
    if request is None:
        await update.message.reply_html(
            "Сначала задайте персонажа: <code>/me друид 6</code>"
        )
        return

    advisor = choose_advisor(request, preferred)
    if advisor is None:
        await update.message.reply_html(
            "Для этого персонажа у меня пока нет советов."
        )
        return

    advice = advise(advisor, catalog=deps.catalogs[CATALOG_FOR[advisor.key]], request=request)
    if not advice.options:
        await update.message.reply_html("Подходящих вариантов не нашлось.")
        return

    # Запрос кладём в состояние пользователя: в callback_data телеграма
    # помещается 64 байта, а нам нужен весь контекст вопроса.
    context.user_data["last"] = (advisor.key, request)

    keyboard = None
    if deps.explainer is not None:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("💬 Объяснить", callback_data="explain")]]
        )
    await update.message.reply_html(format_advice(advice), reply_markup=keyboard)


async def fight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Оценить бой: /fight goblin 4, ogre"""
    deps, user_id = _deps(context), _user_id(update)

    character = deps.storage.get_character(user_id)
    if character is None:
        await update.message.reply_html(
            "Сначала задайте персонажа: <code>/me друид 6</code>"
        )
        return

    by_name = {creature.name: creature for creature in deps.catalogs["creatures"]}
    resolved, unknown = parse_enemies(" ".join(context.args), list(by_name))

    if not resolved:
        await update.message.reply_html(
            "Не понял, кто против вас. Пример: <code>/fight goblin 4, ogre</code>"
        )
        return

    party = deps.storage.full_party(user_id)
    result = estimate_encounter(
        party,
        [(by_name[name], count) for name, count in resolved],
        classes=deps.classes,
    )

    listing = ", ".join(f"{name} ×{count}" for name, count in resolved)
    lines = [
        f"<b>{html.escape(result.verdict.capitalize())}</b>",
        html.escape(result.advice),
        "",
        f"Против вас: {html.escape(listing)}",
        f"Вас: {len(party)} чел., ~{result.party.hp} HP, урон ~{result.party.damage_per_round}",
        f"Их: {result.enemies.hp} HP, урон {result.enemies.damage_per_round}",
    ]
    if unknown:
        lines.append(
            "\n⚠️ Не нашёл и <b>не учёл</b>: " + html.escape(", ".join(unknown))
        )
    lines.append(
        "\n<i>Партия оценена по классам и уровням, противники — по статблокам. "
        "Способности со спасброском (дыхание дракона) не учтены.</i>"
    )
    await update.message.reply_html("\n".join(lines))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update, context, preferred=None)


async def spells(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update, context, preferred="spells")


async def forms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _answer(update, context, preferred="wildshape")


async def explain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Единственное место, где тратится запрос к модели."""
    query = update.callback_query
    await query.answer()

    deps = _deps(context)
    stored = context.user_data.get("last")
    if stored is None:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    advisor_key, request = stored
    advisor = ADVISORS[advisor_key]
    advice = advise(
        advisor,
        catalog=deps.catalogs[CATALOG_FOR[advisor_key]],
        request=request,
        explainer=deps.explainer,
        cache=deps.cache,
        user_id=str(query.from_user.id),
        want_explanation=True,
    )

    if advice.explanation:
        await query.edit_message_text(
            format_advice(advice), parse_mode=ParseMode.HTML, reply_markup=None
        )
    else:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_html(
            "Объяснение недоступно: либо исчерпан суточный лимит, либо модель не ответила. "
            "Варианты выше от этого не зависят."
        )


def build_handlers() -> list:
    """Таблица хэндлеров. Отдельной функцией, чтобы её можно было проверить без токена."""
    return [
        CommandHandler("start", start),
        CommandHandler("help", start),
        CommandHandler("me", me),
        CommandHandler("party", party),
        CommandHandler("spells", spells),
        CommandHandler("forms", forms),
        CommandHandler("fight", fight),
        CommandHandler("member", member),
        CallbackQueryHandler(explain, pattern="^explain$"),
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_text),
    ]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Нет TELEGRAM_BOT_TOKEN. Положите его в .env")

    try:
        deps = Deps()
    except (CatalogMissing, StorageTooNew) as error:
        raise SystemExit(str(error))

    application = Application.builder().token(token).build()
    application.bot_data["deps"] = deps
    application.add_handlers(build_handlers())

    logger.info("Бот запущен, режим long polling")
    application.run_polling()


if __name__ == "__main__":
    main()
