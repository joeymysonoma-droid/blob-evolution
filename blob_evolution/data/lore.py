"""Story and lore text for Blob Evolution."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

TAGLINE = "Eat. Adapt. Remember."

OPENING_BLURB = (
    "The Lattice is dying of sameness. You are a Seedling — unnamed, hungry, possible. "
    "Ten layers stand between you and the Core where evolution began."
)

PILGRIMAGE_OPENING = [
    {
        "eyebrow": "Pilgrimage Begins",
        "title": "You Wake Hungry",
        "body": (
            "Membrane cools around a new Seedling. No name. No caste. Only appetite.\n"
            "Above you, the Lattice stretches in ten layers toward a wound called the First Divide.\n"
            "Wardens keep the peace of Stillness. You are the opposite of peace."
        ),
    },
    {
        "eyebrow": "The Road",
        "title": "Choose Your Path",
        "body": (
            "Fights harden you. Rest folds the membrane around your wounds. "
            "Shops trade essence for organs older than your hunger.\n"
            "At each layer's end, a Warden waits — not to kill you for sport, "
            "but to decide whether change itself should continue."
        ),
    },
]

CREATURE_LORE = {
    "basic": {"name": "Driftling", "blurb": "Unformed Rim-stock. Soft mass, soft will."},
    "shooter": {"name": "Spine Caste", "blurb": "Keeps distance. Speaks in projectiles."},
    "splitter": {"name": "Divide Brood", "blurb": "Death is only rehearsal for more selves."},
    "charger": {"name": "Rush Membrane", "blurb": "Motion as devotion. Impact as prayer."},
    "shielder": {"name": "Bulwark Seed", "blurb": "Faces the pilgrim. Soft only from behind."},
    "orbiter": {"name": "Halo Drift", "blurb": "Circles hunger like a judgment."},
    "bomber": {"name": "Burst Sac", "blurb": "Gets close. Becomes a question mark of heat."},
    "phantom": {"name": "Hollow Echo", "blurb": "Half-remembered. Hard to wound while faded."},
    "leech": {"name": "Siphon Tick", "blurb": "Drinks potential. Grows while you shrink."},
}

VICTORY_EPILOGUE = (
    "The First Divide opens. Forms rush outward — new colors, new hungers, new grief. "
    "You are not a hero. You are a question the world needed again."
)

MERGE_EPILOGUE = (
    "You pour yourself into the Prime Anchor. The Divide seals. Forms freeze mid-becoming — "
    "safe, finished, forever. The Lattice sleeps. Somewhere, a Seedling will never wake."
)

BROKER_EPILOGUE = (
    "You step sideways out of the pilgrimage. Hood raised, organs sorted, smile practiced. "
    "Future Seedlings will meet a merchant who already knows their price."
)

GAME_OVER_EPILOGUE = (
    "Your shape dissolves, but the Lattice keeps a shard. "
    "Somewhere, a new Seedling wakes — and the pilgrimage begins again."
)

ENDING_TITLES = {
    "reopen": "THE DIVIDE REOPENS",
    "merge": "ETERNAL STILLNESS",
    "broker": "THE BROKER'S PATH",
}

ENDING_SUBTITLES = {
    "reopen": "The First Divide opens.",
    "merge": "You become the Anchor.",
    "broker": "You leave the path — and keep the road.",
}

ENDING_EPILOGUES = {
    "reopen": VICTORY_EPILOGUE,
    "merge": MERGE_EPILOGUE,
    "broker": BROKER_EPILOGUE,
}

# NG+ warden line overrides: act_index -> [(min_ng, quote), ...] highest matching wins
NG_WARDEN_QUOTES: Dict[int, List[Tuple[int, str]]] = {
    0: [
        (2, "Again? The Rim remembers your green. Grow slower this time."),
        (5, "We have cradled you through many wakes. Still you rush."),
    ],
    1: [
        (2, "You return to rot. Did the last death teach you mercy?"),
        (5, "I have watched you dissolve here before. Decay still waits."),
    ],
    2: [
        (2, "Your prior selves are already filed. Do not make me catalog another."),
        (5, "Echoes of you line these walls. Leave one unwritten."),
    ],
    3: [
        (2, "Ash knows your shape. Step into the heat again, pilgrim."),
        (5, "How many times must fire prove you?"),
    ],
    4: [
        (2, "Stillness recognized you mid-stride. Stop. Stay."),
        (5, "You have fled the freeze before. It never leaves the Expanse."),
    ],
    5: [
        (2, "The mirage kept a place for you. Why keep choosing thirst?"),
        (5, "I offered peace every cycle. You always leave hungry."),
    ],
    6: [
        (2, "I have worn your face in dreams. It never fits."),
        (5, "Thief of shapes — the Thicket already knows your next mask."),
    ],
    7: [
        (2, "You crawled out of the Hollow once. Do not make me forget you twice."),
        (5, "Silence almost kept you. Almost."),
    ],
    8: [
        (2, "The triad remembers the vote. You still should not pass."),
        (5, "Again you climb our judgments. Again we fail to agree — except on this fight."),
    ],
    9: [
        (2, "You reopened me once. Must the wound learn your name again?"),
        (5, "Returnee. The Divide knows your hunger. Choose carefully."),
        (10, "I no longer hate you. I only ask: leave something unfinished."),
    ],
}


MINIBOSS_NAME = "Lattice Anchor"

# Per-act lore aligned with config.MAP_THEMES order
ACT_LORE: List[dict] = [
    {
        "id": "warden_0",
        "lore_name": "The Verdant Rim",
        "intro": "The outer nursery of the Lattice. Young forms drift here before the world hardens them.",
        "warden": "Warden of Sprouting",
        "warden_quote": "You eat too quickly. The Rim is not a meal — it is a cradle.",
        "fragment": (
            "Once a Seedling who refused to leave the Rim. The Lattice made them a gatekeeper "
            "so that no pilgrim would rush growth again. They still plant soft forms in secret."
        ),
        "journal": (
            "Dream: soft green light, a cradle that never wanted you to leave. "
            "You ate anyway. The Rim forgives slowly."
        ),
        "accent": (58, 150, 75),
    },
    {
        "id": "warden_1",
        "lore_name": "The Sinking Garden",
        "intro": "A failed experiment garden. Poison preserves what should have been allowed to change.",
        "warden": "Warden of Rot",
        "warden_quote": "Decay is mercy. Let what you were rest.",
        "fragment": (
            "They watched a whole lineage dissolve into toxin and called it kindness. "
            "Their memory tastes of green water and unfinished names."
        ),
        "journal": (
            "Dream: names dissolving in green water. Mercy that tastes like surrender. "
            "You wake still hungry."
        ),
        "accent": (90, 140, 45),
    },
    {
        "id": "warden_2",
        "lore_name": "The Memory Vaults",
        "intro": "Crystallized ancestries line the walls. Every extinct blob left an echo.",
        "warden": "Warden of Echoes",
        "warden_quote": "Remember the dead — do not consume them.",
        "fragment": (
            "A librarian of extinct shapes. They catalogued every pilgrim who died here — "
            "including versions of you that never reached the Core."
        ),
        "journal": (
            "Dream: shelves of you that never finished. Crystal eyes watching. "
            "You promise not to become another file."
        ),
        "accent": (90, 160, 220),
    },
    {
        "id": "warden_3",
        "lore_name": "The Forge Veins",
        "intro": "Heat bleeds from the Lattice itself. Weak shapes burn away here by design.",
        "warden": "Warden of Ash",
        "warden_quote": "Fire is not cruelty. It is the law of becoming.",
        "fragment": (
            "Forged themselves into a trial. They believe only what survives heat deserves "
            "a future. Their ash still remembers your heat signature."
        ),
        "journal": (
            "Dream: your outline glowing, then cooling into something sharper. "
            "Ash applauds survival."
        ),
        "accent": (220, 90, 35),
    },
    {
        "id": "warden_4",
        "lore_name": "The Still Expanse",
        "intro": "Stillness touched this layer first. Motion itself feels like rebellion.",
        "warden": "Warden of Frost",
        "warden_quote": "Stop moving. Stillness is the only shape that lasts.",
        "fragment": (
            "Closest ally of the Stillness. They were the first pilgrim to accept freezing "
            "as paradise. Their fragment is cold enough to slow other memories."
        ),
        "journal": (
            "Dream: ice asking you to stay forever. Your pulse answers no, "
            "and the Expanse cracks a little."
        ),
        "accent": (130, 190, 235),
    },
    {
        "id": "warden_5",
        "lore_name": "The Mirage Basin",
        "intro": "False oases trap blobs in comfort. Rest here, and you forget to grow.",
        "warden": "Warden of Thirst",
        "warden_quote": "Why suffer? Stay. The water lies, but the peace is real.",
        "fragment": (
            "Built the mirages so no one else would starve like they did. "
            "Peace was their weapon. Hunger was yours."
        ),
        "journal": (
            "Dream: sweet water that never fills. Comfort without becoming. "
            "You spit it out and keep walking."
        ),
        "accent": (230, 190, 100),
    },
    {
        "id": "warden_6",
        "lore_name": "The Dreaming Thicket",
        "intro": "Reality bends. Identities blur until you cannot tell hunger from memory.",
        "warden": "Warden of Masks",
        "warden_quote": "You are whatever you eat. That is not identity — that is theft.",
        "fragment": (
            "Wore every face they absorbed until none remained theirs. "
            "They envy your unfinished self — and fear it."
        ),
        "journal": (
            "Dream: a hundred faces that almost fit. You keep the unfinished one — "
            "the Seedling still becoming."
        ),
        "accent": (150, 90, 210),
    },
    {
        "id": "warden_7",
        "lore_name": "The Hollow Undermembrane",
        "intro": "Rejected forms dissolve in the dark below. Nothing here wants to be remembered.",
        "warden": "Warden of Silence",
        "warden_quote": "Forget your name. The Hollow will hold you kindly.",
        "fragment": (
            "Speaks only in what is missing. Their gift is erasure. "
            "Their warning: not every shape deserves to return."
        ),
        "journal": (
            "Dream: silence offering to keep you safe by deleting you. "
            "You clutch your scrap of name and crawl upward."
        ),
        "accent": (70, 55, 95),
    },
    {
        "id": "warden_8",
        "lore_name": "The Ascending Strata",
        "intro": "The wardens convene. Each layer you crossed was a verdict they could not agree on.",
        "warden": "Warden of Ascent",
        "warden_quote": "You climbed through our judgments. We still cannot let you pass.",
        "triad_names": ["Warden of Ascent", "Warden of Echoes", "Warden of Stillness"],
        "fragment": (
            "Three verdicts in one membrane: climb, remember, freeze. "
            "They argued for ages. Your arrival was the only motion they could not vote down."
        ),
        "journal": (
            "Dream: three voices voting on your right to exist. "
            "The tie-breaker is your next step."
        ),
        "accent": (190, 210, 255),
    },
    {
        "id": "warden_9",
        "lore_name": "The First Divide",
        "intro": "The origin wound. One blob became many — and one chose never to split again.",
        "warden": "Prime Anchor",
        "warden_quote": "I held the whole world inside me. You would tear it open again?",
        "fragment": (
            "The first blob that refused the Divide. Everything else is their unfinished "
            "children. Defeating them does not kill them — it asks the question again."
        ),
        "journal": (
            "Dream: one body holding every possible future still. "
            "You are the question that body cannot answer alone."
        ),
        "accent": (220, 55, 160),
    },
]

REST_TITLE = "Membrane Pocket"
REST_SUBTITLE = "The Lattice folds around you. You dream of shapes you have not yet eaten."

BLACKSMITH_TITLE = "The Reforger"
BLACKSMITH_SUBTITLE = "A blob fused to an anvil. It claims to unbend ancestral organs, not improve them."

# Always-available Archive cosmology
COSMOLOGY_ENTRIES: List[dict] = [
    {
        "id": "cosmo_lattice",
        "title": "The Lattice",
        "body": (
            "A living dimension of mutable membrane. All life here is blob-form: mass, memory, "
            "and will braided together. Layers deepen toward the Core."
        ),
    },
    {
        "id": "cosmo_stillness",
        "title": "The Stillness",
        "body": (
            "A force that freezes forms into castes and harvests essence to prevent further change. "
            "Wardens enforce its peace. Pilgrims threaten it simply by adapting."
        ),
    },
    {
        "id": "cosmo_essence",
        "title": "Essence",
        "body": (
            "Stored potential — memory, mass, and will shed by defeated forms. "
            "Markets trade it. The Lattice remembers who spent it."
        ),
    },
    {
        "id": "cosmo_shards",
        "title": "Shards",
        "body": (
            "Crystallized failed runs. Fragments of you from pilgrimages that ended early. "
            "Spending them rewrites what the next Seedling inherits."
        ),
    },
    {
        "id": "cosmo_seedling",
        "title": "The Seedling",
        "body": (
            "You. Untyped protoplasm dropped at the Rim after the First Divide cracked the membrane. "
            "You can absorb traits other castes cannot. That makes you a pilgrim — and a threat."
        ),
    },
    {
        "id": "cosmo_core",
        "title": "The Core of Evolution",
        "body": (
            "The First Divide: the origin wound where one blob became many. "
            "Reopening it resumes change. Anchoring it preserves stillness."
        ),
    },
]

LINEAGES: Dict[str, dict] = {
    "kinetic": {
        "name": "Kinetic Lineage",
        "blurb": "Speed cult of the Rim. They believed motion itself was worship.",
    },
    "predatory": {
        "name": "Predatory Lineage",
        "blurb": "Hunters of the Forge Veins. Growth through violence, refined into organs.",
    },
    "symbiotic": {
        "name": "Symbiotic Lineage",
        "blurb": "Oasis parasites and healers. They traded comfort for endurance.",
    },
    "quantum": {
        "name": "Quantum Lineage",
        "blurb": "Dreaming Thicket physics made flesh. They split rules the way others split mass.",
    },
    "anchor": {
        "name": "Anchor Lineage",
        "blurb": "Stillness relics — powerful, heavy, reluctant to change. Wardens favor them.",
    },
}

ARTIFACT_LORE: Dict[str, dict] = {
    "swift_membrane": {
        "lineage": "kinetic",
        "blurb": "Rim skin stretched thin for speed. The first pilgrims wore it raw.",
    },
    "thick_skin": {
        "lineage": "anchor",
        "blurb": "A Stillness gift: denser membrane, slower becoming.",
    },
    "growth_catalyst": {
        "lineage": "symbiotic",
        "blurb": "Garden residue that teaches mass to multiply without thinking.",
    },
    "acidic_core": {
        "lineage": "predatory",
        "blurb": "A hunter's heart. Digests defenses before the body arrives.",
    },
    "vital_essence": {
        "lineage": "symbiotic",
        "blurb": "Bottled life-potential. Warm if you listen closely.",
    },
    "magnetic_field": {
        "lineage": "kinetic",
        "blurb": "Pulls loose essence the way hunger pulls attention.",
    },
    "piercing_shots": {
        "lineage": "predatory",
        "blurb": "Spines of a caste that refused to close distance.",
    },
    "perfect_absorption": {
        "lineage": "symbiotic",
        "blurb": "Nothing wasted. Even death becomes a meal for the membrane.",
    },
    "skill_enhancer": {
        "lineage": "quantum",
        "blurb": "A tutor-organ. Remembers how other pilgrims learned.",
    },
    "xp_chain": {
        "lineage": "quantum",
        "blurb": "Links kills into a single remembered lesson.",
    },
    "explosive_death": {
        "lineage": "predatory",
        "blurb": "A last argument. Some lineages refuse to die quietly.",
    },
    "dash_trail": {
        "lineage": "kinetic",
        "blurb": "Motion left behind as a weapon. The Rim's signature bruise.",
    },
    "multi_shot": {
        "lineage": "predatory",
        "blurb": "One will, many spines. Forge Veins doctrine.",
    },
    "regenerative_matrix": {
        "lineage": "symbiotic",
        "blurb": "A living lattice patch. Knits you while you sleep.",
    },
    "reality_tear": {
        "lineage": "quantum",
        "blurb": "A scar from when the Lattice tried to split twice.",
    },
    "quantum_split": {
        "lineage": "quantum",
        "blurb": "Death as division. The Thicket's favorite heresy.",
    },
    "time_dilation": {
        "lineage": "quantum",
        "blurb": "Borrowed heartbeat from a blob that lived backward.",
    },
    "essence_magnet": {
        "lineage": "kinetic",
        "blurb": "A greedy fold in the membrane. Markets hate it.",
    },
    "hardened_shell": {
        "lineage": "anchor",
        "blurb": "Warden armor. Change slows under it.",
    },
    "rapid_fire": {
        "lineage": "kinetic",
        "blurb": "Pulse glands tuned past comfort. Speed as sacrament.",
    },
    "void_core": {
        "lineage": "predatory",
        "blurb": "The hunger of the Hollow, bottled.",
    },
    "phoenix_heart": {
        "lineage": "symbiotic",
        "blurb": "A second chance grown from ash and stubbornness.",
    },
    "gravity_well": {
        "lineage": "anchor",
        "blurb": "Mass that insists other mass come closer.",
    },
}

ARCHIVE_TABS = ("Cosmology", "Wardens", "Artifacts", "Lineages")

ENDING_ARCHIVE: Dict[str, dict] = {
    "reopen": {
        "id": "ending_reopen",
        "title": "Ending: The Divide Reopens",
        "body": "You chose change. The Lattice remembers the first reopening of the age.",
    },
    "merge": {
        "id": "ending_merge",
        "title": "Ending: Eternal Stillness",
        "body": "You chose preservation. The Prime Anchor has a new heart — yours.",
    },
    "broker": {
        "id": "ending_broker",
        "title": "Ending: The Broker's Path",
        "body": "You left the pilgrimage without ending it. The road still has a merchant.",
    },
}


def get_act_lore(act_index: int) -> dict:
    """Return lore dict for an act, clamped to valid range."""
    return ACT_LORE[min(max(act_index, 0), len(ACT_LORE) - 1)]


def get_warden_quote(act_index: int, ng_plus_level: int = 0) -> str:
    """Warden intro line, with NG+ variants when available."""
    lore = get_act_lore(act_index)
    quote = lore["warden_quote"]
    for min_ng, ng_quote in sorted(NG_WARDEN_QUOTES.get(act_index, []), key=lambda x: x[0]):
        if ng_plus_level >= min_ng:
            quote = ng_quote
    return quote


def get_ending_epilogue(ending: str) -> str:
    """Epilogue text for a Core ending id."""
    return ENDING_EPILOGUES.get(ending, VICTORY_EPILOGUE)


def get_boss_name(act_index: int, *, miniboss: bool = False, slot: int = 0) -> str:
    """Resolve display name for a boss or mini-boss encounter."""
    if miniboss:
        return MINIBOSS_NAME
    lore = get_act_lore(act_index)
    triad = lore.get("triad_names")
    if triad and slot < len(triad):
        return triad[slot]
    if slot == 0:
        return lore["warden"]
    return f"{lore['warden']} {slot + 1}"


def get_warden_fragment_id(act_index: int) -> str:
    """Archive id for a warden memory fragment."""
    return get_act_lore(act_index)["id"]


def get_artifact_lore(artifact_id: str) -> Optional[dict]:
    """Return lineage + blurb for an artifact, if known."""
    return ARTIFACT_LORE.get(artifact_id)


def get_artifact_lineage_name(artifact_id: str) -> str:
    """Display name of an artifact's lineage."""
    lore = ARTIFACT_LORE.get(artifact_id)
    if not lore:
        return "Unknown Lineage"
    return LINEAGES.get(lore["lineage"], {}).get("name", "Unknown Lineage")


