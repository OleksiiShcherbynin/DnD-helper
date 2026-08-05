"""
Streamlit-интерфейс.

Тонкий адаптер над ядром. Интерфейс перебирает реестр советников и ничего не
знает про вайлдшейп и заклинания по отдельности — поэтому новый советник
появится здесь сам, без правок в этом файле.

Поиск вариантов бесплатный, объяснение словами — отдельная кнопка и один
запрос к модели.

    uv run streamlit run apps/ui.py
"""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from adapters.gemini_explainer import explainer_from_env
from adapters.llm_cache import LlmCache
from adapters.sqlite_storage import Storage, StorageTooNew
from adapters.open5e_catalog import (
    BEAST_TYPE,
    CatalogMissing,
    load_classes,
    load_creatures,
    load_spells,
)
from core.advisor import ADVISORS, advise
from core.class_profiles import (
    CASTERS,
    NON_CASTER_NAMES,
    SUBCLASSES,
    display_name,
    subclass_profile,
)
from core.encounter import estimate_encounter
from core.models import ABILITIES, ABILITY_NAMES, ROLE_NAMES, Stats
from core.party_sheet import build_party_sheet
from core.request import AdviceRequest
from core.transfer import ParseError, dump_party, load_party

load_dotenv()

#: Путь к базе можно переопределить: тесты обязаны работать на временном файле,
#: а не писать персонажей в ту базу, которой пользуются за столом.
DB_PATH = Path(
    os.getenv("COPILOT_DB")
    or Path(__file__).resolve().parent.parent / "data" / "copilot.db"
)

#: У сайта нет аккаунтов, поэтому он ведёт записи под одним владельцем.
#: Чтобы считать тот же отряд, что и бот, достаточно ввести код партии.
LOCAL_OWNER = "local"

#: Каким каталогом кормить каждого советника.
CATALOG_FOR = {"wildshape": "beasts", "spells": "spells"}

#: Точный AC противника игроку знать неоткуда, поэтому спрашиваем то, что видно
#: за столом, и подставляем типичное значение. Это приближение, но оно намного
#: ближе к правде, чем расчёт вообще без цели.
ARMOUR_CHOICES: dict[str, int | None] = {
    "Не знаю": None,
    "Без брони — зверь, бандит": 12,
    "Кожа и щит — стражник, разбойник": 15,
    "Кольчуга — латник, вожак орков": 17,
    "Латы — рыцарь, голем": 19,
}

st.set_page_config(page_title="Tabletop Copilot", page_icon="🐺", layout="centered")


@st.cache_resource
def get_catalogs():
    creatures = load_creatures()
    return {
        "beasts": [c for c in creatures if c.creature_type == BEAST_TYPE],
        "spells": load_spells(),
        "creatures": creatures,
    }


@st.cache_resource
def get_classes():
    return load_classes()


@st.cache_resource
def get_cache():
    return LlmCache(
        DB_PATH,
        daily_budget=int(os.getenv("LLM_DAILY_BUDGET", "200")),
        user_daily_budget=int(os.getenv("LLM_USER_DAILY_BUDGET", "30")),
    )


@st.cache_resource
def get_explainer():
    return explainer_from_env()


def get_storage():
    """
    Без кэша: подключение к SQLite дешёвое, а закэшированное соединение
    пережило бы смену базы и утащило бы в тест боевые данные.
    """
    return Storage(DB_PATH)


st.title("🐺 Tabletop Copilot")

try:
    catalogs = get_catalogs()
    class_data = get_classes()
    storage = get_storage()
except (CatalogMissing, StorageTooNew) as error:
    st.error(str(error))
    st.stop()

cache = get_cache()
explainer = get_explainer()

ALL_CLASSES = list(CASTERS) + [f"srd_{key}" for key in NON_CASTER_NAMES]


#: 0 в поле значит «не введено»: отличить пустое от настоящего нуля иначе
#: нельзя, а AC или урон 0 в 5e не бывает.
_NOT_ENTERED = 0


def _optional(value: int | float | None) -> int:
    return int(value) if value else _NOT_ENTERED


def _entered(value: int) -> int | None:
    return value if value != _NOT_ENTERED else None


def _save_stats(stats: Stats) -> None:
    """Записать числа туда, куда сейчас смотрит сайт: в партию или к себе."""
    if watch and acting:
        storage.replace_stats_in_party(watch.party_code, acting.name, stats)
    else:
        storage.replace_stats(LOCAL_OWNER, None, stats)


