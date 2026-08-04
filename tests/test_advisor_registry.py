"""
Реестр советников — второй механизм расширения.

Обещание такое: новая идея становится файлом с одной регистрацией, и она сама
появляется во всех интерфейсах, потому что конвейер, кэш и бюджет общие.
Тест с выдуманным советником проверяет именно это, а не то, что реестр
непустой: если бы конвейер знал про вайлдшейп или заклинания по имени,
чужой советник через него бы не прошёл.
"""

import pytest

from adapters.llm_cache import LlmCache
from core.advisor import ADVISORS, Advice, Option, advise
from core.advisors.spells import PartyMember
from core.request import AdviceRequest


@pytest.fixture
def cache(tmp_path):
    return LlmCache(tmp_path / "cache.db")


class CountingExplainer:
    def __init__(self):
        self.calls = 0

    def explain(self, prompt: str) -> str:
        self.calls += 1
        return "объяснение"


def test_both_advisors_are_registered():
    assert {"wildshape", "spells"} <= set(ADVISORS)


def test_wildshape_is_offered_only_to_druids():
    druid = AdviceRequest(class_key="srd_druid", level=6)
    wizard = AdviceRequest(class_key="srd_wizard", level=6)

    assert ADVISORS["wildshape"].applies_to(druid) is True
    assert ADVISORS["wildshape"].applies_to(wizard) is False


def test_spell_advisor_is_offered_to_every_caster():
    for class_key in ("srd_wizard", "srd_cleric", "srd_bard", "srd_ranger"):
        assert ADVISORS["spells"].applies_to(AdviceRequest(class_key=class_key, level=5))


def test_a_brand_new_advisor_runs_through_the_shared_pipeline(beasts, cache):
    """
    Выдуманный советник, о котором конвейер ничего не знает: он обязан
    получить и кэш, и бюджет, и режим без модели — бесплатно.
    """

    class FeatAdvisor:
        key = "feats"
        title = "Какой фит взять"

        def applies_to(self, request):
            return request.level >= 4

        def rank(self, request, catalog):
            return [Option(name="Sharpshooter", score=1.0, why="дальний бой партии не закрыт")], 1, None

        def prompt(self, request, options):
            return "Посоветуй фит"

    explainer = CountingExplainer()
    request = AdviceRequest(class_key="fighter", level=4)

    free = advise(FeatAdvisor(), catalog=[], request=request, explainer=explainer, cache=cache)
    assert free.options[0].name == "Sharpshooter"
    assert explainer.calls == 0, "по умолчанию модель не зовём ни для одного советника"

    paid = advise(
        FeatAdvisor(), catalog=[], request=request,
        explainer=explainer, cache=cache, want_explanation=True,
    )
    assert paid.explanation == "объяснение"
    assert explainer.calls == 1

    advise(
        FeatAdvisor(), catalog=[], request=request,
        explainer=explainer, cache=cache, want_explanation=True,
    )
    assert explainer.calls == 1, "кэш работает и для чужого советника"


def test_different_advisors_do_not_share_cached_answers(beasts, cache):
    """Ключ кэша содержит советника, иначе один совет подменял бы другой."""

    def make(key):
        class Stub:
            def __init__(self):
                self.key = key
                self.title = key

            def applies_to(self, request):
                return True

            def rank(self, request, catalog):
                return [Option(name="X", score=1.0, why="")], 1, None

            def prompt(self, request, options):
                return f"промпт {key}"

        return Stub()

    explainer = CountingExplainer()
    request = AdviceRequest(class_key="srd_druid", level=6)

    advise(make("a"), catalog=[], request=request, explainer=explainer, cache=cache, want_explanation=True)
    advise(make("b"), catalog=[], request=request, explainer=explainer, cache=cache, want_explanation=True)

    assert explainer.calls == 2


def test_wildshape_through_the_registry_still_respects_the_rules(beasts, cache):
    request = AdviceRequest(class_key="srd_druid", level=2)
    result = advise(ADVISORS["wildshape"], catalog=beasts, request=request)

    assert isinstance(result, Advice)
    assert [option.name for option in result.options] == ["Wolf"]


def test_spell_advice_through_the_registry_uses_the_party(spells_fixture, cache):
    request = AdviceRequest(
        class_key="srd_bard",
        level=3,
        party=(PartyMember("fighter"), PartyMember("rogue")),
    )
    result = advise(ADVISORS["spells"], catalog=spells_fixture, request=request)

    assert result.options
    assert all(option.why for option in result.options)
