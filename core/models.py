"""
Доменные модели.

Это единственное представление зверей и заклинаний, с которым работает ядро.
Сырые ответы Open5e сюда не попадают: адаптер переводит их в эти модели,
попутно отсекая известные ловушки в данных источника.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class Beast(BaseModel):
    """Зверь как кандидат на Wild Shape."""

    key: str
    name: str
    cr: float
    ac: int
    hp: int

    #: Только настоящие скорости из статблока, нулевые не хранятся.
    #: Производные значения Open5e (climb/swim в половину ходьбы) сюда не попадают.
    speeds: dict[str, int] = Field(default_factory=dict)

    #: Ключи местностей: forest, grassland, hills, coast, desert, mountain, arctic...
    environments: list[str] = Field(default_factory=list)

    #: Средний урон за раунд, вытащенный из текста статблока.
    damage_per_round: float = 0.0

    darkvision: int = 0
    blindsight: int = 0
    tremorsense: int = 0
    passive_perception: int = 0

    #: Рой. В данных Open5e рой ничем не отличается от обычного зверя —
    #: type=Beast, size=Medium, category=Monsters, — поэтому признак снимается
    #: с имени. Других зацепок источник не даёт.
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


@dataclass(frozen=True)
class Character:
    """Персонаж игрока: то, что бот помнит между сообщениями."""

    class_key: str
    level: int
    #: Код партии, если игрок в неё вступил.
    party_code: str | None = None


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


#: Роль заклинания в партии. По ней ищутся дыры в составе: если контроль уже
#: закрыт бардом, второму кастеру полезнее взять что-то другое.
SpellRole = Literal["damage", "healing", "control", "defense", "utility"]


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

    @property
    def is_cantrip(self) -> bool:
        return self.level == 0

    @property
    def is_bonus_action(self) -> bool:
        return "bonus" in self.casting_time.lower()
