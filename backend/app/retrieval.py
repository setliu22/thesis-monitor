"""Search all filing chunks for thesis terms before applying the model input budget."""

from collections import Counter
import math
import re
from bs4 import BeautifulSoup

BREAK = "\n\n---\n\n"
LIMIT = 8000
VERSION = "thesis-lexical-v2"
STOP = set(
    "a an the and or to of in on for from with by as at is are was were be been being this that these those it its we our their they i my own stock because company business would could should can will may might have has had do does did not than then into about through also more most such which what when how if some any all each other over under up out us you your thesis believe expect expects investment".split()
)


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {
        w[:-1] if len(w) > 5 and w.endswith("s") else w
        for w in words
        if len(w) > 2 and w not in STOP
    }


def select_evidence(html, thesis):
    soup = BeautifulSoup(html, "html.parser")
    for el in soup(["script", "style", "noscript", "ix:hidden", "ix:header"]):
        el.decompose()
    text = clean(soup.get_text(" ", strip=True))
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + 1400, len(text))
        if end < len(text):
            boundary = text.rfind(". ", start + 800, end)
            if boundary < 0:
                boundary = text.rfind(" ", start + 800, end)
            if boundary > start:
                end = boundary + 1
        chunks.append(
            {
                "id": f"chunk-{len(chunks) + 1}",
                "start": start,
                "end": end,
                "text": text[start:end],
            }
        )
        if end >= len(text):
            break
        start = max(start + 1, end - 160)
        boundary = text.find(" ", start, min(start + 50, end))
        if boundary >= 0:
            start = boundary + 1
    query = tokens(thesis)
    vocab = [tokens(c["text"]) for c in chunks]
    frequency = Counter(t for terms in vocab for t in terms)
    weights = {t: math.log(1 + (len(chunks) + 1) / (frequency[t] + 1)) for t in query}
    selected = []
    covered = set()
    used = 0
    remaining = list(range(len(chunks)))
    clauses = [tokens(c) for c in re.split(r"(?<=[.!?;])\s+|\n+", thesis) if tokens(c)]
    # Give distinct thesis claims a turn before filling the remaining budget.
    targets = clauses + [query] * len(chunks)
    for target_index, target in enumerate(targets):
        if not remaining:
            break

        def score(i):
            overlap = target & vocab[i]
            return sum(weights[t] * (0.5 if t in covered else 1) for t in overlap)

        if (
            min(
                len(chunks[i]["text"]) + (len(BREAK) if selected else 0)
                for i in remaining
            )
            > LIMIT - used
        ):
            break
        added = False
        ranked = sorted(remaining, key=lambda i: (score(i), -i), reverse=True)
        for best in ranked:
            candidate = chunks[best]
            if score(best) <= 0:
                break
            if any(
                max(
                    0,
                    min(candidate["end"], c["end"])
                    - max(candidate["start"], c["start"]),
                )
                > 0.35 * len(candidate["text"])
                for c in selected
            ):
                continue
            cost = len(candidate["text"]) + (len(BREAK) if selected else 0)
            if used + cost > LIMIT:
                continue
            selected.append(candidate)
            used += cost
            covered.update(query & vocab[best])
            remaining.remove(best)
            added = True
            break
        if not added and target_index >= len(clauses):
            break
    if not selected and chunks:
        selected = [chunks[0]]
    # Rank order keeps high-relevance passages within the actual model budget.
    return {
        "text": BREAK.join(c["text"] for c in selected),
        "chunks": selected,
        "version": VERSION,
        "document_characters": len(text),
        "total_chunks": len(chunks),
        "selected_characters": sum(len(c["text"]) for c in selected),
        "matched_thesis_terms": sorted(covered),
        "coverage": "Selected passages, not a full-document semantic review.",
    }
