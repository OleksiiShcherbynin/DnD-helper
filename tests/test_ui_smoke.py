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


def test_a_non_caster_is_told_there_is_nothing_for_them():
    """Воину советовать нечего: ни форм, ни заклинаний."""
    app = _app()
    app.sidebar.selectbox[0].set_value("srd_fighter").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.info, "воин должен получить пояснение, а не пустой экран"
