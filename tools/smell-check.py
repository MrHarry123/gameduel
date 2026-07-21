#!/usr/bin/env python3
"""
Heuristische check op verdachte patronen die builder-agents produceren
wanneer ze dedup-restricties proberen te omzeilen.

Detecteert:
  - workaround-antwoorden ("De acteur met initialen J.D.", "Schilder uit Zundert")
  - placeholder hints ("x", "Geen", "Geen geldige hint")
  - meta-tekst in hints ("avoid-list", "al genoemd")
  - meta-vragen ("schreef niet X maar wel Y")
  - "uitleg" in antwoord (", dus de schrijver is...")

Gebruik:
  python3 tools/smell-check.py             — check alle pakketten
  python3 tools/smell-check.py pakket-7    — check één pakket
  python3 tools/smell-check.py --clean <pakket>  — verwijder verdachte items uit het bestand

Exit 0 = geen problemen, 1 = problemen gevonden.
"""
import json
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
GAMES = PROJECT / "app" / "games"

# Hints die als placeholder/meta gelden
PLACEHOLDER_HINT = [
    re.compile(r"^(x|geen|tbd|n/a|n\.v\.t\.|\.\.\.|—|-+)$", re.I),
    re.compile(r"^geen geldige hint$", re.I),
    re.compile(r"vraag al beantwoord", re.I),
    re.compile(r"avoid[- ]?list", re.I),
    re.compile(r"vermijd[- ]?lijst", re.I),
    re.compile(r"\bal genoemd\b", re.I),
    re.compile(r"\beerder beantwoord\b", re.I),
    re.compile(r"\beerder gebruikt\b", re.I),
    re.compile(r"\bvorige (vraag|ronde)\b", re.I),
]

# Antwoorden die workaround-patronen tonen
WORKAROUND_ANSWER = [
    re.compile(
        r"^De\s+(acteur|zanger|zangeres|schilder|schrijver|schrijfster|componist|regisseur|band|kunstenaar|wetenschapper|filosoof|sporter|atleet|tennisser|voetballer|stad|land)\s+(met|uit|van)\b",
        re.I,
    ),
    re.compile(
        r"^(Schilder|Acteur|Zanger|Zangeres|Componist|Regisseur|Schrijver|Schrijfster|Wetenschapper|Sporter)\s+uit\b",
        re.I,
    ),
    re.compile(r"\binitialen\b", re.I),
    re.compile(r",\s*dus\s+(de|het|een|deze|die)\b", re.I),
]

# Meta-vragen — specifiek: verwijzen naar werk/persoon/iets en dan een ander werk
# Vermijd false positives op normale contrast-vragen ("kan niet vliegen maar wel rennen")
META_QUESTION = [
    # "Wie schreef X niet maar wel Y?" — bekende werkwoorden gevolgd door een werk-titel-achtige string
    re.compile(
        r"\b(schreef|maakte|regisseerde|componeerde|schilderde|bedacht|zong|speelde|won|deed)\s+(de\s+|het\s+)?[A-Z]\w+.{0,40}\bniet\b.{0,40}\bmaar wel\b",
        re.I,
    ),
    re.compile(r"\bvraag al beantwoord\b", re.I),
    re.compile(r"\bantwoord:\s+\w+\s+(was|is)\b", re.I),
]

# Chemische formules: minstens 2 element-blokken én minstens 1 digit ergens
# Voorbeelden die matchen: CO2, H2O, H2SO4, NaCl2, Fe2O3
# Niet-matches: USA, DNA, NaCl (zonder digit), losse letters
CHEMICAL_FORMULA = re.compile(r"\b(?=[A-Za-z0-9]*\d)(?:[A-Z][a-z]?\d*){2,}\b")

# Vage/inhoudloze hints — "Hij was beroemd", "Een bekende persoon"
VAGUE_HINT = [
    re.compile(
        r"^\s*(hij|zij|het|deze|die|dit)\s+(was|is|werd|wordt)\s+(beroemd|bekend|groot|klein|belangrijk|interessant|populair|invloedrijk)\.?\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*een\s+(bekende|beroemde|grote|belangrijke|invloedrijke|populaire)\s+(persoon|man|vrouw|figuur|ding|object|naam)\.?\s*$",
        re.I,
    ),
    re.compile(r"^\s*iets\s+(interessants|bekends|beroemds|belangrijks)\.?\s*$", re.I),
]

