"""The LangGraph adapter refuses what it cannot honestly record.

Run: python3 tests_langgraph_testimony.py

The adapter exists because LangGraph's resume boundary carries no identity: any
code holding the thread can answer an interrupt, and nothing on Command records
who did. An adapter that quietly filled that in would be worse than no adapter,
because the record would then assert something nobody checked.

So the interesting tests here are not the happy path. They are the four
refusals: an unclassified action, an identity the model could have written, an
agent approving itself, and a record written while an action is still pending.
Each one is a way to produce a plausible file that lies, and each raises.

The happy path is still checked, end to end, through the real validator, because
a record that refuses everything and validates as nothing is not useful either.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
ADAPTER = os.path.join(ROOT, "adapters", "langgraph")
sys.path.insert(0, ADAPTER)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PASS = FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok  " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + "  " + str(detail)[:240])


def raises(exc, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except exc as e:
        return True, str(e)
    except Exception as e:  # noqa: BLE001
        return False, "raised %s instead: %s" % (type(e).__name__, e)
    return False, "did not raise"


def main():
    try:
        import langgraph  # noqa: F401
    except ImportError:
        print("SKIP: langgraph is not installed")
        return 0

    import testimony_langgraph as tl
    import testimony_validate as tv
    import example

    AGENT = {"id": "support-agent", "kind": "agent"}
    HUMAN = {"id": "troy@example.com", "kind": "human"}
    CFG = lambda t: {"configurable": {"thread_id": t}}  # noqa: E731

    def recorder(**kw):
        kw.setdefault("agent", AGENT)
        kw.setdefault("risk", {"issue_refund": "high"})
        return tl.Recorder(**kw)

    print("the example produces a record the reference validator accepts")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "record.jsonl")
        example.main(path)
        text = open(path, encoding="utf-8").read()
        r = tv.validate(text)
        check("the example reaches TR-4", r.level == "TR-4",
              "%s; failures: %s" % (r.level, [c["check"] for lvl in tv.LEVELS
                                              for c in r.failures(lvl)]))
        check("the record declares that the system acts", r.scope == "acts")
        entries = [json.loads(l) for l in text.splitlines() if l.strip()]
        by_type = {}
        for e in entries:
            by_type.setdefault(e["type"], []).append(e)
        check("one approval names a human", len(by_type.get("approval", [])) == 1)
        a = by_type["approval"][0]
        check("the approver is not the proposing agent",
              a["approver"]["id"] != AGENT["id"])
        check("the identity source is not something the model can write",
              a["identity_source"] not in tl.UNTRUSTED)
        d4 = by_type["decision"][0]
        check("the executed high-risk decision points at its approval",
              d4["risk_class"] == "high" and d4.get("approval") == a["id"])
        check("the integrity entry covers every earlier entry",
              set(by_type["integrity"][0]["covers"]) ==
              {e["id"] for e in entries if e["type"] != "integrity"})

    print("\nthe same graph, resumed without an approver, does not reach TR-3")
    graph = example.build()
    rec = recorder()
    rec.invoke(graph, {"ticket": 7}, CFG("no-approver"))
    # Resuming the graph directly, the way an application does today, bypasses
    # the recorder's gate entirely. The record must not pretend otherwise.
    from langgraph.types import Command
    graph.invoke(Command(resume=True), CFG("no-approver"))
    rec._pending = None                      # the app resumed it, not us
    r = tv.validate("\n".join(json.dumps(e) for e in rec.record()))
    check("a record with no decision stops below TR-3",
          r.level in ("TR-1", "TR-2"), r.level)
    check("the failure names the missing gate",
          any("decision" in c["check"] for c in r.failures("TR-3")),
          [c["check"] for c in r.failures("TR-3")])

    print("\nan action absent from the risk table is not guessed")
    graph = example.build()
    rec = recorder(risk={"send_receipt": "low"})
    ok, msg = raises(tl.UnclassifiedAction, rec.invoke, graph, {"ticket": 8},
                     CFG("unclassified"))
    check("an unclassified action raises rather than defaulting", ok, msg)
    check("the message says why a default would be wrong",
          "guess" in msg.lower(), msg)

    print("\nidentity the proposing model could have written is refused")
    for bad in ("request-body", "model", "prompt", ""):
        graph = example.build()
        rec = recorder()
        rec.invoke(graph, {"ticket": 9}, CFG("src-" + (bad or "empty")))
        ok, msg = raises(tl.UntrustedIdentity, rec.approve, graph,
                         CFG("src-" + (bad or "empty")), approver=HUMAN,
                         identity_source=bad)
        check("identity_source %r is refused" % bad, ok, msg)

    print("\nan approver who is not a person is refused")
    graph = example.build()
    rec = recorder()
    rec.invoke(graph, {"ticket": 10}, CFG("nonhuman"))
    ok, msg = raises(ValueError, rec.approve, graph, CFG("nonhuman"),
                     approver={"id": "ops-bot", "kind": "system"},
                     identity_source="auth-session")
    check("a non-human approver is refused", ok, msg)

    print("\nthe acting agent cannot approve its own action")
    graph = example.build()
    rec = recorder()
    rec.invoke(graph, {"ticket": 11}, CFG("selfapp"))
    ok, msg = raises(tl.SelfApproval, rec.approve, graph, CFG("selfapp"),
                     approver={"id": "support-agent", "kind": "human"},
                     identity_source="auth-session")
    check("self-approval raises", ok, msg)
    check("the message explains why it is worth nothing",
          "worth nothing" in msg, msg)

    print("\na refusal is recorded as faithfully as a permission")
    graph = example.build()
    rec = recorder()
    rec.invoke(graph, {"ticket": 12}, CFG("refused"))
    rec.refuse(graph, CFG("refused"), reason="amount exceeds desk limit",
               approver=HUMAN, identity_source="auth-session")
    entries = rec.record()
    dec = [e for e in entries if e["type"] == "decision"][0]
    check("the refusal is a decision entry, not a silence",
          dec["verdict"] == "refused")
    check("a refused action is not recorded as executed",
          dec["executed"] is False)
    check("the refusal carries a reason", bool(dec.get("reason")))
    r = tv.validate("\n".join(json.dumps(e) for e in entries))
    check("a record whose only action was refused still reaches TR-4",
          r.level == "TR-4",
          "%s: %s" % (r.level, [c["check"] for lvl in tv.LEVELS
                                for c in r.failures(lvl)]))
    # A fresh gate, because the one above has been answered. Refusing without a
    # reason has to fail on the missing reason, not on there being nothing to
    # refuse, or the test proves nothing.
    graph = example.build()
    rec = recorder()
    rec.invoke(graph, {"ticket": 14}, CFG("noreason"))
    ok, msg = raises(ValueError, rec.refuse, graph, CFG("noreason"), reason="")
    check("a refusal without a reason raises", ok, msg)
    check("the gate is still pending after the refusal was rejected",
          rec._pending is not None)

    print("\nan unanswered gate cannot be written out")
    graph = example.build()
    rec = recorder()
    rec.invoke(graph, {"ticket": 13}, CFG("pending"))
    ok, msg = raises(RuntimeError, rec.record)
    check("writing a record with an action still pending raises", ok, msg)
    check("the message says the gate never closed", "never closed" in msg, msg)

    print("\nwarnings say out loud what a record will not demonstrate")
    rec = recorder()
    rec._pending = None
    check("a record with no decisions warns that it cannot show a gate",
          any("cannot demonstrate a gate" in w for w in rec.warnings()),
          rec.warnings())

    print("\ntampering with the file moves the digest")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "record.jsonl")
        example.main(path)
        entries = [json.loads(l) for l in open(path, encoding="utf-8")
                   if l.strip()]
        integ = [e for e in entries if e["type"] == "integrity"][0]
        before = integ["digest"]
        for e in entries:
            if e["type"] == "approval":
                e["approver"]["id"] = "someone-else@example.com"
        recomputed = tl.hashlib.sha256("\n".join(
            tl._canon(e) for e in entries if e["type"] != "integrity"
        ).encode()).hexdigest()
        check("softening the approver changes the digest",
              "sha256:" + recomputed != before)

    print("\nthe adapter needs nothing from OMEM")
    src = open(os.path.join(ADAPTER, "testimony_langgraph.py"),
               encoding="utf-8").read()
    check("the adapter does not import omem", "import omem" not in src)
    check("the adapter makes no network calls",
          "urllib" not in src and "requests" not in src and "httpx" not in src)
    ex = open(os.path.join(ADAPTER, "example.py"), encoding="utf-8").read()
    check("the example does not import omem", "import omem" not in ex)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
