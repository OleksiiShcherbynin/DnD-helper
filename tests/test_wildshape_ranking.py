"""
Эвристическое ранжирование форм — второй слой советника.

Этот слой должен быть полезен сам по себе: именно он работает, когда ключа
к модели нет или суточный бюджет исчерпан. Поэтому проверяем не только то,
что он что-то возвращает, а что цель из описания реально меняет порядок.
"""

from core.advisors.wildshape import rank_beasts
from core.filtering import legal_wild_shape_beasts
from core.situation import parse_situation


def _order(beasts, text, level=8):
    legal = legal_wild_shape_beasts(beasts, druid_level=level)
    return [scored.beast.name for scored in rank_beasts(legal, parse_situation(text))]


def test_chase_puts_the_fastest_form_first(beasts):
    """Гигантский орёл летает на 80, медведь ходит на 40 — в погоне решает скорость."""
    order = _order(beasts, "надо догнать убегающего")
    assert order.index("Giant Eagle") < order.index("Brown Bear")


def test_damage_puts_the_hardest_hitter_first(beasts):
    """У медведя мультиатака на 19, у орла на 16 — в размене решает урон."""
    order = _order(beasts, "рубимся, надо нанести урон")
    assert order.index("Brown Bear") < order.index("Giant Eagle")


def test_tank_puts_the_toughest_form_first(beasts):
    """Гигантский осьминог держит 52 HP против 34 у медведя."""
    order = _order(beasts, "надо продержаться в обороне")
    assert order.index("Giant Octopus") < order.index("Brown Bear")


def test_matching_terrain_raises_the_score(beasts):
    """Волк водится в лесу и не водится в пустыне."""
    legal = legal_wild_shape_beasts(beasts, druid_level=8)
    in_forest = {s.beast.name: s.score for s in rank_beasts(legal, parse_situation("в лесу"))}
    in_desert = {s.beast.name: s.score for s in rank_beasts(legal, parse_situation("в пустыне"))}
    assert in_forest["Wolf"] > in_desert["Wolf"]


def test_results_are_sorted_by_score(beasts):
    legal = legal_wild_shape_beasts(beasts, druid_level=8)
    scores = [s.score for s in rank_beasts(legal, parse_situation("бой в лесу"))]
    assert scores == sorted(scores, reverse=True)


def test_every_result_explains_itself_without_a_model(beasts):
    """
    Режим без LLM обязан оставаться осмысленным: рядом с каждой формой должны
    стоять те самые цифры из каталога, ради которых всё и затевалось.
    """
    legal = legal_wild_shape_beasts(beasts, druid_level=8)
    top = rank_beasts(legal, parse_situation("бой в лесу"))[0]
    assert str(top.beast.hp) in top.why
    assert str(top.beast.ac) in top.why


def test_empty_candidate_list_gives_empty_ranking():
    assert rank_beasts([], parse_situation("в лесу")) == []


def test_swim_speed_does_not_count_on_dry_land(beasts):
    """
    У гигантского осьминога плавание 60 при ходьбе 10. В подземелье эта
    скорость бесполезна, поэтому обгонять волка с его 40 он не должен.
    """
    order = _order(beasts, "подземелье, надо догнать убегающего")
    assert order.index("Wolf") < order.index("Giant Octopus")


def test_swim_speed_counts_in_water(beasts):
    """А в озере всё наоборот."""
    order = _order(beasts, "в озере, надо догнать убегающего")
    assert order.index("Giant Octopus") < order.index("Wolf")