def get_artifact_blurb(artifact_id: str) -> str:
    """Short flavor line for an artifact."""
    lore = ARTIFACT_LORE.get(artifact_id)
    return lore["blurb"] if lore else "A fossilized organ of unclear ancestry."


def get_act_journal(act_index: int) -> str:
    """Rest-site dream journal for the current act."""
    lore = get_act_lore(act_index)
    return lore.get("journal", REST_SUBTITLE)


def get_creature_lore(creature_type: str) -> dict:
    """Display name and blurb for a creature archetype."""
    return CREATURE_LORE.get(creature_type, {"name": "Unknown Form", "blurb": ""})


def build_pilgrimage_pages() -> List[dict]:
    """Opening story pages for a new run."""
    return list(PILGRIMAGE_OPENING)


def build_act_descent_pages(act_index: int) -> List[dict]:
    """Story pages when descending into a new Lattice layer."""
    lore = get_act_lore(act_index)
    return [
        {
            "eyebrow": f"Layer {act_index + 1} of 10",
            "title": lore["lore_name"],
            "body": f"{lore['intro']}\n\nThe Warden of this layer: {lore['warden']}.",
            "accent": lore.get("accent", (52, 200, 120)),
        },
    ]


def build_boss_intro_pages(act_index: int, ng_plus_level: int = 0, miniboss: bool = False) -> List[dict]:
    """Story pages when confronting a warden or lattice anchor."""
    lore = get_act_lore(act_index)
    accent = lore.get("accent", (52, 200, 120))
    if miniboss:
        return [
            {
                "eyebrow": "Lattice Anchor",
                "title": MINIBOSS_NAME,
                "body": (
                    f"A compressed memory of {lore['lore_name']} bars the path.\n"
                    "It does not speak. It only tests whether you still remember how to change."
                ),
                "accent": accent,
            },
        ]
    quote = get_warden_quote(act_index, ng_plus_level)
    return [
        {
            "eyebrow": "Warden Encounter",
            "title": lore["warden"],
            "body": f'"{quote}"\n\n{lore["intro"]}',
            "accent": accent,
        },
    ]


