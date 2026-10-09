"""Static DE/FR/IT -> EN customs glossary for bill-of-materials words, used when no model rewrite exists.

Retrieval runs over the English HS 2022 nomenclature, so a German line such as "Kugellager Edelstahl 6204"
shares no word with heading 8482 ("Ball or roller bearings") and the char n-gram ranker drifts to whatever
looks alike. `gloss` is a deterministic stand-in for the Apertus rewrite step:

- multi-word terms are matched first ("roulement à billes" -> "ball bearing");
- single words are looked up after accent folding, with light plural/adjective endings of the word's own
  language removed ("Schrauben" -> "Schraube", "cuscinetti" -> "cuscinetto", "électriques" -> "électrique");
- German compounds are split on their longest known German head ("Edelstahlgehäuse" -> "Edelstahl" + "Gehäuse"),
  the modifier translated if known and kept as written otherwise ("Zentrifugalpumpe" -> "zentrifugal pump");
- every other token (part numbers, norms, unknown words, punctuation) is kept exactly as written;
- English lines are left alone: a line is glossed only if it shows it is not English (a translated word that
  is not also an English word or is written with an accent, or a German/French/Italian function word).

The English side uses HS vocabulary where an exact equivalent exists ("Typenschild" -> "name-plate"). Entries
translate words; none encodes an HS code or a classification decision. They were written by hand from general
technical and customs vocabulary for the parts Swiss SMEs list in BOMs, not from the evaluation set; the three
"Sicherungs-" entries were added after a dev-split line was glossed as "fuse nut" instead of "lock nut".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

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
    "Sicherungsmutter": "lock nut",
    "Sicherungsring": "retaining ring circlip",
    "Sicherungsscheibe": "lock washer",
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

# French (Swiss usage), written with accents: lookups fold them, but a stemmed match must not add an accent the
# key lacks ("fraisée" is not an inflection of "fraise"). Multi-word keys are matched on whole folded tokens.
FR: dict[str, str] = {
    "roulement": "bearing",
    "roulement à billes": "ball bearing",
    "roulements à billes": "ball bearings",
    "roulement à rouleaux": "roller bearing",
    "bille": "ball",
    "vis": "screw",
    "écrou": "nut",
    "boulon": "bolt",
    "rondelle": "washer",
    "goupille": "pin",
    "ressort": "spring",
    "joint torique": "o-ring seal",
    "joints toriques": "o-ring seals",
    "joint": "gasket seal",
    "garniture": "packing seal",
    "boîtier": "housing case",
    "boîte": "case box",
    "couvercle": "lid cover",
    "fond": "back",
    "cadre": "frame",
    "support": "bracket support",
    "poignée": "handle",
    "arbre": "shaft",
    "axe": "axle pin",
    "engrenage": "gear",
    "roue dentée": "toothed wheel gear",
    "roue": "wheel",
    "accouplement": "coupling",
    "embrayage": "clutch",
    "courroie": "belt",
    "chaîne": "chain",
    "poulie": "pulley",
    "douille": "bush sleeve",
    "bague": "ring",
    "plaque": "plate",
    "tôle": "sheet",
    "barre": "bar",
    "profilé": "profile",
    "tuyau": "pipe tube",
    "flexible": "flexible hose",
    "raccord": "fitting",
    "bride": "flange",
    "pièce": "part",
    "membrane": "membrane diaphragm",
    "vérin": "cylinder actuator",
    "buse": "nozzle",
    "filtre": "filter",
    "pompe": "pump",
    "vanne": "valve",
    "soupape": "valve",
    "électrovanne": "solenoid valve",
    "moteur": "motor",
    "actionneur": "actuator",
    "ventilateur": "fan",
    "outil": "tool",
    "fraise": "milling cutter",
    "machine à café": "coffee machine",
    "circuit imprimé": "printed circuit",
    "circuits imprimés": "printed circuits",
    "carte électronique": "printed circuit board electronic",
    "carte": "board card",
    "câble": "cable",
    "fil": "wire",
    "fil de cuivre": "copper wire",
    "connecteur": "connector",
    "prise": "plug socket",
    "borne": "terminal",
    "interrupteur": "switch",
    "fusible": "fuse",
    "résistance": "resistor",
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
    "écran": "screen display",
    "lampe": "lamp",
    "capteur": "sensor",
    "sonde": "probe sensor",
    "débitmètre": "flow meter",
    "régulateur": "regulator",
    "électrode": "electrode",
    "presse-étoupe": "cable gland",
    "presse-étoupes": "cable glands",
    "appareil auditif": "hearing aid",
    "seringue": "syringe",
    "montre": "watch",
    "montre-bracelet": "wrist watch",
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
    "écrin": "case box",
    "acier": "steel",
    "acier inoxydable": "stainless steel",
    "inox": "stainless steel",
    "fonte": "cast iron",
    "fer": "iron",
    "cuivre": "copper",
    "laiton": "brass",
    "titane": "titanium",
    "plastique": "plastic",
    "matière plastique": "plastics",
    "caoutchouc": "rubber",
    "cuir": "leather",
    "bois": "wood",
    "papier": "paper",
    "carton": "paperboard carton",
    "céramique": "ceramic",
    "peinture": "paint",
    "vernis": "varnish",
    "colle": "glue adhesive",
    "graisse": "grease",
    "huile": "oil",
    "emballage": "packing",
    "sachet": "bag",
    "étiquette": "label",
    "plaque signalétique": "name-plate",
    "notice": "instructions printed",
    "électrique": "electric",
    "électronique": "electronic",
    "pneumatique": "pneumatic",
    "hydraulique": "hydraulic",
    "automatique": "automatic",
    "mécanique": "mechanical",
    "médical": "medical",
    "chirurgical": "surgical",
    "centrifuge": "centrifugal",
    "courant continu": "DC direct current",
    "courant alternatif": "AC alternating current",
    "jetable": "disposable",
    "assemblé": "assembled",
    "soudé": "welded",
    "zingué": "zinc-plated",
    "nickelé": "nickel-plated",
    "chromé": "chromium-plated",
    "isolé": "insulated",
    "émaillé": "enamelled",
    "imprimé": "printed",
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
    "macchina da caffè": "coffee machine",
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

# Keys that are also English words (or codes): translated only when the line shows it is not English.
ENGLISH_HOMOGRAPHS = frozenset(
    {
        "alimentation", "aluminium", "assemble", "axe", "borne", "bride", "cable", "cadre", "carte", "carton",
        "centrifuge", "chrome", "corona", "dado", "electrode", "ensemble", "etiquette", "ferro", "filo", "filter",
        "flexible", "fond", "fusible", "glace", "glas", "halter", "inverter", "joint", "kit", "lack", "lager",
        "lunette", "medical", "membrane", "messing", "motor", "mutter", "notice", "ol", "piece", "pile", "plaque",
        "prise", "profile", "rad", "resistance", "ring", "sachet", "sensor", "set", "silicone", "sonde", "splint",
        "stab", "support", "taster", "titan", "ventilator",
    }
)

# English words of the HS 2022 nomenclature that would otherwise reach a non-homograph key by stemming or
# compound splitting ("tube" -> Italian "tubo", "files" -> French "fil"). They are never stemmed or split, so an
# English line is not mistaken for a foreign one; tests/test_hs_glossary.py re-derives the list from the
# nomenclature. (Splits onto a homograph head, such as "bearing" -> "bea" + "Ring", are weak evidence and only
# used in lines that are already known to be foreign.)
ENGLISH_FORMS = frozenset({"batteries", "buses", "file", "files", "perna", "profiles", "spiegeleisen", "tube"})

# Function words of German, French and Italian BOM lines that English lines do not use. Compared before accent
# folding, so French "à" counts and English "fur" (from "für") does not. Left out because they double as English
# words or codes: "an", "am", "die", "in", "per", "pro", "un", "aux", "par", "den", "bis", "en" ("EN AW-6060"),
# "de" (Germany), "a".
FOREIGN_FUNCTION_WORDS = frozenset(
    "für fuer mit aus ohne und oder der das dem des ein eine einer eines einem einen vom zum zur im bei nach zu "
    "als auf inkl à du et ou avec sans pour au sur dans le la les une il lo gli di del della dei degli delle da "
    "dal dalla con senza su nel nella alla una uno".split()
)

LANGS = ("de", "fr", "it")
MAX_PHRASE = 3
MIN_HEAD = 4  # shortest German key that may be split off as a compound head ("Ring" in "Polyamidring")
MIN_MODIFIER = 3  # shortest compound modifier ("Uhr" in "Uhrglas")
MIN_STEM = 3  # shortest word left after removing an ending
# Endings tried, in order, when a word is not a key: (suffix to remove, replacement), per language.
ENDINGS: dict[str, tuple[tuple[str, str], ...]] = {
    "de": (("n", ""), ("s", ""), ("e", ""), ("en", ""), ("er", ""), ("es", ""), ("em", "")),
    "fr": (("s", ""), ("x", ""), ("e", ""), ("es", ""), ("aux", "al")),
    "it": (("i", "o"), ("i", "e"), ("e", "a"), ("a", "o"), ("e", "o"), ("he", "o"), ("hi", "o")),
}
_WORD_RE = re.compile(r"[^\W_]+")


@dataclass(frozen=True)
class Entry:
    key: str  # folded lookup key
    source: str  # the glossary spelling, case-folded with its accents
    english: str
    lang: str


@dataclass(frozen=True)
class _Match:
    start: int  # character span in the input text
    end: int
    english: str
    strong: bool  # evidence on its own that the line is not English


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _key(text: str) -> str:
    return " ".join(fold(w) for w in _WORD_RE.findall(_nfc(text)))


def _build() -> tuple[dict[str, dict[str, Entry]], dict[str, Entry]]:
    words: dict[str, dict[str, Entry]] = {lang: {} for lang in LANGS}
    phrases: dict[str, Entry] = {}
    seen: dict[str, str] = {}
    for lang, table in zip(LANGS, (DE, FR, IT)):
        for source, english in table.items():
            key = _key(source)
            if seen.get(key, english) != english:
                raise ValueError(f"glossary key {key!r} has two translations")
            seen[key] = english
            entry = Entry(key, _nfc(source).casefold(), english, lang)
            (phrases if " " in key else words[lang])[key] = entry
    return words, phrases


WORDS, PHRASES = _build()
# Every folded key (words and phrases) -> English.
LEXICON: dict[str, str] = {e.key: e.english for table in (*WORDS.values(), PHRASES) for e in table.values()}


def gloss(text: str) -> str | None:
    """English customs gloss of a German/French/Italian BOM line, or None.

    None when no word is translated or when nothing shows that the line is not English (only English homographs
    such as "Motor" or "Ring" matched and no German/French/Italian function word occurs). Everything that is not
    translated (part numbers, norms, unknown words, punctuation) is kept exactly as written.
    """
    text = _nfc(text)
    tokens = list(_WORD_RE.finditer(text))
    folded = [fold(t.group()) for t in tokens]
    matches: list[_Match] = []
    i = 0
    while i < len(tokens):
        n, entry = _phrase(folded, i)
        if entry is not None:
            matches.append(_Match(tokens[i].start(), tokens[i + n - 1].end(), entry.english, True))
            i += n
            continue
        found = _word(tokens[i].group(), folded[i])
        if found is not None:
            matches.append(_Match(tokens[i].start(), tokens[i].end(), *found))
        i += 1
    foreign = any(m.strong for m in matches) or any(t.group().casefold() in FOREIGN_FUNCTION_WORDS for t in tokens)
    if not matches or not foreign:
        return None
    out: list[str] = []
    pos = 0
    for m in matches:
        out += [text[pos : m.start], m.english]
        pos = m.end
    out.append(text[pos:])
    return " ".join("".join(out).split())


def _phrase(folded: list[str], i: int) -> tuple[int, Entry | None]:
    for n in range(min(MAX_PHRASE, len(folded) - i), 1, -1):
        entry = PHRASES.get(" ".join(folded[i : i + n]))
        if entry is not None:
            return n, entry
    return 0, None


def _word(surface: str, folded: str) -> tuple[str, bool] | None:
    """(English, strong) for one word: a key, an inflected key, or a German compound; None if unknown."""
    entry = lookup(surface, folded, LANGS)
    if entry is not None:
        # A homograph written with an accent ("Pièces", "câble") is not the English word.
        return entry.english, entry.key not in ENGLISH_HOMOGRAPHS or folded != surface.casefold()
    if folded in ENGLISH_FORMS:
        return None
    return _compound(surface, folded)


def lookup(surface: str, folded: str, langs: tuple[str, ...] = LANGS) -> Entry | None:
    """Entry for a word or one of its inflected forms (endings of the entry's language), or None."""
    cf = surface.casefold()
    for lang in langs:
        entry = WORDS[lang].get(folded)
        if entry is not None and _accents_agree(cf, entry.source):
            return entry
    if folded in ENGLISH_FORMS:
        return None
    for lang in langs:
        for suffix, replacement in ENDINGS[lang]:
            if not folded.endswith(suffix) or len(folded) - len(suffix) < MIN_STEM:
                continue
            entry = WORDS[lang].get(folded[: -len(suffix)] + replacement)
            stem = cf[: -len(suffix)] + replacement if cf.endswith(suffix) else None
            if entry is not None and (stem is None or _accents_agree(stem, entry.source)):
                return entry
    return None


def _accents_agree(written: str, source: str) -> bool:
    """False if `written` carries an accent where the glossary spelling has none ("fraisé" vs "fraise").

    A missing accent is fine (BOMs are often typed without them); compared only when the letters align 1:1.
    """
    if len(written) != len(source):
        return True
    return not any(w != s and fold(w) == s for w, s in zip(written, source))


def _compound(surface: str, folded: str) -> tuple[str, bool] | None:
    """German compound split on its longest known head; the modifier is translated (recursively) or kept as written.

    Strong evidence of German only if the head is not an English homograph or a modifier part was translated
    ("Getriebemotor"); "Polyamidring" (unknown modifier + "Ring") is weak.
    """
    for start in range(MIN_MODIFIER, len(folded) - MIN_HEAD + 1):
        head = lookup(surface[_cut(surface, start) :], folded[start:], ("de",))
        if head is None or len(head.key) < MIN_HEAD:
            continue
        cut = _cut(surface, start)
        modifier = lookup(surface[:cut], folded[:start], ("de",))
        if modifier is not None:
            english, strong = modifier.english, modifier.key not in ENGLISH_HOMOGRAPHS
        else:
            english, strong = _compound(surface[:cut], folded[:start]) or (surface[:cut], False)
        return f"{english} {head.english}", strong or head.key not in ENGLISH_HOMOGRAPHS
    return None


def _cut(surface: str, folded_len: int) -> int:
    """Index in `surface` whose folded prefix has `folded_len` characters ("Gehäuse" folds to "gehause")."""
    for i in range(len(surface) + 1):
        if len(fold(surface[:i])) >= folded_len:
            return i
    return len(surface)