def _save_spells(keys: set[str]) -> None:
    if watch and acting:
        storage.set_spells_in_party(watch.party_code, acting.name, keys)
    else:
        storage.set_spells(LOCAL_OWNER, None, keys)


def _edit_stats(current: Stats) -> None:
    """
    Форма ввода чисел. Сохраняет сразу, как и остальные поля на этой странице.

    Пустым считается ноль: в 5e не бывает ни AC 0, ни урона 0, а различать
    «не введено» и «введён ноль» отдельным флажком значит удвоить число полей.
    """
    suffix = "current"
    columns = st.columns(3)
    abilities: dict[str, int] = {}
    for index, code in enumerate(ABILITIES):
        value = columns[index % 3].number_input(
            ABILITY_NAMES[code], 0, 30, current.abilities.get(code, _NOT_ENTERED),
            key=f"ability_{code}_{suffix}",
        )
        if value != _NOT_ENTERED:
            abilities[code] = int(value)

    combat = st.columns(4)
    ac = combat[0].number_input("AC", 0, 40, _optional(current.ac), key=f"ac_{suffix}")
    hp = combat[1].number_input("Хиты", 0, 999, _optional(current.hp), key=f"hp_{suffix}")
    attack = combat[2].number_input(
        "Атака", -5, 30, current.attack_bonus or _NOT_ENTERED, key=f"atk_{suffix}"
    )
    damage = combat[3].number_input(
        "Урон", 0, 999, _optional(current.damage_per_round), key=f"dmg_{suffix}"
    )

    filled = Stats(
        abilities=abilities,
        ac=_entered(int(ac)),
        hp=_entered(int(hp)),
        attack_bonus=_entered(int(attack)),
        damage_per_round=float(damage) if damage != _NOT_ENTERED else None,
    )
    if filled != current:
        # Полная замена, а не дополнение: форма показывает лист целиком,
        # поэтому очищенное поле должно очищаться, а не оставаться прежним.
        _save_stats(filled)
        st.rerun()


def _edit_spells(current: frozenset[str]) -> None:
    """
    Выбор заклинаний из каталога.

    Список не ограничен доступным кругом: свитки, предметы и хоумбрю мастера
    в него не укладываются, а спорить с игроком о том, что у него есть,
    программе незачем.
    """
    by_key = {spell.key: spell for spell in catalogs["spells"]}
    chosen = st.multiselect(
        "Что персонаж умеет",
        sorted(by_key, key=lambda key: by_key[key].name),
        default=sorted(current & by_key.keys()),
        format_func=lambda key: (
            f"{by_key[key].name} "
            f"({'заговор' if by_key[key].is_cantrip else f'{by_key[key].level} круг'})"
        ),
        key="spells_current",
    )

    if set(chosen) != set(current):
        _save_spells(set(chosen))
        st.rerun()


def _pick_subclass(class_key: str, current: str | None, widget_key: str) -> str | None:
    """
    Выпадающий список подклассов — только тех, что принадлежат этому классу.

    Классу без описанных подклассов список не показывается вовсе: пустой
    выбор из одного варианта «нет» только занимает место.
    """
    options = [key for key, item in SUBCLASSES.items() if item.parent == class_key]
    if not options:
        return None

    choices = [None, *options]
    return st.selectbox(
        "Подкласс",
        choices,
        index=choices.index(current) if current in choices else 0,
        format_func=lambda key: "не выбран" if key is None else subclass_profile(key).name,
        key=f"subclass_{widget_key}",
    )

#: Сайт может работать двумя способами. Сам по себе он ведёт свой персонаж.
#: Введён код партии — он становится окном в чужой отряд и выступает за одного
#: из тех, кто в нём уже есть, не добавляя туда никого от себя.
watch = storage.get_watch(LOCAL_OWNER)
party_roster = storage.party_by_code(watch.party_code) if watch else []
acting = (
    next((m for m in party_roster if m.name == watch.acting_as), None) if watch else None
)
own = acting or storage.get_character(LOCAL_OWNER)

