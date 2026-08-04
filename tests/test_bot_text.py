"""
Разбор команд и текстовый вывод бота.

Транспорт телеграма здесь не участвует: хэндлеры остаются тонкими, а вся
логика, которую стоит проверять, вынесена в чистые функции. Так тесты
гоняются без сети и без токена.
"""

import pytest

from apps.formatting import format_advice, format_character, format_party, parse_character
from core.advisor import ADVISORS, advise
from core.class_profiles import parse_class
from core.models import Character, PartyMember
from core.request import AdviceRequest


@pytest.mark.parametrize("text, expected", [
    ("друид", "srd_druid"),
    ("Друид", "srd_druid"),
    ("  ВОЛШЕБНИК  ", "srd_wizard"),
    ("wizard", "srd_wizard"),
    ("жрец", "srd_cleric"),
    ("следопыт", "srd_ranger"),
    ("воин", "srd_fighter"),
    ("плут", "srd_rogue"),
])
def test_class_names_are_understood(text, expected):
    assert parse_class(text) == expected


def test_unknown_class_gives_nothing_instead_of_guessing():
    assert parse_class("некромант") is None


@pytest.mark.parametrize("text, class_key, level", [
    ("друид 6", "srd_druid", 6),
    ("волшебник 12", "srd_wizard", 12),
    ("  жрец   3  ", "srd_cleric", 3),
])
def test_character_line_is_parsed(text, class_key, level):
    assert parse_character(text) == (class_key, level)


@pytest.mark.parametrize("text", ["друид", "друид 0", "друид 21", "друид шесть", "", "6"])
def test_broken_character_line_is_refused(text):
    assert parse_character(text) is None


def test_character_is_shown_in_russian():
    text = format_character(Character(class_key="srd_druid", level=6))
    assert "Друид" in text
    assert "6" in text


def test_party_listing_names_everyone():
    text = format_party([PartyMember("srd_cleric", 4), PartyMember("srd_fighter", 5)])
    assert "Жрец" in text
    assert "Воин" in text


def test_empty_party_says_so_instead_of_showing_nothing():
    assert format_party([]).strip(), "пустой ответ бот отправить не может"


def test_advice_message_carries_the_numbers(beasts):
    request = AdviceRequest(class_key="srd_druid", level=8, situation_text="лес, догнать")
    advice = advise(ADVISORS["wildshape"], catalog=beasts, request=request)

    text = format_advice(advice)

    assert advice.options[0].name in text
    assert advice.options[0].facts["HP"] in text
    assert "1." in text, "варианты пронумерованы"


def test_advice_message_escapes_html():
    """
    Описание ситуации приходит от пользователя и попадает в сообщение.
    Телеграм разбирает HTML, поэтому угловые скобки обязаны быть экранированы.
    """
    from core.advisor import Advice, Option

    advice = Advice(
        advisor="test",
        title="<b>заголовок</b>",
        options=[Option(name="<script>", score=1.0, why="a & b")],
        legal_count=1,
    )
    text = format_advice(advice)

    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "&amp;" in text
