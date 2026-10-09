"""Static DE/FR/IT -> EN customs glossary for bill-of-materials words, used when no model rewrite exists.

Retrieval runs over the English HS 2022 nomenclature, so a German line such as "Kugellager Edelstahl 6204"
shares no word with heading 8482 ("Ball or roller bearings") and the char n-gram ranker drifts to whatever
looks alike. `gloss` is a deterministic stand-in for the Apertus rewrite step:

- multi-word terms are matched first ("roulement à billes" -> "ball bearing");
- single words are looked up after accent folding, with light plural/adjective endings removed
  ("Schrauben" -> "Schraube", "cuscinetti" -> "cuscinetto", "électriques" -> "électrique");
- German compounds are split on their longest known head ("Edelstahlgehäuse" -> "Edelstahl" + "Gehäuse"),
  the modifier translated if known and kept as written otherwise ("Zentrifugalpumpe" -> "zentrifugal pump");
- every other token (part numbers, norms, unknown words) is kept, so cognates still reach the n-gram ranker.

The English side uses HS vocabulary where an exact equivalent exists ("Typenschild" -> "name-plate"). Entries
translate words; none encodes an HS code or a classification decision. They were written by hand from general
technical and customs vocabulary for the parts Swiss SMEs list in BOMs, not from the evaluation set.
"""

from __future__ import annotations

import re

from .index import fold