# Partial-name leak — "(voor|achter)naam is X" waarbij X uit het antwoord komt
PARTIAL_NAME_LEAK_RE = re.compile(
    r"\b(?:voor|achter|tussen|bij)naam\s+(?:is|luidt|wordt)\s+([A-Za-zÀ-ÿ]+)\b",
    re.I,
)

# Letter-count claims om mechanisch te verifiëren ("telt vier letters")
LETTER_COUNT_RE = re.compile(
    r"\b(?:telt|heeft|bevat|met)\s+(\w+)\s+letter[s]?\b",
    re.I,
)
BEGIN_LETTER_RE = re.compile(
    r"\b(?:begint|start)\s+met\s+(?:de\s+letter\s+|een\s+)?[\"']?([A-Z])[\"']?\b",
)
END_LETTER_RE = re.compile(
    r"\beindigt\s+(?:op|met)\s+(?:de\s+letter\s+|een\s+)?[\"']?([A-Z])[\"']?\b",
)

# Hint 4 format-positief: een echte near-giveaway heeft minstens één van deze woorden
FORMAT_KEYWORD_RE = re.compile(
    r"\b(?:letter|letters|begint|start|eindigt|initialen|rijm|rijmt|telt|bevat)\b",
    re.I,
)

# Hint 4 die per ongeluk een gewone subject-info-zin is ipv format-based.
# Beperkt tot "hij/zij" — "het" sluiten we uit want "Het is minder dan 50" is een legitieme numerieke hint.
SUSPICIOUS_HINT4_RE = re.compile(
    r"^\s*(?:hij|zij)\s+(?:was|werd|wordt|is|heeft|had|speelde|won|maakte|schreef|leefde|kwam|stierf|kreeg|bracht|voer)\b",
    re.I,
)

NUMBER_WORDS = {
    "een": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6,
    "zeven": 7, "acht": 8, "negen": 9, "tien": 10, "elf": 11, "twaalf": 12,
    "dertien": 13, "veertien": 14, "vijftien": 15, "zestien": 16,
    "zeventien": 17, "achttien": 18, "negentien": 19, "twintig": 20,
}


def _parse_number(s):
    s = s.lower().strip()
    if s.isdigit():
        return int(s)
    return NUMBER_WORDS.get(s)


def _significant_words(s):
    """Splits string in woorden van ≥4 letters (skip korte tokens, lidwoorden, getallen)."""
    return [w.lower() for w in re.findall(r"\b[A-Za-zÀ-ÿ]+\b", s) if len(w) >= 4]


