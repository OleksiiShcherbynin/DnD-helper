"""
Несколько персонажей у одного владельца.

Основной сценарий сменился: раньше каждый вёл себя сам, теперь один человек
ведёт весь отряд, потому что остальные ботом не пользуются. Персонаж перестал
быть жёстко привязан к аккаунту телеграма.
"""

import sqlite3

import pytest

from adapters.sqlite_storage import Storage, StorageTooNew

#: Схема, с которой бот работал до появления ручных участников. Нужна, чтобы
#: проверить миграцию на настоящих данных, а не на выдуманных.
_OLD_SCHEMA = """
CREATE TABLE characters (
    user_id    TEXT PRIMARY KEY,
    class_key  TEXT NOT NULL,
    level      INTEGER NOT NULL,
    party_code TEXT
);
CREATE TABLE parties (
    code       TEXT PRIMARY KEY,
    created_by TEXT NOT NULL
);
"""


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "copilot.db")


def test_own_character_still_works_as_before(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    character = storage.get_character("вася")

    assert character.class_key == "srd_druid"
    assert character.level == 6


def test_manual_member_joins_the_party_of_whoever_added_them(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member("вася", name="Гарет", class_key="srd_fighter", level=5)

    assert [member.name for member in storage.party_members("вася")] == ["Гарет"]


def test_manual_members_do_not_replace_the_owner_character(storage):
    """Раньше запись была одна на аккаунт — теперь их несколько, и своя отдельно."""
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member("вася", name="Гарет", class_key="srd_fighter", level=5)

    assert storage.get_character("вася").class_key == "srd_druid"


def test_full_party_includes_the_owner(storage):
    """
    Лист партии считает отряд целиком, а советник по заклинаниям — только
    союзников. Поэтому нужны обе выборки, и путать их нельзя.
    """
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member("вася", name="Гарет", class_key="srd_fighter", level=5)

    names = {member.name for member in storage.full_party("вася")}
    assert "Гарет" in names
    assert len(names) == 2


def test_several_manual_members_coexist(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member("вася", name="Гарет", class_key="srd_fighter", level=5)
    storage.add_member("вася", name="Лия", class_key="srd_cleric", level=5)

    assert len(storage.party_members("вася")) == 2


def test_member_can_be_removed_by_name(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member("вася", name="Гарет", class_key="srd_fighter", level=5)

    assert storage.remove_member("вася", "гарет") is True
    assert storage.party_members("вася") == []


def test_removing_someone_who_is_not_there_is_not_an_error(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    assert storage.remove_member("вася", "Никого") is False


def test_you_cannot_remove_another_players_character(storage):
    """Ручные участники принадлежат тому, кто их завёл, и только ему."""
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.save_character("петя", class_key="srd_cleric", level=4)
    code = storage.create_party("вася")
    storage.join_party("петя", code)

    assert storage.remove_member("вася", "петя") is False
    assert len(storage.party_members("вася")) == 1


def test_manual_members_follow_the_owner_into_a_party(storage):
    """
    Участника завели до вступления в партию — он всё равно обязан оказаться
    в ней вместе с владельцем, иначе отряд посчитается неполным.
    """
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member("вася", name="Гарет", class_key="srd_fighter", level=5)
    storage.save_character("петя", class_key="srd_cleric", level=4)

    code = storage.create_party("вася")
    storage.join_party("петя", code)

    names = {member.name for member in storage.party_members("петя")}
    assert "Гарет" in names, "чужой ручной участник тоже часть отряда"


def test_old_database_is_migrated_without_losing_anyone(tmp_path):
    """
    Персонажей друзей уже завели, терять их нельзя. Проверяется на настоящей
    старой схеме, а не на пересказе того, как она выглядела.
    """
    path = tmp_path / "copilot.db"
    old = sqlite3.connect(path)
    old.executescript(_OLD_SCHEMA)
    old.execute("INSERT INTO parties VALUES ('ABC123', 'вася')")
    old.executemany(
        "INSERT INTO characters (user_id, class_key, level, party_code) VALUES (?, ?, ?, ?)",
        [("вася", "srd_druid", 6, "ABC123"), ("петя", "srd_cleric", 4, "ABC123")],
    )
    old.commit()
    old.close()

    storage = Storage(path)

    assert storage.get_character("вася").class_key == "srd_druid"
    assert storage.get_character("петя").level == 4
    assert [m.class_key for m in storage.party_members("вася")] == ["srd_cleric"]


def test_subclass_is_remembered(storage):
    storage.save_character("вася", class_key="srd_druid", level=6, subclass_key="moon")
    assert storage.get_character("вася").subclass_key == "moon"


def test_subclass_is_optional(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    assert storage.get_character("вася").subclass_key is None


def test_member_subclass_reaches_the_party(storage):
    storage.save_character("вася", class_key="srd_druid", level=6)
    storage.add_member(
        "вася", name="Кузьма", class_key="hb_artificer", level=5,
        subclass_key="artillerist",
    )

    member = storage.party_members("вася")[0]
    assert member.class_key == "hb_artificer"
    assert member.subclass_key == "artillerist"


def test_the_old_artillerist_class_becomes_a_subclass(tmp_path):
    """
    Артиллерист какое-то время был заведён отдельным классом. Персонажи,
    созданные тогда, обязаны пережить переезд, а не остаться с ключом класса,
    которого больше нет.
    """
    path = tmp_path / "copilot.db"
    before = Storage(path)
    before.save_character("вася", class_key="srd_druid", level=6)
    before._db.execute(
        "UPDATE characters SET class_key = 'hb_artificer_artillerist' "
        "WHERE telegram_id = 'вася'"
    )
    before._db.execute("UPDATE schema_meta SET version = 2")
    before._db.commit()
    before.close()

    character = Storage(path).get_character("вася")

    assert character.class_key == "hb_artificer"
    assert character.subclass_key == "artillerist"


def test_database_from_a_newer_version_says_to_restart(tmp_path):
    """
    Работающий бот держит модули в памяти, и правка файлов его не меняет.
    После смены схемы старый процесс бьётся о новую базу сырой ошибкой SQL
    вида «no such column» — по ней не догадаешься, что нужен перезапуск.
    """
    path = tmp_path / "copilot.db"
    Storage(path).save_character("вася", class_key="srd_druid", level=6)

    ahead = sqlite3.connect(path)
    ahead.execute("UPDATE schema_meta SET version = 99")
    ahead.commit()
    ahead.close()

    with pytest.raises(StorageTooNew, match="[Пп]ерезапуст"):
        Storage(path)


def test_migration_runs_only_once(tmp_path):
    """Повторное открытие не должно ни дублировать, ни терять записи."""
    path = tmp_path / "copilot.db"
    Storage(path).save_character("вася", class_key="srd_druid", level=6)
    Storage(path).add_member("вася", name="Гарет", class_key="srd_fighter", level=5)

    reopened = Storage(path)
    assert reopened.get_character("вася").class_key == "srd_druid"
    assert len(reopened.party_members("вася")) == 1