# German (Swiss spelling, "ss"). Keys are written as in a BOM; lookups fold case and accents.
DE: dict[str, str] = {
    # bearings, fasteners, springs
    "Lager": "bearing",
    "Kugellager": "ball bearing",
    "Rillenkugellager": "deep groove ball bearing",
    "Rollenlager": "roller bearing",
    "Kegelrollenlager": "tapered roller bearing",
    "Nadellager": "needle roller bearing",
    "Gleitlager": "plain bearing bush",
    "Kugel": "ball",
    "Schraube": "screw",
    "Stiftschraube": "stud bolt",
    "Sechskantschraube": "hexagon head bolt",
    "Bolzen": "bolt",
    "Mutter": "nut",
    "Unterlegscheibe": "washer",
    "Scheibe": "washer disc",
    "Niete": "rivet",
    "Stift": "pin",
    "Splint": "cotter pin",
    "Dübel": "dowel plug",
    "Feder": "spring",
    "Druckfeder": "compression spring",
    "Zugfeder": "tension spring",
    "Gewinde": "threaded",
    "Verschraubung": "fitting union",
    "Kabelverschraubung": "cable gland",
    # seals
    "Dichtung": "gasket seal",
    "Gleitringdichtung": "mechanical seal",
    "Dichtring": "sealing ring gasket",
    "Wellendichtring": "shaft seal ring",
    "Packung": "packing",
    # mechanical parts
    "Gehäuse": "housing case",
    "Deckel": "lid cover",
    "Abdeckung": "cover",
    "Rahmen": "frame",
    "Grundrahmen": "base frame",
    "Halter": "holder bracket",
    "Halterung": "bracket holder",
    "Griff": "handle",
    "Welle": "shaft",
    "Achse": "axle shaft",
    "Zahnrad": "gear toothed wheel",
    "Getriebe": "gearbox gearing",
    "Kupplung": "coupling clutch",
    "Riemen": "belt",
    "Zahnriemen": "toothed transmission belt",
    "Kette": "chain",
    "Kettenrad": "sprocket wheel",
    "Riemenscheibe": "pulley",
    "Rad": "wheel",
    "Laufrad": "impeller wheel",
    "Hülse": "sleeve",
    "Buchse": "bush socket",
    "Ring": "ring",
    "Platte": "plate",
    "Blech": "sheet",
    "Stange": "rod bar",
    "Stab": "bar rod",
    "Profil": "profile",
    "Rohr": "tube pipe",
    "Schlauch": "hose",
    "Flansch": "flange",
    "Teil": "part",
    "Rohteil": "unfinished part blank",
    "Ersatzteil": "spare part",
    "Spindel": "spindle stem",
    "Joch": "yoke",
    "Kegel": "cone plug",
    "Sitz": "seat",
    "Membran": "diaphragm membrane",
    "Kolben": "piston",
    "Zylinder": "cylinder",
    "Düse": "nozzle",
    "Filter": "filter",
    # machines and drives
    "Pumpe": "pump",
    "Kreiselpumpe": "centrifugal pump",
    "Ventil": "valve",
    "Magnetventil": "solenoid valve",
    "Motor": "motor",
    "Elektromotor": "electric motor",
    "Antrieb": "actuator drive",
    "Stellantrieb": "actuator",
    "Lüfter": "fan",
    "Ventilator": "fan",
    "Kompressor": "compressor",
    "Heizung": "heating heater",
    "Heizelement": "heating resistor element",
    "Werkzeug": "tool",
    "Fräser": "milling cutter",
    "Bohrer": "drill",
    "Maschine": "machine",
    "Kaffeemaschine": "coffee machine",
    # electrical and electronic
    "Leiterplatte": "printed circuit board",
    "Platine": "printed circuit board",
    "Steuerplatine": "control printed circuit board",
    "Elektronik": "electronic",
    "Kabel": "cable",
    "Draht": "wire",
    "Litze": "stranded wire",
    "Stecker": "plug connector",
    "Steckverbinder": "connector",
    "Klemme": "terminal",
    "Klemmenkasten": "terminal box",
    "Schalter": "switch",
    "Endschalter": "limit switch",
    "Taster": "push button switch",
    "Relais": "relay",
    "Sicherung": "fuse",
    "Widerstand": "resistor",
    "Kondensator": "capacitor",
    "Spule": "coil inductor",
    "Transformator": "transformer",
    "Trafo": "transformer",
    "Netzteil": "power supply",
    "Umrichter": "converter",
    "Frequenzumrichter": "frequency converter",
    "Wechselrichter": "inverter",
    "Akku": "accumulator battery",
    "Batterie": "battery",
    "Anzeige": "display",
    "Bildschirm": "screen display",
    "Leuchte": "lamp luminaire",
    "Lampe": "lamp",
    "Sensor": "sensor",
    "Fühler": "sensor probe",
    "Messgerät": "measuring instrument",
    "Durchflussmesser": "flow meter",
    "Regler": "regulator controller",
    "Stellungsregler": "positioner regulator",
    "Steuerung": "control controller",
    "Hörgerät": "hearing aid",
    "Spritze": "syringe",
    # watches
    "Uhr": "watch clock",
    "Armbanduhr": "wrist watch",
    "Uhrwerk": "watch movement",
    "Werk": "movement",
    "Zifferblatt": "dial",
    "Zeiger": "hands",
    "Krone": "crown",
    "Armband": "strap bracelet",
    "Uhrarmband": "watch strap",
    "Schliesse": "clasp buckle",
    "Dornschliesse": "buckle",
    "Faltschliesse": "folding clasp",
    "Glas": "glass",
    "Uhrglas": "watch glass",
    "Saphir": "sapphire",
    "Saphirglas": "synthetic sapphire glass",
    "Lünette": "bezel",
    "Boden": "back",
    "Unruh": "balance wheel",
    "Aufzug": "winding",
    "Schwungmasse": "oscillating weight rotor",
    # materials
    "Stahl": "steel",
    "Edelstahl": "stainless steel",
    "Guss": "casting cast",
    "Stahlguss": "cast steel",
    "Grauguss": "grey cast iron",
    "Rohguss": "rough casting",
    "Feinguss": "investment casting",
    "Eisen": "iron",
    "Aluminium": "aluminium",
    "Kupfer": "copper",
    "Messing": "brass",
    "Titan": "titanium",
    "Kunststoff": "plastic",
    "Gummi": "rubber",
    "Leder": "leather",
    "Holz": "wood",
    "Papier": "paper",
    "Karton": "paperboard carton",
    "Keramik": "ceramic",
    "Lack": "paint varnish",
    "Decklack": "paint varnish",
    "Grundierung": "primer paint",
    "Klebstoff": "adhesive glue",
    "Fett": "grease",
    "Öl": "oil",
    # packaging and printed matter
    "Verpackung": "packing",
    "Schachtel": "box",
    "Etui": "case box",
    "Beutel": "bag",
    "Etikett": "label",
    "Typenschild": "name-plate",
    "Anleitung": "instructions printed",
    "Bedienungsanleitung": "instructions manual printed",
    # qualifiers
    "elektrisch": "electric",
    "elektronisch": "electronic",
    "pneumatisch": "pneumatic",
    "hydraulisch": "hydraulic",
    "automatisch": "automatic",
    "mechanisch": "mechanical",
    "medizinisch": "medical",
    "chirurgisch": "surgical",
    "zentrifugal": "centrifugal",
    "Gleichstrom": "DC direct current",
    "Wechselstrom": "AC alternating current",
    "Drehstrom": "three-phase AC",
    "Druckluft": "compressed air",
    "bestückt": "assembled",
    "unbestückt": "bare",
    "geschweisst": "welded",
    "verzinkt": "galvanised zinc-plated",
    "vernickelt": "nickel-plated",
    "verchromt": "chromium-plated",
    "isoliert": "insulated",
    "emailliert": "enamelled",
    "Einweg": "disposable",
    "Haushalt": "household domestic",
    "Satz": "set",
    "Rille": "groove",
    "Spirale": "spiral",
}

