"""
Разбор свободного описания ситуации в теги — без LLM.

Теги решают две задачи: дают эвристике понять местность и цель, и служат
основой ключа кэша. Именно поэтому разбор обязан быть детерминированным:
одинаковая по смыслу ситуация должна давать одинаковый ключ, иначе кэш
будет промахиваться и каждый запрос начнёт стоить обращения к модели.
"""

from core.situation import parse_situation


def test_extracts_terrain_and_goal():
    situation = parse_situation("болото, преследуем убегающего гоблина")
    assert situation.terrains == {"swamp"}
    assert "chase" in situation.goals


def test_mountains_are_not_confused_with_a_city():
    """Ловушка: "город" начинается на те же буквы, что "гора"."""
    assert parse_situation("прячемся в горах").terrains == {"mountain"}
    assert parse_situation("драка в городе").terrains == {"urban"}


def test_tracks_do_not_look_like_ice():
    """
    Ловушка: слово "лёд" пишется через ё, а "лед" сидит внутри слова "следам".
    Поиск по подстроке дал бы здесь арктику посреди леса.
    """
    situation = parse_situation("идём по следам в лесу")
    assert situation.terrains == {"forest"}


def test_recognises_english_input_too():
    assert parse_situation("swamp, chasing a fleeing goblin").terrains == {"swamp"}


def test_unknown_text_yields_no_tags_instead_of_guessing():
    situation = parse_situation("что-то происходит")
    assert situation.terrains == set()
    assert situation.goals == set()


def test_same_meaning_gives_the_same_cache_key():
    """Ключ кэша не должен зависеть от регистра, пробелов и порядка слов."""
    a = parse_situation("Болото,   преследуем  убегающего")
    b = parse_situation("преследуем убегающего, болото")
    assert a.cache_key() == b.cache_key()


def test_different_meaning_gives_a_different_cache_key():
    a = parse_situation("болото, преследуем убегающего")
    b = parse_situation("болото, надо продержаться в обороне")
    assert a.cache_key() != b.cache_key()
