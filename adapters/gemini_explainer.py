"""
Адаптер модели: Gemini через официальный SDK.

Импорт SDK ленивый, а фабрика возвращает None вместо исключения, если ключа
или пакета нет. Это осознанно: приложение обязано работать без модели —
детерминированные слои дают рейтинг с цифрами и без неё.
"""

import os

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiExplainer:
    """Порт ExplainerProtocol поверх Gemini."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        import google.generativeai as genai  # ленивый: нужен только с ключом

        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        )

    def explain(self, prompt: str) -> str:
        return (self._model.generate_content(prompt).text or "").strip()


def explainer_from_env() -> GeminiExplainer | None:
    """
    Собрать адаптер из переменных окружения.

    Возвращает None, если ключа нет или SDK не установлен — вызывающая сторона
    просто останется без объяснений, а не упадёт.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        return GeminiExplainer(api_key)
    except ImportError:
        return None