# French (Swiss usage). Multi-word keys are matched on whole folded tokens, plurals included explicitly.
FR: dict[str, str] = {
    "roulement": "bearing",
    "roulement a billes": "ball bearing",
    "roulements a billes": "ball bearings",
    "roulement a rouleaux": "roller bearing",
    "bille": "ball",
    "vis": "screw",
    "ecrou": "nut",
    "boulon": "bolt",
    "rondelle": "washer",
    "goupille": "pin",
    "ressort": "spring",
    "joint torique": "o-ring seal",
    "joints toriques": "o-ring seals",
    "joint": "gasket seal",
    "garniture": "packing seal",
    "boitier": "housing case",
    "boite": "case box",
    "couvercle": "lid cover",
    "fond": "back",
    "cadre": "frame",
    "support": "bracket support",
    "poignee": "handle",
    "arbre": "shaft",
    "axe": "axle pin",
    "engrenage": "gear",
    "roue dentee": "toothed wheel gear",
    "roue": "wheel",
    "accouplement": "coupling",
    "embrayage": "clutch",
    "courroie": "belt",
    "chaine": "chain",
    "poulie": "pulley",
    "douille": "bush sleeve",
    "bague": "ring",
    "plaque": "plate",
    "tole": "sheet",
    "barre": "bar",
    "profile": "profile",
    "tuyau": "pipe tube",
    "flexible": "flexible hose",
    "raccord": "fitting",
    "bride": "flange",
    "piece": "part",
    "membrane": "membrane diaphragm",
    "verin": "cylinder actuator",
    "buse": "nozzle",
    "filtre": "filter",
    "pompe": "pump",
    "vanne": "valve",
    "soupape": "valve",
    "electrovanne": "solenoid valve",
    "moteur": "motor",
    "actionneur": "actuator",
    "ventilateur": "fan",
    "outil": "tool",
    "fraise": "milling cutter",
    "machine a cafe": "coffee machine",
    "circuit imprime": "printed circuit",
    "circuits imprimes": "printed circuits",
    "carte electronique": "printed circuit board electronic",
    "carte": "board card",
    "cable": "cable",
    "fil": "wire",
    "fil de cuivre": "copper wire",
    "connecteur": "connector",
    "prise": "plug socket",
    "borne": "terminal",
    "interrupteur": "switch",
    "fusible": "fuse",
    "resistance": "resistor",
    "condensateur": "capacitor",
    "bobine": "coil",
    "transformateur": "transformer",
    "alimentation": "power supply",
    "convertisseur": "converter",
    "onduleur": "inverter",
    "pile": "battery cell",
    "batterie": "battery",
    "accumulateur": "accumulator",
    "afficheur": "display",
    "ecran": "screen display",
    "lampe": "lamp",
    "capteur": "sensor",
    "sonde": "probe sensor",
    "debitmetre": "flow meter",
    "regulateur": "regulator",
    "electrode": "electrode",
    "presse etoupe": "cable gland",
    "presse etoupes": "cable glands",
    "appareil auditif": "hearing aid",
    "seringue": "syringe",
    "montre": "watch",
    "montre bracelet": "wrist watch",
    "horloge": "clock",
    "mouvement": "movement",
    "cadran": "dial",
    "aiguille": "hand needle",
    "couronne": "crown",
    "boucle": "buckle",
    "fermoir": "clasp",
    "lunette": "bezel",
    "glace": "glass",
    "verre": "glass",
    "saphir": "sapphire",
    "masse oscillante": "oscillating weight rotor",
    "ecrin": "case box",
    "acier": "steel",
    "acier inoxydable": "stainless steel",
    "inox": "stainless steel",
    "fonte": "cast iron",
    "fer": "iron",
    "cuivre": "copper",
    "laiton": "brass",
    "titane": "titanium",
    "plastique": "plastic",
    "matiere plastique": "plastics",
    "caoutchouc": "rubber",
    "cuir": "leather",
    "bois": "wood",
    "papier": "paper",
    "carton": "paperboard carton",
    "ceramique": "ceramic",
    "peinture": "paint",
    "vernis": "varnish",
    "colle": "glue adhesive",
    "graisse": "grease",
    "huile": "oil",
    "emballage": "packing",
    "sachet": "bag",
    "etiquette": "label",
    "plaque signaletique": "name-plate",
    "notice": "instructions printed",
    "electrique": "electric",
    "electronique": "electronic",
    "pneumatique": "pneumatic",
    "hydraulique": "hydraulic",
    "automatique": "automatic",
    "mecanique": "mechanical",
    "medical": "medical",
    "chirurgical": "surgical",
    "centrifuge": "centrifugal",
    "courant continu": "DC direct current",
    "courant alternatif": "AC alternating current",
    "jetable": "disposable",
    "assemble": "assembled",
    "soude": "welded",
    "zingue": "zinc-plated",
    "nickele": "nickel-plated",
    "chrome": "chromium-plated",
    "isole": "insulated",
    "emaille": "enamelled",
    "imprime": "printed",
    "domestique": "domestic household",
    "jeu": "set",
    "ensemble": "assembly set",
}

