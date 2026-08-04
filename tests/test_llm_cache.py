"""
Кэш ответов модели и суточный бюджет.

Смысл слоя — чтобы бесплатного тира хватало. Кэш общий: в ключе нет ничего
личного, только советник, класс с уровнем, теги ситуации и состав кандидатов.
Поэтому запрос друга с похожим раскладом попадает в чужой кэш, и расход на
человека с ростом числа пользователей падает, а не растёт.
"""

import pytest

from adapters.llm_cache import LlmCache


@pytest.fixture
def cache(tmp_path):
    return LlmCache(tmp_path / "test.db", daily_budget=3, user_daily_budget=2)


def test_missing_key_returns_nothing(cache):
    assert cache.get("нет такого") is None


def test_stored_value_is_returned(cache):
    cache.put("ключ", "объяснение")
    assert cache.get("ключ") == "объяснение"


def test_value_survives_reopening_the_database(tmp_path):
    """За столом приложение перезапускают — кэш обязан переживать это."""
    path = tmp_path / "test.db"
    LlmCache(path).put("ключ", "объяснение")
    assert LlmCache(path).get("ключ") == "объяснение"


def test_cache_does_not_depend_on_who_asked(cache):
    """
    Ключ не содержит пользователя, поэтому ответ, оплаченный одним игроком,
    достаётся остальным даром. Это и делает общего бота выгодным.
    """
    cache.put("общий ключ", "объяснение")
    assert cache.get("общий ключ") == "объяснение"


def test_user_budget_runs_out_before_the_shared_one(cache):
    assert cache.try_spend("вася") is True
    assert cache.try_spend("вася") is True
    assert cache.try_spend("вася") is False, "личный лимит 2 запроса"


def test_one_exhausted_user_does_not_block_another(cache):
    cache.try_spend("вася")
    cache.try_spend("вася")
    assert cache.try_spend("петя") is True


def test_shared_budget_stops_everyone(cache):
    cache.try_spend("вася")
    cache.try_spend("вася")
    cache.try_spend("петя")
    assert cache.try_spend("петя") is False, "общий лимит 3 запроса на всех"


def test_budget_resets_on_a_new_day(tmp_path):
    day = ["2026-08-04"]
    cache = LlmCache(
        tmp_path / "test.db", daily_budget=1, user_daily_budget=1, clock=lambda: day[0]
    )
    assert cache.try_spend("вася") is True
    assert cache.try_spend("вася") is False

    day[0] = "2026-08-05"
    assert cache.try_spend("вася") is True
