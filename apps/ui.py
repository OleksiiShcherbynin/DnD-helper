"""
Streamlit-интерфейс советника.

Тонкий адаптер: вся логика в ядре, здесь только ввод и вывод. Кнопка
объяснения намеренно отделена от поиска — искать бесплатно, объяснять
за один запрос к модели.

    uv run streamlit run apps/ui.py
"""

import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from adapters.gemini_explainer import explainer_from_env
from adapters.llm_cache import LlmCache
from adapters.open5e_catalog import CatalogMissing, load_beasts
from core.orchestrator import recommend_wild_shape

load_dotenv()

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "copilot.db"

st.set_page_config(page_title="Tabletop Copilot", page_icon="🐺", layout="centered")


@st.cache_resource
def get_catalog():
    return load_beasts()


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


st.title("🐺 Wild Shape — во что превратиться")

try:
    catalog = get_catalog()
except CatalogMissing as error:
    st.error(str(error))
    st.stop()

cache = get_cache()
explainer = get_explainer()

with st.sidebar:
    st.header("Персонаж")
    level = st.slider("Уровень друида", 1, 20, 6)
    allow_swarms = st.checkbox(
        "Разрешить рои",
        value=False,
        help="Большинство мастеров превращение в рой не разрешает.",
    )
    top_n = st.slider("Сколько вариантов показать", 1, 5, 3)

    st.divider()
    st.caption(f"Каталог: {len(catalog)} зверей SRD 5.1")
    if explainer is None:
        st.caption("Модель не подключена — объяснения недоступны, рейтинг работает.")
    else:
        st.caption(f"Запросов к модели сегодня: {cache.spent_today()}")

situation_text = st.text_input(
    "Что происходит?",
    placeholder="болото, преследуем убегающего гоблина",
)

if not situation_text:
    st.info("Опишите обстановку и задачу. Поиск вариантов бесплатный и мгновенный.")
    st.stop()

result = recommend_wild_shape(
    catalog,
    druid_level=level,
    situation_text=situation_text,
    top_n=top_n,
    allow_swarms=allow_swarms,
)

if not result.options:
    st.warning(
        f"Друид {level} уровня не может принимать форму зверя."
        if level < 2
        else "Под эти условия не нашлось ни одной легальной формы."
    )
    st.stop()

st.caption(
    f"Легальных форм: {result.legal_count} из {len(catalog)} · "
    f"местность: {', '.join(sorted(result.situation.terrains)) or 'не распознана'} · "
    f"цель: {', '.join(sorted(result.situation.goals)) or 'не распознана'}"
)

for position, option in enumerate(result.options, start=1):
    beast = option.beast
    with st.container(border=True):
        st.subheader(f"{position}. {beast.name}")
        columns = st.columns(4)
        columns[0].metric("CR", f"{beast.cr:g}")
        columns[1].metric("HP", beast.hp)
        columns[2].metric("AC", beast.ac)
        columns[3].metric("Урон/раунд", f"{beast.damage_per_round:g}")
        st.caption(option.why)

st.divider()

if explainer is None:
    st.caption(
        "Чтобы получать объяснения словами, добавьте GEMINI_API_KEY в .env "
        "и установите зависимости: uv sync --extra llm"
    )
elif st.button("Объяснить выбор", help="Тратит один запрос к модели"):
    with st.spinner("Спрашиваю модель..."):
        explained = recommend_wild_shape(
            catalog,
            druid_level=level,
            situation_text=situation_text,
            top_n=top_n,
            allow_swarms=allow_swarms,
            explainer=explainer,
            cache=cache,
            want_explanation=True,
        )

    if explained.explanation:
        st.success(explained.explanation)
        st.caption(
            "Новый запрос к модели." if explained.used_llm else "Ответ взят из кэша, запрос не потрачен."
        )
    else:
        st.warning(
            "Объяснение недоступно: либо исчерпан суточный лимит, либо модель не ответила. "
            "Рейтинг выше от этого не зависит."
        )