# Italian. Same conventions as French.
IT: dict[str, str] = {
    "cuscinetto": "bearing",
    "cuscinetto a sfere": "ball bearing",
    "cuscinetti a sfere": "ball bearings",
    "cuscinetto a rulli": "roller bearing",
    "sfera": "ball",
    "vite": "screw",
    "bullone": "bolt",
    "dado": "nut",
    "rondella": "washer",
    "rivetto": "rivet",
    "perno": "pin pivot",
    "molla": "spring",
    "guarnizione": "gasket seal",
    "anello di tenuta": "sealing ring",
    "tenuta": "seal",
    "corpo": "body housing",
    "scatola": "box case",
    "cassa": "case",
    "coperchio": "lid cover",
    "fondello": "case back",
    "telaio": "frame",
    "supporto": "bracket support",
    "maniglia": "handle",
    "albero": "shaft",
    "ingranaggio": "gear",
    "riduttore": "gear reducer gearbox",
    "ruota": "wheel",
    "giunto": "coupling joint",
    "frizione": "clutch",
    "cinghia": "belt",
    "catena": "chain",
    "puleggia": "pulley",
    "boccola": "bush sleeve",
    "anello": "ring",
    "piastra": "plate",
    "lamiera": "sheet",
    "barra": "bar",
    "profilato": "profile",
    "tubo": "tube pipe",
    "raccordo": "fitting",
    "flangia": "flange",
    "pezzo": "part",
    "membrana": "membrane diaphragm",
    "cilindro": "cylinder",
    "pistone": "piston",
    "ugello": "nozzle",
    "filtro": "filter",
    "pompa": "pump",
    "valvola": "valve",
    "elettrovalvola": "solenoid valve",
    "motore": "motor",
    "micromotore": "micro motor",
    "attuatore": "actuator",
    "ventilatore": "fan",
    "utensile": "tool",
    "fresa": "milling cutter",
    "macchina da caffe": "coffee machine",
    "circuito stampato": "printed circuit",
    "circuiti stampati": "printed circuits",
    "scheda elettronica": "printed circuit board electronic",
    "scheda": "board",
    "cavo": "cable",
    "filo": "wire",
    "connettore": "connector",
    "spina": "plug",
    "morsetto": "terminal",
    "interruttore": "switch",
    "fusibile": "fuse",
    "resistenza": "resistor",
    "condensatore": "capacitor",
    "bobina": "coil",
    "trasformatore": "transformer",
    "alimentatore": "power supply",
    "convertitore": "converter",
    "inverter": "inverter",
    "pila": "battery cell",
    "batteria": "battery",
    "accumulatore": "accumulator",
    "lampada": "lamp",
    "sensore": "sensor",
    "sonda": "probe sensor",
    "pedale": "pedal",
    "apparecchio acustico": "hearing aid",
    "siringa": "syringe",
    "orologio": "watch clock",
    "orologio da polso": "wrist watch",
    "movimento": "movement",
    "quadrante": "dial",
    "lancetta": "hand",
    "corona": "crown",
    "cinturino": "strap",
    "bracciale": "bracelet",
    "fibbia": "buckle",
    "chiusura": "clasp",
    "lunetta": "bezel",
    "vetro": "glass",
    "zaffiro": "sapphire",
    "massa oscillante": "oscillating weight rotor",
    "acciaio": "steel",
    "acciaio inossidabile": "stainless steel",
    "acciaio inox": "stainless steel",
    "ghisa": "cast iron",
    "ferro": "iron",
    "rame": "copper",
    "ottone": "brass",
    "alluminio": "aluminium",
    "titanio": "titanium",
    "plastica": "plastic",
    "materia plastica": "plastics",
    "gomma": "rubber",
    "silicone": "silicone",
    "pelle": "leather",
    "cuoio": "leather",
    "legno": "wood",
    "carta": "paper",
    "cartone": "paperboard carton",
    "ceramica": "ceramic",
    "vernice": "paint varnish",
    "colla": "glue adhesive",
    "grasso": "grease",
    "olio": "oil",
    "imballaggio": "packing",
    "valigetta": "case",
    "sacchetto": "bag",
    "etichetta": "label",
    "istruzioni": "instructions printed",
    "elettrico": "electric",
    "elettronico": "electronic",
    "pneumatico": "pneumatic",
    "idraulico": "hydraulic",
    "automatico": "automatic",
    "meccanico": "mechanical",
    "medicale": "medical",
    "medico": "medical",
    "chirurgico": "surgical",
    "centrifugo": "centrifugal",
    "corrente continua": "DC direct current",
    "corrente alternata": "AC alternating current",
    "monouso": "disposable",
    "assemblato": "assembled",
    "saldato": "welded",
    "zincato": "zinc-plated",
    "nichelato": "nickel-plated",
    "cromato": "chromium-plated",
    "isolato": "insulated",
    "smaltato": "enamelled",
    "stampato": "printed",
    "domestico": "domestic household",
    "set": "set",
    "kit": "set",
}

