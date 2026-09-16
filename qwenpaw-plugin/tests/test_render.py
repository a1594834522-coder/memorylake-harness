# -*- coding: utf-8 -*-
import re

from memorylake_backend.render import (
    EMPTY_RESULT_HINT,
    FACT_CLIP,
    SPAN_CLIP,
    SUMMARY_CLIP,
    normalize_search_payload,
    render_search_result,
)


def test_empty_payload_renders_hint() -> None:
    assert render_search_result(normalize_search_payload({})) == EMPTY_RESULT_HINT
    assert render_search_result(normalize_search_payload(None)) == EMPTY_RESULT_HINT
    assert render_search_result(normalize_search_payload({"facts": "nope"})) == EMPTY_RESULT_HINT


def test_scores_order_but_never_render() -> None:
    payload = {"facts": [
        {"id": "low", "fact": "low score", "score": 0.11},
        {"id": "high", "fact": "high score", "score": 0.97},
        {"id": "none", "fact": "no score"},
    ]}
    text = render_search_result(normalize_search_payload(payload))
    assert text.index("[high]") < text.index("[low]") < text.index("[none]")
    assert "0.97" not in text and "0.11" not in text and "score" not in text.lower().replace("high score", "").replace("low score", "").replace("no score", "")
    assert text.startswith("FACTS (3, most relevant first)")
    assert "judge each fact" in text.lower()


def test_facts_without_text_are_dropped() -> None:
    rendering = normalize_search_payload({"facts": [{"id": "x"}, {"id": "y", "fact": "kept"}, "junk"]})
    assert [f.id for f in rendering.facts] == ["y"]


def test_clipping_rules() -> None:
    payload = {
        "facts": [{"id": "f", "fact": "a" * (FACT_CLIP + 50)}],
        "documents": [{
            "document_id": "d1", "document_name": "notes.md",
            "document_summary": "s" * (SUMMARY_CLIP + 10),
            "items": [{"text": "t" * (SPAN_CLIP + 10)}, {"text": "2"}, {"text": "3"}, {"text": "4"}],
        }],
    }
    text = render_search_result(normalize_search_payload(payload))
    assert "a" * FACT_CLIP + "…" in text and "a" * (FACT_CLIP + 1) not in text
    assert "s" * SUMMARY_CLIP + "…" in text
    assert "t" * SPAN_CLIP + "…" in text
    assert '"4"' not in text and '"3"' in text
    assert "FILES (1)" in text and "[d1]" in text
    assert text.index("FACTS") < text.index("FILES")


def test_document_name_fallbacks() -> None:
    rendering = normalize_search_payload({"documents": [{"file_name": "f.txt"}, {}]})
    assert [d.name for d in rendering.documents] == ["f.txt", "?"]
    assert [d.id for d in rendering.documents] == ["?", "?"]


def test_notice_precedes_results_and_replaces_hint_when_empty() -> None:
    from memorylake_backend.render import SearchRendering
    assert render_search_result(SearchRendering(notice="degraded")) == "degraded"
    text = render_search_result(SearchRendering(notice="degraded", facts=(normalize_search_payload({"facts": [{"id": "1", "fact": "x"}]}).facts)))
    assert re.match(r"^degraded\n\nFACTS", text)
