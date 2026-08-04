"""
Хранилище персонажей и партий.

Бот многопользовательский: у каждого игрока свой персонаж, и данные одного
не должны быть видны другому. Партия собирается по коду-приглашению — именно
она даёт советнику по заклинаниям состав, ради которого он и писался.
"""

import pytest

from adapters.sqlite_storage import Storage


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "copilot.db")


def test_missing_character_is_none(storage):
    assert storage.get_character("вася") is None


def test_saved_character_comes_back(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    character = storage.get_character("вася")

    assert character.class_key == "srd_druid"
    assert character.level == 6


def test_saving_again_replaces_the_previous_character(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.save_character("вася", class_key="srd_wizard", level=7)

    assert storage.get_character("вася").class_key == "srd_wizard"


def test_characters_of_different_players_do_not_mix(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.save_character("петя", class_key="srd_cleric", level=4)

    assert storage.get_character("вася").class_key == "srd_druid"
    assert storage.get_character("петя").class_key == "srd_cleric"


def test_character_survives_reopening_the_database(tmp_path):
    """Бота перезапускают — персонажи обязаны это пережить."""
    path = tmp_path / "copilot.db"
    Storage(path).save_character("вася", class_key="srd_druid", level=6)

    assert Storage(path).get_character("вася").level == 6


def test_party_code_is_short_enough_to_retype(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    code = storage.create_party("вася")

    assert 4 <= len(code) <= 8
    assert code == code.upper(), "код читают вслух за столом"


def test_joining_by_code_puts_players_in_one_party(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.save_character("петя", class_key="srd_cleric", level=4)
    code = storage.create_party("вася")

    assert storage.join_party("петя", code) is True
    assert [m.class_key for m in storage.party_members("вася")] == ["srd_cleric"]


def test_party_listing_excludes_the_asker(storage):
    """Советник смотрит на союзников: собственный класс в дыры партии не входит."""
    storage.save_character("вася", class_key="srd_druid", level=6)
    code = storage.create_party("вася")
    storage.save_character("петя", class_key="srd_cleric", level=4)
    storage.join_party("петя", code)

    assert all(m.class_key != "srd_druid" for m in storage.party_members("вася"))
    assert [m.class_key for m in storage.party_members("петя")] == ["srd_druid"]


def test_unknown_code_is_refused(storage):
    storage.save_character("петя", class_key="srd_cleric", level=4)
    assert storage.join_party("петя", "НЕТУ") is False


def test_player_without_a_party_has_no_allies(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    assert storage.party_members("вася") == []


def test_leaving_a_party_removes_the_player_from_it(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.save_character("петя", class_key="srd_cleric", level=4)
    code = storage.create_party("вася")
    storage.join_party("петя", code)

    storage.leave_party("петя")

    assert storage.party_members("вася") == []
    assert storage.party_members("петя") == []


def test_creating_a_party_requires_a_character(storage):
    """Без персонажа в партию вступать нечем."""
    with pytest.raises(LookupError):
        storage.create_party("никто")