# Keys that are also English words: translated only when another glossary word shows the line is not English.
ENGLISH_HOMOGRAPHS = frozenset(
    {
        "alimentation", "aluminium", "assemble", "axe", "borne", "cable", "cadre", "carte", "carton", "centrifuge",
        "chrome", "corona", "dado", "electrode", "ensemble", "etiquette", "filo", "filter", "flexible", "fond",
        "fusible", "glace", "glas", "halter", "inverter", "joint", "kit", "lager", "lunette", "medical", "membrane",
        "messing", "motor", "mutter", "notice", "piece", "pile", "plaque", "prise", "profile", "rad", "resistance",
        "ring", "sachet", "sensor", "set", "silicone", "sonde", "splint", "stab", "support", "taster", "titan",
    }
)

MAX_PHRASE = 3
MIN_HEAD = 4  # shortest German compound head that may be split off ("Lager" in "Kugellager")
MIN_MODIFIER = 3
# Endings tried, in order, when a word is not a key: (suffix to remove, replacement).
_ENDINGS = (
    ("n", ""), ("s", ""), ("e", ""), ("x", ""), ("en", ""), ("er", ""), ("es", ""), ("em", ""),
    ("i", "o"), ("i", "e"), ("e", "a"), ("a", "o"), ("e", "o"), ("he", "o"), ("hi", "o"),
)
_WORD_RE = re.compile(r"[^\W_]+")


