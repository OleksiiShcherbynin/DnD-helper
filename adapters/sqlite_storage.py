"""
Хранилище персонажей и партий.

Бот многопользовательский, поэтому JSON-файл из джоб-ассистента здесь не
годится: обращения конкурентные, а данные одного игрока не должны быть видны
другому. Всё ключуется по идентификатору пользователя — для телеграма это
его user_id, для Streamlit отдельный локальный.

Партия собирается по короткому коду-приглашению. Именно она даёт советнику
по заклинаниям состав союзников, без которого совет «чего не хватает» невозможен.
"""

import secrets
import sqlite3
from pathlib import Path

from core.models import Character, PartyMember

_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    user_id    TEXT PRIMARY KEY,
    class_key  TEXT NOT NULL,
    level      INTEGER NOT NULL,
    party_code TEXT
);
CREATE TABLE IF NOT EXISTS parties (
    code       TEXT PRIMARY KEY,
    created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS characters_by_party ON characters (party_code);
"""

#: Код читают вслух за столом и перенабирают руками, поэтому он короткий и
#: без символов, которые легко перепутать: без нуля, O, единицы и I.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6


class Storage:
    """Персонажи и партии в SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    # ── Персонажи ─────────────────────────────────────────────────────────────

    def save_character(self, user_id: str, *, class_key: str, level: int) -> None:
        """Создать или заменить персонажа игрока, не трогая его партию."""
        self._db.execute(
            "INSERT INTO characters (user_id, class_key, level) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET class_key = excluded.class_key, "
            "level = excluded.level",
            (user_id, class_key, level),
        )
        self._db.commit()

    def get_character(self, user_id: str) -> Character | None:
        row = self._db.execute(
            "SELECT class_key, level, party_code FROM characters WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return Character(class_key=row[0], level=row[1], party_code=row[2])

    # ── Партии ────────────────────────────────────────────────────────────────

    def create_party(self, user_id: str) -> str:
        """Завести партию и сразу вступить в неё. Возвращает код-приглашение."""
        if self.get_character(user_id) is None:
            raise LookupError(
                "Сначала нужен персонаж: без него вступать в партию нечем."
            )

        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        self._db.execute(
            "INSERT INTO parties (code, created_by) VALUES (?, ?)", (code, user_id)
        )
        self._db.execute(
            "UPDATE characters SET party_code = ? WHERE user_id = ?", (code, user_id)
        )
        self._db.commit()
        return code

    def join_party(self, user_id: str, code: str) -> bool:
        """
        Вступить в партию по коду.

        Возвращает False на неизвестный код: опечатка в шести символах —
        обычное дело, и падать из-за неё незачем.
        """
        code = code.strip().upper()
        exists = self._db.execute(
            "SELECT 1 FROM parties WHERE code = ?", (code,)
        ).fetchone()
        if exists is None:
            return False

        self._db.execute(
            "UPDATE characters SET party_code = ? WHERE user_id = ?", (code, user_id)
        )
        self._db.commit()
        return True

    def leave_party(self, user_id: str) -> None:
        self._db.execute(
            "UPDATE characters SET party_code = NULL WHERE user_id = ?", (user_id,)
        )
        self._db.commit()

    def party_members(self, user_id: str) -> list[PartyMember]:
        """
        Союзники игрока — без него самого.

        Собственный класс в покрытие ролей не входит: советник ищет, чего
        партии не хватает помимо того, что игрок уже приносит сам.
        """
        character = self.get_character(user_id)
        if character is None or character.party_code is None:
            return []

        rows = self._db.execute(
            "SELECT class_key, level FROM characters "
            "WHERE party_code = ? AND user_id != ? ORDER BY class_key",
            (character.party_code, user_id),
        ).fetchall()
        return [PartyMember(class_key=row[0], level=row[1]) for row in rows]

    def close(self) -> None:
        self._db.close()