def wrap_text(text: str, font, max_width: int) -> List[str]:
    """Word-wrap text to fit within max pixel width."""
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font.size(trial)[0] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def archive_entries_for_tab(
    tab: int,
    unlocked_wardens: List[str],
    unlocked_artifacts: List[str],
    endings_seen: Optional[List[str]] = None,
) -> List[Tuple[str, str, str, bool]]:
    """
    Build Archive list for a tab.

    Returns list of (entry_id, title, body, unlocked).
    Locked entries use placeholder body.
    """
    endings_seen = endings_seen or []
    locked = "???"
    if tab == 0:
        entries = [(e["id"], e["title"], e["body"], True) for e in COSMOLOGY_ENTRIES]
        for ending_id, entry in ENDING_ARCHIVE.items():
            unlocked = ending_id in endings_seen
            entries.append((
                entry["id"],
                entry["title"] if unlocked else "Unknown Ending",
                entry["body"] if unlocked else locked,
                unlocked,
            ))
        return entries
    if tab == 1:
        entries: List[Tuple[str, str, str, bool]] = []
        for act in ACT_LORE:
            unlocked = act["id"] in unlocked_wardens
            title = act["warden"] if unlocked else "Unknown Warden"
            body = act["fragment"] if unlocked else locked
            entries.append((act["id"], title, body, unlocked))
        return entries
    if tab == 2:
        entries = []
        for art_id, art_lore in ARTIFACT_LORE.items():
            unlocked = art_id in unlocked_artifacts
            from blob_evolution.systems.artifacts import ARTIFACT_DEFINITIONS
            name = ARTIFACT_DEFINITIONS.get(art_id, {}).get("name", art_id)
            lineage = LINEAGES.get(art_lore["lineage"], {}).get("name", "")
            title = name if unlocked else "Unknown Artifact"
            body = f"{lineage}\n{art_lore['blurb']}" if unlocked else locked
            entries.append((art_id, title, body, unlocked))
        return entries
    # Lineages
    entries = []
    for lin_id, lin in LINEAGES.items():
        owned = [
            aid for aid, al in ARTIFACT_LORE.items()
            if al["lineage"] == lin_id and aid in unlocked_artifacts
        ]
        unlocked = bool(owned)
        title = lin["name"] if unlocked else "Unknown Lineage"
        if unlocked:
            body = f"{lin['blurb']}\nRecovered organs: {len(owned)}"
        else:
            body = locked
        entries.append((lin_id, title, body, unlocked))
    return entries
