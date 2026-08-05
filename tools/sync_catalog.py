"""
Разовая загрузка каталога SRD 5.1 из Open5e в data/catalog/.

После неё приложение работает офлайн: 98 зверей и 319 заклинаний занимают
считанные мегабайты, поэтому за столом ничего не зависит от доступности API.

    uv run python -m tools.sync_catalog
"""

import json
from pathlib import Path

import httpx

API = "https://api.open5e.com/v2"
DOCUMENT = "srd-2014"
CATALOG_DIR = Path(__file__).resolve().parent.parent / "data" / "catalog"

#: Ожидаемые количества, снятые с живого API. Служат стражем: расхождение
#: означает либо сломанный фильтр, либо изменение данных на стороне источника.
EXPECTED_CREATURES = 325
EXPECTED_BEASTS = 98
EXPECTED_SPELLS = 319

#: Проверка соглашения об именовании ключей классов. Правильный ключ —
#: srd_wizard; на "wizard" API молча возвращает пустоту, и без этой сверки
#: советник по заклинаниям будущей фазы не нашёл бы ни одного варианта.
WIZARD_CLASS_KEY = "srd_wizard"
EXPECTED_WIZARD_SPELLS = 204

#: 12 базовых классов и 12 подклассов. Нам нужны только базовые: у них лежат
#: кость хитов и владения спасбросками.
EXPECTED_CLASSES = 12


class CatalogCountMismatch(RuntimeError):
    """Каталог загрузился не в том объёме, что ожидался."""


def verify_count(label: str, actual: int, expected: int) -> None:
    """
    Сверить количество записей с ожидаемым.

    Ноль выделен отдельно: Open5e на неизвестное значение фильтра не падает,
    а молча возвращает пустой список. Без этой проверки опечатка в фильтре
    выглядела бы как "просто нет подходящих вариантов".
    """
    if actual == expected:
        return

    if actual == 0:
        raise CatalogCountMismatch(
            f"{label}: получено 0 записей вместо {expected}. "
            f"Скорее всего опечатка в значении фильтра — Open5e на неизвестное "
            f"значение не отдаёт ошибку, а возвращает пустой список."
        )

    raise CatalogCountMismatch(
        f"{label}: получено {actual} записей вместо {expected}. "
        f"Либо изменился фильтр, либо данные в источнике."
    )


def _fetch_all(
    endpoint: str, params: dict, *, client: httpx.Client | None = None
) -> list[dict]:
    """Собрать все страницы выдачи."""
    results: list[dict] = []
    url: str | None = f"{API}/{endpoint}/"
    query: dict | None = dict(params, limit=200)

    owned = client is None
    client = client or httpx.Client(timeout=60)
    try:
        while url:
            response = client.get(url, params=query)
            response.raise_for_status()
            payload = response.json()
            results.extend(payload["results"])
            url = payload.get("next")
            # Ссылка next уже несёт все параметры, поэтому свои больше не передаём.
            # Именно None, а не пустой словарь: httpx на params={} затирает
            # query-строку целиком, next теряет page=2, и первая страница
            # качается по кругу — синхронизация зависает молча.
            query = None
    finally:
        if owned:
            client.close()

    return results


def _write(name: str, records: list[dict]) -> Path:
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    path = CATALOG_DIR / f"{name}.json"
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return path


def sync() -> None:
    # Один файл на всех: звери нужны как формы, остальные — как противники.
    creatures = _fetch_all("creatures", {"document__key": DOCUMENT})
    verify_count("Существа", len(creatures), EXPECTED_CREATURES)

    beasts = [c for c in creatures if (c.get("type") or {}).get("key") == "beast"]
    verify_count("Звери", len(beasts), EXPECTED_BEASTS)

    path = _write("creatures", creatures)
    print(f"Существа: {len(creatures)} -> {path} (из них зверей: {len(beasts)})")

    spells = _fetch_all("spells", {"document__key": DOCUMENT})
    verify_count("Заклинания", len(spells), EXPECTED_SPELLS)

    # Сверка соглашения об именовании ключей классов на уже скачанных данных,
    # без лишнего запроса. Ломается тихо, поэтому проверяется явно.
    wizard = sum(
        1
        for spell in spells
        if any(cls["key"] == WIZARD_CLASS_KEY for cls in spell.get("classes") or ())
    )
    verify_count("Заклинания волшебника", wizard, EXPECTED_WIZARD_SPELLS)

    path = _write("spells", spells)
    print(f"Заклинания: {len(spells)} -> {path} (из них у волшебника: {wizard})")

    # desc и features у классов огромные, а листу партии не нужны: из класса
    # берутся только кость хитов и владения спасбросками.
    classes = [
        {key: value for key, value in item.items() if key not in ("desc", "features")}
        for item in _fetch_all("classes", {"document__key": DOCUMENT})
        if not item.get("subclass_of")
    ]
    verify_count("Классы", len(classes), EXPECTED_CLASSES)
    path = _write("classes", classes)
    print(f"Классы: {len(classes)} -> {path}")


if __name__ == "__main__":
    sync()
