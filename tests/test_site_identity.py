"""
Сайт как окно в отряд, а не как ещё один игрок.

У сайта нет аккаунтов, поэтому он заводил себе персонажа сам. Стоило ввести код
партии — и эта заглушка вступала в отряд наравне со всеми: в партии появлялся
пустой друид, которого никто не создавал, а расчёты считали его в составе.

Правильно иначе: сайт смотрит на партию по коду и выступает за одного из тех,
кто в ней уже есть.
"""

import pytest

from adapters.sqlite_storage import Storage
from core.models import Stats

SITE = "local"


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "copilot.db")


@pytest.fixture
def party(storage):
    storage.save_character("вася", class_key="srd_druid", level=4)
    storage.add_member("вася", name="Миша", class_key="hb_artificer", level=4)
    return storage.create_party("вася")


def test_watching_a_party_adds_nobody_to_it(storage, party):
    """Заглушка сайта не должна оказываться в чужом отряде."""
    storage.watch_party(SITE, party, acting_as="Друид")

    names = [m.name for m in storage.party_by_code(party)]
    assert sorted(names) == ["Друид", "Миша"]


def test_the_watched_party_is_remembered(storage, party):
    storage.watch_party(SITE, party, acting_as="Друид")

    state = storage.get_watch(SITE)
    assert (state.party_code, state.acting_as) == (party, "Друид")


def test_nothing_is_watched_until_asked(storage):
    assert storage.get_watch(SITE) is None


def test_an_unknown_code_is_refused(storage):
    assert storage.watch_party(SITE, "НЕТУ", acting_as="Друид") is False


def test_the_watcher_can_fill_in_the_character_it_plays(storage, party):
    """Сайт правит настоящего персонажа, а не свою копию."""
    storage.watch_party(SITE, party, acting_as="Друид")

    assert storage.update_stats_in_party(party, "Друид", Stats(ac=16)) is True
    assert storage.get_character("вася").stats.ac == 16


def test_the_watcher_can_fill_in_anyone_in_that_party(storage, party):
    assert storage.update_spells_in_party(party, "Миша", add={"srd_fireball"}) is True

    misha = next(m for m in storage.party_by_code(party) if m.name == "Миша")
    assert misha.spell_keys == {"srd_fireball"}


def test_someone_outside_the_party_stays_untouchable(storage, party):
    storage.save_character("чужак", class_key="srd_bard", level=3)
    assert storage.update_stats_in_party(party, "Бард", Stats(ac=20)) is False


def test_leaving_forgets_the_party(storage, party):
    storage.watch_party(SITE, party, acting_as="Друид")
    storage.stop_watching(SITE)

    assert storage.get_watch(SITE) is None


def test_a_watcher_never_appears_in_the_party_it_watches(storage, party):
    """
    Даже если у сайта остался свой персонаж со времён работы в одиночку —
    в чужую партию он не попадает.
    """
    storage.save_character(SITE, class_key="srd_wizard", level=6)
    storage.watch_party(SITE, party, acting_as="Друид")

    assert "Волшебник" not in [m.name for m in storage.party_by_code(party)]
