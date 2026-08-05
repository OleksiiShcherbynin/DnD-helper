"""
Списки заклинаний для классов, которых каталог не размечает.

Классы вне SRD приходится описывать самим: открытый документ о них не знает,
и ни одно заклинание не помечено как их. Списки лежат отдельно от механики
классов просто потому, что это крупные наборы данных, а не логика.

Ключи сверяются с каталогом тестом: набраны они вручную, а опечатка в слаге
не падает — заклинание молча исчезает из выдачи.
"""

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

#: Артиллерист получает эти заклинания сверх списка класса, и они всегда
#: подготовлены. Круги открываются по общей прогрессии Изобретателя.
ARTILLERIST_EXTRA = frozenset({
    "srd_shield", "srd_thunderwave", "srd_scorching-ray", "srd_shatter",
    "srd_fireball", "srd_wind-wall", "srd_ice-storm", "srd_wall-of-fire",
    "srd_cone-of-cold", "srd_wall-of-force",
})
