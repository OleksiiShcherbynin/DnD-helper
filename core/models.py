"""
Доменные модели.

Это единственное представление зверей и заклинаний, с которым работает ядро.
Сырые ответы Open5e сюда не попадают: адаптер переводит их в эти модели,
попутно отсекая известные ловушки в данных источника.
"""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field


class Attack(BaseModel):
    """
    Одна атака из статблока.

    Бонус атаки берётся из структурированного поля источника — ему здесь можно
    верить, по всем 118 атакам каталога оно совпало с текстом. А вот кости и
    прибавку приходится доставать из описания: структурные damage_bonus и
    damage_type у источника битые.
    """

    name: str
    to_hit: int = 0
    dice_count: int = 0
    die_size: int = 0
    damage_bonus: int = 0
    #: Средний урон, как он напечатан в статблоке.
    average: float = 0.0


class Creature(BaseModel):
    """
    Существо со статблоком: и зверь как форма для Wild Shape, и монстр как
    противник в столкновении. Поля у них одни и те же, поэтому модель общая.
    """

    key: str
    name: str
    cr: float
    ac: int
    hp: int
    #: Ключ типа: beast, dragon, humanoid... По нему отбираются формы для
    #: Wild Shape — превращаться можно только в зверя.
    creature_type: str = ""

    #: Только настоящие скорости из статблока, нулевые не хранятся.
    #: Производные значения Open5e (climb/swim в половину ходьбы) сюда не попадают.
    speeds: dict[str, int] = Field(default_factory=dict)

    #: Ключи местностей: forest, grassland, hills, coast, desert, mountain, arctic...
    environments: list[str] = Field(default_factory=list)

    #: Средний урон за раунд, вытащенный из текста статблока. Считается без
    #: цели: сколько выйдет, если все атаки попадут.
    damage_per_round: float = 0.0

    #: Разобранные атаки — нужны, чтобы считать урон против конкретного AC.
    attacks: list[Attack] = Field(default_factory=list)
    #: Сколько атак существо делает за раунд. У зверей это один или два удара,
    #: у монстров бывает больше: дракон бьёт укусом и двумя когтями.
    attacks_per_round: int = 1

    @property
    def has_multiattack(self) -> bool:
        return self.attacks_per_round > 1

    darkvision: int = 0
    blindsight: int = 0
    tremorsense: int = 0
    passive_perception: int = 0

    #: Рой. В данных Open5e рой ничем не отличается от обычного зверя:
    #: у него та же type=Beast, size=Medium и category=Monsters, — поэтому
    #: признак снимается с имени. Других зацепок источник не даёт.
    is_swarm: bool = False

    @property
    def has_flight(self) -> bool:
        return self.speeds.get("fly", 0) > 0

    @property
    def has_swimming(self) -> bool:
        return self.speeds.get("swim", 0) > 0

    @property
    def walk(self) -> int:
        return self.speeds.get("walk", 0)

    @property
    def has_special_senses(self) -> bool:
        return bool(self.darkvision or self.blindsight or self.tremorsense)


#: Короткие коды характеристик. Внутри везде так — с ними сравниваются
#: спасброски, которые требуют заклинания и способности монстров.
ABILITIES = ("str", "dex", "con", "int", "wis", "cha")

ABILITY_NAMES = {
    "str": "Сила",
    "dex": "Ловкость",
    "con": "Телосложение",
    "int": "Интеллект",
    "wis": "Мудрость",
    "cha": "Харизма",
}


class ClassData(BaseModel):
    """
    То, что источник надёжно знает о классе.

    Прогрессии слотов и формул подготовки здесь нет — их SRD не даёт,
    они живут в core/class_profiles.py.
    """

    key: str
    name: str
    hit_die: int
    #: Владения спасбросками, короткими кодами.
    saving_throws: frozenset[str] = Field(default_factory=frozenset)


@dataclass(frozen=True)
class Character:
    """Персонаж игрока: то, что бот помнит между сообщениями."""

    class_key: str
    level: int
    #: Код партии, если игрок в неё вступил.
    party_code: str | None = None
    name: str = ""
    #: Подкласс, если выбран: он меняет и заклинания, и правила.
    subclass_key: str | None = None
    #: Что про персонажа ввели руками. Пустое — считаем сами.
    stats: "Stats" = field(default_factory=lambda: Stats())
    #: Заклинания, которыми персонаж располагает. Пусто — «не знаю».
    spell_keys: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Stats:
    """
    Числа, введённые про персонажа вручную. Всё необязательно.

    Пустое поле означает «посчитай сам», а не ноль. Заполнять можно сколько
    угодно и в любом порядке: каждое введённое число уточняет расчёт, а
    остальное продолжает оцениваться по классу и уровню.
    """

    #: Характеристики короткими кодами: {"dex": 16}. Заполненные не обязаны
    #: покрывать все шесть.
    abilities: dict[str, int] = field(default_factory=dict)

    ac: int | None = None
    hp: int | None = None
    attack_bonus: int | None = None
    damage_per_round: float | None = None

    @property
    def combat_is_complete(self) -> bool:
        """Все боевые числа введены — значит гадать больше не о чем."""
        return None not in (self.ac, self.hp, self.attack_bonus, self.damage_per_round)

    @property
    def is_empty(self) -> bool:
        return not self.abilities and not any(
            value is not None
            for value in (self.ac, self.hp, self.attack_bonus, self.damage_per_round)
        )


@dataclass(frozen=True)
class PartyMember:
    """
    Союзник по партии.

    Класс может быть и кастером (srd_cleric), и обычным (fighter): без воина
    с разбойником картина покрытия ролей была бы неполной.

    Обычный dataclass, а не модель Pydantic: значение собирается в коде, а не
    приходит из внешних данных, и позиционный вызов тут читается лучше.
    """

    class_key: str
    level: int = 1
    #: Как участника зовут за столом. У заведённых вручную это имя, которое
    #: дал владелец; у остальных подставляется название класса.
    name: str = ""
    subclass_key: str | None = None
    #: Что про участника ввели руками. Пустое — считаем сами.
    stats: "Stats" = field(default_factory=lambda: Stats())
    #: Заклинания, которые персонаж действительно может применить. Пусто —
    #: значит «не знаю», и роли считаются по списку класса, как раньше.
    spell_keys: frozenset[str] = field(default_factory=frozenset)


#: Роль заклинания в партии. По ней ищутся дыры в составе: если контроль уже
#: закрыт бардом, второму кастеру полезнее взять что-то другое.
SpellRole = Literal["damage", "healing", "control", "defense", "utility"]

ROLE_NAMES = {
    "damage": "урон",
    "healing": "лечение",
    "control": "контроль",
    "defense": "защита",
    "utility": "утилита",
}


class Spell(BaseModel):
    """Заклинание как кандидат на изучение или подготовку."""

    key: str
    name: str
    level: int
    school: str
    #: Ключи классов вида srd_wizard — то же соглашение, что в каталоге.
    classes: list[str] = Field(default_factory=list)

    concentration: bool = False
    ritual: bool = False
    casting_time: str = ""
    duration: str = ""

    role: SpellRole = "utility"
    #: Кости урона, если источник их дал. Пустая строка — не значит, что урона нет.
    damage_dice: str = ""
    #: Типы урона. Заполняются только у заклинаний с ролью "damage": иначе
    #: побочные упоминания урона добавили бы партии умение, которого у неё нет.
    damage_types: frozenset[str] = Field(default_factory=frozenset)

    @property
    def is_cantrip(self) -> bool:
        return self.level == 0

    @property
    def is_bonus_action(self) -> bool:
        return "bonus" in self.casting_time.lower()
