#!/usr/bin/env python3
"""
Mechanische check op alle pakket-bestanden in games/.
Detecteert structurele fouten, missende velden, lege strings, duplicaten.

Gebruik:  python3 tools/validate-questions.py
Exit 0 bij OK, exit 1 bij gevonden problemen.
"""
import difflib
import json
import re
import sys
from pathlib import Path

GAMES_DIR = Path(__file__).resolve().parent.parent / "app" / "games"
EXPECTED_PROMPTS = {"Welke uitspraak is waar?", "Welke uitspraak is NIET waar?"}

errors = []
warnings = []
all_ids = {}
all_classic_answers = {}  # normalized → (pakket_id, idx)
all_classic_answers_list = []  # [(norm, pakket_id, idx)] voor near-dup check
all_statements_keys = {}  # normalized → (pakket_id, idx)


def err(loc, msg):
    errors.append(f"❌ {loc}: {msg}")


def warn(loc, msg):
    warnings.append(f"⚠️  {loc}: {msg}")


def norm(s):
    return " ".join(s.lower().split()).rstrip(".!?")


def validate_classic(pakket_id, idx, item):
    loc = f"{pakket_id}[{idx}]"
    if not isinstance(item, dict):
        err(loc, "is geen object")
        return
    for key in ("question", "answer", "hints"):
        if key not in item:
            err(loc, f"mist veld '{key}'")
    q = item.get("question")
    a = item.get("answer")
    hints = item.get("hints")
    if not isinstance(q, str) or not q.strip():
        err(loc, "vraag is leeg of geen string")
    if not isinstance(a, str) or not a.strip():
        err(loc, "antwoord is leeg of geen string")
    if not isinstance(hints, list):
        err(loc, "hints is geen array")
        return
    if len(hints) != 4:
        err(loc, f"verwacht 4 hints, heeft er {len(hints)}")
    for i, h in enumerate(hints):
        if not isinstance(h, str) or not h.strip():
            err(loc, f"hint {i+1} is leeg of geen string")
    # Cross-pakket: duplicate answer (exact match) en near-dup detectie
    if isinstance(a, str) and a.strip():
        key = norm(a)
        if key in all_classic_answers:
            other = all_classic_answers[key]
            warn(loc, f"antwoord '{a}' lijkt op antwoord bij {other[0]}[{other[1]}]")
        else:
            all_classic_answers[key] = (pakket_id, idx)
        # Near-dup: word-bounded substring + ratio (catches "Rembrandt" vs "Rembrandt van Rijn"
        # of "Tennis" vs "Lawn tennis"; mijdt false positives als "Groen" vs "Groenland")
        if len(key) >= 5:
            for prev_norm, prev_pakket, prev_idx in all_classic_answers_list:
                if prev_pakket == pakket_id and prev_idx == idx:
                    continue
                if prev_norm == key:
                    continue
                if len(prev_norm) < 5:
                    continue
                shorter, longer = (key, prev_norm) if len(key) < len(prev_norm) else (prev_norm, key)
                if re.search(r"\b" + re.escape(shorter) + r"\b", longer):
                    warn(loc, f"antwoord '{a}' is bijna identiek aan '{prev_norm}' bij {prev_pakket}[{prev_idx}] (substring)")
                    break
                ratio = difflib.SequenceMatcher(None, key, prev_norm).ratio()
                if ratio > 0.85:
                    warn(loc, f"antwoord '{a}' lijkt op '{prev_norm}' bij {prev_pakket}[{prev_idx}] ({int(ratio*100)}% gelijk)")
                    break
        all_classic_answers_list.append((key, pakket_id, idx))


def validate_statements(pakket_id, idx, item):
    loc = f"{pakket_id}[{idx}]"
    if not isinstance(item, dict):
        err(loc, "is geen object")
        return
    for key in ("prompt", "statements", "correctIndex"):
        if key not in item:
            err(loc, f"mist veld '{key}'")
    prompt = item.get("prompt")
    statements = item.get("statements")
    ci = item.get("correctIndex")
    if not isinstance(prompt, str) or not prompt.strip():
        err(loc, "prompt is leeg")
    elif prompt not in EXPECTED_PROMPTS:
        warn(loc, f"onbekende prompt: '{prompt}' — verwacht een van: {EXPECTED_PROMPTS}")
    if not isinstance(statements, list):
        err(loc, "statements is geen array")
        return
    if len(statements) != 3:
        err(loc, f"verwacht 3 statements, heeft er {len(statements)}")
    seen = set()
    for i, s in enumerate(statements):
        if not isinstance(s, str) or not s.strip():
            err(loc, f"statement {i+1} is leeg of geen string")
        elif norm(s) in seen:
            err(loc, f"duplicaat-statement op positie {i+1}")
        elif isinstance(s, str):
            seen.add(norm(s))
    if not isinstance(ci, int) or not (0 <= ci < 3):
        err(loc, f"correctIndex moet 0, 1 of 2 zijn (kreeg {ci!r})")
    # Cross-pakket: gelijke triple
    if isinstance(statements, list) and all(isinstance(s, str) for s in statements):
        key = "|".join(sorted(norm(s) for s in statements))
        if key in all_statements_keys:
            other = all_statements_keys[key]
            warn(loc, f"zelfde set statements als {other[0]}[{other[1]}]")
        else:
            all_statements_keys[key] = (pakket_id, idx)


