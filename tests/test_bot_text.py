"""
Разбор команд и текстовый вывод бота.

Транспорт телеграма здесь не участвует: хэндлеры остаются тонкими, а вся
логика, которую стоит проверять, вынесена в чистые функции. Так тесты
гоняются без сети и без токена.
"""

import pytest

from apps.formatting import (
    format_advice,
    format_character,
    format_party,
    format_sheet,
    parse_character,
    parse_enemies,
    parse_member,
    parse_spell_command,
    parse_stats,
)
from core.party_sheet import build_party_sheet
from core.advisor import ADVISORS, advise
from core.class_profiles import parse_class
from core.models import Character, PartyMember, Stats
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


@pytest.mark.parametrize("text, expected", [
    ("друид 6", ("srd_druid", 6, None)),
    ("волшебник 12", ("srd_wizard", 12, None)),
    ("  жрец   3  ", ("srd_cleric", 3, None)),
    ("друид 6 круг луны", ("srd_druid", 6, "moon")),
    ("изобретатель 5 артиллерист", ("hb_artificer", 5, "artillerist")),
])
def test_character_line_is_parsed(text, expected):
    assert parse_character(text) == expected


def test_character_line_refuses_a_subclass_of_another_class():
    assert parse_character("волшебник 5 круг луны") is None


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


@pytest.mark.parametrize("text, expected", [
    ("Гарет воин 5", ("Гарет", "srd_fighter", 5, None)),
    ("Сир Гарет Отважный воин 5", ("Сир Гарет Отважный", "srd_fighter", 5, None)),
    ("  Лия   жрец  7 ", ("Лия", "srd_cleric", 7, None)),
])
def test_member_line_is_parsed(text, expected):
    """Имя может быть из нескольких слов, поэтому разбор идёт с конца."""
    assert parse_member(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Кузьма изобретатель 5 артиллерист",
     ("Кузьма", "hb_artificer", 5, "artillerist")),
    ("Мира друид 6 круг луны", ("Мира", "srd_druid", 6, "moon")),
    ("Сир Гарет изобретатель 3 артиллерист",
     ("Сир Гарет", "hb_artificer", 3, "artillerist")),
])
def test_subclass_goes_after_the_level(text, expected):
    """
    Уровень служит разделителем: имя до класса, подкласс после уровня. Иначе
    многословные имя и подкласс пришлось бы разделять кавычками.
    """
    assert parse_member(text) == expected


def test_unknown_subclass_is_refused_rather_than_ignored():
    """
    Молча выбросить непонятый подкласс значит посчитать персонажа не тем,
    кто он есть, и никак об этом не сказать.
    """
    assert parse_member("Кузьма изобретатель 5 кузнец") is None


def test_subclass_of_another_class_is_refused():
    assert parse_member("Кузьма изобретатель 5 круг луны") is None


@pytest.mark.parametrize("text", [
    "Гарет воин",        # без уровня
    "воин 5",            # без имени
    "Гарет некромант 5",  # класса нет в справочнике
    "Гарет воин 0",      # уровень вне 1-20
    "",
])
def test_broken_member_line_is_refused(text):
    assert parse_member(text) is None


def test_stats_without_a_name_are_for_yourself():
    assert parse_stats("сил 16 лов 14") == (
        None, Stats(abilities={"str": 16, "dex": 14})
    )


def test_stats_with_a_name_are_for_that_member():
    """Имя — всё, что стоит до первого понятного ключа, хоть в три слова."""
    assert parse_stats("Сир Гарет hp 44 урон 22") == (
        "Сир Гарет", Stats(hp=44, damage_per_round=22.0)
    )


@pytest.mark.parametrize("text, expected", [
    ("кд 17", Stats(ac=17)),
    ("ac 17", Stats(ac=17)),
    ("хиты 44", Stats(hp=44)),
    ("атака 7", Stats(attack_bonus=7)),
    ("мдр 18", Stats(abilities={"wis": 18})),
    ("МДР 18", Stats(abilities={"wis": 18})),
])
def test_keys_are_understood_in_both_languages(text, expected):
    assert parse_stats(text) == (None, expected)


@pytest.mark.parametrize("text, expected", [
    ("урон 1d8+4", 8.5),
    ("урон 1d8", 4.5),
    ("урон 2d6+3", 10.0),
    ("урон 1d10-1", 4.5),
])
def test_damage_can_be_entered_as_dice(text, expected):
    """
    В листе персонажа написано "1d8+4", а не "8.5". Требовать средний урон
    значит требовать того, чего у игрока перед глазами нет.
    """
    assert parse_stats(text) == (None, Stats(damage_per_round=expected))


