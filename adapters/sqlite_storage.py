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

import json
import secrets
import sqlite3
from pathlib import Path

from core.class_profiles import display_name
from core.models import ABILITIES, Character, PartyMember, Stats

_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id    TEXT NOT NULL,
    telegram_id TEXT,
    name        TEXT NOT NULL,
    class_key   TEXT NOT NULL,
    level       INTEGER NOT NULL,
    party_code  TEXT,
    subclass_key TEXT,
    -- Введённые вручную числа одним полем JSON. Отдельными колонками их было
    -- бы десять, и каждое новое требовало бы менять схему; по ним никогда не
    -- ищут, поэтому хранить их разобранными незачем.
    stats       TEXT,
    -- Список заклинаний тоже полем JSON, а не отдельной таблицей: он всегда
    -- нужен вместе с персонажем, и отдельная таблица означала бы запрос на
    -- каждого участника при выводе отряда.
    spells      TEXT
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
SCHEMA_VERSION = 5

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


def _decode_stats(raw: str | None) -> Stats:
    """Разобрать введённые числа. Битое поле не должно ронять весь отряд."""
    if not raw:
        return Stats()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return Stats()
    return Stats(
        abilities={
            key: int(value)
            for key, value in (data.get("abilities") or {}).items()
            if key in ABILITIES
        },
        ac=data.get("ac"),
        hp=data.get("hp"),
        attack_bonus=data.get("attack_bonus"),
        damage_per_round=data.get("damage_per_round"),
    )


def _encode_stats(stats: Stats) -> str:
    return json.dumps(
        {
            "abilities": stats.abilities,
            "ac": stats.ac,
            "hp": stats.hp,
            "attack_bonus": stats.attack_bonus,
            "damage_per_round": stats.damage_per_round,
        },
        ensure_ascii=False,
    )


def _merge_stats(current: Stats, patch: Stats) -> Stats:
    """
    Дополнить лист, а не заменить его.

    Ввести всё одной командой невозможно, поэтому каждая правка обязана
    сохранять то, что уже введено, — иначе второй ввод стирал бы первый.
    """
    return Stats(
        abilities={**current.abilities, **patch.abilities},
        ac=patch.ac if patch.ac is not None else current.ac,
        hp=patch.hp if patch.hp is not None else current.hp,
        attack_bonus=(
            patch.attack_bonus if patch.attack_bonus is not None else current.attack_bonus
        ),
        damage_per_round=(
            patch.damage_per_round
            if patch.damage_per_round is not None
            else current.damage_per_round
        ),
    )


def _decode_spells(raw: str | None) -> frozenset[str]:
    """Разобрать список заклинаний. Битое поле не должно ронять весь отряд."""
    if not raw:
        return frozenset()
    try:
        keys = json.loads(raw)
    except json.JSONDecodeError:
        return frozenset()
    return frozenset(str(key) for key in keys) if isinstance(keys, list) else frozenset()


def _row_to_member(row) -> PartyMember:
    return PartyMember(
        class_key=row[0], level=row[1], name=row[2],
        subclass_key=row[3], stats=_decode_stats(row[4]),
        spell_keys=_decode_spells(row[5]),
    )


