"""
Советник по заклинаниям: что взять с учётом состава партии.

Вопрос здесь не «какое заклинание сильнее вообще», а «чего партии не хватает».
Второе лечащее заклинание в отряде с жрецом и друидом стоит меньше первого
контроля в отряде, где контролировать некому, — и оценка обязана это отражать.

Как и у советника по формам, первый слой отсекает всё, чего персонаж просто
не может взять: чужой список класса и недоступный круг.
"""

from collections.abc import Iterable
from collections import Counter
from dataclasses import dataclass

from core.class_profiles import max_spell_level, profile, roles_of
from core.models import Spell

#: Вклад закрытости роли в оценку. Роль, которую не закрывает никто, ценнее
#: всего; каждый следующий союзник с той же ролью снижает ценность.
_COVERAGE_VALUE = {0: 1.0, 1: 0.55, 2: 0.3}
_COVERAGE_FLOOR = 0.2

#: Насколько партия вообще выигрывает от добавки в эту роль.
#: Утилита стоит особняком: это остаток классификации, под который подпадает
#: больше половины каталога, а не роль, которой отряду может не хватать.
#: Без этого веса советник предлагал волшебнику Tiny Hut и Water Breathing
#: вместо боевых заклинаний, причём одинаково для любого состава партии.
_ROLE_PRIOR = {
    "healing": 1.00,
    "control": 0.95,
    "damage": 0.90,
    "defense": 0.60,
    "utility": 0.35,
}

#: Постоянный вклад утилиты вместо расчёта по закрытости.
_UTILITY_COVERAGE = 0.5

_WEIGHT_COVERAGE = 0.60
_WEIGHT_CIRCLE = 0.25
_WEIGHT_RITUAL = 0.06
_WEIGHT_BONUS_ACTION = 0.05


@dataclass(frozen=True)
class PartyMember:
    """Союзник. Класс может быть и кастером (srd_cleric), и обычным (fighter)."""

    class_key: str
    level: int = 1


@dataclass(frozen=True)
class ScoredSpell:
    spell: Spell
    score: float
    why: str


def role_coverage(party: Iterable[PartyMember]) -> Counter:
    """Сколько союзников закрывают каждую роль."""
    covered: Counter = Counter()
    for member in party:
        for role in roles_of(member.class_key):
            covered[role] += 1
    return covered


def _gap_value(role: str, covered_by: int) -> float:
    """
    Насколько партии полезна добавка в эту роль.

    Утилита считается отдельно: её «незакрытость» ничего не значит, потому что
    в неё попадает всё, что не опознано как лечение, контроль, урон или защита.
    """
    if role == "utility":
        return _ROLE_PRIOR["utility"] * _UTILITY_COVERAGE
    coverage = _COVERAGE_VALUE.get(covered_by, _COVERAGE_FLOOR)
    return _ROLE_PRIOR.get(role, 0.5) * coverage


def _describe(spell: Spell, covered_by: int) -> str:
    if spell.role == "utility":
        gap = "утилита — универсальная польза, не привязана к составу"
    elif covered_by == 0:
        gap = f"роль «{spell.role}» не закрыта никем в партии"
    elif covered_by == 1:
        gap = f"роль «{spell.role}» закрыта одним союзником"
    else:
        gap = f"роль «{spell.role}» уже закрыта ({covered_by} союзника)"

    extras = []
    if spell.ritual:
        extras.append("ритуал — не тратит ячейку")
    if spell.is_bonus_action:
        extras.append("бонусное действие")
    if spell.concentration:
        extras.append("требует концентрации")

    circle = "заговор" if spell.is_cantrip else f"{spell.level} круг"
    return ", ".join([circle, gap, *extras])


def rank_spells(
    catalog: Iterable[Spell],
    *,
    class_key: str,
    character_level: int,
    party: Iterable[PartyMember] = (),
    include_cantrips: bool = True,
) -> list[ScoredSpell]:
    """
    Отранжировать доступные персонажу заклинания по пользе для этой партии.

    Пустой список означает, что заклинаний ещё нет: у полукастера до 2 уровня
    их действительно нет, и это не ошибка.
    """
    profile(class_key)  # неизвестный класс — ошибка, а не пустая выдача
    circle_cap = max_spell_level(class_key, character_level)
    if circle_cap == 0:
        return []

    available = [
        spell
        for spell in catalog
        if class_key in spell.classes
        and spell.level <= circle_cap
        and (include_cantrips or not spell.is_cantrip)
    ]
    if not available:
        return []

    covered = role_coverage(party)

    scored = []
    for spell in available:
        covered_by = covered[spell.role]
        score = (
            _WEIGHT_COVERAGE * _gap_value(spell.role, covered_by)
            # Круг повыше — заклинание посильнее, при прочих равных берём его.
            + _WEIGHT_CIRCLE * (spell.level / circle_cap)
            + _WEIGHT_RITUAL * float(spell.ritual)
            + _WEIGHT_BONUS_ACTION * float(spell.is_bonus_action)
        )
        scored.append(
            ScoredSpell(spell, round(score, 4), _describe(spell, covered_by))
        )

    return sorted(scored, key=lambda item: (-item.score, item.spell.name))
