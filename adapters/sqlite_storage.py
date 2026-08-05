"""
Хранилище персонажей и партий.

Бот многопользовательский, поэтому JSON-файл здесь не годится: обращения
конкурентные, а данные одного игрока не должны быть видны другому.

Основной сценарий — **один человек ведёт весь отряд**: остальные участники
ботом не пользуются, и заводить их приходится за них. Поэтому персонаж не
привязан жёстко к аккаунту телеграма: у владельца их несколько, и лишь у
одного проставлен telegram_id — это он сам.

Партия собирается по короткому коду-приглашению. Заведённые вручную участники
следуют за владельцем: он вступает в партию — они вместе с ним, иначе отряд
посчитается неполным.
"""

import secrets
import sqlite3
from pathlib import Path

from core.class_profiles import display_name
from core.models import Character, PartyMember

_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    TEXT NOT NULL,
    telegram_id TEXT,
    name        TEXT NOT NULL,
    class_key   TEXT NOT NULL,
    level       INTEGER NOT NULL,
    party_code  TEXT,
    subclass_key TEXT
);
CREATE TABLE IF NOT EXISTS parties (
    code       TEXT PRIMARY KEY,
    created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS characters_by_party ON characters (party_code);
CREATE INDEX IF NOT EXISTS characters_by_owner ON characters (owner_id);
CREATE UNIQUE INDEX IF NOT EXISTS characters_by_telegram
    ON characters (telegram_id) WHERE telegram_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL);
