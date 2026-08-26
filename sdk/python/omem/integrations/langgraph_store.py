"""OMEM as a LangGraph `BaseStore`, so LangChain agents get belief-tracked memory.

    pip install omem-infrastructure langgraph

    from omem import Memory
    from omem.integrations.langgraph_store import OmemStore

    store = OmemStore(Memory(api_key="omem_sk_...", project="proj_..."))
    store.put(("memories", "alice"), "pref", {"text": "prefers annual billing"})
    store.get(("memories", "alice"), "pref").value
    # -> {"text": "prefers annual billing"}

Why bother, when InMemoryStore and the Postgres store already exist: those
overwrite. `put` on an existing key destroys what was there and `delete`
destroys it entirely. That is correct for a key-value store and wrong for
memory, because the question an agent needs answered later is usually "what did
I believe, when, and what changed it".

Through this adapter:

  * `put` over an existing key SUPERSEDES rather than overwrites. The previous
    value stays on the record, with the moment it stopped being believed.
  * `delete` RETRACTS. The key stops resolving; the history of what it held
    survives.
  * every write is attributed to an agent and carries provenance, so
    `mem.why(assertion_id)` answers where a memory came from.

The trade is a network round trip per operation against a real server, where
InMemoryStore is a dict. Use this where the audit trail is worth more than the
microseconds.

STORAGE MODEL. LangGraph addresses items by (namespace tuple, key). OMEM stores
claims about subjects. The mapping is one subject entity per item:

    ("memories", "alice"), "pref"  ->  subject  lg:memories/alice/pref
                                       claim    stored_value
                                       label    the JSON envelope

The value round-trips through `label`, which is the field OMEM already treats as
an item's content. `created_at` and `updated_at` ride in the envelope because
OMEM's assertion_time is a logical clock, not a wall clock, and BaseStore's
`Item` requires real datetimes.

NOT IMPLEMENTED YET: vector `index` on put, `ttl`, and `search(query=...)`.
The first two are accepted and ignored. The third RAISES rather than quietly
returning unranked results, because a semantic search that is secretly a
substring match is exactly the kind of thing you find out about in production.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Tuple

try:
    from langgraph.store.base import (
        BaseStore, GetOp, Item, ListNamespacesOp, PutOp, SearchItem, SearchOp,
    )
except ImportError as e:  # pragma: no cover - depends on the caller's env
    raise ImportError(
        "OmemStore needs langgraph. Install it with: pip install langgraph"
    ) from e

CLAIM = "stored_value"
DEFAULT_PREFIX = "lg"
DEFAULT_AGENT = "agent:langgraph"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(s: Optional[str]) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return datetime.now(timezone.utc)


class OmemStore(BaseStore):
    """A LangGraph store backed by OMEM.

    Only `batch` and `abatch` are abstract on BaseStore. get, put, search,
    delete and list_namespaces are implemented on the base class in terms of
    them, so implementing the two gets the whole surface.
    """

    def __init__(self, memory, *, agent: str = DEFAULT_AGENT,
                 prefix: str = DEFAULT_PREFIX) -> None:
        self.mem = memory
        self.agent = agent if agent.startswith("agent:") else "agent:" + agent
        self.prefix = prefix
        self._agent_ready = False

    # ---- addressing ----
    def _subject(self, namespace: Tuple[str, ...], key: str) -> str:
        return self.prefix + ":" + "/".join(namespace) + "/" + key

    def _ns_prefix(self, namespace_prefix: Tuple[str, ...]) -> str:
        joined = "/".join(namespace_prefix)
        return self.prefix + ":" + joined + "/" if joined else self.prefix + ":"

    @staticmethod
    def _split(subject: str) -> Optional[Tuple[Tuple[str, ...], str]]:
        """subject -> (namespace, key), or None if it is not one of ours."""
        if ":" not in subject:
            return None
        _, rest = subject.split(":", 1)
        parts = rest.split("/")
        if len(parts) < 2:
            return None
        return tuple(parts[:-1]), parts[-1]

    # ---- OMEM plumbing ----
    def _ensure_agent(self) -> None:
        if self._agent_ready:
            return
        try:
            self.mem._req("POST", "/v1/agents", {"id": self.agent, "kind": "ai"})
        except Exception:
            pass  # already recorded
        self._agent_ready = True

    def _live(self, subject: str) -> Optional[dict]:
        """The currently believed stored_value assertion for this subject."""
        rows = self.mem._req(
            "GET", "/v1/assertions?subject=" + subject + "&open=true").get("data", [])
        for a in rows:
            if a.get("proposition") == CLAIM:
                return a
        return None

    def _rows_under(self, ns_prefix: str) -> list:
        rows = self.mem._req("GET", "/v1/assertions?open=true").get("data", [])
        out = []
        for a in rows:
            if a.get("proposition") != CLAIM:
                continue
            for s in a.get("subjects", []):
                if s.startswith(ns_prefix):
                    out.append(a)
                    break
        return out

    @staticmethod
    def _envelope(a: dict) -> dict:
        try:
            return json.loads(a.get("label") or "{}")
        except (TypeError, ValueError):
            return {}

    def _to_item(self, a: dict, subject: str) -> Optional[Item]:
        split = self._split(subject)
        if split is None:
            return None
        ns, key = split
        env = self._envelope(a)
        return Item(value=env.get("value", {}), key=key, namespace=ns,
                    created_at=_parse_dt(env.get("created_at")),
                    updated_at=_parse_dt(env.get("updated_at")))

    # ---- the two abstract methods ----
    def batch(self, ops: Iterable[Any]) -> list:
        return [self._one(op) for op in ops]

    async def abatch(self, ops: Iterable[Any]) -> list:
        # The SDK speaks blocking HTTP. to_thread keeps the event loop free
        # instead of pretending this is natively async.
        return await asyncio.to_thread(self.batch, list(ops))

    # ---- one operation ----
    def _one(self, op: Any) -> Any:
        if isinstance(op, GetOp):
            subject = self._subject(op.namespace, op.key)
            a = self._live(subject)
            return self._to_item(a, subject) if a else None

        if isinstance(op, PutOp):
            return self._put(op)

        if isinstance(op, SearchOp):
            return self._search(op)

        if isinstance(op, ListNamespacesOp):
            return self._list_namespaces(op)

        raise NotImplementedError("unsupported op " + type(op).__name__)

    def _put(self, op) -> None:
        subject = self._subject(op.namespace, op.key)
        if op.value is None:
            # BaseStore expresses delete as a put with value None.
            a = self._live(subject)
            if a:
                # The agent is required: a retraction is an attributed write, so
                # that taking a belief off the record reads as this store doing
                # it rather than as nobody in particular.
                self._ensure_agent()
                self.mem._req("POST", "/v1/assertions/" + a["id"] + "/retract",
                              {"agent": self.agent})
            return None

        self._ensure_agent()
        existing = self._live(subject)
        created = (self._envelope(existing).get("created_at") if existing else None)
        label = json.dumps({"value": op.value,
                            "created_at": created or _now_iso(),
                            "updated_at": _now_iso()})
        if existing:
            # Supersede rather than overwrite, so the previous value stays on
            # the record with the moment it stopped being believed. This is the
            # entire reason to use OMEM here instead of a dict.
            self.mem._req(
                "POST", "/v1/assertions/" + existing["id"] + "/supersede",
                {"new": {"agent": self.agent, "subjects": [subject],
                         "proposition": CLAIM, "label": label}})
        else:
            try:
                self.mem._req("POST", "/v1/entities",
                              {"id": subject, "type": "memory"})
            except Exception:
                pass  # already recorded
            self.mem._req("POST", "/v1/assertions",
                          {"agent": self.agent, "subjects": [subject],
                           "proposition": CLAIM, "label": label})
        return None

    def _search(self, op) -> list:
        if op.query:
            raise NotImplementedError(
                "OmemStore has no vector search yet. Namespace filtering and "
                "`filter` work. A `query` would have to return something, and "
                "an unranked substring match dressed as semantic search is "
                "worse than refusing.")
        items = []
        for a in self._rows_under(self._ns_prefix(op.namespace_prefix)):
            for s in a.get("subjects", []):
                it = self._to_item(a, s)
                if it is None:
                    continue
                if op.filter and not all(
                        it.value.get(k) == v for k, v in op.filter.items()):
                    continue
                items.append(SearchItem(
                    namespace=it.namespace, key=it.key, value=it.value,
                    created_at=it.created_at, updated_at=it.updated_at))
        return items[op.offset:op.offset + op.limit]

    def _list_namespaces(self, op) -> list:
        seen = set()
        for a in self._rows_under(self.prefix + ":"):
            for s in a.get("subjects", []):
                split = self._split(s)
                if split is None:
                    continue
                ns = split[0]
                if op.max_depth is not None:
                    ns = ns[:op.max_depth]
                seen.add(ns)
        out = sorted(seen)
        return out[op.offset:op.offset + op.limit]
