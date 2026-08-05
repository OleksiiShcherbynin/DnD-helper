"""
Дымовой прогон интерфейса.

Проверяет то, что HTTP-ответ Streamlit проверить не может: что скрипт
отрабатывает без исключений и что поиск вариантов не трогает модель.
Streamlit отдаёт свою HTML-оболочку даже когда скрипт падает, поэтому
проверка кодом 200 прошла бы и на полностью сломанном приложении.

Требует загруженного каталога, поэтому пропускается, если
tools.sync_catalog ещё не запускали.
"""

import pytest
from streamlit.testing.v1 import AppTest

from adapters.open5e_catalog import DEFAULT_CREATURES_PATH, DEFAULT_SPELLS_PATH

pytestmark = pytest.mark.skipif(
    not (DEFAULT_CREATURES_PATH.exists() and DEFAULT_SPELLS_PATH.exists()),
    reason="каталог не загружен: uv run python -m tools.sync_catalog",
)

UI = "apps/ui.py"


@pytest.fixture
def database_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture(autouse=True)
def isolated_database(database_path, monkeypatch):
    """
    Интерфейс сохраняет персонажей, поэтому тесты обязаны работать на своей
    базе. Без этого прогон тестов дописывал бы участников в ту базу, которой
    пользуются за столом, и вердикты плыли бы от запуска к запуску.
    """
    monkeypatch.setenv("COPILOT_DB", str(database_path))


def _app(monkeypatch=None):
    return AppTest.from_file(UI, default_timeout=30).run()


def test_app_starts_without_exceptions():
    app = _app()
    assert not app.exception, [str(e) for e in app.exception]


def test_wildshape_advice_shows_forms_and_spends_nothing(monkeypatch):
    """Без ключа модель недоступна вовсе — а варианты обязаны появиться."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    app = _app()
    app.text_input[0].set_value("болото, преследуем убегающего").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.subheader, "варианты не показаны"


def test_switching_class_offers_the_spell_advisor(monkeypatch):
    """
    Второй советник появляется в интерфейсе сам, через реестр: файл ui.py
    не знает про заклинания ничего, кроме того, каким каталогом их кормить.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    app = _app()
    app.sidebar.selectbox[0].set_value("srd_wizard").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.subheader, "заклинания не показаны"


def test_level_1_druid_gets_spells_but_not_forms():
    """
    Превращаться друид научится со 2 уровня, а заклинания у него уже есть.
    Реестр обязан предложить ровно то, что доступно, а не всё подряд.
    """
    app = _app()
    app.sidebar.slider[0].set_value(1).run()

    assert not app.exception, [str(e) for e in app.exception]
    offered = app.radio[0].options if app.radio else []
    assert "Во что превратиться" not in offered
    assert "Какие заклинания взять" in offered


def test_party_sheet_warns_about_uncovered_saves():
    """
    Лист показывается до выбора советника, поэтому он полезен даже тому, кому
    советовать нечего. Волшебник в одиночку не тянет Ловкость — это должно
    быть видно, а не спрятано.
    """
    app = _app()
    app.sidebar.selectbox[0].set_value("srd_wizard").run()

    assert not app.exception, [str(e) for e in app.exception]
    warnings = " ".join(str(w.value) for w in app.warning)
    assert "Ловкость" in warnings


def test_party_sheet_is_shown_even_to_a_class_with_no_advice():
    """Воину советовать нечего, но состав отряда ему всё равно полезен."""
    app = _app()
    app.sidebar.selectbox[0].set_value("srd_fighter").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.warning, "лист партии не отрисовался"
    assert app.info, "и при этом должно быть сказано, что советов нет"


