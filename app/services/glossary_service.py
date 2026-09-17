"""Character/terminology normalization shared by writers, TTS and QA."""
from __future__ import annotations

import re
from typing import Any


class GlossaryService:
    @staticmethod
    def merge_proposals(glossary: list[dict[str, Any]], proposals: Any) -> None:
        existing = {str(item.get("canonical_name", "")).casefold(): item for item in glossary}
        for raw in proposals if isinstance(proposals, list) else []:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("canonical_name", "")).strip()
            if not name or name.casefold() in existing:
                continue
            term = {
                "term_id": str(raw.get("term_id") or f"TERM-{len(glossary)+1:04d}"),
                "canonical_name": name,
                "aliases": [str(value).strip() for value in raw.get("aliases", []) if str(value).strip()],
                "type": str(raw.get("type", "concept")), "role": str(raw.get("role", "")),
                "tts_pronunciation_override": raw.get("tts_pronunciation_override"),
                "first_appearance_cue": int(raw.get("first_appearance_cue", 0) or 0),
                "notes": str(raw.get("notes", "")), "status": "pending",
            }
            glossary.append(term)
            existing[name.casefold()] = term

    @staticmethod
    def canonicalize(text: str, glossary: list[dict[str, Any]]) -> str:
        output = str(text or "")
        for term in glossary:
            if str(term.get("status", "pending")) != "approved":
                continue
            canonical = str(term.get("canonical_name") or "").strip()
            for alias in sorted((str(value).strip() for value in term.get("aliases", [])), key=len, reverse=True):
                if alias and canonical and alias.casefold() != canonical.casefold():
                    output = re.sub(rf"(?<!\w){re.escape(alias)}(?!\w)", canonical, output, flags=re.I)
        return " ".join(output.split()).strip()

    @staticmethod
    def apply_pronunciation(plan: list[dict[str, Any]], glossary: list[dict[str, Any]]) -> None:
        replacements = [(str(term.get("canonical_name") or "").strip(),
                         str(term.get("tts_pronunciation_override") or "").strip())
                        for term in glossary if str(term.get("status", "pending")) == "approved"]
        for row in plan:
            spoken = str(row.get("text", ""))
            for source, target in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
                if source and target:
                    spoken = re.sub(re.escape(source), target, spoken, flags=re.I)
            row["tts_text"] = spoken