with st.sidebar:
    if watch:
        st.header("Вы играете за")
        names = [m.name for m in party_roster]
        if not names:
            st.warning("В этой партии никого нет.")
            st.stop()

        chosen_name = st.selectbox(
            "Персонаж", names,
            index=names.index(watch.acting_as) if watch.acting_as in names else 0,
        )
        if chosen_name != watch.acting_as:
            storage.watch_party(LOCAL_OWNER, watch.party_code, acting_as=chosen_name)
            st.rerun()
        acting = next(m for m in party_roster if m.name == chosen_name)
        own = acting
    else:
        st.header("Ваш персонаж")

    class_key = st.selectbox(
        "Класс", ALL_CLASSES,
        index=ALL_CLASSES.index(own.class_key if own else "srd_druid"),
        format_func=display_name,
    )
    level = st.slider("Уровень", 1, 20, own.level if own else 6)
    subclass_key = _pick_subclass(class_key, own.subclass_key if own else None, "own")

    # Персонаж сохраняется сразу: отдельная кнопка «сохранить» только
    # добавляет способ забыть её нажать.
    changed = own is None or (own.class_key, own.level, own.subclass_key) != (
        class_key, level, subclass_key
    )
    if changed and watch and acting:
        storage.set_character_in_party(
            watch.party_code, acting.name,
            class_key=class_key, level=level, subclass_key=subclass_key,
        )
        st.rerun()
    elif changed and not watch:
        storage.save_character(
            LOCAL_OWNER, class_key=class_key, level=level, subclass_key=subclass_key
        )
        own = storage.get_character(LOCAL_OWNER)

    with st.expander("Числа персонажа"):
        st.caption(
            "Всё необязательно. Незаполненное считается по классу и уровню, "
            "а введённое перебивает расчёт.\n\n"
            "**Урон** — это средний урон за раунд, и знать его наизусть не нужно: "
            "оставьте ноль, и он посчитается сам. Вписывать стоит, только если "
            "расчёт врёт — например у артиллериста с пушкой. В боте туда можно "
            "написать кости как в листе: `/stats урон 2x1d8+4`."
        )
        _edit_stats(own.stats if own else Stats())

    with st.expander("Заклинания персонажа"):
        st.caption(
            "Пока список пуст, роли партии считаются по всему списку класса — "
            "для барда и чародея это завышает. Отметьте то, что персонаж "
            "действительно может применить."
        )
        _edit_spells(own.spell_keys if own else frozenset())

    st.header("Отряд")
    if watch:
        st.caption(f"Партия {watch.party_code} из бота — правится там же.")
        for member in party_roster:
            mark = " ← вы" if acting and member.name == acting.name else ""
            st.write(
                f"{member.name} — {display_name(member.class_key)} {member.level}{mark}"
            )
        allies = []
    else:
        allies = storage.party_members(LOCAL_OWNER)

    if allies:
        # Ключ по порядковому номеру, а не по имени: двух друидов в отряде
        # ничто не запрещает, а Streamlit падает на одинаковых ключах.
        for position, ally in enumerate(allies):
            columns = st.columns([4, 1])
            columns[0].write(f"{ally.name} — {display_name(ally.class_key)} {ally.level}")
            if columns[1].button("✕", key=f"drop_{position}", help="Убрать"):
                storage.remove_member(LOCAL_OWNER, ally.name)
                st.rerun()
    elif not watch:
        st.caption("Пока никого. Добавьте тех, кто ботом не пользуется.")

    with st.form("add_member", clear_on_submit=True):
        st.caption("Добавить участника")
        new_name = st.text_input("Имя", placeholder="Гарет")
        new_class = st.selectbox(
            "Класс участника", ALL_CLASSES, format_func=display_name, key="new_class"
        )
        new_level = st.number_input("Уровень участника", 1, 20, 5)
        new_subclass = _pick_subclass(new_class, None, "new")
        if st.form_submit_button("Добавить") and new_name.strip():
            storage.add_member(
                LOCAL_OWNER,
                name=new_name.strip(),
                class_key=new_class,
                level=int(new_level),
                subclass_key=new_subclass,
            )
            st.rerun()

    st.header("Отряд из бота")
    st.caption(
        "Введите код партии — сайт покажет тот же отряд. Своего персонажа он "
        "туда не добавляет: вы выбираете, за кого из уже существующих играете."
    )
    code = st.text_input("Код партии", value=watch.party_code if watch else "", max_chars=8)
    watch_it, forget = st.columns(2)
    if watch_it.button("Смотреть") and code.strip():
        if storage.watch_party(LOCAL_OWNER, code, acting_as=None):
            st.rerun()
        else:
            st.warning("Такого кода нет.")
    if forget.button("Забыть"):
        storage.stop_watching(LOCAL_OWNER)
        st.rerun()

    with st.expander("Перенос отряда"):
        st.caption(
            "Сайт и бот ведут записи отдельно. Слепок переносит отряд между ними "
            "целиком: скопируйте текст и вставьте на другой стороне."
        )
        try:
            st.text_area("Отсюда — скопировать", dump_party(storage, LOCAL_OWNER), height=90)
        except LookupError as error:
            st.caption(str(error))

        incoming = st.text_area("Сюда — вставить", height=90, key="import_text")
        if st.button("Применить") and incoming.strip():
            try:
                skipped = load_party(storage, LOCAL_OWNER, incoming)
            except ParseError as error:
                st.error(str(error))
            else:
                if skipped:
                    st.info(
                        "Пропущены персонажи живых игроков: "
                        + ", ".join(skipped)
                        + ". Они остаются у своих владельцев."
                    )
                st.rerun()

    st.header("Настройки")
    top_n = st.slider("Сколько вариантов показать", 1, 8, 3)
    allow_swarms = st.checkbox(
        "Разрешить рои", value=False,
        help="Большинство мастеров превращение в рой не разрешает.",
    )

    st.divider()
    st.caption(f"Каталог: {len(catalogs['beasts'])} зверей, {len(catalogs['spells'])} заклинаний")
    if explainer is None:
        st.caption("Модель не подключена: объяснения недоступны, рейтинг работает.")
    else:
        st.caption(f"Запросов к модели сегодня: {cache.spent_today()}")

