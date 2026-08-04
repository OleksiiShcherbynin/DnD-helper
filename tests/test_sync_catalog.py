"""
Проверка количеств при синхронизации каталога.

Open5e на неизвестное значение фильтра не отдаёт ошибку, а молча возвращает
count: 0 — так, classes__key=wizard даёт ноль, а правильный srd_wizard даёт 204.
Без этой проверки опечатка в фильтре выглядела бы как "просто нет подходящих
вариантов" и всплыла бы уже за столом.
"""

import httpx
import pytest

from tools.sync_catalog import CatalogCountMismatch, _fetch_all, verify_count


def test_matching_count_passes():
    verify_count("beasts", actual=98, expected=98)


def test_mismatched_count_raises():
    with pytest.raises(CatalogCountMismatch):
        verify_count("beasts", actual=97, expected=98)


def test_zero_result_names_the_silent_filter_trap():
    """Ноль — самый вероятный симптом опечатки в фильтре, и сообщение обязано это сказать."""
    with pytest.raises(CatalogCountMismatch, match="фильтр"):
        verify_count("spells", actual=0, expected=319)


def test_pagination_advances_instead_of_refetching_the_first_page():
    """
    Ловушка httpx: client.get(url, params={}) затирает query-строку целиком,
    поэтому ссылка next теряет page=2 и первая страница качается по кругу.
    Синхронизация от этого зависает молча, без единого сообщения об ошибке.

    Мок считает обращения и обрывает цикл, иначе тест просто повис бы.
    """
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) > 4:
            raise AssertionError(f"Зациклилось, запросы: {calls}")
        if "page=2" in str(request.url):
            return httpx.Response(200, json={"results": [{"key": "b"}], "next": None})
        return httpx.Response(
            200,
            json={
                "results": [{"key": "a"}],
                "next": "https://api.open5e.com/v2/spells/?document__key=srd-2014&limit=200&page=2",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    records = _fetch_all("spells", {"document__key": "srd-2014"}, client=client)

    assert [record["key"] for record in records] == ["a", "b"]
    assert len(calls) == 2
