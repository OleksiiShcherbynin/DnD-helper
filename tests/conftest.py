"""Общие фикстуры: настоящий срез каталога SRD, разобранный в доменные модели."""

import json
from pathlib import Path

import pytest

from adapters.open5e_catalog import parse_beast

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "beasts_sample.json"


@pytest.fixture(scope="session")
def beasts():
    """
    Шесть зверей SRD, подобранных так, чтобы каждый порог правил на них срабатывал:

      Wolf                  CR 1/4, без полёта и плавания
      Bat                   CR 0,   настоящий полёт     -> нелегален до 8 уровня
      Giant Poisonous Snake CR 1/4, настоящее плавание  -> нелегален до 4 уровня
      Brown Bear            CR 1,   climb
      Giant Eagle           CR 1,   полёт
      Giant Octopus         CR 1,   плавание
    """
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [parse_beast(item) for item in raw]


@pytest.fixture(scope="session")
def names(beasts):
    """Имена зверей — удобно сравнивать множествами."""
    return lambda selection: {beast.name for beast in selection}
