"""
Дымовой прогон интерфейса.

Проверяет то, что HTTP-ответ Streamlit проверить не может: что скрипт
действительно отрабатывает без исключений и что поиск вариантов не трогает
модель. Требует загруженного каталога, поэтому пропускается, если
tools.sync_catalog ещё не запускали.
"""

import pytest
from streamlit.testing.v1 import AppTest

from adapters.open5e_catalog import DEFAULT_BEASTS_PATH

pytestmark = pytest.mark.skipif(
    not DEFAULT_BEASTS_PATH.exists(),
    reason="каталог не загружен: uv run python -m tools.sync_catalog",
)

UI = "apps/ui.py"


def test_app_starts_without_exceptions():
    app = AppTest.from_file(UI, default_timeout=30).run()
    assert not app.exception, [str(e) for e in app.exception]


def test_searching_shows_forms_and_spends_nothing(monkeypatch):
    """Без ключа модель недоступна вовсе — а варианты обязаны появиться."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    app = AppTest.from_file(UI, default_timeout=30).run()
    app.text_input[0].set_value("болото, преследуем убегающего").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.subheader, "варианты не показаны"
    assert "Wild Shape" in app.title[0].value


def test_low_level_druid_is_told_it_cannot_transform():
    app = AppTest.from_file(UI, default_timeout=30).run()
    app.sidebar.slider[0].set_value(1).run()
    app.text_input[0].set_value("болото").run()

    assert not app.exception, [str(e) for e in app.exception]
    assert app.warning, "друид 1 уровня должен получить предупреждение"
