"""
Реестр советников и общий конвейер.

Второй механизм расширения. Новый советник — это модуль, реализующий протокол
ниже, плюс одна строка регистрации. Дальше он получает бесплатно всё, что уже
построено: режим без модели по умолчанию, общий кэш, суточный бюджет и
одинаковое отображение в интерфейсах.

Конвейер намеренно ничего не знает про вайлдшейп и заклинания: он работает с
протоколом. Тест с выдуманным советником по фитам проверяет, что это правда.
"""

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from core.ports import CacheProtocol, ExplainerProtocol
from core.request import AdviceRequest
from core.situation import Situation

#: Входит в ключ кэша: правка формулировки промпта обязана обесценить старые
#: ответы, иначе к новому вопросу подошёл бы ответ на старый.
PROMPT_VERSION = "2"


@dataclass(frozen=True)
class Option:
    """Один вариант в выдаче — в одинаковом виде для любого советника."""

    name: str
    score: float
    why: str
    #: Короткие числа для показа: CR/HP/AC у формы, круг/школа у заклинания.
    facts: dict[str, str] = field(default_factory=dict)
    #: Исходный объект советника, если вызывающей стороне нужны подробности.
    source: Any = None


@dataclass(frozen=True)
class Advice:
    """Готовый ответ. Explanation равен None, если модель не звали."""

    advisor: str
    title: str
    options: list[Option]
    legal_count: int
    situation: Situation | None = None
    explanation: str | None = None
    used_llm: bool = False


class Advisor(Protocol):
    """Контракт советника. Всё остальное берёт на себя конвейер."""

    key: str
    title: str

    def applies_to(self, request: AdviceRequest) -> bool:
        """Имеет ли этот совет смысл для такого персонажа."""
        ...

    def rank(
        self, request: AdviceRequest, catalog: Iterable[Any]
    ) -> tuple[list[Option], int, Situation | None]:
        """Варианты, число легальных кандидатов и разобранная ситуация."""
        ...

    def prompt(self, request: AdviceRequest, options: list[Option]) -> str:
        """Промпт из уже посчитанных цифр."""
        ...


ADVISORS: dict[str, Advisor] = {}


def register(advisor: Advisor) -> Advisor:
    """Добавить советника в реестр. Интерфейсы подхватят его сами."""
    ADVISORS[advisor.key] = advisor
    return advisor


def _cache_key(advisor: Advisor, request: AdviceRequest, options: list[Option]) -> str:
    """
    Ключ без единого личного поля — поэтому кэш общий для всех пользователей.

    Советник входит в ключ: без него совет по формам и совет по заклинаниям
    для одного и того же персонажа схлопнулись бы в одну запись.
    """
    variants = ",".join(sorted(option.name for option in options))
    party = ",".join(sorted(f"{m.class_key}{m.level}" for m in request.party))
    situation = request.situation_text.lower().split()
    return (
        f"v{PROMPT_VERSION}|{advisor.key}|{request.class_key}{request.level}"
        f"|{' '.join(sorted(situation))}|{party}|{variants}"
    )


def advise(
    advisor: Advisor,
    *,
    catalog: Iterable[Any],
    request: AdviceRequest,
    explainer: ExplainerProtocol | None = None,
    cache: CacheProtocol | None = None,
    user_id: str = "local",
    want_explanation: bool = False,
) -> Advice:
    """
    Прогнать советника через общий конвейер.

    Без want_explanation не тратит ни одного запроса к модели. Отказ модели,
    отсутствие ключа и исчерпанный бюджет обрабатываются одинаково: объяснения
    не будет, варианты останутся. За столом падать нельзя.
    """
    options, legal_count, situation = advisor.rank(request, catalog)
    options = options[: request.top_n]

    base = Advice(
        advisor=advisor.key,
        title=advisor.title,
        options=options,
        legal_count=legal_count,
        situation=situation,
    )

    if not want_explanation or not options:
        return base

    key = _cache_key(advisor, request, options)

    if cache is not None:
        cached = cache.get(key)
        if cached is not None:
            return replace(base, explanation=cached)

    if explainer is None:
        return base

    # Бюджет спрашиваем до вызова: исчерпанный лимит — штатный режим, а не сбой.
    if cache is not None and not cache.try_spend(user_id):
        return base

    try:
        answer = explainer.explain(advisor.prompt(request, options))
    except Exception:
        return base

    if cache is not None:
        cache.put(key, answer)

    return replace(base, explanation=answer, used_llm=True)


# Регистрация штатных советников. Импорт стоит в конце файла осознанно:
# советники импортируют Option и register отсюда, и к этому моменту оба уже
# определены. Добавление нового советника — файл рядом и строка здесь.
from core.advisors.spells import SpellAdvisor  # noqa: E402
from core.advisors.wildshape import WildShapeAdvisor  # noqa: E402

register(WildShapeAdvisor())
register(SpellAdvisor())
