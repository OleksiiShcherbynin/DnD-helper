"""
Адаптер модели: Gemini через google-genai.

Раньше здесь был пакет google-generativeai. Он закрыт: при импорте сам печатает
"All support for the google.generativeai package has ended" и отсылает к
google.genai, поэтому адаптер переписан на новый SDK.

Импорт ленивый, а фабрика возвращает None вместо исключения, если ключа или
пакета нет. Это осознанно: приложение обязано работать без модели —
детерминированные слои дают рейтинг с цифрами и без неё.
"""

import os

#: Переопределяется переменной GEMINI_MODEL без правки кода.
DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiExplainer:
    """Порт ExplainerProtocol поверх Gemini."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        from google import genai  # ленивый: нужен только когда есть ключ

        self._client = genai.Client(api_key=api_key)
        self._model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)

    def explain(self, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self._model, contents=prompt
        )
        return (response.text or "").strip()

    def available_models(self) -> list[str]:
        """Модели, доступные этому ключу. Нужно, чтобы не гадать с названием."""
        return sorted(
            model.name.removeprefix("models/")
            for model in self._client.models.list()
            if "generateContent" in (model.supported_actions or ())
        )


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
