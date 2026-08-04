"""
Порты — контракты, через которые ядро говорит с внешним миром.

Методы синхронные. Ядро обслуживает один запрос за раз, распараллеливать
нечего, а синхронный код проще и напрямую ложится на Streamlit. Телеграм-бот
из будущей фазы асинхронный, но обёрнет эти вызовы в asyncio.to_thread —
это дешевле, чем тащить async через всё ядро ради одного адаптера.
"""

from typing import Protocol


class ExplainerProtocol(Protocol):
    """Порт модели: получает готовый промпт, возвращает текст объяснения."""

    def explain(self, prompt: str) -> str:
        ...


class CacheProtocol(Protocol):
    """Порт хранилища оплаченных ответов и суточного бюджета."""

    def get(self, key: str) -> str | None:
        ...

    def put(self, key: str, value: str) -> None:
        ...

    def try_spend(self, user_id: str) -> bool:
        ...