"""

#: Версия схемы, которую понимает этот код. Поднимается при каждой её смене.
SCHEMA_VERSION = 3

#: Артиллерист какое-то время был отдельным классом. Персонажи, созданные
#: тогда, переезжают на класс с подклассом.
_RETIRED_CLASS_KEYS = {"hb_artificer_artillerist": ("hb_artificer", "artillerist")}


class StorageTooNew(RuntimeError):
    """База новее кода, который её открыл."""

#: Код читают вслух за столом и перенабирают руками, поэтому он короткий и
#: без символов, которые легко перепутать: без нуля, O, единицы и I.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6


#: Колонки, которыми описывается участник отряда. Один список на все выборки,
#: чтобы порядок полей не разъезжался между запросами.
_MEMBER_COLUMNS = "class_key, level, name, subclass_key"


def _row_to_member(row) -> PartyMember:
    return PartyMember(class_key=row[0], level=row[1], name=row[2], subclass_key=row[3])


class Storage:
    """Персонажи и партии в SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._refuse_if_newer_than_code()
        self._migrate_if_needed()
        self._db.executescript(_SCHEMA)
        self._add_subclass_column()
        self._retire_old_class_keys()
        self._remember_version()
        self._db.commit()

    def _add_subclass_column(self) -> None:
        """Дополнить существующую таблицу колонкой подкласса, не теряя записей."""
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(characters)")}
        if "subclass_key" not in columns:
            self._db.execute("ALTER TABLE characters ADD COLUMN subclass_key TEXT")

    def _retire_old_class_keys(self) -> None:
        """Перевести классы, которые стали подклассами."""
        for retired, (class_key, subclass_key) in _RETIRED_CLASS_KEYS.items():
            self._db.execute(
                "UPDATE characters SET class_key = ?, subclass_key = ? "
                "WHERE class_key = ?",
                (class_key, subclass_key, retired),
            )

    def _stored_version(self) -> int | None:
        try:
            row = self._db.execute("SELECT version FROM schema_meta").fetchone()
        except sqlite3.OperationalError:
            return None  # таблицы ещё нет: база старая или пустая
        return row[0] if row else None

    def _refuse_if_newer_than_code(self) -> None:
        """
        Не работать с базой, которую писала более новая версия.

        Работающий бот держит модули в памяти, и правка файлов его не меняет.
        После смены схемы старый процесс бьётся о новую базу сырой ошибкой SQL
        вида «no such column» — по ней не догадаешься, что нужен перезапуск.
        """
        version = self._stored_version()
        if version is not None and version > SCHEMA_VERSION:
            raise StorageTooNew(
                f"База данных версии {version}, а этот код понимает {SCHEMA_VERSION}. "
                f"Скорее всего запущена старая версия программы — перезапустите её."
            )

    def _remember_version(self) -> None:
        self._db.execute("DELETE FROM schema_meta")
        self._db.execute("INSERT INTO schema_meta (version) VALUES (?)", (SCHEMA_VERSION,))

    # ── Миграция ──────────────────────────────────────────────────────────────

    def _migrate_if_needed(self) -> None:
        """
        Перенести данные со старой схемы, где персонаж был один на аккаунт.

        Персонажей друзей уже завели, терять их нельзя, поэтому переносим, а не
        пересоздаём. Признак старой схемы — отсутствие owner_id.
        """
        columns = {
            row[1] for row in self._db.execute("PRAGMA table_info(characters)")
        }
        if not columns or "owner_id" in columns:
            return

        old = self._db.execute(
            "SELECT user_id, class_key, level, party_code FROM characters"
        ).fetchall()

        self._db.execute("DROP TABLE characters")
        self._db.executescript(_SCHEMA)
        self._db.executemany(
            "INSERT INTO characters (owner_id, telegram_id, name, class_key, level, party_code) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (user_id, user_id, display_name(class_key), class_key, level, code)
                for user_id, class_key, level, code in old
            ],
        )
        self._db.commit()

    # ── Свой персонаж ─────────────────────────────────────────────────────────

    def save_character(
        self,
        user_id: str,
        *,
        class_key: str,
        level: int,
        name: str | None = None,
        subclass_key: str | None = None,
    ) -> None:
        """Создать или заменить собственного персонажа владельца."""
        existing = self._db.execute(
            "SELECT id FROM characters WHERE telegram_id = ?", (user_id,)
        ).fetchone()

        label = name or display_name(class_key)
        if existing:
            self._db.execute(
                "UPDATE characters SET class_key = ?, level = ?, name = ?, "
                "subclass_key = ? WHERE id = ?",
                (class_key, level, label, subclass_key, existing[0]),
            )
        else:
            self._db.execute(
                "INSERT INTO characters "
                "(owner_id, telegram_id, name, class_key, level, subclass_key) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, user_id, label, class_key, level, subclass_key),
            )
        self._db.commit()

    def get_character(self, user_id: str) -> Character | None:
        row = self._db.execute(
            "SELECT class_key, level, party_code, name, subclass_key FROM characters "
            "WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return Character(
            class_key=row[0], level=row[1], party_code=row[2],
            name=row[3], subclass_key=row[4],
        )

    # ── Участники, заведённые вручную ─────────────────────────────────────────

    def add_member(
        self,
        owner_id: str,
        *,
        name: str,
        class_key: str,
        level: int,
        subclass_key: str | None = None,
    ) -> None:
        """
        Завести участника, который ботом не пользуется.

        Он сразу попадает в ту же партию, что и владелец — иначе его пришлось бы
        добавлять повторно после каждого вступления.
        """
        own = self.get_character(owner_id)
        self._db.execute(
            "INSERT INTO characters "
            "(owner_id, telegram_id, name, class_key, level, party_code, subclass_key) "
            "VALUES (?, NULL, ?, ?, ?, ?, ?)",
            (
                owner_id, name, class_key, level,
                own.party_code if own else None, subclass_key,
            ),
        )
        self._db.commit()

    def remove_member(self, owner_id: str, name: str) -> bool:
        """
        Убрать заведённого вручную участника. Чужих персонажей не трогает:
        они принадлежат тем, кто ими играет.

        Имя сравнивается в Python, а не запросом: встроенный lower() в SQLite
        работает только с латиницей, и «гарет» не нашёл бы «Гарет».
        """
        wanted = name.strip().casefold()
        rows = self._db.execute(
            "SELECT id, name FROM characters "
            "WHERE owner_id = ? AND telegram_id IS NULL",
            (owner_id,),
        ).fetchall()

        matched = [row[0] for row in rows if row[1].casefold() == wanted]
        if not matched:
            return False

        self._db.executemany(
            "DELETE FROM characters WHERE id = ?", [(item,) for item in matched]
        )
        self._db.commit()
        return True

    # ── Партия ────────────────────────────────────────────────────────────────

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
        self._set_party(user_id, code)
        return code

    def join_party(self, user_id: str, code: str) -> bool:
        """
        Вступить в партию по коду вместе со всеми своими подопечными.

        Возвращает False на неизвестный код: опечатка в шести символах —
        обычное дело, и падать из-за неё незачем.
        """
        code = code.strip().upper()
        exists = self._db.execute(
            "SELECT 1 FROM parties WHERE code = ?", (code,)
        ).fetchone()
        if exists is None:
            return False

        self._set_party(user_id, code)
        return True

    def leave_party(self, user_id: str) -> None:
        self._set_party(user_id, None)

    def _set_party(self, owner_id: str, code: str | None) -> None:
        """Владелец ходит в партию вместе со всеми, кого завёл."""
        self._db.execute(
            "UPDATE characters SET party_code = ? WHERE owner_id = ?", (code, owner_id)
        )
        self._db.commit()

    def full_party(self, user_id: str) -> list[PartyMember]:
        """
        Весь отряд, включая самого спрашивающего — это картина группы.

        Без кода партии отрядом считаются те, кого владелец завёл сам: до
        приглашения друзей это ровно те, кем он играет.
        """
        character = self.get_character(user_id)
        if character is None:
            return []

        if character.party_code:
            rows = self._db.execute(
                "SELECT class_key, level, name, subclass_key FROM characters "
                "WHERE party_code = ? ORDER BY telegram_id IS NULL, name",
                (character.party_code,),
            )
        else:
            rows = self._db.execute(
                "SELECT class_key, level, name, subclass_key FROM characters "
                "WHERE owner_id = ? ORDER BY telegram_id IS NULL, name",
                (user_id,),
            )
        return [_row_to_member(row) for row in rows]

    def party_members(self, user_id: str) -> list[PartyMember]:
        """
        Союзники — весь отряд без самого спрашивающего.

        Советник по заклинаниям ищет, чего партии не хватает помимо того, что
        игрок приносит сам, поэтому собственный класс сюда входить не должен.
        """
        character = self.get_character(user_id)
        if character is None:
            return []

        where = (
            ("party_code = ?", character.party_code)
            if character.party_code
            else ("owner_id = ?", user_id)
        )
        rows = self._db.execute(
            f"SELECT class_key, level, name, subclass_key FROM characters "
            f"WHERE {where[0]} AND (telegram_id IS NULL OR telegram_id != ?) "
            f"ORDER BY telegram_id IS NULL, name",
            (where[1], user_id),
        )
        return [_row_to_member(row) for row in rows]

    def close(self) -> None:
        self._db.close()
