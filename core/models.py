"""
Доменные модели.

Это единственное представление зверей и заклинаний, с которым работает ядро.
Сырые ответы Open5e сюда не попадают: адаптер переводит их в эти модели,
попутно отсекая известные ловушки в данных источника.
"""

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
