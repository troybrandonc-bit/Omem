"""Semantic recall gets real embeddings, a cache, and richer text. Run:
python3 tests_semantic_embedder.py

Three defects, one module. The retriever embedded ONLY the proposition token,
so "prefers_annual_billing" about Acme and about anyone else were the same
point and a query naming the customer gained nothing. It re-embedded every
assertion in the project on EVERY recall, an irritation for the free hashing
embedding and a per-recall bill for a real one. And set_embedder() existed
with nothing ever wired into it, so "pluggable real embeddings" was a
docstring, not a feature.

Now the text is proposition + label + subject labels, vectors cache per
(assertion, text, embedder) fingerprint, and OMEM_EMBED_MODEL wires an
OpenAI-compatible /embeddings endpoint at boot -- with every failure falling
back to the dependency-free hashing embedding, because narrower recall beats
no recall.
"""
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
TMP = os.environ.get("TEMP") or "/tmp"
DB = os.path.join(TMP, "omem_semantic_embedder.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB

import api  # noqa: E402
import semantic_recall as sr  # noqa: E402
import providers  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


# A project built directly: this suite tests the retriever, not the routes.
P = api.Project("proj_embed_test", "embed test")
api.PROJECTS[P.id] = P
api.CONTRADICTIONS[P.id] = []
api._DECLARED_PAIRS[P.id] = set()
api.apply_op(P, "agent", {"id": "agent:t", "kind": "system"})
api.apply_op(P, "entity", {"id": "customer:acme", "type": "org",
                           "label": "Acme Corporation"})
api.apply_op(P, "entity", {"id": "customer:globex", "type": "org",
                           "label": "Globex"})
api.apply_op(P, "assert", {"id": "a_acme", "agent": "agent:t",
                           "subjects": ["customer:acme"],
                           "proposition": "prefers_annual_billing",
                           "assertion_time": P.tick()})
api.apply_op(P, "assert", {"id": "a_glob", "agent": "agent:t",
                           "subjects": ["customer:globex"],
                           "proposition": "prefers_annual_billing",
                           "assertion_time": P.tick()})

print("== the text is the proposition IN CONTEXT ==")
r = sr.SemanticRetriever(P)
hits = r.retrieve("what does Acme Corporation want about invoicing")
check("a query naming the customer finds the customer's memory",
      "a_acme" in hits, hits)
check("and ranks it above the same token about someone else",
      "a_glob" not in hits or hits["a_acme"] > hits["a_glob"], hits)

print("== identity claims and retraction markers are machinery, not meaning ==")
api.apply_op(P, "corefer", {"id": "cor_1", "entity_a": "customer:acme",
                            "entity_b": "customer:globex", "agent": "agent:t",
                            "assertion_time": P.tick()})
hits2 = sr.SemanticRetriever(P).retrieve("COREF customer acme globex")
check("a coreference assertion never surfaces as a memory",
      "cor_1" not in hits2, hits2)

print("== the cache: embed once, not once per recall ==")
CALLS = {"texts": 0, "batches": 0}


def counting_embedder(texts):
    CALLS["texts"] += len(texts)
    CALLS["batches"] += 1
    return [sr._hash_embed(t) for t in texts]


sr.set_embedder(counting_embedder, tag="fake-1")
sr.SemanticRetriever(P).retrieve("annual billing")
first = CALLS["texts"]
check("the first recall embeds the corpus plus the query", first >= 3, CALLS)
sr.SemanticRetriever(P).retrieve("annual billing again")
check("the second recall embeds ONLY the query: the corpus is cached",
      CALLS["texts"] == first + 1, CALLS)

api.apply_op(P, "assert", {"id": "a_new", "agent": "agent:t",
                           "subjects": ["customer:acme"],
                           "proposition": "wants_quarterly_reviews",
                           "assertion_time": P.tick()})
before = CALLS["texts"]
sr.SemanticRetriever(P).retrieve("reviews")
check("a new assertion embeds exactly itself, plus the query",
      CALLS["texts"] == before + 2, CALLS)

sr.set_embedder(counting_embedder, tag="fake-2")
before = CALLS["texts"]
sr.SemanticRetriever(P).retrieve("annual billing")
check("a different embedder tag re-embeds everything: one model's vectors "
      "are never served as another's", CALLS["texts"] >= before + 4, CALLS)


def broken_embedder(texts):
    raise RuntimeError("provider outage")


sr.set_embedder(broken_embedder, tag="broken")
hits3 = sr.SemanticRetriever(P).retrieve("Acme Corporation invoicing")
check("a broken embedder falls back to the hashing embedding, recall survives",
      "a_acme" in hits3, hits3)
sr.set_embedder(None)

print("== the wire to a real provider ==")
REQUESTS = []


class StubEmbeddings(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        REQUESTS.append(body)
        vecs = [{"index": i, "embedding": [float(len(t)), 1.0, 0.0]}
                for i, t in enumerate(body["input"])]
        out = json.dumps({"data": vecs}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


stub = ThreadingHTTPServer(("127.0.0.1", 0), StubEmbeddings)
threading.Thread(target=stub.serve_forever, daemon=True).start()
time.sleep(0.1)

check("no model configured means no remote embedder",
      not providers.embeddings_configured())
os.environ["OMEM_LLM_API_KEY"] = "sk-test"
os.environ["OMEM_LLM_BASE_URL"] = "http://127.0.0.1:%d" % stub.server_address[1]
os.environ["OMEM_EMBED_MODEL"] = "text-embedding-3-small"
check("a model plus the LLM key configures it", providers.embeddings_configured())

vecs = providers.embed_texts(["alpha", "beta"])
check("the endpoint answers in order", vecs == [[5.0, 1.0, 0.0], [4.0, 1.0, 0.0]],
      vecs)
check("carrying the model the operator named",
      REQUESTS and REQUESTS[0]["model"] == "text-embedding-3-small", REQUESTS[:1])
REQUESTS.clear()
providers.embed_texts([f"t{i}" for i in range(150)])
check("large corpora are chunked, 100 per request",
      len(REQUESTS) == 2 and len(REQUESTS[0]["input"]) == 100
      and len(REQUESTS[1]["input"]) == 50, [len(r["input"]) for r in REQUESTS])
for k in ("OMEM_LLM_API_KEY", "OMEM_LLM_BASE_URL", "OMEM_EMBED_MODEL"):
    os.environ.pop(k, None)
stub.shutdown()

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
