from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).resolve().parents[2] / "static" / "product_catalog.json"


def load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    with CATALOG_PATH.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return payload if isinstance(payload, list) else []


_NORM_RE = re.compile(r"[^a-z0-9]+")


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    return _NORM_RE.sub(" ", text.lower()).strip()


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def match_material(
    material: dict[str, Any],
    catalog: list[dict[str, Any]] | None = None,
    *,
    name_threshold: float = 0.78,
) -> tuple[dict[str, Any] | None, float]:
    """Versucht ein Material gegen den lokalen `product_catalog.json` zu matchen.

    Match-Strategie (deterministisch, kostenlos):
    1) Exakte Catalog-Number-Uebereinstimmung schlaegt alles (score=1.0).
    2) Substring-Match auf normalisiertem Item-Namen oder Aliases (score=0.95).
    3) Fuzzy-Ratio (SequenceMatcher) ueber Item-Namen und Aliases.

    Rueckgabe: (catalog_entry | None, match_score in [0,1]).
    """
    if catalog is None:
        catalog = load_catalog()
    if not catalog:
        return None, 0.0

    needle_cat = (material.get("catalog_number") or "").strip().lower()
    needle_name = _normalize(material.get("item"))

    best: dict[str, Any] | None = None
    best_score = 0.0

    for entry in catalog:
        entry_cat = str(entry.get("catalog_number") or "").strip().lower()
        if needle_cat and entry_cat and needle_cat == entry_cat:
            return entry, 1.0

        candidates: list[str] = []
        if entry.get("item"):
            candidates.append(_normalize(entry["item"]))
        for alias in entry.get("aliases") or []:
            candidates.append(_normalize(alias))

        if not needle_name:
            continue

        for candidate in candidates:
            if not candidate:
                continue
            if candidate in needle_name or needle_name in candidate:
                score = 0.95
            else:
                score = _ratio(candidate, needle_name)
            if score > best_score:
                best_score = score
                best = entry

    if best is not None and best_score >= name_threshold:
        return best, round(best_score, 3)
    return None, round(best_score, 3)


def verify_against_catalog(
    materials: list[dict[str, Any]],
    catalog: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Markiert Materials als `verified` wenn ein lokaler Catalog-Eintrag passt.

    - Setzt `verification = 'verified'`
    - Setzt `verified_via = 'local_catalog'`
    - Setzt `match_score`
    - Befuellt `source_url`, `storage`, `supplier`, `catalog_number`, falls leer.

    Rueckgabe: (gepatchte Materials, Summary mit Counts fuer das UI).
    """
    if catalog is None:
        catalog = load_catalog()

    patched: list[dict[str, Any]] = []
    matched_count = 0

    for raw in materials:
        if not isinstance(raw, dict):
            patched.append(raw)
            continue
        item = dict(raw)
        entry, score = match_material(item, catalog)
        if entry is not None:
            matched_count += 1
            item["verification"] = "verified"
            item["verified_via"] = "local_catalog"
            item["match_score"] = score
            if not item.get("source_url"):
                item["source_url"] = entry.get("source_url")
            if not item.get("storage"):
                item["storage"] = entry.get("storage")
            if not item.get("catalog_number"):
                item["catalog_number"] = entry.get("catalog_number") or ""
            if not item.get("supplier"):
                item["supplier"] = entry.get("supplier") or ""
        else:
            # Wenn weder lokaler Catalog-Match noch eine bestaetigende URL
            # vorliegt, ist die LLM-Aussage 'verified' nicht belastbar -> auf
            # 'suggested_verify' herunterstufen. Tavily-Verify im naechsten
            # Schritt kann dann gezielt versuchen, die fehlende source_url zu
            # ergaenzen und den Status wieder auf 'verified' anzuheben.
            if not item.get("source_url"):
                item["verification"] = "suggested_verify"
        patched.append(item)

    summary = {
        "catalog_size": len(catalog),
        "materials_total": len(patched),
        "matched_local_catalog": matched_count,
        "match_rate": round(matched_count / len(patched), 3) if patched else 0.0,
    }
    return patched, summary
