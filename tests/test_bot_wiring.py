"""
Сборка бота: то, что можно проверить без сети и без токена.

Транспорт телеграма не тестируется — тестируется, что модуль импортируется,
таблица хэндлеров собирается, и выбор советника по сообщению работает так,
как задумано. Этого достаточно, чтобы поймать разъехавшуюся проводку.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("telegram", reason="не установлен экстра bot")

from apps.bot import build_handlers, build_request, choose_advisor  # noqa: E402
from adapters.sqlite_storage import Storage  # noqa: E402
from core.request import AdviceRequest  # noqa: E402


@pytest.fixture
def deps(tmp_path):
    return SimpleNamespace(storage=Storage(tmp_path / "bot.db"))


def test_handler_table_covers_the_documented_commands():
    from telegram.ext import CommandHandler

    commands = {
        command
        for handler in build_handlers()
        if isinstance(handler, CommandHandler)
        for command in handler.commands
    }
    assert {"start", "me", "party", "spells", "fight", "member"} <= commands


def test_free_text_from_a_druid_goes_to_the_forms_advisor():
    """Свободный текст — это обстановка, а обстановка про формы."""
    request = AdviceRequest(class_key="srd_druid", level=6, situation_text="болото")
    assert choose_advisor(request).key == "wildshape"


def test_a_wizard_gets_the_spell_advisor_since_forms_do_not_apply():
    request = AdviceRequest(class_key="srd_wizard", level=5)
    assert choose_advisor(request).key == "spells"


def test_a_druid_can_ask_for_spells_explicitly():
    request = AdviceRequest(class_key="srd_druid", level=6)
    assert choose_advisor(request, preferred="spells").key == "spells"


def test_a_fighter_gets_no_advisor_at_all():
    request = AdviceRequest(class_key="srd_fighter", level=5)
    assert choose_advisor(request) is None


def test_request_is_none_until_a_character_exists(deps):
    assert build_request(deps, "вася") is None


def test_request_picks_up_the_character_and_the_party(deps):
    deps.storage.save_character("вася", class_key="srd_druid", level=6)
    deps.storage.save_character("петя", class_key="srd_cleric", level=4)
    code = deps.storage.create_party("вася")
    deps.storage.join_party("петя", code)

    request = build_request(deps, "вася", "болото")

    assert request.class_key == "srd_druid"
    assert request.level == 6
    assert request.situation_text == "болото"
    assert [member.class_key for member in request.party] == ["srd_cleric"]
