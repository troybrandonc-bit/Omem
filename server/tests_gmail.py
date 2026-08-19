"""Phase 1-6 + 9 tests. Run: python3 tests_gmail.py
Covers Gmail connector (OAuth store, sync, incremental, dedup, isolation),
LLM extraction (valid/empty/malformed/anti-hallucination), entity resolution
audit, background scheduler, the agent loop, and conflicting sources."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/omem_gmail_tests.db"
if os.path.exists(DB):
    os.remove(DB)
os.environ["OMEM_DB"] = DB
os.environ["OMEM_LLM"] = "1"
os.environ["OMEM_ALLOW_MOCK_LLM"] = "1"  # tests only  # exercise the LLM extraction path

import os as _os_seed
_os_seed.environ['OMEM_SEED_DEMO']='1'
import api  # noqa: E402
from connectors import (MockGmailTransport, GmailConnector, LLMExtractor,
                        MockLLMClient, EntityResolver)  # noqa: E402

PASS = FAIL = 0


def _fails_with(fn):
    try:
        fn()
        return None
    except Exception as e:
        return e


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}  {detail}")


# fresh project
org = api.STORE.signup("gmail@corp.com", "Corp")
proj = api.STORE.create_project(api.STORE.org_for_user(org["user_id"])["id"], "Gmail test")
PID = proj["id"]
api.PROJECTS[PID] = api.Project(PID, proj["name"], "development", proj["org_id"])
api.CONTRADICTIONS[PID] = []
p = api.PROJECTS[PID]

MESSAGES = [
    {"id": "m1", "from": "ada@acme.com", "subject": "Billing",
     "body": "Hi, we would like to move to annual billing for our subscription renewal. Thanks, Ada",
     "internalDate": 1000},
    {"id": "m2", "from": "grace@hooper.com", "subject": "Leaving",
     "body": "Hello, we are considering to cancel our contract at the end of the term. Regards, Grace",
     "internalDate": 2000},
    {"id": "m3", "from": "ada@acme.com", "subject": "Contact",
     "body": "Hi, please prefer email over phone for all account discussions from now on. Thanks, Ada",
     "internalDate": 3000},
]

print("== LLM extraction unit ==")
ex = LLMExtractor(MockLLMClient("smart"))
facts = ex.extract({"from": "ada@acme.com", "subject": "x", "body": "we want annual billing", "at": "now"})
check("valid email -> 1 fact", len(facts) == 1 and facts[0]["proposition"] == "prefers_annual_billing")
check("sender resolves customer id", facts[0]["subject"]["id"] == "customer:ada")
check("empty model output -> no facts", LLMExtractor(MockLLMClient("empty")).extract({"body": "hi", "from": "x@y.com"}) == [])
check("malformed model output -> no facts", LLMExtractor(MockLLMClient("malformed")).extract({"body": "annual billing", "from": "x@y.com"}) == [])

# anti-hallucination: evidence not in text is dropped
class LiarClient(MockLLMClient):
    def complete(self, system, user):
        return json.dumps({"facts": [{"subject_email": "ghost@x.com", "subject_kind": "person",
                                      "proposition": "is_vip", "confidence": 0.9,
                                      "evidence": "the CEO told me personally"}]})
check("hallucinated evidence dropped", LLMExtractor(LiarClient()).extract({"body": "nothing relevant", "from": "a@b.com"}) == [])

print("== Gmail connector: OAuth + sync ==")
transport = MockGmailTransport(MESSAGES)
api.GMAIL_TRANSPORT_FACTORY = lambda conn: transport  # inject mock
conn = api.INGEST.add_connector(PID, "gmail", "Gmail (Ada)", {}, agent_id="connector:gmail", authority=0.8)
api.OAUTH.save(conn["id"], "gmail", "tok", "refresh", 9e9, "gmail.readonly", "ada@acme.com")
creds = api.OAUTH.get(conn["id"], include_secrets=True)
check("token stored encrypted+recovered", creds["access_token"] == "tok" and creds["account"] == "ada@acme.com")

q1 = api.INGEST.poll_connector(conn["id"])
check("initial sync pulls 3 messages", q1 == 3)
q2 = api.INGEST.poll_connector(conn["id"])
check("incremental sync (cursor) pulls 0", q2 == 0)
res = api.INGEST.process_pending(PID)
check("emails extracted to assertions", res["assertions"] >= 2, str(res))

st = p.engine.proposition_state(["customer:ada"], "prefers_annual_billing", p.now())
check("ada annual billing believed", st == "BELIEVED_TRUE", st)
st2 = p.engine.proposition_state(["customer:grace"], "intends_to_cancel", p.now())
check("grace cancel believed (separate entity)", st2 == "BELIEVED_TRUE", st2)

print("== entity resolution audit ==")
hist = api.RESOLVER.history_for(PID, "customer:ada")
check("resolution recorded for ada", len(hist) >= 1 and hist[0]["method"] in ("email_localpart", "exact_id", "explicit_id"))
check("resolution has evidence", all(h["evidence"] for h in hist))

print("== source-level dedup across restart of sync ==")
before = api.INGEST.stats(PID)["sources"]
api.INGEST.poll_connector(conn["id"])  # same messages, cursor at end
check("no duplicate source records", api.INGEST.stats(PID)["sources"] == before)

print("== tenant isolation ==")
proj2 = api.STORE.create_project(api.STORE.org_for_user(org["user_id"])["id"], "Other")
api.PROJECTS[proj2["id"]] = api.Project(proj2["id"], "Other", "development", proj2["org_id"])
api.CONTRADICTIONS[proj2["id"]] = []
p2 = api.PROJECTS[proj2["id"]]
check("other project has no ada memory", p2.engine.proposition_state(["customer:ada"], "prefers_annual_billing", p2.now()) == "UNKNOWN")

print("== conflicting sources -> engine says CONTRADICTED ==")
api.record(p, "declare", {"token_a": "prefers_email_over_phone", "token_b": "not:prefers_email_over_phone"})
# a CRM connector that emits the negation for ada
class CRMClient(MockLLMClient):
    def complete(self, system, user):
        if "ada" in user.lower() or "acme" in user.lower():
            return json.dumps({"facts": [{"subject_email": "ada@acme.com",
                                          "subject_kind": "person",
                                          "proposition": "not:prefers_email_over_phone",
                                          "confidence": 0.9,
                                          "evidence": "prefers phone over email"}]})
        return '{"facts": []}'
crm_msgs = [{"id": "c1", "from": "sync@acme.com", "subject": "CRM update for ada",
             "body": "Account note: ada prefers phone over email for all contract and billing discussions.",
             "internalDate": 5000}]
crm_transport = MockGmailTransport(crm_msgs)
api.GMAIL_TRANSPORT_FACTORY = lambda conn: crm_transport
crm = api.INGEST.add_connector(PID, "gmail", "CRM", {}, agent_id="connector:crm", authority=0.9)
api.OAUTH.save(crm["id"], "gmail", "t2", "r2", 9e9, "s", "crm@acme.com")
# attach the CRM llm by temporarily overriding factory extractor
import connectors as _c
_orig = api._connector_factory
def crm_factory(conn):
    inst = GmailConnector(crm_transport, "t2", LLMExtractor(CRMClient()))
    return inst if conn["id"] == crm["id"] else _orig(conn)
api.INGEST.connector_factory = crm_factory
api.INGEST.poll_connector(crm["id"])
api.INGEST.process_pending(PID)
api.INGEST.connector_factory = _orig
st3 = p.engine.proposition_state(["customer:ada"], "prefers_email_over_phone", p.now())
check("competing gmail+crm facts -> CONTRADICTED", st3 == "CONTRADICTED", st3)

print("== background scheduler ==")
from scheduler import Scheduler
api.GMAIL_TRANSPORT_FACTORY = lambda conn: MockGmailTransport(MESSAGES)
sched = Scheduler(api.INGEST, interval=0.2, min_project_gap=0)
acted = sched.tick()
check("scheduler tick returns per-project activity", isinstance(acted, dict))
check("scheduler counted a run", sched.runs == 1)

print("== agent loop ==")
from agent import SupportAgent
agent = SupportAgent(api.PROJECTS[PID], api.INGEST)
decision = agent.handle("ada", "Can you change my billing plan?")
check("agent recalled ada's billing memory", "annual" in decision["memory_used"].lower(), decision["memory_used"])
check("agent cited a source", decision["source"] is not None)
# conversation writes back into memory
agent.learn("ada", "Hi, further to our contract discussion, we now prefer phone over email for account matters. Thanks")
api.INGEST.process_pending(PID)
check("agent conversation produced new candidate belief",
      p.engine.proposition_state(["customer:ada"], "not:prefers_email_over_phone", p.now()) in ("BELIEVED_TRUE", "CONTRADICTED"))

print("== unconfigured Gmail fails honestly (regression: was a raw crash) ==")
import threading as _th, urllib.request as _u, urllib.error as _ue, json as _j, time
from http.server import ThreadingHTTPServer as _THS
from connectors import GmailTransport, ProviderNotConfigured
_saved = api.GMAIL_TRANSPORT_FACTORY
api.GMAIL_TRANSPORT_FACTORY = None  # no injected mock, no GOOGLE_* env
_srv = _THS(("127.0.0.1", 0), api.Handler)
_port = _srv.server_address[1]
_th.Thread(target=_srv.serve_forever, daemon=True).start()
time.sleep(0.2)


def _call(m, path, body=None, key=None):
    r = _u.Request(f"http://127.0.0.1:{_port}{path}", method=m,
                   data=_j.dumps(body).encode() if body is not None else None,
                   headers={"Content-Type": "application/json",
                            **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with _u.urlopen(r, timeout=10) as resp:
            return resp.status, _j.loads(resp.read() or b"{}")
    except _ue.HTTPError as e:
        return e.code, _j.loads(e.read())


_, _acct = _call("POST", "/v1/signup", {"email": "notconf@x.com"})
_k = _acct["api_key"]["secret"]; _p = _acct["project"]["id"]
_, _beg = _call("POST", f"/v1/oauth/gmail/begin?project={_p}", {"name": "Gmail"}, _k)
_cid = _beg["connector_id"]
_call("POST", f"/v1/oauth/gmail/callback?project={_p}", {"connector_id": _cid, "account": "u@gmail.com"}, _k)
_st, _r = _call("POST", f"/v1/connectors/{_cid}/poll?project={_p}", {}, _k)
check("unconfigured Gmail poll -> 503 (not a 500/crash)", _st == 503, str(_st))
check("error names the provider + required env",
      _r["error"]["provider"] == "google" and "GOOGLE_CLIENT_ID" in _r["error"]["required_env"])
check("message tells the operator what to do", "GOOGLE_CLIENT_SECRET" in _r["error"]["message"])
_st, _s = _call("GET", f"/v1/connectors/{_cid}/status?project={_p}", None, _k)
check("connector status NOT_CONFIGURED", _s["status"] == "NOT_CONFIGURED", str(_s["status"]))
check("base transport raises typed error, not NotImplementedError",
      isinstance(_fails_with(lambda: GmailTransport().list_messages(None, None)), ProviderNotConfigured))
_srv.shutdown()
api.GMAIL_TRANSPORT_FACTORY = _saved

print("== env file loading + real consent URL ==")
import env_loader
_tmp = "/tmp/omem_env_test.env"
open(_tmp, "w").write("FOO_TEST_KEY=bar\nQUOTED='q v'\n# comment\nexport EXPORTED=yes\n")
_vals = env_loader.parse_env_file(_tmp)
check("env parser: plain, quoted, export, comments",
      _vals == {"FOO_TEST_KEY": "bar", "QUOTED": "q v", "EXPORTED": "yes"}, str(_vals))
os.environ["ALREADY_SET"] = "original"
open(_tmp, "w").write("ALREADY_SET=from_file\n")
_saved_cands = env_loader.CANDIDATES[:]
env_loader.CANDIDATES[:] = [_tmp]
env_loader.load_env()
check("real environment wins over env file", os.environ["ALREADY_SET"] == "original")
env_loader.CANDIDATES[:] = _saved_cands
os.remove(_tmp)

# begin: honest when unconfigured, real Google URL when configured
_srv2 = _THS(("127.0.0.1", 0), api.Handler)
_p2 = _srv2.server_address[1]
_th.Thread(target=_srv2.serve_forever, daemon=True).start()
time.sleep(0.2)


def _c2(m, path, body=None, key=None):
    r = _u.Request(f"http://127.0.0.1:{_p2}{path}", method=m,
                   data=_j.dumps(body).encode() if body is not None else None,
                   headers={"Content-Type": "application/json",
                            **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with _u.urlopen(r, timeout=10) as resp:
            return resp.status, _j.loads(resp.read() or b"{}")
    except _ue.HTTPError as e:
        return e.code, _j.loads(e.read())


_, _ac = _c2("POST", "/v1/signup", {"email": "beginflow@x.com"})
_k2 = _ac["api_key"]["secret"]; _pj = _ac["project"]["id"]
_st, _bg = _c2("POST", f"/v1/oauth/gmail/begin?project={_pj}", {"name": "Gmail"}, _k2)
check("unconfigured begin: real=false, no fake auth_url",
      _bg["real"] is False and _bg["auth_url"] is None)
check("unconfigured begin names required env", "GOOGLE_CLIENT_ID" in _bg["required_env"])

os.environ["GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-secret"
os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:8787/oauth/gmail/callback"
_st, _bg2 = _c2("POST", f"/v1/oauth/gmail/begin?project={_pj}", {"name": "Gmail2"}, _k2)
check("configured begin returns real Google consent URL",
      _bg2["real"] is True and _bg2["auth_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth"))
check("consent URL carries client_id and signed state",
      "test-client" in _bg2["auth_url"] and "state=" in _bg2["auth_url"])
_st, _cb = _c2("GET", "/oauth/gmail/callback?code=x&state=forged")
check("browser callback rejects forged state", _st == 400)
for _v in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
    os.environ.pop(_v, None)
_srv2.shutdown()

print("== frontend redirect callback (regression: 404 on :3000) ==")
import providers as _prov
_srv3 = _THS(("127.0.0.1", 0), api.Handler)
_p3 = _srv3.server_address[1]
_th.Thread(target=_srv3.serve_forever, daemon=True).start()
time.sleep(0.2)


def _c3(m, path, body=None, key=None):
    r = _u.Request(f"http://127.0.0.1:{_p3}{path}", method=m,
                   data=_j.dumps(body).encode() if body is not None else None,
                   headers={"Content-Type": "application/json",
                            **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with _u.urlopen(r, timeout=10) as resp:
            return resp.status, _j.loads(resp.read() or b"{}")
    except _ue.HTTPError as e:
        try:
            return e.code, _j.loads(e.read())
        except Exception:
            return e.code, {}


os.environ["GOOGLE_CLIENT_ID"] = "cb-client.apps.googleusercontent.com"
os.environ["GOOGLE_CLIENT_SECRET"] = "cb-secret"
os.environ["GOOGLE_REDIRECT_URI"] = "http://localhost:3000/oauth/gmail/callback"
_, _acb = _c3("POST", "/v1/signup", {"email": "cbflow@x.com"})
_kcb = _acb["api_key"]["secret"]; _pcb = _acb["project"]["id"]
_st, _bg3 = _c3("POST", f"/v1/oauth/gmail/begin?project={_pcb}", {"name": "Gmail"}, _kcb)
_state = _bg3["state"]
_real_exchange = _prov.google_exchange_code
_prov.google_exchange_code = lambda code: {"access_token": "at", "refresh_token": "rt",
                                           "expires_in": 3600, "scope": "gmail.readonly"}
_st, _cb = _c3("POST", f"/v1/oauth/gmail/callback?project={_pcb}",
               {"code": "code-from-google", "state": _state}, _kcb)
check("callback works with only code+state (connector from state)",
      _st == 200 and _cb["connected"] and _cb["connector_id"] == _bg3["connector_id"])
check("real exchange path taken when configured", _cb["real_exchange"] is True)
_st, _s3 = _c3("GET", f"/v1/connectors/{_bg3['connector_id']}/status?project={_pcb}", None, _kcb)
check("connector becomes HEALTHY after connect", _s3["status"] == "HEALTHY", str(_s3["status"]))
_st, _ = _c3("POST", f"/v1/oauth/gmail/callback?project={_pcb}",
             {"code": "again", "state": _state}, _kcb)
check("single-use state cannot be replayed", _st == 403)
_st, _ = _c3("POST", f"/v1/oauth/gmail/callback?project={_pcb}", {"code": "x"}, _kcb)
check("missing state and connector_id -> 422", _st == 422)
_prov.google_exchange_code = _real_exchange
for _v in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI"):
    os.environ.pop(_v, None)
_srv3.shutdown()

print("== real Gmail message parsing + source view (regression) ==")
import base64 as _b64
from connectors import GmailConnector as _GC, GmailTransport as _GT
from ingest import RuleExtractor as _RE

_raw = ("From: Jane Cooper <jane.cooper@acme.com>\r\n"
        "To: support@omem.dev\r\n"
        "Subject: Upgrading our plan\r\n"
        "Date: Fri, 08 Aug 2026 18:22:11 +0100\r\n\r\n"
        "Hi team, we would like to upgrade to the enterprise tier next month.\r\n")


class _RawOnly(_GT):
    """Mimics Gmail format=raw: NO payload.headers, only the raw message."""
    def list_messages(self, token, cursor):
        if cursor:
            return [], cursor
        return [{"id": "18f2c", "threadId": "t1", "internalDate": "1786000000000",
                 "raw": _b64.urlsafe_b64encode(_raw.encode()).decode()}], "1"


_items, _ = _GC(_RawOnly(), "tok", _RE()).poll(None)
_pl = _items[0][1]
check("real RFC822 headers parsed from raw", _pl["from_email"] == "jane.cooper@acme.com")
check("subject parsed from raw", _pl["subject"] == "Upgrading our plan")
check("body parsed from raw", "enterprise tier" in _pl["body"])
check("gmail deep link built", _pl["gmail_url"].endswith("18f2c"))
check("identity derives from sender, not a sentinel",
      _RE.identity_of(_pl) == "jane.cooper")
_facts = _RE().extract(_pl)
check("facts attach to the real person", all(f["subject"]["id"] == "customer:jane.cooper" for f in _facts))
check("label uses the real subject line",
      any(f["label"].startswith("Upgrading our plan") for f in _facts))

# LLM extractor must never invent a placeholder entity
from connectors import LLMExtractor as _LX, MockLLMClient as _MC
_no_sender = _LX(_MC("smart")).extract({"body": "we want annual billing", "subject": "x",
                                        "from": "", "at": "now"})
check("no identity -> no fabricated entity", _no_sender == [], str(_no_sender))

# end-to-end: source view exposes the original email
_srv4 = _THS(("127.0.0.1", 0), api.Handler)
_p4 = _srv4.server_address[1]
_th.Thread(target=_srv4.serve_forever, daemon=True).start()
time.sleep(0.2)


def _c4(m, path, body=None, key=None):
    r = _u.Request(f"http://127.0.0.1:{_p4}{path}", method=m,
                   data=_j.dumps(body).encode() if body is not None else None,
                   headers={"Content-Type": "application/json",
                            **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with _u.urlopen(r, timeout=10) as resp:
            return resp.status, _j.loads(resp.read() or b"{}")
    except _ue.HTTPError as e:
        return e.code, _j.loads(e.read())


_saved_f = api.GMAIL_TRANSPORT_FACTORY
api.GMAIL_TRANSPORT_FACTORY = lambda conn: _RawOnly()
_, _av = _c4("POST", "/v1/signup", {"email": "sview@x.com"})
_kv = _av["api_key"]["secret"]; _pv = _av["project"]["id"]
_, _bv = _c4("POST", f"/v1/oauth/gmail/begin?project={_pv}", {"name": "Gmail"}, _kv)
_c4("POST", f"/v1/oauth/gmail/callback?project={_pv}",
    {"connector_id": _bv["connector_id"], "account": "me@gmail.com"}, _kv)
_c4("POST", f"/v1/connectors/{_bv['connector_id']}/poll?project={_pv}", {}, _kv)
_c4("POST", f"/v1/ingest/process?project={_pv}", {}, _kv)
# Subject scope depends on the active extractor: the LLM path attaches facts to
# the person, the deterministic business path to their organisation. Both are
# valid, so accept either.
_rv = None
for _about in ("customer:jane.cooper", "company:acme"):
    _, _cand = _c4("POST", f"/v1/recall?project={_pv}", {"about": _about}, _kv)
    if _cand["count"] >= 1:
        _rv = _cand
        break
check("email produced memories for the counterparty", _rv is not None and _rv["count"] >= 1)
_aid = _rv["memories"][0]["assertion"]
_, _sv = _c4("GET", f"/v1/assertions/{_aid}/source?project={_pv}", None, _kv)
_v = _sv["view"]
check("source view shows the subject", _v["title"] == "Upgrading our plan")
check("source view shows sender + recipient",
      _v["from_email"] == "jane.cooper@acme.com" and "support@omem.dev" in (_v["to"] or ""))
check("source view includes the body and a link",
      "enterprise tier" in _v["body"] and _v["link"].endswith("18f2c"))
_, _wv = _c4("GET", f"/v1/assertions/{_aid}/why?project={_pv}", None, _kv)
check("why also carries the readable source view",
      _wv["source"]["view"]["title"] == "Upgrading our plan")
api.GMAIL_TRANSPORT_FACTORY = _saved_f
_srv4.shutdown()

print("== html email body renders as readable text (regression) ==")
from connectors import html_to_text as _h2t, readable_body as _rb, _parse_rfc822 as _prfc

_html_raw = ("From: Acme Billing <billing@acme.com>\r\n"
             "Subject: Your invoice\r\n"
             "MIME-Version: 1.0\r\n"
             "Content-Type: text/html; charset=UTF-8\r\n"
             "Content-Transfer-Encoding: quoted-printable\r\n\r\n"
             "<!DOCTYPE html><html><head><style>.hide{display:none}</style></head>"
             "<body><p>Hi Jane,</p><p>We want to =\r\nupgrade to annual billing.</p>"
             "<a href=3D\"https://x\">View</a></body></html>\r\n")
_parsed = _prfc(_html_raw)
check("html-only email becomes readable text",
      "Hi Jane," in _parsed["body"] and "upgrade to annual billing" in _parsed["body"])
check("no markup survives", "<" not in _parsed["body"] and "DOCTYPE" not in _parsed["body"])
check("css and script content dropped", "display:none" not in _parsed["body"])
check("quoted-printable soft breaks rejoined", "to upgrade" in _parsed["body"].replace("\n", " "))

# multipart: the plain part must win over the html part
_multi = ("From: a@b.com\r\nSubject: Multi\r\n"
          "Content-Type: multipart/alternative; boundary=BB\r\n\r\n"
          "--BB\r\nContent-Type: text/plain\r\n\r\nPlain wins here.\r\n"
          "--BB\r\nContent-Type: text/html\r\n\r\n<p>HTML loses</p>\r\n--BB--\r\n")
check("multipart prefers the plain part", "Plain wins here" in _prfc(_multi)["body"])

# legacy rows stored before MIME handling still render
_legacy = '<html><body><p>Hi Jane,</p><p>We want to =\r\nupgrade (href=3D"x").</p></body></html>'
_clean = _rb(_legacy)
check("legacy stored html cleaned at read time",
      "Hi Jane," in _clean and "<" not in _clean and "=3D" not in _clean)
check("entities unescaped", _h2t("<p>Tom &amp; Jerry &lt;3</p>").strip() == "Tom & Jerry <3")

# source_view exposes the readable body and an honest title
import json as _json2
# use a REAL connector: foreign keys are enforced on Postgres
_hconn = api.INGEST.add_connector("demo", "webhook", "html-test", {},
                                  agent_id="connector:htmltest")
api.STORE.db.execute(
    "INSERT INTO source_records(id,project_id,connector_id,external_id,payload,content_hash,received) "
    "VALUES(?,?,?,?,?,?,?)",
    ("src_htmltest", "demo", _hconn["id"], "msgid123",
     _json2.dumps({"body": _legacy}), "hh", time.time()))
api.STORE.db.commit()
_srow = api.STORE.db.execute("SELECT * FROM source_records WHERE id='src_htmltest'").fetchone()
_view = api.source_view(_srow, None)
check("source view body is readable", "Hi Jane," in _view["body"] and "<" not in _view["body"])
check("missing subject shows '(no subject)', not a message id",
      _view["title"] == "(no subject)", _view["title"])

print("== relevance filter: only real business mail is ingested ==")
from connectors import is_automated as _isauto, GmailTransport as _GT2, GmailConnector as _GC2
from ingest import RuleExtractor as _RE2
import base64 as _b642

def _mk(mid, frm, subj, body, extra=""):
    _r = f"From: {frm}\r\nTo: sales@omem.dev\r\nSubject: {subj}\r\n{extra}\r\n{body}\r\n"
    return {"id": mid, "threadId": mid, "internalDate": "1786000000000",
            "raw": _b642.urlsafe_b64encode(_r.encode()).decode()}

check("real business mail kept",
      _isauto({"from": "Jane <jane@acme.com>", "subject": "Renewal", "headers": {}})[0] is False)
check("a real person at billing@ is kept (not over-filtered)",
      _isauto({"from": "billing@acme.com", "subject": "Invoice 42", "headers": {}})[0] is False)
check("noreply sender excluded",
      _isauto({"from": "noreply@linkedin.com", "subject": "x", "headers": {}})[0] is True)
check("newsletter excluded via List-Unsubscribe",
      _isauto({"from": "news@sub.com", "subject": "Digest",
               "headers": {"List-Unsubscribe": "<u>"}})[0] is True)
check("auto-reply excluded",
      _isauto({"from": "bob@acme.com", "subject": "Out of office: back Monday",
               "headers": {}})[0] is True)
check("bulk precedence excluded",
      _isauto({"from": "a@b.com", "subject": "x", "headers": {"Precedence": "bulk"}})[0] is True)

_MIX = [
    _mk("f1", "Jane Cooper <jane.cooper@acme.com>", "Contract renewal",
        "We would like to move to annual billing when we renew."),
    _mk("f2", "noreply@linkedin.com", "5 new notifications", "click"),
    _mk("f3", "news@substack.com", "Weekly digest", "read", "List-Unsubscribe: <https://x>\r"),
    _mk("f4", "Bob <bob@acme.com>", "Out of office: back Monday", "away"),
]


class _MixT(_GT2):
    def list_messages(self, token, cursor):
        return ([], cursor) if cursor else (_MIX, "1")


_c = _GC2(_MixT(), "tok", _RE2())
_kept, _ = _c.poll(None)
# Retrieval no longer filters: every message becomes a source record so the
# exclusion decision stays inspectable. Relevance is decided by the classifier.
check("poll keeps every message for auditability", len(_kept) == 4, str(len(_kept)))
from classifier import classify as _cls_check
_verdicts = {ext: _cls_check(p, "")["classification"] for ext, p in _kept}
check("the business email is classified relevant",
      _verdicts["f1"] == "BUSINESS_RELEVANT", str(_verdicts))
check("the noise is not classified relevant",
      all(v != "BUSINESS_RELEVANT" for k, v in _verdicts.items() if k != "f1"), str(_verdicts))

print("== extraction quality: real business facts, hallucination dropped ==")
from connectors import LLMExtractor as _LX2, LLMClient as _LC2
import json as _j3

_EMAIL = {"from": "Jane Cooper <jane.cooper@acme.com>", "to": "sales@omem.dev",
          "subject": "Re: contract renewal + SSO",
          "body": ("We'd like to move to annual billing when we renew in September. "
                   "I'm the one who signs off on this. "
                   "One blocker: we can't go ahead without SAML SSO."),
          "at": "now"}


class _Model(_LC2):
    def complete(self, system, user):
        return _j3.dumps({"facts": [
            {"subject_email": "jane.cooper@acme.com", "subject_kind": "person",
             "proposition": "prefers_annual_billing", "confidence": 0.95,
             "evidence": "We'd like to move to annual billing when we renew in September."},
            {"subject_email": "jane.cooper@acme.com", "subject_kind": "person",
             "proposition": "is_decision_maker", "confidence": 0.9,
             "evidence": "I'm the one who signs off on this"},
            {"subject_email": "acme.com", "subject_kind": "company",
             "proposition": "requires_saml_sso", "confidence": 0.9,
             "evidence": "we can't go ahead without SAML SSO"},
            {"subject_email": "jane.cooper@acme.com", "subject_kind": "person",
             "proposition": "is_very_happy", "confidence": 0.95,
             "evidence": "Jane said she loves the product"},
            {"subject_email": "jane.cooper@acme.com", "subject_kind": "person",
             "proposition": "maybe_interested", "confidence": 0.3,
             "evidence": "I'm the one who signs off on this"},
        ]})


_facts = _LX2(_Model()).extract(_EMAIL)
_props = {f["proposition"]: f for f in _facts}
check("extracts multiple distinct business facts", len(_facts) == 3, str(list(_props)))
check("person-level facts attach to the person",
      _props["is_decision_maker"]["subject"]["id"] == "customer:jane.cooper")
check("company-level facts attach to the company",
      _props["requires_saml_sso"]["subject"]["id"] == "company:acme")
check("fabricated evidence is dropped", "is_very_happy" not in _props)
check("low-confidence facts are dropped", "maybe_interested" not in _props)
check("evidence is a verbatim quote from the source",
      "annual billing" in _props["prefers_annual_billing"]["evidence"])

_bad = _LX2(type("B", (_LC2,), {"complete": lambda self, s, u: "not json at all"})()).extract(_EMAIL)
check("malformed model output yields no facts", _bad == [])
_fenced = _LX2(type("F", (_LC2,), {"complete": lambda self, s, u:
    '```json\n{"facts":[{"subject_email":"jane.cooper@acme.com","subject_kind":"person",'
    '"proposition":"is_decision_maker","confidence":0.9,'
    '"evidence":"I\'m the one who signs off on this"}]}\n```'})()).extract(_EMAIL)
check("code-fenced JSON still parses", len(_fenced) == 1)

print("== expired Google grant asks for reconnection, not a retry ==")
import providers as _pv4, urllib.error as _ue4, io as _io4, urllib.request as _ur4

_saved_open = _pv4.urllib.request.urlopen


def _google_401(req, timeout=15):
    raise _ue4.HTTPError(req.full_url, 401, "Unauthorized", {},
                         _io4.BytesIO(b'{"error":"invalid_grant"}'))


_pv4.urllib.request.urlopen = _google_401
try:
    _req = _ur4.Request("https://gmail.googleapis.com/gmail/v1/users/me/messages")
    _pv4._open_or_explain(_req)
    check("401 raises", False)
except _pv4.NeedsReauth as _e:
    check("Google 401 becomes NeedsReauth", True)
    check("message says reconnect", "reconnected" in str(_e))
    check("message carries the provider reason", "invalid_grant" in str(_e))
except Exception as _e:
    check("Google 401 classified", False, type(_e).__name__)
finally:
    _pv4.urllib.request.urlopen = _saved_open

# a non-google 401 must NOT be treated as a dead grant
_pv4.urllib.request.urlopen = _google_401
try:
    _pv4._open_or_explain(_ur4.Request("https://api.groq.com/openai/v1/chat/completions"))
    check("non-google 401 raises", False)
except _pv4.NeedsReauth:
    check("non-google 401 is not misreported as reauth", False)
except _ue4.HTTPError:
    check("non-google 401 stays an HTTPError", True)
finally:
    _pv4.urllib.request.urlopen = _saved_open

print("== real Gmail transport classifies auth failures (regression) ==")
# This is the check that would have caught the silent no-op: assert on the CODE,
# not on the intention. Every Google call must go through the classifier.
import inspect as _insp
import providers as _pv5
_src = _insp.getsource(_pv5.RealGmailTransport)
check("no unclassified urlopen in RealGmailTransport",
      "urllib.request.urlopen(" not in _src, "raw urlopen still present")
check("every Gmail call goes through the classified _gmail_get helper",
      _src.count("self._gmail_get(") >= 2 and "_open_or_explain(" in _src,
      f"gmail_get={_src.count('self._gmail_get(')}")

# and end-to-end: a dead grant must reach the connector as NEEDS_REAUTH
_saved_gid = os.environ.get("GOOGLE_CLIENT_ID")
_saved_gsec = os.environ.get("GOOGLE_CLIENT_SECRET")
os.environ["GOOGLE_CLIENT_ID"] = "x"
os.environ["GOOGLE_CLIENT_SECRET"] = "y"
_srv5 = _THS(("127.0.0.1", 0), api.Handler)
_p5 = _srv5.server_address[1]
_th.Thread(target=_srv5.serve_forever, daemon=True).start()
time.sleep(0.2)


def _c5(m, path, body=None, key=None):
    r = _u.Request(f"http://127.0.0.1:{_p5}{path}", method=m,
                   data=_j.dumps(body).encode() if body is not None else None,
                   headers={"Content-Type": "application/json",
                            **({"Authorization": f"Bearer {key}"} if key else {})})
    try:
        with _u.urlopen(r, timeout=20) as resp:
            return resp.status, _j.loads(resp.read() or b"{}")
    except _ue.HTTPError as e:
        return e.code, _j.loads(e.read() or b"{}")


_, _a5 = _c5("POST", "/v1/signup", {"email": "deadgrant@x.com"})
_k5 = _a5["api_key"]["secret"]; _p5id = _a5["project"]["id"]
_, _c5conn = _c5("POST", f"/v1/connectors?project={_p5id}", {"kind": "gmail", "name": "G"}, _k5)
# stored access token EXPIRED -> transport must attempt a refresh; the
# simulated token endpoint then reports the grant as dead (invalid_grant),
# which is the one genuine reconnect condition.
api.OAUTH.save(_c5conn["id"], "gmail", "tok", "refresh", time.time() - 100, "s", "me@gmail.com")
_saved_factory = api.GMAIL_TRANSPORT_FACTORY
api.GMAIL_TRANSPORT_FACTORY = None  # force the REAL transport
import io as _io
import providers as _pv5b
_real_urlopen = _pv5b.urllib.request.urlopen
def _fake_google(req, timeout=15):
    url = req.full_url if hasattr(req, "full_url") else str(req)
    if "127.0.0.1" in url or "localhost" in url:
        return _real_urlopen(req, timeout=timeout)
    if "oauth2.googleapis.com/token" in url:
        raise _ue.HTTPError(url, 400, "err", {}, _io.BytesIO(
            _j.dumps({"error": "invalid_grant",
                       "error_description": "Token has been expired or revoked."}).encode()))
    raise AssertionError(f"unexpected outbound call in test: {url}")
_pv5b.urllib.request.urlopen = _fake_google
_st5, _r5 = _c5("POST", f"/v1/connectors/{_c5conn['id']}/poll?project={_p5id}", {}, _k5)
check("dead grant -> 409 needs_reauth (not a bare 500)",
      _st5 == 409 and _r5["error"]["type"] == "needs_reauth", f"{_st5} {str(_r5)[:80]}")
check("response tells the user to reconnect", "Reconnect" in (_r5["error"].get("action") or ""))
_st5, _s5 = _c5("GET", f"/v1/connectors/{_c5conn['id']}/status?project={_p5id}", None, _k5)
check("connector status becomes NEEDS_REAUTH", _s5["status"] == "NEEDS_REAUTH", _s5["status"])
api.GMAIL_TRANSPORT_FACTORY = _saved_factory
_pv5b.urllib.request.urlopen = _real_urlopen
for _k, _v in (("GOOGLE_CLIENT_ID", _saved_gid), ("GOOGLE_CLIENT_SECRET", _saved_gsec)):
    if _v is None:
        os.environ.pop(_k, None)
    else:
        os.environ[_k] = _v
_srv5.shutdown()

print("== google 403s are classified by CAUSE, not lumped together ==")
import io as _io6, urllib.error as _ue6, urllib.request as _ur6
import providers as _pv6

_saved_open6 = _ur6.urlopen


def _google_fails_with(body, code=403):
    def _fake(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "googleapis.com" in url:
            raise _ue6.HTTPError(url, code, "err", {}, _io6.BytesIO(body))
        return _saved_open6(req, timeout=timeout)
    return _fake


_API_OFF = (b'{"error":{"message":"Gmail API has not been used in project 1639 before '
            b'or it is disabled. Enable it by visiting '
            b'https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=1639 then retry."}}')
_pv6.urllib.request.urlopen = _google_fails_with(_API_OFF)
try:
    _pv6._open_or_explain(_ur6.Request("https://gmail.googleapis.com/x"))
    check("api-disabled raises", False)
except _pv6.ProviderApiDisabled as _e:
    check("API-not-enabled is its own error", True)
    check("it does NOT tell the user to reconnect", "reconnect" not in str(_e).lower()
          or "will not help" in str(_e).lower())
    check("it captures Google's console link", _e.console_url.startswith("https://console."))
except Exception as _e:
    check("api-disabled classified", False, type(_e).__name__)
finally:
    _pv6.urllib.request.urlopen = _saved_open6

_DEAD = b'{"error":"invalid_grant"}'
_pv6.urllib.request.urlopen = _google_fails_with(_DEAD, code=401)
try:
    _pv6._open_or_explain(_ur6.Request("https://gmail.googleapis.com/x"))
    check("dead grant raises", False)
except _pv6.NeedsReauth as _e:
    check("a genuinely dead grant still says reconnect", "reconnected" in str(_e))
except Exception as _e:
    check("dead grant classified", False, type(_e).__name__)
finally:
    _pv6.urllib.request.urlopen = _saved_open6

_SCOPE = b'{"error":{"message":"Request had insufficient authentication scopes."}}'
_pv6.urllib.request.urlopen = _google_fails_with(_SCOPE)
try:
    _pv6._open_or_explain(_ur6.Request("https://gmail.googleapis.com/x"))
    check("scope error raises", False)
except _pv6.ProviderScopeError as _e:
    check("missing scope is distinguished", "scope" in str(_e).lower())
except Exception as _e:
    check("scope error classified", False, type(_e).__name__)
finally:
    _pv6.urllib.request.urlopen = _saved_open6

print("== persistence replay ==")
srcs = api.INGEST.stats(PID)["sources"]
import importlib
sys.modules.pop("api")
api2 = importlib.import_module("api")
check("source records persisted", api2.INGEST.stats(PID)["sources"] == srcs)
p_re = api2.PROJECTS.get(PID)
check("ada memory replayed", p_re is not None and
      p_re.engine.proposition_state(["customer:ada"], "prefers_annual_billing", p_re.now()) == "BELIEVED_TRUE")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
