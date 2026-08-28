"""Semantic candidate retrieval for OMEM recall.

The base retriever finds candidates by exact entity/token overlap, which misses
memories phrased differently from the query ("prefers annual billing" vs "wants
yearly invoicing"). This module adds a SEMANTIC candidate source: it surfaces
memories whose *meaning* is close to the context, even without shared tokens.

Two design constraints shape this:

1. STDLIB-ONLY BY DEFAULT. The SDK/install story is "zero dependencies, instant
   install". So the default embedding is a deterministic, dependency-free
   character n-gram hashing vector (a lightweight semantic signal that catches
   morphological variants and paraphrase overlap far better than exact tokens).
   It is not a neural embedding: but it needs no model, no network, no GPU, and
   is fully reproducible.

2. PLUGGABLE REAL EMBEDDINGS. If a real embedding function is provided (OpenAI,
   a local model, etc.) via set_embedder(), the retriever uses it instead. The
   ranking/decision layer is untouched either way: this only FINDS candidates;
   the deterministic ranker still decides, and the frozen engine still validates.

The retriever never changes belief state or ranking authority, it only widens
the candidate set, tagged with the "semantic" source and a similarity score used
as a soft signal, never as ground truth.
"""
from __future__ import annotations
import hashlib
import math
import re

from omem_engine.canon import RETRACTED

_DIM = 256  # hashed-embedding dimensionality (small, fast, dependency-free)
_TOKEN = re.compile(r"[a-z0-9]+")

# Optional real embedder: fn(list[str]) -> list[list[float]]. When set, used
# instead of the hashing embedding. Kept module-level so a deployment can wire a
# provider once at boot without touching call sites.
_EMBEDDER = None
_EMBED_TAG = "hash-v1"   # names the active embedder; cached vectors key on it
_GEN = 0

# Per-project vector cache: {project_id: {assertion_id: (fingerprint, vec)}}.
# Assertions are immutable and never deleted, so an entry goes stale only when
# its rendered TEXT changes (a label edit) or the embedder changes -- both of
# which change the fingerprint. Before this cache existed, every recall
# re-embedded every assertion in the project, which was an irritation for the
# free hashing embedding and a per-recall bill for a real one.
_VECS: dict = {}


def set_embedder(fn, tag: str | None = None):
    """Install a real embedding function fn(list[str]) -> list[list[float]].
    Pass None to revert to the built-in dependency-free hashing embedding.
    `tag` names the embedder (use the model id): cached vectors key on it, so
    swapping embedders can never serve one model's vectors as another's."""
    global _EMBEDDER, _EMBED_TAG, _GEN
    _GEN += 1
    _EMBEDDER = fn
    _EMBED_TAG = tag or (f"custom-{_GEN}" if fn is not None else "hash-v1")


def _char_ngrams(text: str, n: int = 3):
    text = text.lower().replace("_", " ")
    toks = _TOKEN.findall(text)
    grams = []
    for tok in toks:
        grams.append(tok)  # whole token
        padded = f"^{tok}$"
        for i in range(len(padded) - n + 1):
            grams.append(padded[i:i + n])  # char n-grams catch morphology/typos
    return grams


def _hash_embed(text: str) -> list[float]:
    """Deterministic hashing embedding: char n-grams -> signed hashed dims -> L2
    normalised vector. No model, no deps. Similar surface forms land near each
    other, so paraphrase/morphological overlap produces nonzero cosine."""
    vec = [0.0] * _DIM
    for gram in _char_ngrams(text):
        h = int(hashlib.md5(gram.encode()).hexdigest(), 16)
        idx = h % _DIM
        sign = 1.0 if (h >> 8) & 1 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def embed(texts: list[str]) -> list[list[float]]:
    if _EMBEDDER is not None:
        try:
            out = _EMBEDDER(texts)
            if out and len(out) == len(texts):
                return out
        except Exception:
            pass  # any provider failure -> fall back to the built-in embedding
    return [_hash_embed(t) for t in texts]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    # vectors are already normalised in the hashing path; normalise defensively
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class SemanticRetriever:
    """Finds memories whose proposition is semantically close to the query
    context. Returns {assertion_id: similarity} above a threshold, capped."""

    def __init__(self, p, min_similarity: float = 0.18, cap: int = 50):
        self.p = p
        self.min_similarity = min_similarity
        self.cap = cap

    def _text_of(self, a) -> str:
        """What gets embedded: the proposition IN ITS CONTEXT. Embedding only
        the bare token meant "prefers_annual_billing" about Acme and the same
        token about anyone else were identical points, and a query naming the
        customer gained nothing. The human label and the subjects' labels are
        part of the meaning, so they are part of the vector."""
        meta = self.p.labels.get(a.id)
        label = meta.get("label") if isinstance(meta, dict) else None
        subj = []
        for s in a.subjects:
            m = self.p.labels.get(s)
            subj.append((m.get("label") if isinstance(m, dict) else None)
                        or s.split(":", 1)[-1].replace("_", " ").replace("-", " "))
        parts = [(a.proposition or "").replace("_", " "), label or "",
                 " ".join(subj)]
        return " ".join(x for x in parts if x).strip()

    def retrieve(self, context_text: str, *, exclude: set[str] | None = None) -> dict[str, float]:
        context_text = (context_text or "").strip()
        if not context_text:
            return {}
        # Machinery is not meaning: coreference claims and retraction markers
        # would only surface as noise now that subject labels are embedded.
        assertions = [a for a in self.p.engine.store.assertions()
                      if a.proposition and a.proposition != RETRACTED
                      and not a.proposition.startswith("COREF(")]
        if not assertions:
            return {}
        cache = _VECS.setdefault(self.p.id, {})
        keyed = []
        for a in assertions:
            text = self._text_of(a)
            fp = hashlib.md5(f"{_EMBED_TAG}|{text}".encode()).hexdigest()[:16]
            keyed.append((a, text, fp))
        missing = [(i, text) for i, (a, text, fp) in enumerate(keyed)
                   if cache.get(a.id, (None, None))[0] != fp]
        if missing:
            vecs = embed([t for _, t in missing])
            for (i, _), v in zip(missing, vecs):
                a, _, fp = keyed[i]
                cache[a.id] = (fp, v)
        qv = embed([context_text])[0]
        scored = []
        exclude = exclude or set()
        for a, _, _fp in keyed:
            if a.id in exclude:
                continue
            sim = _cosine(qv, cache[a.id][1])
            if sim >= self.min_similarity:
                scored.append((a.id, sim, -a.assertion_time))
        # highest similarity first; ties broken deterministically (newer, then id)
        scored.sort(key=lambda t: (-t[1], t[2], t[0]))
        return {aid: round(sim, 4) for aid, sim, _ in scored[:self.cap]}
