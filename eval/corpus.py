"""Exécution du corpus de déclarations, partagée entre la CI et le rapport.

Aucun appel au modèle : cette couche transforme du langage libre en faits
structurés avec des règles déterministes, elle est donc mesurable hors ligne.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = Path(__file__).resolve().parent / "incident_cases.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import merge_incident_statement  # noqa: E402
from eu261 import classify_cause  # noqa: E402

# Champs remis à zéro avant chaque cas : le parseur écrit par effet de bord.
BLANK_RECORD: dict[str, Any] = {
    "disruption_type": None,
    "delay_minutes": None,
    "arrival_delay_minutes": None,
    "departure_delay_minutes": None,
    "trip_completed": None,
    "disruption_cause": None,
    "evidence": [],
}


def load_cases() -> list[dict[str, Any]]:
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    """Exécute un cas et retourne ses écarts, sans jamais lever."""
    record = dict(BLANK_RECORD)
    record["evidence"] = []
    merge_incident_statement(record, case["statement"])

    mismatches = []
    for field, expected in (case.get("expect") or {}).items():
        actual = record.get(field)
        if actual != expected:
            mismatches.append(f"{field}: attendu {expected!r}, obtenu {actual!r}")

    expected_risk = case.get("expect_cause_risk")
    if expected_risk is not None:
        actual_risk = classify_cause(record.get("disruption_cause"))
        if actual_risk != expected_risk:
            mismatches.append(
                f"cause_risk: attendu {expected_risk!r}, obtenu {actual_risk!r}"
            )

    return {
        "id": case["id"],
        "status": case.get("status", "supported"),
        "statement": case["statement"],
        "passed": not mismatches,
        "mismatches": mismatches,
        "why": case.get("why", ""),
    }


def run_all() -> list[dict[str, Any]]:
    return [run_case(case) for case in load_cases()]


def main() -> int:
    results = run_all()
    supported = [r for r in results if r["status"] == "supported"]
    gaps = [r for r in results if r["status"] == "known_gap"]

    print(f"Corpus de déclarations — {len(results)} cas\n")
    ok = sum(1 for r in supported if r["passed"])
    print(f"  Attendus     : {ok}/{len(supported)} passent")
    promoted = [r for r in gaps if r["passed"]]
    print(f"  Trous connus : {len(gaps)} documentés, {len(promoted)} désormais résolus")

    failures = [r for r in supported if not r["passed"]]
    if failures:
        print("\nÉCHECS sur des cas attendus :")
        for r in failures:
            print(f"  ✕ {r['id']}")
            print(f"      « {r['statement']} »")
            for m in r["mismatches"]:
                print(f"      {m}")

    if promoted:
        print("\nTrous connus qui passent maintenant — à promouvoir en supported :")
        for r in promoted:
            print(f"  → {r['id']}")

    if gaps and not promoted:
        print("\nTrous assumés, documentés dans le corpus :")
        for r in gaps:
            print(f"  · {r['id']} — {r['why'].split(':', 1)[-1].strip()[:80]}")

    return 1 if failures or promoted else 0


if __name__ == "__main__":
    raise SystemExit(main())
