"""
Общий конвейер на примере советника по формам.

Проверяется главное обещание проекта: по умолчанию не тратится ни одного
запроса, а когда тратится — ровно один и только если такого ответа ещё не
покупали. Конвейер один на всех советников, поэтому эти гарантии
распространяются и на будущие (см. tests/test_advisor_registry.py).
"""

import pytest

from adapters.llm_cache import LlmCache
from core.advisor import ADVISORS, advise
from core.request import AdviceRequest

WILDSHAPE = ADVISORS["wildshape"]


class CountingExplainer:
    """Считает обращения. Расход запросов — это и есть проверяемое поведение."""

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


def _recommend(beasts, explainer=None, cache=None, level=8, **kwargs):
    request = AdviceRequest(
        class_key="srd_druid",
        level=level,
        situation_text=kwargs.pop("situation_text", "болото, догнать убегающего"),
    )
    return advise(
        WILDSHAPE, catalog=beasts, request=request,
        explainer=explainer, cache=cache, **kwargs,
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
    assert all(option.facts["HP"] for option in result.options)


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
    """Уровень меняет состав кандидатов, значит и ответ покупается заново."""
    explainer = CountingExplainer()
    _recommend(beasts, explainer, cache, want_explanation=True, level=8)
    _recommend(beasts, explainer, cache, want_explanation=True, level=4)

    assert explainer.calls == 2


def test_editing_the_prompt_invalidates_paid_answers(beasts, cache, monkeypatch):
    """Версия промпта входит в ключ: после правки формулировки старые ответы не подходят."""
    import core.advisor as advisor_module

    explainer = CountingExplainer()
    _recommend(beasts, explainer, cache, want_explanation=True)

    monkeypatch.setattr(advisor_module, "PROMPT_VERSION", "999")
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

    _recommend(beasts, Recording(), cache, want_explanation=True, level=2)

    assert "Giant Eagle" not in seen["prompt"], "летающий не может попасть к друиду 2 уровня"
    assert "Wolf" in seen["prompt"]