if watch and acting:
    full_party = party_roster
    allies_for_advice = [m for m in party_roster if m.name != acting.name]
else:
    full_party = storage.full_party(LOCAL_OWNER)
    allies_for_advice = storage.party_members(LOCAL_OWNER)

request = AdviceRequest(
    class_key=class_key,
    level=level,
    subclass_key=subclass_key,
    party=tuple(allies_for_advice),
    top_n=top_n,
    allow_swarms=allow_swarms,
)

sheet = build_party_sheet(
    full_party, classes=class_data, spells=catalogs["spells"]
)

with st.expander("📋 Лист партии — что отряд умеет и чего ему не хватает"):
    st.caption(
        "Считается вся партия вместе с вами. Спасброски решают, кого выключают "
        "из боя одним броском, поэтому дыра в них дороже остальных."
    )

    saves = st.columns(6)
    for column, (ability, holders) in zip(saves, sheet.saves.items()):
        column.metric(
            ABILITY_NAMES[ability],
            "✅" if holders else "—",
            help=", ".join(holders) if holders else "не владеет никто",
        )

    covered_roles = {
        ROLE_NAMES.get(role, role): len(names)
        for role, names in sheet.roles.items()
        if names
    }
    if covered_roles:
        st.write(
            "**Умения:** "
            + ", ".join(f"{role} ({count})" for role, count in covered_roles.items())
        )
    st.write(f"**Типов урона:** {len(sheet.damage_types)} из 13")

    for gap in sheet.gaps:
        st.warning(gap.text)
    if sheet.missing_roles:
        missing = ", ".join(ROLE_NAMES.get(role, role) for role in sheet.missing_roles)
        st.warning(f"Никто не закрывает: {missing}.")
    if sheet.only_physical_damage:
        st.warning(
            "Партия наносит только физический урон: сопротивление немагическому "
            "оружию обойти нечем."
        )

