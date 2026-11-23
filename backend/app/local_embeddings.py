"""Encode passage vectors using the installed local MiniLM runtime."""

import json
import logging
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
logger = logging.getLogger(__name__)
ENCODE = r"""
import json, re, sys
from collections import Counter
from sentence_transformers import SentenceTransformer
model = SentenceTransformer(sys.argv[1], device="cpu", local_files_only=True)
texts = json.load(sys.stdin)
# Offset windows preserve original spelling and cover text beyond the encoder limit.
tokenizer = model.tokenizer
limit = model.max_seq_length
offsets = tokenizer(texts, truncation=True, max_length=limit, stride=32,
                    return_overflowing_tokens=True, return_offsets_mapping=True)
windows, parents = [], []
for parent, spans in zip(offsets["overflow_to_sample_mapping"], offsets["offset_mapping"]):
    spans = [(start, end) for start, end in spans if end > start]
    if spans:
        windows.append(texts[parent][spans[0][0]:spans[-1][1]])
        parents.append(parent)
counts = Counter(parents)
for parent, count in counts.items():
    if count <= 1:
        continue
    sentences = dict.fromkeys(re.split(r"(?<=[.!?])\s+", texts[parent]))
    for sentence in sentences:
        if sentence and len(tokenizer.encode(sentence)) <= limit:
            windows.append(sentence)
            parents.append(parent)
groups = [[] for _ in texts]
if windows:
    vectors = model.encode(windows, normalize_embeddings=True, show_progress_bar=False)
    for parent, vector in zip(parents, vectors):
        groups[parent].append(vector.tolist())
print(json.dumps(groups))
"""


def embed(texts):
    if not texts:
        return []
    interpreter = Path(os.environ.get(
        "THESIS_EMBEDDING_PYTHON", ROOT / "work/local-model-eval-venv/bin/python"
    ))
    model = os.environ.get("THESIS_EMBEDDING_MODEL", MODEL)
    encoded = json.dumps(texts, ensure_ascii=False)
    try:
        result = subprocess.run(
            [str(interpreter), "-c", ENCODE, model],
            input=encoded, text=True, capture_output=True, check=True, timeout=180,
            env=dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1"),
        )
        vectors = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        logger.warning("Local embeddings unavailable (%s); using keyword retrieval.", type(exc).__name__)
        return None
    return vectors