def _key(text: str) -> str:
    return " ".join(fold(w) for w in _WORD_RE.findall(text))


def _merge() -> dict[str, str]:
    merged: dict[str, str] = {}
    for table in (DE, FR, IT):
        for source, english in table.items():
            key = _key(source)
            if merged.get(key, english) != english:
                raise ValueError(f"glossary key {key!r} has two translations")
            merged[key] = english
    return merged


LEXICON: dict[str, str] = _merge()
_WORDS = {k: v for k, v in LEXICON.items() if " " not in k}
_PHRASES = {k: v for k, v in LEXICON.items() if " " in k}


def gloss(text: str) -> str | None:
    """English customs gloss of a DE/FR/IT line (unknown tokens kept), or None if no word was translated."""
    tokens = [fold(w) for w in _WORD_RE.findall(text)]
    out: list[str] = []
    translated = foreign = False
    i = 0
    while i < len(tokens):
        for n in range(min(MAX_PHRASE, len(tokens) - i), 1, -1):
            english = _PHRASES.get(" ".join(tokens[i : i + n]))
            if english:
                out.append(english)
                translated = foreign = True
                i += n
                break
        else:
            key, english = _lookup(tokens[i])
            if english is None:
                english = _split_compound(tokens[i])
                foreign |= english is not None
            else:
                foreign |= key not in ENGLISH_HOMOGRAPHS
            translated |= english is not None
            out.append(english or tokens[i])
            i += 1
    return " ".join(out) if translated and foreign else None


def _lookup(word: str) -> tuple[str, str | None]:
    """(matched key, English) for a word or one of its inflected forms; (word, None) if unknown."""
    if word in _WORDS:
        return word, _WORDS[word]
    for suffix, replacement in _ENDINGS:
        if word.endswith(suffix) and len(word) - len(suffix) >= MIN_MODIFIER:
            stem = word[: len(word) - len(suffix)] + replacement
            if stem in _WORDS:
                return stem, _WORDS[stem]
    return word, None


def _split_compound(word: str) -> str | None:
    """German compound: longest known head; the modifier is translated (recursively) or kept as written."""
    for start in range(MIN_MODIFIER, len(word) - MIN_HEAD + 1):
        _, head = _lookup(word[start:])
        if head is None:
            continue
        modifier = word[:start]
        _, english = _lookup(modifier)
        if english is None and modifier.endswith("s") and len(modifier) > MIN_MODIFIER:
            _, english = _lookup(modifier[:-1])  # linking -s- ("Stellungsregler")
        return f"{english or _split_compound(modifier) or modifier} {head}"
    return None