@pytest.mark.parametrize("text, expected", [
    ("урон 2x1d8+4", 17.0),
    ("урон 3х1d6+3", 19.5),
])
def test_several_attacks_a_round_are_multiplied(text, expected):
    """Второй удар на 5 уровне удваивает урон, и записать это надо просто."""
    assert parse_stats(text) == (None, Stats(damage_per_round=expected))


def test_a_plain_number_still_works():
    assert parse_stats("урон 12") == (None, Stats(damage_per_round=12.0))


def test_dice_are_only_accepted_where_they_make_sense():
    """Кости в силе или в AC — почти наверняка опечатка."""
    assert parse_stats("сил 1d8") is None
    assert parse_stats("кд 2d6") is None


def test_a_negative_attack_bonus_is_allowed():
    """Бонус атаки бывает отрицательным, и минус нельзя терять."""
    assert parse_stats("атака -1") == (None, Stats(attack_bonus=-1))


@pytest.mark.parametrize("text", ["", "чепуха", "сил", "Кузьма", "сил лов"])
def test_unparsable_stats_are_refused(text):
    assert parse_stats(text) is None


def test_a_key_without_a_number_invalidates_the_line():
    """
    Принять половину строки значит записать не то, что просили, и промолчать
    про остальное. Лучше переспросить целиком.
    """
    assert parse_stats("сил 16 лов") is None


SPELL_NAMES = ["Fireball", "Cure Wounds", "Web", "Fire Bolt", "Wall of Fire"]


@pytest.mark.parametrize("text, expected", [
    ("add fireball", (None, True, ["Fireball"], [])),
    ("remove web", (None, False, ["Web"], [])),
    ("Кузьма add cure wounds", ("Кузьма", True, ["Cure Wounds"], [])),
    ("Сир Гарет remove fireball", ("Сир Гарет", False, ["Fireball"], [])),
])
def test_spell_command_is_parsed(text, expected):
    assert parse_spell_command(text, SPELL_NAMES) == expected


def test_several_spells_go_in_one_command():
    """
    Список заклинаний вводят целиком, а не по одному сообщению на штуку:
    двадцать сообщений подряд — верный способ бросить это занятие.
    """
    assert parse_spell_command("add fireball, web, cure wounds", SPELL_NAMES) == (
        None, True, ["Fireball", "Web", "Cure Wounds"], []
    )


def test_unrecognised_spells_are_reported_separately():
    """
    Молча проглотить непонятое значит записать не весь список и не сказать
    об этом — игрок решит, что всё на месте.
    """
    name, adding, found, unknown = parse_spell_command(
        "add fireball, такого-нет, web", SPELL_NAMES
    )
    assert found == ["Fireball", "Web"]
    assert unknown == ["такого-нет"]


def test_a_prefix_is_enough():
    """За столом никто не печатает Wall of Fire целиком."""
    assert parse_spell_command("add wall of", SPELL_NAMES) == (
        None, True, ["Wall of Fire"], []
    )


def test_an_ambiguous_prefix_is_not_guessed():
    """"fire" подходит и Fireball, и Fire Bolt, и Wall of Fire."""
    assert parse_spell_command("add fire", SPELL_NAMES) == (None, True, [], ["fire"])


def test_names_the_srd_stripped_are_still_understood():
    """
    В SRD именные заклинания переименованы: Tenser's Floating Disk стал просто
    Floating Disk. Игрок печатает то, что написано в его книге.
    """
    names = ["Floating Disk", "Arcane Hand", "Black Tentacles"]
    assert parse_spell_command("add tenser's floating disk", names) == (
        None, True, ["Floating Disk"], []
    )
    assert parse_spell_command("add bigby's hand", names) == (
        None, True, ["Arcane Hand"], []
    )


def test_a_curly_apostrophe_is_the_same_apostrophe():
    """
    Телефон подставляет ’ вместо ', и различать их значит отвергать половину
    введённого с телефона.
    """
    names = ["Floating Disk", "Hunter's Mark"]
    assert parse_spell_command("add tenser’s floating disk", names) == (
        None, True, ["Floating Disk"], []
    )
    assert parse_spell_command("add hunter’s mark", names) == (
        None, True, ["Hunter's Mark"], []
    )


