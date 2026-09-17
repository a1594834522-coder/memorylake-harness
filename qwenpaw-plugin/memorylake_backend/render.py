# -*- coding: utf-8 -*-
"""Rendering search results for the model.

Every rule here was added after an observed failure in an earlier harness and
is a cross-harness contract — a user moving between clients reads the same
shape of answer:

1. Facts first; documents after.
2. Document summaries and matched spans are clipped, at most three spans per
   document.
3. An empty result carries a hint, never a bare empty list.
4. Relevance scores order the list and are NEVER shown. They are weakly
   calibrated and a model shown a number treats it as authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

EMPTY_RESULT_HINT = (
    "No stored memory matched. Retry ONCE with different wording — entity "
    "names, synonyms, statement-style keywords. If still nothing: say you have "
    "no record of it and offer to remember it. Memory only holds what was "
    "stored, so never claim the user did not mention or tell you something "
    "(e.g. not \"you never told me\" / \"你之前没跟我提过\"); do not invent an answer."
)

FACT_CLIP = 300
SUMMARY_CLIP = 120
SPAN_CLIP = 400
SPANS_PER_DOCUMENT = 3


@dataclass(frozen=True)
class SearchFact:
    id: str
    fact: str
    score: float | None = None


@dataclass(frozen=True)
class SearchDocument:
    id: str
    name: str
    summary: str = ""
    spans: tuple[str, ...] = ()


@dataclass(frozen=True)
class SearchRendering:
    facts: tuple[SearchFact, ...] = ()
    documents: tuple[SearchDocument, ...] = ()
    notice: str = ""

    @property
    def empty(self) -> bool:
        return not self.facts and not self.documents


def clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _str(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def normalize_search_payload(payload: Any) -> SearchRendering:
    """Normalize the CLI's JSON into the renderer's shape, tolerantly: a
    drifted payload degrades to fewer results, never to an exception."""
    root = payload if isinstance(payload, dict) else {}
    raw_facts = root.get("facts") if isinstance(root.get("facts"), list) else []
    raw_docs = root.get("documents") if isinstance(root.get("documents"), list) else []

    facts = [
        SearchFact(
            id=_str(item, "id") or "?",
            fact=_str(item, "fact"),
            score=item["score"] if isinstance(item.get("score"), (int, float)) else None,
        )
        for item in raw_facts
        if isinstance(item, dict)
    ]
    facts = [f for f in facts if f.fact]
    facts.sort(key=lambda f: f.score if f.score is not None else 0.0, reverse=True)

    documents = []
    for item in raw_docs:
        if not isinstance(item, dict):
            continue
        items = item.get("items") if isinstance(item.get("items"), list) else []
        spans = tuple(
            _str(span, "text") for span in items if isinstance(span, dict) and _str(span, "text")
        )
        documents.append(
            SearchDocument(
                id=_str(item, "document_id") or "?",
                name=_str(item, "document_name", "file_name") or "?",
                summary=_str(item, "document_summary"),
                spans=spans,
            ),
        )
    return SearchRendering(facts=tuple(facts), documents=tuple(documents))


def render_search_result(value: SearchRendering) -> str:
    """Render the text the model reads."""
    parts: list[str] = []
    if value.notice:
        parts.append(value.notice)

    if value.empty:
        if not parts:
            parts.append(EMPTY_RESULT_HINT)
        return "\n\n".join(parts)

    if value.facts:
        lines = "\n".join(
            f"  - {clip(fact.fact, FACT_CLIP)}  [{fact.id}]" for fact in value.facts
        )
        parts.append(
            f"FACTS ({len(value.facts)}, most relevant first)\n{lines}\n\n"
            "  Judge each fact against the question by its content — the list may "
            "include unrelated matches, and a memory written in another project may "
            "not apply here.",
        )

    if value.documents:
        lines = []
        for document in value.documents:
            summary = f" — {clip(document.summary, SUMMARY_CLIP)}" if document.summary else ""
            spans = "".join(
                f'\n      "{clip(span, SPAN_CLIP)}"'
                for span in document.spans[:SPANS_PER_DOCUMENT]
            )
            lines.append(f"  {document.name}{summary}  [{document.id}]{spans}")
        parts.append(f"FILES ({len(value.documents)})\n" + "\n".join(lines))

    return "\n\n".join(parts)