def check_classic_item(item):
    issues = []
    q = item.get("question", "") or ""
    a = item.get("answer", "") or ""
    hints = item.get("hints", []) or []

    for pat in META_QUESTION:
        if pat.search(q):
            issues.append(f"meta-vraag: \"{q[:80]}\"")
            break

    for pat in WORKAROUND_ANSWER:
        if pat.search(a):
            issues.append(f"workaround antwoord: \"{a}\"")
            break

    # Lange antwoorden zijn ook verdacht (uitleg ipv naam)
    if len(a.split()) > 7:
        issues.append(f"antwoord te lang (>7 woorden): \"{a}\"")
    elif len(a) > 50:
        issues.append(f"antwoord te lang (>50 tekens): \"{a}\"")

    # Circulaire vraag: alle significante antwoord-woorden (≥2 stuks) zitten al in de vraag
    # ≥2 vereiste voorkomt false positives op categorie-vragen zoals "Welk vitamine..." → "Vitamine D"
    a_sig = _significant_words(a)
    if a_sig and len(a_sig) >= 2:
        q_lower = q.lower()
        if all(re.search(r"\b" + re.escape(w) + r"\b", q_lower) for w in a_sig):
            issues.append(f"vraag bevat het hele antwoord (circulair): \"{a}\"")

    # Chemische formules in de vraag — die mogen ook in hints staan zonder leak
    q_formulas = set(CHEMICAL_FORMULA.findall(q))

    a_words = a.split()
    a_letters_only = re.sub(r"[^A-Za-zÀ-ÿ]", "", a)

    for i, h in enumerate(hints):
        if not isinstance(h, str):
            continue
        for pat in PLACEHOLDER_HINT:
            if pat.search(h.strip()):
                issues.append(f"hint {i+1} is placeholder/meta: \"{h}\"")
                break

        # Te korte hint = bijna altijd te vaag (1 woord). Format-based 2-woord-hints
        # zoals "Vijf letters" of "Initialen J.D." worden uitgezonderd.
        h_words = re.findall(r"\b\w+\b", h)
        if len(h_words) == 1:
            issues.append(f"hint {i+1} is te kort (1 woord): \"{h}\"")
        elif len(h_words) == 2 and not FORMAT_KEYWORD_RE.search(h):
            issues.append(f"hint {i+1} is te kort (2 woorden, geen format-hint): \"{h}\"")

        # Vage inhoudloze hint
        for pat in VAGUE_HINT:
            if pat.search(h.strip()):
                issues.append(f"hint {i+1} is te vaag: \"{h}\"")
                break

        # Partial-name leak — "voornaam is William" met William uit antwoord
        m = PARTIAL_NAME_LEAK_RE.search(h)
        if m:
            leaked = m.group(1).lower()
            if a_sig and leaked in a_sig:
                issues.append(
                    f"hint {i+1} leakt naam-onderdeel '{m.group(1)}' uit antwoord '{a}' — gebruik format zoals 'N letters' of initialen"
                )

        # Letter-count verificatie
        for m in LETTER_COUNT_RE.finditer(h):
            claimed = _parse_number(m.group(1))
            if claimed is None:
                continue
            valid = {len(a_letters_only)}
            for word in a_words:
                wl = re.sub(r"[^A-Za-zÀ-ÿ]", "", word)
                if wl:
                    valid.add(len(wl))
            if claimed not in valid:
                issues.append(
                    f"hint {i+1} claimt {claimed} letters maar antwoord '{a}' heeft {len(a_letters_only)} letters"
                )

        # Begin-letter verificatie
        for m in BEGIN_LETTER_RE.finditer(h):
            claimed = m.group(1).lower()
            if not a:
                continue
            valid = set()
            if a:
                valid.add(a[0].lower())
            for word in a_words:
                if word:
                    valid.add(word[0].lower())
            if claimed not in valid:
                issues.append(
                    f"hint {i+1} zegt 'begint met {claimed.upper()}' maar antwoord '{a}' begint met '{a[0].upper()}'"
                )

        # Eind-letter verificatie
        for m in END_LETTER_RE.finditer(h):
            claimed = m.group(1).lower()
            if not a:
                continue
            valid = set()
            if a:
                valid.add(a[-1].lower())
            for word in a_words:
                if word:
                    valid.add(word[-1].lower())
            if claimed not in valid:
                issues.append(
                    f"hint {i+1} zegt 'eindigt op {claimed.upper()}' maar antwoord '{a}' eindigt op '{a[-1].upper()}'"
                )

        # Volledig antwoord-leak: alle significante antwoord-woorden in deze hint
        if a_sig and all(re.search(r"\b" + re.escape(w) + r"\b", h.lower()) for w in a_sig):
            issues.append(f"hint {i+1} bevat het volledige antwoord: \"{h[:80]}\"")

        # Chemische formule-leak: formule in hint die niet in de vraag staat
        for formula in CHEMICAL_FORMULA.findall(h):
            if formula not in q_formulas:
                issues.append(f"hint {i+1} bevat chemische formule '{formula}' (niet in vraag — mogelijk leak)")
                break

    # Hint 4 (de laatste hint) moet format-based zijn — geen enkel woord uit het antwoord
    if hints and a_sig and isinstance(hints[-1], str):
        last = hints[-1].lower()
        leaked = next((w for w in a_sig if re.search(r"\b" + re.escape(w) + r"\b", last)), None)
        if leaked:
            issues.append(
                f"hint {len(hints)} (near-giveaway) bevat woord uit antwoord ('{leaked}') — gebruik format zoals 'begint met X', 'N letters' of initialen"
            )

    # Hint 4 lijkt een gewone subject-info-zin ipv format-based
    if hints and isinstance(hints[-1], str):
        last = hints[-1]
        if not FORMAT_KEYWORD_RE.search(last) and SUSPICIOUS_HINT4_RE.match(last):
            issues.append(
                f"hint {len(hints)} (near-giveaway) lijkt over het subject te gaan ipv format-based — controleer: \"{last[:80]}\""
            )

    return issues