def test_an_exact_name_wins_over_a_longer_one():
    """
    "shield" — это целиком название заклинания, хотя оно же начинает
    "Shield of Faith". Отказываться от точного имени из-за того, что оно
    чему-то предшествует, значит не дать ввести половину каталога.
    """
    names = ["Shield", "Shield of Faith", "Fireball"]
    assert parse_spell_command("add shield", names) == (None, True, ["Shield"], [])
    assert parse_spell_command("add shield of faith", names) == (
        None, True, ["Shield of Faith"], []
    )


@pytest.mark.parametrize("text", ["", "add", "fireball", "Кузьма fireball"])
def test_broken_spell_command_is_refused(text):
    assert parse_spell_command(text, SPELL_NAMES) is None


CATALOG_NAMES = ["Goblin", "Orc", "Ogre", "Young Red Dragon", "Giant Spider"]


@pytest.mark.parametrize("text, expected", [
    ("goblin 4", [("Goblin", 4)]),
    ("4 goblin", [("Goblin", 4)]),
    ("goblin", [("Goblin", 1)]),
    ("GOBLIN x3", [("Goblin", 3)]),
    ("goblin 4, ogre", [("Goblin", 4), ("Ogre", 1)]),
])
def test_enemy_line_is_parsed(text, expected):
    resolved, unknown = parse_enemies(text, CATALOG_NAMES)
    assert resolved == expected
    assert unknown == []


def test_partial_names_are_resolved():
    """За столом никто не напечатает Young Red Dragon целиком."""
    resolved, unknown = parse_enemies("young red 1", CATALOG_NAMES)
    assert resolved == [("Young Red Dragon", 1)]


def test_unknown_enemy_is_reported_not_swallowed():
    """
    Промолчать про нераспознанного противника опаснее, чем не посчитать бой:
    игрок решит, что дракон учтён, а его в расчёте нет.
    """
    resolved, unknown = parse_enemies("goblin 2, василиск", CATALOG_NAMES)
    assert resolved == [("Goblin", 2)]
    assert unknown == ["василиск"]


def test_ambiguous_prefix_is_not_guessed():
    """"giant" подходит и пауку, и другим — гадать нельзя."""
    resolved, unknown = parse_enemies("giant", CATALOG_NAMES + ["Giant Eagle"])
    assert resolved == []
    assert unknown == ["giant"]


def test_an_exact_enemy_name_wins_over_a_longer_one():
    """У врагов та же ловушка, что у заклинаний: короткое имя внутри длинного."""
    resolved, unknown = parse_enemies("bat 3", ["Bat", "Bat Swarm"])
    assert resolved == [("Bat", 3)]
    assert unknown == []


def _sheet(class_data, spells, *pairs):
    return build_party_sheet(
        [PartyMember(key, level) for key, level in pairs],
        classes=class_data,
        spells=spells,
    )


def test_sheet_message_names_the_dangerous_gap(class_data, spells_fixture):
    """Дыра в спасбросках — самое ценное в листе, она обязана быть заметна."""
    sheet = _sheet(class_data, spells_fixture, ("srd_barbarian", 5), ("srd_rogue", 5))
    text = format_sheet(sheet)

    assert "Мудрост" in text
    assert "Hold Person" in text


def test_sheet_message_warns_about_physical_only_damage(class_data, spells_fixture):
    sheet = _sheet(class_data, spells_fixture, ("srd_barbarian", 5), ("srd_rogue", 5))
    assert "физическ" in format_sheet(sheet).lower()


def test_sheet_message_stays_quiet_when_there_is_nothing_to_warn_about(
    class_data, spells_fixture
):
    """
    Лист без предупреждений не должен придумывать их: если партия закрыта,
    сообщение говорит об этом, а не перечисляет шесть пунктов «всё хорошо».
    """
    sheet = _sheet(
        class_data, spells_fixture,
        ("srd_barbarian", 5), ("srd_cleric", 5), ("srd_rogue", 5), ("srd_wizard", 5),
    )
    text = format_sheet(sheet)

    assert "Hold Person" not in text
    assert sheet.covered_saves


def test_sheet_message_escapes_html(class_data, spells_fixture):
    sheet = _sheet(class_data, spells_fixture, ("srd_cleric", 5))
    assert "<" not in format_sheet(sheet).replace("<b>", "").replace("</b>", "").replace(
        "<i>", ""
    ).replace("</i>", "")


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