def validate_pakket(path):
    pakket_id = path.stem
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        err(pakket_id, f"ongeldige JSON: {e}")
        return

    if not isinstance(data, dict):
        err(pakket_id, "topniveau is geen object")
        return

    for key in ("id", "title", "emoji", "questions"):
        if key not in data:
            err(pakket_id, f"mist veld '{key}'")

    pid = data.get("id")
    if isinstance(pid, str):
        if pid in all_ids:
            err(pakket_id, f"dubbele id '{pid}' — al gebruikt in {all_ids[pid]}")
        else:
            all_ids[pid] = pakket_id

    mode = data.get("mode", "classic")
    if mode not in ("classic", "statements"):
        err(pakket_id, f"onbekende mode '{mode}'")

    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        err(pakket_id, "questions is leeg of geen array")
        return

    # Even-aantal check — zonder even aantal kan het spel oneerlijk eindigen
    if len(questions) % 2 != 0:
        warn(
            pakket_id,
            f"oneven aantal items ({len(questions)}) — voor fairness wordt het laatste item bij elke ronde geskipt; voeg 1 item toe of verwijder er 1."
        )

    # Stellingen-balans: correctIndex-verdeling en prompt-verdeling
    if mode == "statements":
        idx_count = {0: 0, 1: 0, 2: 0}
        prompt_count = {}
        for item in questions:
            if not isinstance(item, dict):
                continue
            ci = item.get("correctIndex")
            if isinstance(ci, int) and 0 <= ci < 3:
                idx_count[ci] += 1
            p = item.get("prompt")
            if isinstance(p, str):
                prompt_count[p] = prompt_count.get(p, 0) + 1
        total = sum(idx_count.values())
        if total > 0:
            for i, n in idx_count.items():
                if n > total * 0.6:
                    warn(pakket_id, f"correctIndex {i} wordt {n}/{total} keer gebruikt (>60%) — verdeel beter")
        waar = prompt_count.get("Welke uitspraak is waar?", 0)
        niet = prompt_count.get("Welke uitspraak is NIET waar?", 0)
        if waar + niet > 0:
            ratio = waar / (waar + niet)
            if ratio < 0.3 or ratio > 0.7:
                warn(pakket_id, f"prompt-balans scheef: 'waar?' {waar}x vs 'NIET waar?' {niet}x (mik op 50/50)")

    seen_questions = set()
    for idx, item in enumerate(questions):
        if mode == "statements":
            validate_statements(pid or pakket_id, idx, item)
        else:
            validate_classic(pid or pakket_id, idx, item)
            q = item.get("question") if isinstance(item, dict) else None
            if isinstance(q, str):
                k = norm(q)
                if k in seen_questions:
                    err(f"{pid or pakket_id}[{idx}]", f"duplicaat-vraag binnen pakket")
                else:
                    seen_questions.add(k)


def main():
    index_path = GAMES_DIR / "index.json"
    if not index_path.exists():
        print(f"❌ games/index.json niet gevonden")
        sys.exit(1)

    files = json.loads(index_path.read_text(encoding="utf-8"))
    print(f"📦 {len(files)} pakketten in index.json")

    locked_count = 0
    for fname in files:
        path = GAMES_DIR / fname
        if not path.exists():
            err(fname, "bestand bestaat niet")
            continue
        validate_pakket(path)
        # Lock-status tonen
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            lock_marker = " 🔒" if data.get("locked") else ""
            if lock_marker:
                locked_count += 1
            print(f"  - {data.get('emoji','?')} {data.get('title','?')}{lock_marker}")
        except Exception:
            pass

    if locked_count:
        print(f"\n🔒 {locked_count} pakket(ten) gelockt (mogen niet aangepast worden).")
    print()

    # Ook losse bestanden in games/ die niet in index.json staan
    indexed = set(files)
    for path in sorted(GAMES_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        if path.name not in indexed:
            warn(path.name, "bestand staat niet in index.json — wordt niet geladen")

    if errors:
        print(f"\n=== {len(errors)} FOUT(EN) ===")
        for e in errors:
            print(e)
    if warnings:
        print(f"\n=== {len(warnings)} WAARSCHUWING(EN) ===")
        for w in warnings:
            print(w)
    if not errors and not warnings:
        print("✅ Alles ziet er structureel goed uit.")
    print()

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