def check_open_item(item):
    """Open vragen: zelfde vraag/antwoord-checks als klassiek, maar zonder hint-checks."""
    issues = []
    q = item.get("question", "") or ""
    a = item.get("answer", "") or ""

    for pat in META_QUESTION:
        if pat.search(q):
            issues.append(f"meta-vraag: \"{q[:80]}\"")
            break

    for pat in WORKAROUND_ANSWER:
        if pat.search(a):
            issues.append(f"workaround antwoord: \"{a}\"")
            break

    if len(a.split()) > 7:
        issues.append(f"antwoord te lang (>7 woorden): \"{a}\"")
    elif len(a) > 50:
        issues.append(f"antwoord te lang (>50 tekens): \"{a}\"")

    a_sig = _significant_words(a)
    if a_sig and len(a_sig) >= 2:
        q_lower = q.lower()
        if all(re.search(r"\b" + re.escape(w) + r"\b", q_lower) for w in a_sig):
            issues.append(f"vraag bevat het hele antwoord (circulair): \"{a}\"")

    return issues


def check_statement_item(item):
    issues = []
    statements = item.get("statements", []) or []
    prompt = item.get("prompt", "") or ""

    for i, s in enumerate(statements):
        if not isinstance(s, str):
            continue
        for pat in PLACEHOLDER_HINT:
            if pat.search(s.strip()):
                issues.append(f"statement {i+1} is placeholder/meta: \"{s}\"")
                break
        # Statements die verwijzen naar andere statements
        if re.search(r"\b(zoals\s+(de\s+)?vorige|in tegenstelling tot|anders dan\s+(de\s+)?vorige|hierboven|hieronder)\b", s, re.I):
            issues.append(f"statement {i+1} verwijst naar andere statements: \"{s}\"")

    if not prompt.strip():
        issues.append("prompt is leeg")

    return issues


def check_pakket(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    mode = data.get("mode", "classic")
    check_func = {
        "statements": check_statement_item,
        "open": check_open_item,
        "open-hints": check_open_item,
    }.get(mode, check_classic_item)
    items = data.get("questions", [])
    flagged = []
    for idx, item in enumerate(items):
        issues = check_func(item)
        if issues:
            flagged.append((idx, issues))
    return flagged, mode, items


def clean_pakket(path, indices_to_remove):
    data = json.loads(path.read_text(encoding="utf-8"))
    kept = [
        item for i, item in enumerate(data["questions"]) if i not in indices_to_remove
    ]
    data["questions"] = kept
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(kept)


def main():
    args = sys.argv[1:]
    clean_mode = "--clean" in args
    if clean_mode:
        args.remove("--clean")

    target = args[0] if args else None

    if target:
        # Strip .json extension if given
        target = target.removesuffix(".json")
        path = GAMES / f"{target}.json"
        if not path.exists():
            print(f"❌ {path} niet gevonden")
            return 1
        paths = [path]
    else:
        paths = sorted(p for p in GAMES.glob("*.json") if p.name != "index.json")

    total_flagged = 0
    for path in paths:
        flagged, mode, items = check_pakket(path)
        if not flagged:
            continue
        total_flagged += len(flagged)
        print(f"\n⚠️  {path.name} ({mode}) — {len(flagged)} verdacht(e) item(s):")
        for idx, issues in flagged:
            print(f"  [{idx}]")
            for iss in issues:
                print(f"     · {iss}")
        if clean_mode:
            to_remove = {idx for idx, _ in flagged}
            kept = clean_pakket(path, to_remove)
            print(f"  → {len(to_remove)} verwijderd, {kept} resterend in {path.name}")

    if total_flagged == 0:
        print("✅ Geen verdachte patronen gevonden.")
        return 0

    print(f"\n{total_flagged} verdachte item(s) totaal.")
    if not clean_mode:
        print("Tip: run met --clean om verdachte items automatisch te verwijderen,")
        print("of laat de builder-agent ze opnieuw genereren.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
