"""
Списки заклинаний для классов, которых каталог не размечает.

Классы вне SRD приходится описывать самим: открытый документ о них не знает,
и ни одно заклинание не помечено как их. Списки лежат отдельно от механики
классов просто потому, что это крупные наборы данных, а не логика.

Ключи сверяются с каталогом тестом: набраны они вручную, а опечатка в слаге
не падает — заклинание молча исчезает из выдачи.
"""

from core.models import Spell

#: Ключ Изобретателя. Определён в class_profiles, но импортировать его отсюда
#: нельзя — он импортирует этот модуль. Строка короче, чем распутывание цикла.
ARTIFICER_KEY = "hb_artificer"

#: Изобретатель (Tasha's Cauldron of Everything).
#:
#: Из 66 заклинаний класса в SRD есть 57. Отсутствуют пришедшие вместе с
#: классом из Tasha's: Snare, Tasha's Caustic Brew, Catnap, Elemental Weapon,
#: Flame Arrows, Intellect Fortress, Summon Construct, Skill Empowerment,
#: Transmute Rock. В открытом документе их нет, и придумывать их нельзя.
#:
#: Именные заклинания в SRD переименованы, и здесь они под новыми именами:
#: Bigby's Hand -> Arcane Hand, Mordenkainen's Faithful Hound -> Faithful Hound,
#: Leomund's Secret Chest -> Secret Chest, и так далее.
ARTIFICER_SPELLS = frozenset({
    # 1 круг
    "srd_alarm", "srd_cure-wounds", "srd_detect-magic", "srd_disguise-self",
    "srd_expeditious-retreat", "srd_faerie-fire", "srd_false-life",
    "srd_feather-fall", "srd_grease", "srd_identify", "srd_jump",
    "srd_longstrider", "srd_purify-food-and-drink", "srd_sanctuary",
    # 2 круг. Ключ "Enlarge/Reduce" без дефиса: слэш в слаге просто выброшен.
    "srd_aid", "srd_alter-self", "srd_arcane-lock", "srd_blur",
    "srd_continual-flame", "srd_darkvision", "srd_enhance-ability",
    "srd_enlargereduce", "srd_heat-metal", "srd_invisibility",
    "srd_lesser-restoration", "srd_levitate", "srd_magic-mouth",
    "srd_magic-weapon", "srd_protection-from-poison", "srd_rope-trick",
    "srd_see-invisibility", "srd_spider-climb", "srd_web",
    # 3 круг
    "srd_blink", "srd_create-food-and-water", "srd_dispel-magic", "srd_fly",
    "srd_glyph-of-warding", "srd_haste", "srd_protection-from-energy",
    "srd_revivify", "srd_water-breathing", "srd_water-walk",
    # 4 круг
    "srd_arcane-eye", "srd_fabricate", "srd_freedom-of-movement",
    "srd_stone-shape", "srd_stoneskin", "srd_secret-chest",
    "srd_faithful-hound", "srd_private-sanctum", "srd_resilient-sphere",
    # 5 круг
    "srd_animate-objects", "srd_creation", "srd_greater-restoration",
    "srd_wall-of-stone", "srd_arcane-hand",
})

