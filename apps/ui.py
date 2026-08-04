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
from adapters.open5e_catalog import CatalogMissing, load_beasts, load_spells
from core.advisor import ADVISORS, advise
from core.class_profiles import CASTERS, NON_CASTER_NAMES, display_name
from core.models import PartyMember
from core.request import AdviceRequest

load_dotenv()

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "copilot.db"

#: Каким каталогом кормить каждого советника.
CATALOG_FOR = {"wildshape": "beasts", "spells": "spells"}

st.set_page_config(page_title="Tabletop Copilot", page_icon="🐺", layout="centered")


@st.cache_resource
def get_catalogs():
    return {"beasts": load_beasts(), "spells": load_spells()}


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


st.title("🐺 Tabletop Copilot")

try:
    catalogs = get_catalogs()
except CatalogMissing as error:
    st.error(str(error))
    st.stop()

cache = get_cache()
explainer = get_explainer()

ALL_CLASSES = list(CASTERS) + [f"srd_{key}" for key in NON_CASTER_NAMES]

with st.sidebar:
    st.header("Персонаж")
    class_key = st.selectbox(
        "Класс", ALL_CLASSES, index=ALL_CLASSES.index("srd_druid"),
        format_func=display_name,
    )
    level = st.slider("Уровень", 1, 20, 6)

    st.header("Партия")
    party_keys = st.multiselect(
        "Кто ещё в отряде", ALL_CLASSES, format_func=display_name,
        help="Нужно, чтобы советовать то, чего партии не хватает.",
    )

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

request = AdviceRequest(
    class_key=class_key,
    level=level,
    party=tuple(PartyMember(key) for key in party_keys),
    top_n=top_n,
    allow_swarms=allow_swarms,
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
if chosen.key == "wildshape":
    situation_text = st.text_input(
        "Что происходит?", placeholder="болото, преследуем убегающего гоблина"
    )
    if not situation_text:
        st.info("Опишите обстановку и задачу. Поиск вариантов бесплатный и мгновенный.")
        st.stop()

request = AdviceRequest(**{**vars(request), "situation_text": situation_text})
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
