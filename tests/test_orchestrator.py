"""
Конвейер целиком: правила -> эвристика -> (только по запросу) модель.

Здесь проверяется главное обещание проекта — что инструмент по умолчанию
не тратит ни одного запроса, а когда тратит, то ровно один и только если
такого ответа ещё не покупали.
"""

import pytest

from adapters.llm_cache import LlmCache
from core.orchestrator import recommend_wild_shape


class CountingExplainer:
    """Считает обращения. Проверяем именно расход запросов — это и есть поведение."""

    def __init__(self, answer="потому что быстрый"):
        self.calls = 0
        self.answer = answer

    def explain(self, prompt: str) -> str:
        self.calls += 1
        return self.answer


class BrokenExplainer:
    def explain(self, prompt: str) -> str:
        raise RuntimeError("модель недоступна")


@pytest.fixture
def cache(tmp_path):
    return LlmCache(tmp_path / "cache.db")


def _recommend(beasts, explainer=None, cache=None, **kwargs):
    return recommend_wild_shape(
        beasts,
        druid_level=kwargs.pop("druid_level", 8),
        situation_text=kwargs.pop("situation_text", "болото, догнать убегающего"),
        explainer=explainer,
        cache=cache,
        **kwargs,
    )


def test_no_request_is_spent_by_default(beasts, cache):
    explainer = CountingExplainer()
    result = _recommend(beasts, explainer, cache)

    assert explainer.calls == 0, "по умолчанию модель звать нельзя"
    assert result.used_llm is False
    assert result.explanation is None


def test_numbers_are_available_without_the_model(beasts, cache):
    result = _recommend(beasts, CountingExplainer(), cache)

    assert result.options, "рейтинг обязан быть даже без модели"
    assert all(option.why for option in result.options)


def test_explanation_costs_exactly_one_request(beasts, cache):
    explainer = CountingExplainer()
    result = _recommend(beasts, explainer, cache, want_explanation=True)

    assert explainer.calls == 1
    assert result.used_llm is True
    assert result.explanation == "потому что быстрый"


def test_repeating_the_same_question_costs_nothing(beasts, cache):
    explainer = CountingExplainer()
    _recommend(beasts, explainer, cache, want_explanation=True)
    second = _recommend(beasts, explainer, cache, want_explanation=True)

    assert explainer.calls == 1, "второй раз ответ обязан прийти из кэша"
    assert second.explanation == "потому что быстрый"
    assert second.used_llm is False


def test_a_different_level_is_a_different_question(beasts, cache):
    """Уровень меняет состав кандидатов, значит и ответ должен покупаться заново."""
    explainer = CountingExplainer()
    _recommend(beasts, explainer, cache, want_explanation=True, druid_level=8)
    _recommend(beasts, explainer, cache, want_explanation=True, druid_level=4)

    assert explainer.calls == 2


def test_editing_the_prompt_invalidates_paid_answers(beasts, cache, monkeypatch):
    """
    Версия промпта входит в ключ: после правки формулировки старые ответы
    больше не подходят, и кэш обязан их не отдавать.
    """
    import core.orchestrator as orchestrator

    explainer = CountingExplainer()
    _recommend(beasts, explainer, cache, want_explanation=True)

    monkeypatch.setattr(orchestrator, "PROMPT_VERSION", "2")
    _recommend(beasts, explainer, cache, want_explanation=True)

    assert explainer.calls == 2


def test_exhausted_budget_degrades_instead_of_failing(beasts, tmp_path):
    explainer = CountingExplainer()
    spent = LlmCache(tmp_path / "c.db", daily_budget=0, user_daily_budget=0)
    result = _recommend(beasts, explainer, spent, want_explanation=True)

    assert explainer.calls == 0
    assert result.explanation is None
    assert result.options, "рейтинг обязан остаться"


def test_broken_model_degrades_instead_of_failing(beasts, cache):
    result = _recommend(beasts, BrokenExplainer(), cache, want_explanation=True)

    assert result.explanation is None
    assert result.options, "за столом падать нельзя"


def test_missing_model_degrades_instead_of_failing(beasts, cache):
    """Ключа Gemini нет вовсе — приложение обязано работать."""
    result = _recommend(beasts, None, cache, want_explanation=True)

    assert result.explanation is None
    assert result.options


def test_illegal_forms_never_reach_the_prompt(beasts, cache):
    """
    Главная гарантия: в текст запроса попадают только легальные формы,
    поэтому предложить нелегальную модель физически не может.
    """
    seen = {}

    class Recording:
        def explain(self, prompt: str) -> str:
            seen["prompt"] = prompt
            return "ok"

    _recommend(beasts, Recording(), cache, want_explanation=True, druid_level=2)

    assert "Giant Eagle" not in seen["prompt"], "летающий не может попасть к друиду 2 уровня"
    assert "Wolf" in seen["prompt"]
