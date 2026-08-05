"""
Перенос отряда текстом между ботом и сайтом.

Сайт и бот ведут записи под разными владельцами, и общий код партии связывает
их только пока оба смотрят в одну базу. Текстовый слепок переносит отряд туда,
где базы нет — на другую машину, в резервную копию, к другому человеку.

Ввозится только то, чем ввозящий распоряжается: свой персонаж и заведённые
вручную. Персонажи живых игроков пропускаются, иначе каждый перенос плодил бы
их копии.
"""

import pytest

from adapters.sqlite_storage import Storage
from core.models import PartyMember, Stats
from core.transfer import ParseError, dump_party, load_party


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "copilot.db")


def _filled_party(storage, owner="вася"):
    storage.save_character(owner, class_key="srd_druid", level=6, subclass_key="moon")
    storage.update_stats(owner, None, Stats(ac=16, hp=52, abilities={"wis": 18}))
    storage.update_spells(owner, None, add={"srd_entangle", "phb_thorn-whip"})
    storage.add_member(
        owner, name="Миша", class_key="hb_artificer", level=4,
        subclass_key="artillerist",
    )
    storage.update_stats(owner, "Миша", Stats(damage_per_round=24.0))


def test_a_dump_survives_a_round_trip(storage, tmp_path):
    _filled_party(storage)
    text = dump_party(storage, "вася")

    elsewhere = Storage(tmp_path / "other.db")
    load_party(elsewhere, "петя", text)

    mine = elsewhere.get_character("петя")
    assert (mine.class_key, mine.level, mine.subclass_key) == ("srd_druid", 6, "moon")
    assert mine.stats.ac == 16
    assert mine.stats.abilities == {"wis": 18}
    assert mine.spell_keys == {"srd_entangle", "phb_thorn-whip"}

    members = elsewhere.party_members("петя")
    assert [m.name for m in members] == ["Миша"]
    assert members[0].subclass_key == "artillerist"
    assert members[0].stats.damage_per_round == 24.0


def test_importing_twice_does_not_multiply_the_party(storage, tmp_path):
    """Слепок — это «сделай как здесь», а не «добавь ещё раз»."""
    _filled_party(storage)
    text = dump_party(storage, "вася")

    elsewhere = Storage(tmp_path / "other.db")
    load_party(elsewhere, "петя", text)
    load_party(elsewhere, "петя", text)

    assert len(elsewhere.party_members("петя")) == 1


def test_characters_of_live_players_are_skipped(storage, tmp_path):
    """
    Персонаж друга останется у друга. Ввозить его копией значит развести
    двойников и посчитать отряд вдвое больше, чем он есть.
    """
    _filled_party(storage)
    storage.save_character("друг", class_key="srd_wizard", level=4)
    code = storage.create_party("вася")
    storage.join_party("друг", code)

    text = dump_party(storage, "вася")
    elsewhere = Storage(tmp_path / "other.db")
    skipped = load_party(elsewhere, "петя", text)

    assert "Волшебник" in skipped
    assert [m.name for m in elsewhere.party_members("петя")] == ["Миша"]


def test_an_empty_party_gives_nothing_to_carry(storage):
    with pytest.raises(LookupError):
        dump_party(storage, "никто")


@pytest.mark.parametrize("text", ["", "не текст вовсе", "{}", '{"v": 999}'])
def test_broken_text_is_refused_with_an_explanation(storage, text):
    """
    Слепок переносят копипастой, и она рвётся. Молча ничего не сделать хуже,
    чем сказать, что перенос не удался.
    """
    with pytest.raises(ParseError):
        load_party(storage, "вася", text)


def test_a_dump_is_pasteable_as_one_message(storage):
    """Телеграм режет сообщения на 4096 символах."""
    _filled_party(storage)
    assert len(dump_party(storage, "вася")) < 4000
