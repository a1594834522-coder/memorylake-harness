# -*- coding: utf-8 -*-
"""The query automatic recall runs with.

QwenPaw hands the backend the user's latest message verbatim (capped by the
platform). Most messages are fine as they are; the ones below are not worth
a round trip, or would return noise that the model then has to dismiss:

- slash commands and bare acknowledgements ("ok", "好的", "thanks")
- messages too short to carry a searchable statement
- messages that are all punctuation, emoji, or whitespace

Nothing here rewrites the user's words: the model is told (protocol) that
automatic recall used the message verbatim and when to search again with a
better query. Rewriting without a model would only make that promise false.
"""

from __future__ import annotations

import re
import unicodedata

MIN_QUERY_CHARS = 4
MAX_QUERY_CHARS = 300

_WHITESPACE = re.compile(r"\s+")
# Frequent one-word replies that are never worth a search, both scripts.
_FILLERS = frozenset({
    "ok", "okay", "yes", "no", "sure", "thanks", "thank you", "thx", "good", "great", "fine", "done", "go",
    "continue", "next", "yep", "nope", "cool", "nice", "hi", "hello", "hey",
    "好", "好的", "行", "可以", "嗯", "嗯嗯", "对", "是", "是的", "不", "不是", "谢谢", "多谢", "继续", "下一个",
    "收到", "了解", "明白", "知道了", "没问题", "不用", "不用了", "你好", "在吗",
})


def recall_query(text: str) -> str:
    """Return the query automatic recall should run, or ``""`` to skip it."""
    query = _WHITESPACE.sub(" ", (text or "")).strip()
    if not query or query.startswith("/"):
        return ""
    lowered = query.lower().rstrip("。！？!?.,，、~～ ")
    if lowered in _FILLERS:
        return ""
    letters = [ch for ch in query if unicodedata.category(ch)[0] in ("L", "N")]
    if len(letters) < MIN_QUERY_CHARS:
        return ""
    return query[:MAX_QUERY_CHARS]