#: Заклинания, которых нет в открытом документе.
#:
#: SRD 5.1 содержит 319 заклинаний из примерно 360 в PHB, и часть привычных за
#: столом в него не попала. Сюда же попадают заклинания из книг помимо PHB.
#: Все описаны минимумом полей, которые программа действительно использует:
#: круг, школа, классы, роль и тип урона.
#: Описаний нет и не будет — это чужой текст, а механика текстом не является.
#:
#: Добавить ещё — дописать строку.
EXTRA_SPELLS: tuple[Spell, ...] = (
    Spell(
        key="phb_thorn-whip",
        name="Thorn Whip",
        level=0,
        school="transmutation",
        classes=["srd_druid"],
        casting_time="action",
        duration="instantaneous",
        role="damage",
        damage_dice="1d6",
        damage_types=frozenset({"piercing"}),
    ),
    Spell(
        # Strixhaven: A Curriculum of Chaos. Реакцией отменяет удавшийся бросок
        # врага, поэтому роль — контроль: он отнимает у противника действие.
        key="scc_silvery-barbs",
        name="Silvery Barbs",
        level=1,
        school="enchantment",
        classes=["srd_wizard", "srd_sorcerer", "srd_bard"],
        casting_time="reaction",
        duration="instantaneous",
        role="control",
    ),
    Spell(
        key="phb_hex",
        name="Hex",
        level=1,
        school="enchantment",
        classes=["srd_warlock"],
        casting_time="bonus action",
        duration="1 hour",
        concentration=True,
        role="damage",
        damage_dice="1d6",
        damage_types=frozenset({"necrotic"}),
    ),
    Spell(
        # PHB, но в SRD не попал.
        key="phb_chromatic-orb",
        name="Chromatic Orb",
        level=1,
        school="evocation",
        classes=["srd_sorcerer", "srd_wizard"],
        casting_time="action",
        duration="instantaneous",
        role="damage",
        damage_dice="3d8",
        # Тип выбирается при накладывании, поэтому доступны все шесть.
        damage_types=frozenset({"acid", "cold", "fire", "lightning", "poison", "thunder"}),
    ),
    Spell(
        # Xanathar's Guide to Everything.
        key="xge_absorb-elements",
        name="Absorb Elements",
        level=1,
        school="abjuration",
        classes=["srd_druid", "srd_ranger", "srd_sorcerer", "srd_wizard", ARTIFICER_KEY],
        casting_time="reaction",
        duration="1 round",
        role="defense",
    ),
    Spell(
        key="xge_mold-earth",
        name="Mold Earth",
        level=0,
        school="transmutation",
        classes=["srd_druid", "srd_sorcerer", "srd_wizard"],
        casting_time="action",
        duration="instantaneous",
        role="utility",
    ),
    Spell(
        key="xge_dragons-breath",
        name="Dragon's Breath",
        level=2,
        school="transmutation",
        classes=["srd_sorcerer", "srd_wizard"],
        casting_time="bonus action",
        duration="1 minute",
        concentration=True,
        role="damage",
        damage_dice="3d6",
        damage_types=frozenset({"acid", "cold", "fire", "lightning", "poison"}),
    ),
    Spell(
        # Tasha's Cauldron of Everything.
        key="tce_mind-sliver",
        name="Mind Sliver",
        level=0,
        school="enchantment",
        classes=["srd_sorcerer", "srd_warlock", "srd_wizard"],
        casting_time="action",
        duration="instantaneous",
        role="damage",
        damage_dice="1d6",
        damage_types=frozenset({"psychic"}),
    ),
    Spell(
        # Урон есть, но берут его ради отнятого действия — это контроль.
        key="tce_mind-whip",
        name="Tasha's Mind Whip",
        level=2,
        school="enchantment",
        classes=["srd_sorcerer", "srd_wizard"],
        casting_time="action",
        duration="1 round",
        role="control",
        damage_dice="3d6",
        damage_types=frozenset({"psychic"}),
    ),
    Spell(
        # Fizban's Treasury of Dragons. Держит цель на месте, отсюда контроль.
        key="ftd_rimes-binding-ice",
        name="Rime's Binding Ice",
        level=2,
        school="evocation",
        classes=["srd_sorcerer", "srd_wizard"],
        casting_time="action",
        duration="instantaneous",
        role="control",
        damage_dice="3d8",
        damage_types=frozenset({"cold"}),
    ),
)


#: Как заклинание называется в книге игрока -> как оно называется в SRD.
#:
#: В открытый документ именные заклинания попали без имён: Tenser's Floating
#: Disk стал просто Floating Disk. Игрок печатает то, что написано у него,
#: и без этой таблицы шестнадцать заклинаний просто «не находились».
#:
#: Все шестнадцать сверены с каталогом тестом.
SRD_RENAMES: dict[str, str] = {
    "bigby's hand": "Arcane Hand",
    "drawmij's instant summons": "Instant Summons",
    "evard's black tentacles": "Black Tentacles",
    "leomund's secret chest": "Secret Chest",
    "leomund's tiny hut": "Tiny Hut",
    "melf's acid arrow": "Acid Arrow",
    "mordenkainen's faithful hound": "Faithful Hound",
    "mordenkainen's magnificent mansion": "Magnificent Mansion",
    "mordenkainen's private sanctum": "Private Sanctum",
    "mordenkainen's sword": "Arcane Sword",
    "nystul's magic aura": "Arcanist's Magic Aura",
    "otiluke's freezing sphere": "Freezing Sphere",
    "otiluke's resilient sphere": "Resilient Sphere",
    "otto's irresistible dance": "Irresistible Dance",
    "rary's telepathic bond": "Telepathic Bond",
    "tenser's floating disk": "Floating Disk",
}


#: Артиллерист получает эти заклинания сверх списка класса, и они всегда
#: подготовлены. Круги открываются по общей прогрессии Изобретателя.
ARTILLERIST_EXTRA = frozenset({
    "srd_shield", "srd_thunderwave", "srd_scorching-ray", "srd_shatter",
    "srd_fireball", "srd_wind-wall", "srd_ice-storm", "srd_wall-of-fire",
    "srd_cone-of-cold", "srd_wall-of-force",
})