with st.expander("⚔️ Опасность боя — драться или бежать"):
    st.caption(
        "Считается по боевой математике, а не по таблицам опыта: сколько раундов "
        "нужно, чтобы их убить, и сколько вы продержитесь. Противники берутся "
        "точно из статблоков, партия оценивается по классам и уровням."
    )

    by_name = {creature.name: creature for creature in catalogs["creatures"]}
    chosen_enemies = st.multiselect("Кто против вас", sorted(by_name))

    enemies = []
    if chosen_enemies:
        st.caption("Сколько их — по каждому виду:")
        columns = st.columns(min(4, len(chosen_enemies)))
        for index, name in enumerate(chosen_enemies):
            count = columns[index % len(columns)].number_input(
                f"{name} — сколько",
                min_value=1, max_value=99, value=1, key=f"count_{index}",
            )
            enemies.append((by_name[name], int(count)))

    if not enemies:
        st.info("Выберите противников — хотя бы одного.")
    else:
        fight = estimate_encounter(full_party, enemies, classes=class_data)

        banner = {
            "лёгкая": st.success,
            "по силам": st.success,
            "тяжёлая": st.warning,
            "смертельно": st.error,
        }.get(fight.verdict, st.info)
        banner(f"**{fight.verdict.capitalize()}.** {fight.advice}")

        left, right = st.columns(2)
        left.metric("Раундов, чтобы убить", fight.rounds_to_win or "—")
        right.metric("Раундов, пока держитесь", fight.rounds_to_fall or "—")

        st.caption(
            f"Партия: {fight.party.hp} HP, AC ≈{fight.party.armour_class}, "
            f"урон ≈{fight.party.damage_per_round} — **оценка** по классам и уровням.\n\n"
            f"Противники: {fight.enemies.hp} HP, AC {fight.enemies.armour_class}, "
            f"урон {fight.enemies.damage_per_round} — по статблокам."
        )
        st.caption(
            "Не учитываются: дыхание дракона и прочие способности со спасброском, "
            "лечение, контроль и отступление. Считайте это нижней границей опасности."
        )

# Интерфейс не знает про конкретных советников — он спрашивает у реестра.
available = [advisor for advisor in ADVISORS.values() if advisor.applies_to(request)]

if not available:
    st.info(
        f"{display_name(class_key)} {level} уровня — для него пока нет ни одного совета. "
        f"Друид получает формы со 2 уровня, кастеры — заклинания с 1 (следопыт со 2)."
    )
    st.stop()

chosen = st.radio(
    "О чём спросить", available, format_func=lambda advisor: advisor.title, horizontal=True
)

situation_text = ""
target_ac = None
if chosen.key == "wildshape":
    situation_text = st.text_input(
        "Что происходит?", placeholder="болото, преследуем убегающего гоблина"
    )
    armour = st.selectbox(
        "Насколько защищён противник?",
        list(ARMOUR_CHOICES),
        help=(
            "Оценка на глаз: точный AC игроку знать неоткуда. С ней урон считается "
            "по попаданиям, без неё — по костям."
        ),
    )
    target_ac = ARMOUR_CHOICES[armour]

    if not situation_text:
        st.info("Опишите обстановку и задачу. Поиск вариантов бесплатный и мгновенный.")
        st.stop()

request = AdviceRequest(
    **{**vars(request), "situation_text": situation_text, "target_ac": target_ac}
)
result = advise(chosen, catalog=catalogs[CATALOG_FOR[chosen.key]], request=request)

if not result.options:
    st.warning("Под эти условия не нашлось ни одного подходящего варианта.")
    st.stop()

caption = f"Подходящих вариантов: {result.legal_count}"
if result.situation is not None:
    caption += (
        f" · местность: {', '.join(sorted(result.situation.terrains)) or 'не распознана'}"
        f" · цель: {', '.join(sorted(result.situation.goals)) or 'не распознана'}"
    )
st.caption(caption)

for position, option in enumerate(result.options, start=1):
    with st.container(border=True):
        st.subheader(f"{position}. {option.name}")
        if option.facts:
            columns = st.columns(len(option.facts))
            for column, (label, value) in zip(columns, option.facts.items()):
                column.metric(label, value)
        st.caption(option.why)

st.divider()

if explainer is None:
    st.caption(
        "Чтобы получать объяснения словами, добавьте GEMINI_API_KEY в .env "
        "и установите зависимости: uv sync --extra llm"
    )
elif st.button("Объяснить выбор", help="Тратит один запрос к модели"):
    with st.spinner("Спрашиваю модель..."):
        explained = advise(
            chosen,
            catalog=catalogs[CATALOG_FOR[chosen.key]],
            request=request,
            explainer=explainer,
            cache=cache,
            want_explanation=True,
        )

    if explained.explanation:
        st.success(explained.explanation)
        st.caption(
            "Новый запрос к модели."
            if explained.used_llm
            else "Ответ взят из кэша, запрос не потрачен."
        )
    else:
        st.warning(
            "Объяснение недоступно: либо исчерпан суточный лимит, либо модель не ответила. "
            "Рейтинг выше от этого не зависит."
        )
