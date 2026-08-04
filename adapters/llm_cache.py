"""
Кэш ответов модели и суточный бюджет запросов.

Слой существует ради того, чтобы хватало бесплатного тира. Он не решает,
звать ли модель — это дело оркестратора; он лишь отвечает на два вопроса:
"такой ответ уже покупали?" и "лимит ещё не выбран?".

Кэш общий на всех. В ключе нет ничего личного — советник, класс с уровнем,
теги ситуации и состав кандидатов, — поэтому ответ, оплаченный одним игроком,
достаётся остальным даром: с ростом числа пользователей общего бота расход
на человека падает, а не растёт.
"""

import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
    day     TEXT NOT NULL,
    user_id TEXT NOT NULL,
    calls   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, user_id)
);
"""

#: Строка, под которой в usage лежит общий расход за сутки.
_EVERYONE = "*"


def _today() -> str:
    return date.today().isoformat()


class LlmCache:
    """Хранилище оплаченных ответов и счётчиков расхода."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        daily_budget: int = 200,
        user_daily_budget: int = 30,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._daily_budget = daily_budget
        self._user_daily_budget = user_daily_budget
        self._clock = clock or _today

        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def get(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO cache (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._db.commit()

    def _calls(self, day: str, who: str) -> int:
        row = self._db.execute(
            "SELECT calls FROM usage WHERE day = ? AND user_id = ?", (day, who)
        ).fetchone()
        return row[0] if row else 0

    def try_spend(self, user_id: str) -> bool:
        """
        Списать один запрос, если оба лимита позволяют.

        Возвращает False вместо исключения: исчерпанный бюджет — не сбой, а
        штатный режим, в котором советник просто перестаёт звать модель и
        продолжает работать на детерминированных слоях.
        """
        day = self._clock()
        if self._calls(day, _EVERYONE) >= self._daily_budget:
            return False
        if self._calls(day, user_id) >= self._user_daily_budget:
            return False

        self._db.executemany(
            "INSERT INTO usage (day, user_id, calls) VALUES (?, ?, 1) "
            "ON CONFLICT(day, user_id) DO UPDATE SET calls = calls + 1",
            [(day, _EVERYONE), (day, user_id)],
        )
        self._db.commit()
        return True

    def spent_today(self) -> int:
        """Сколько запросов израсходовано за сегодня всеми вместе."""
        return self._calls(self._clock(), _EVERYONE)

    def close(self) -> None:
        self._db.close()