def _widget_by_label(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def test_encounter_calculator_gives_a_verdict():
    """Один гоблин против друида 6 уровня — очевидно не угроза."""
    app = _app()
    _widget_by_label(app.multiselect, "Кто против вас").set_value(["Goblin"]).run()

    assert not app.exception, [str(e) for e in app.exception]
    verdicts = " ".join(str(m.value) for m in list(app.success) + list(app.error))
    assert "Лёгкая" in verdicts


def test_a_hopeless_fight_is_called_hopeless():
    """
    Молодой красный дракон против одинокого друида 6 уровня — вердикт обязан
    быть недвусмысленным, иначе калькулятор бесполезен там, где нужнее всего.
    """
    app = _app()
    _widget_by_label(app.multiselect, "Кто против вас").set_value(
        ["Young Red Dragon"]
    ).run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.error, "смертельный бой должен показываться тревожно"
    assert "мертельно" in " ".join(str(m.value) for m in app.error)


def test_a_manually_added_member_counts_in_the_sheet(database_path):
    """
    Ради этого всё и затевалось: участник, который ботом не пользуется, должен
    попадать в расчёты наравне с остальными.

    Друид владеет Интеллектом и Мудростью, а Ловкость не тянет — плут её
    закрывает, и предупреждение про урон по площади обязано исчезнуть.
    """
    from adapters.sqlite_storage import Storage

    alone = _app()
    assert "Ловкость" in " ".join(str(w.value) for w in alone.warning)

    storage = Storage(database_path)
    storage.add_member("local", name="Тень", class_key="srd_rogue", level=5)

    with_rogue = _app()
    assert not with_rogue.exception, [str(e) for e in with_rogue.exception]
    assert "Ловкость" not in " ".join(str(w.value) for w in with_rogue.warning)


def test_subclass_is_offered_only_where_it_exists():
    """
    У друида есть Круг Луны, у волшебника описанных подклассов нет. Пустой
    выбор из одного варианта «не выбран» только занимал бы место.
    """
    druid = _app()
    assert any(box.label == "Подкласс" for box in druid.sidebar.selectbox)

    wizard = _app()
    wizard.sidebar.selectbox[0].set_value("srd_wizard").run()
    assert not any(box.label == "Подкласс" for box in wizard.sidebar.selectbox)


def test_moon_druid_is_offered_bigger_beasts():
    """CR 2 против CR 1/2 — это разные звери, и разница обязана быть видна."""
    app = _app()
    _widget_by_label(app.sidebar.selectbox, "Подкласс").set_value("moon").run()
    _widget_by_label(app.text_input, "Что происходит?").set_value("бой в лесу").run()

    assert not app.exception, [str(e) for e in app.exception]
    offered = " ".join(str(header.value) for header in app.subheader)
    assert offered, "формы не показаны"


def test_entered_numbers_change_the_fight_estimate(database_path):
    """
    Ради этого фаза и делалась: введённые хиты и урон должны попадать в
    расчёт боя, а не украшать карточку персонажа.
    """
    from adapters.sqlite_storage import Storage
    from core.models import Stats

    before = _app()
    _widget_by_label(before.multiselect, "Кто против вас").set_value(["Ogre"]).run()
    weak = " ".join(str(m.value) for m in list(before.success) + list(before.error))

    storage = Storage(database_path)
    storage.update_stats(
        "local", None, Stats(hp=250, damage_per_round=90.0, attack_bonus=12)
    )

    after = _app()
    _widget_by_label(after.multiselect, "Кто против вас").set_value(["Ogre"]).run()

    assert not after.exception, [str(e) for e in after.exception]
    strong = " ".join(str(m.value) for m in list(after.success) + list(after.error))
    assert strong != weak, "введённые числа не дошли до расчёта"


def test_a_known_spell_list_narrows_what_the_party_covers(database_path):
    """
    Ради этого фаза и делалась. Друид без списка «закрывает» и лечение, и
    контроль — просто потому, что они есть в списке его класса. Стоит указать,
    что он знает только Entangle, и лечение обязано стать дырой.
    """
    from adapters.sqlite_storage import Storage

    wide = _app()
    assert "лечение" not in " ".join(str(w.value) for w in wide.warning)

    storage = Storage(database_path)
    storage.update_spells("local", None, add={"srd_entangle"})

    narrow = _app()
    assert not narrow.exception, [str(e) for e in narrow.exception]
    assert "лечение" in " ".join(str(w.value) for w in narrow.warning)


def test_two_members_with_the_same_name_do_not_break_the_page(database_path):
    """
    Двух друидов в отряде ничто не запрещает, а Streamlit падает на одинаковых
    ключах элементов. Страница обязана рисоваться, а не разваливаться.
    """
    from adapters.sqlite_storage import Storage

    storage = Storage(database_path)
    storage.save_character("local", class_key="srd_druid", level=6)
    storage.add_member("local", name="Миша", class_key="hb_artificer", level=4)
    storage.add_member("local", name="Миша", class_key="srd_fighter", level=3)

    app = _app()
    assert not app.exception, [str(e) for e in app.exception]


def test_an_old_placeholder_is_removed_from_the_party(database_path):
    """
    Пока сайт вступал в партию своим персонажем, он оставлял там пустого
    друида. Смена поведения тех записей не убрала — их надо вычищать, иначе
    отряд так и считается на одного больше.
    """
    from adapters.sqlite_storage import Storage

    storage = Storage(database_path)
    storage.save_character("вася", class_key="srd_druid", level=4)
    code = storage.create_party("вася")

    storage.save_character("local", class_key="srd_druid", level=6)
    storage.join_party("local", code)
    assert len(storage.party_by_code(code)) == 2

    _app()

    assert len(storage.party_by_code(code)) == 1, "заглушка осталась в отряде"


def test_watching_a_party_shows_it_without_joining_it(database_path):
    """
    Сайт — окно в отряд, а не ещё один игрок. Раньше ввод кода добавлял туда
    его заглушку, и в партии появлялся пустой друид, которого никто не создавал.
    """
    from adapters.sqlite_storage import Storage

    storage = Storage(database_path)
    storage.save_character("вася", class_key="srd_druid", level=4)
    storage.add_member("вася", name="Миша", class_key="hb_artificer", level=4)
    code = storage.create_party("вася")
    storage.watch_party("local", code, acting_as="Друид")

    app = _app()

    assert not app.exception, [str(e) for e in app.exception]
    assert len(storage.party_by_code(code)) == 2, "сайт добавил кого-то от себя"

    shown = " ".join(str(w.value) for w in app.sidebar.markdown)
    assert "Миша" in shown


def test_acting_as_a_party_member_edits_that_character(database_path):
    """Правки на сайте попадают в настоящего персонажа, а не в его копию."""
    from adapters.sqlite_storage import Storage

    storage = Storage(database_path)
    storage.save_character("вася", class_key="srd_druid", level=4)
    code = storage.create_party("вася")
    storage.watch_party("local", code, acting_as="Друид")

    app = _app()
    app.sidebar.slider[0].set_value(9).run()

    assert not app.exception, [str(e) for e in app.exception]
    assert storage.get_character("вася").level == 9


def test_a_non_caster_is_told_there_is_nothing_for_them():
    """Воину советовать нечего: ни форм, ни заклинаний."""
    app = _app()
    app.sidebar.selectbox[0].set_value("srd_fighter").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.info, "воин должен получить пояснение, а не пустой экран"