class Storage:
    """Персонажи и партии в SQLite."""

    def __init__(self, db_path: Path | str) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._refuse_if_newer_than_code()
        self._migrate_if_needed()
        self._db.executescript(_SCHEMA)
        self._add_missing_columns()
        self._retire_old_class_keys()
        self._remember_version()
        self._db.commit()

    def _add_missing_columns(self) -> None:
        """Дополнить существующую таблицу новыми колонками, не теряя записей."""
        columns = {row[1] for row in self._db.execute("PRAGMA table_info(characters)")}
        for name in ("subclass_key", "stats", "spells"):
            if name not in columns:
                self._db.execute(f"ALTER TABLE characters ADD COLUMN {name} TEXT")

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
            "SELECT class_key, level, party_code, name, subclass_key, stats, spells FROM characters "
            "WHERE telegram_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return Character(
            class_key=row[0], level=row[1], party_code=row[2],
            name=row[3], subclass_key=row[4], stats=_decode_stats(row[5]),
            spell_keys=_decode_spells(row[6]),
        )

    # ── Заклинания персонажа ──────────────────────────────────────────────────

    def update_spells(
        self,
        owner_id: str,
        name: str | None,
        *,
        add: set[str] = frozenset(),
        remove: set[str] = frozenset(),
    ) -> bool:
        """
        Добавить или убрать заклинания. За столом правят по одному, а не
        переписывают список целиком.
        """
        return self._write_spells(
            owner_id, name, lambda current: (current | set(add)) - set(remove)
        )

    def set_spells(self, owner_id: str, name: str | None, keys: set[str]) -> bool:
        """
        Записать список целиком, убирая всё, чего в нём нет.

        Нужно формам: они показывают список полностью, и снятое там должно
        сниматься.
        """
        return self._write_spells(owner_id, name, lambda _: set(keys))

    def _write_spells(self, owner_id: str, name: str | None, change) -> bool:
        found = self._find_editable(owner_id, name, "spells")
        if found is None:
            return False

        row_id, raw = found
        updated = change(set(_decode_spells(raw)))
        self._db.execute(
            "UPDATE characters SET spells = ? WHERE id = ?",
            (json.dumps(sorted(updated)), row_id),
        )
        self._db.commit()
        return True

    def replace_stats(self, owner_id: str, name: str | None, stats: Stats) -> bool:
        """
        Записать лист целиком, стирая незаполненное.

        Нужно формам: они показывают лист полностью, и очищенное там поле
        обязано очиститься. Команды в боте вводят по частям и пользуются
        update_stats.
        """
        return self._write_stats(owner_id, name, lambda _: stats)

    def update_stats(self, owner_id: str, name: str | None, patch: Stats) -> bool:
        """
        Дополнить лист персонажа введёнными числами.

        name = None — свой персонаж. Иначе имя того, кого владелец завёл сам:
        чужие персонажи принадлежат тем, кто ими играет, и правке не подлежат.

        Возвращает False, если такого персонажа у владельца нет: опечатка в
        имени — обычное дело, и падать из-за неё незачем.
        """
        return self._write_stats(owner_id, name, lambda current: _merge_stats(current, patch))

    def _find_editable(
        self, owner_id: str, name: str | None, column: str
    ) -> tuple[int, str | None] | None:
        """
        Найти персонажа, которого можно заполнять.

        name = None — свой. Иначе любой в той же партии: обычно её ведёт один
        человек, а остальные ботом не пользуются, и запрет трогать чужой лист
        мешал ровно тому, ради чего всё делалось. Границей остаётся партия.

        Двух одинаковых имён достаточно, чтобы отказаться: записать наугад
        значит испортить лист не тому персонажу.
        """
        if name is None:
            return self._db.execute(
                f"SELECT id, {column} FROM characters WHERE telegram_id = ?",
                (owner_id,),
            ).fetchone()

        character = self.get_character(owner_id)
        if character is None:
            return None

        where, value = (
            ("party_code = ?", character.party_code)
            if character.party_code
            else ("owner_id = ?", owner_id)
        )
        # Сравнение в Python: встроенный lower() в SQLite кириллицу не трогает.
        rows = self._db.execute(
            f"SELECT id, {column}, name FROM characters WHERE {where}", (value,)
        ).fetchall()

        wanted = name.strip().casefold()
        matched = [(item[0], item[1]) for item in rows if item[2].casefold() == wanted]
        return matched[0] if len(matched) == 1 else None

    def _write_stats(self, owner_id: str, name: str | None, change) -> bool:
        row = self._find_editable(owner_id, name, "stats")
        if row is None:
            return False

        updated = change(_decode_stats(row[1]))
        self._db.execute(
            "UPDATE characters SET stats = ? WHERE id = ?", (_encode_stats(updated), row[0])
        )
        self._db.commit()
        return True

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

    def is_played_by_someone(self, owner_id: str, name: str) -> bool:
        """
        Играет ли этим персонажем живой игрок, или его завели вручную.

        Нужно переносу: копия чужого персонажа развела бы двойников.
        """
        character = self.get_character(owner_id)
        if character is None:
            return False

        where, value = (
            ("party_code = ?", character.party_code)
            if character.party_code
            else ("owner_id = ?", owner_id)
        )
        rows = self._db.execute(
            f"SELECT name, telegram_id FROM characters WHERE {where}", (value,)
        ).fetchall()

        wanted = name.strip().casefold()
        return any(row[1] for row in rows if row[0].casefold() == wanted)

    def names_belonging_to_others(self, owner_id: str) -> set[str]:
        """
        Имена в партии, которые ведёт не этот владелец.

        Нужно переносу: если обе стороны смотрят в одну базу и состоят в одной
        партии, они уже видят друг друга, и ввоз только плодил бы двойников.
        """
        character = self.get_character(owner_id)
        if character is None:
            return set()

        where, value = (
            ("party_code = ?", character.party_code)
            if character.party_code
            else ("owner_id = ?", owner_id)
        )
        return {
            str(row[0]).casefold()
            for row in self._db.execute(
                f"SELECT name FROM characters WHERE {where} AND owner_id != ?",
                (value, owner_id),
            )
        }

    def drop_manual_members(self, owner_id: str) -> int:
        """
        Убрать всех заведённых вручную. Нужно переносу: слепок применяется
        целиком, иначе повторный ввоз удваивал бы отряд.
        """
        cursor = self._db.execute(
            "DELETE FROM characters WHERE owner_id = ? AND telegram_id IS NULL",
            (owner_id,),
        )
        self._db.commit()
        return cursor.rowcount

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
                "SELECT class_key, level, name, subclass_key, stats, spells FROM characters "
                "WHERE party_code = ? ORDER BY telegram_id IS NULL, name",
                (character.party_code,),
            )
        else:
            rows = self._db.execute(
                "SELECT class_key, level, name, subclass_key, stats, spells FROM characters "
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
            f"SELECT class_key, level, name, subclass_key, stats, spells FROM characters "
            f"WHERE {where[0]} AND (telegram_id IS NULL OR telegram_id != ?) "
            f"ORDER BY telegram_id IS NULL, name",
            (where[1], user_id),
        )
        return [_row_to_member(row) for row in rows]

    def close(self) -> None:
        self._db.close()
