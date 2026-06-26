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

    for i, h in enumerate(hints):
        if not isinstance(h, str):
            continue
        for pat in PLACEHOLDER_HINT:
            if pat.search(h.strip()):
                issues.append(f"hint {i+1} is placeholder/meta: \"{h}\"")
                break

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
    items = data.get("questions", [])
    flagged = []
    for idx, item in enumerate(items):
        if mode == "statements":
            issues = check_statement_item(item)
        else:
            issues = check_classic_item(item)
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
