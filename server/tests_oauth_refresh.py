"""OAuth token lifecycle. Run: python3 tests_oauth_refresh.py

The bug this suite pins down: the Gmail transport used the access token stored
at connect time forever. Google access tokens live ~1 hour, so every poll after
that got a 401 which was misreported as "reconnect the account, refresh token
revoked", even though the refresh token was never tried. These tests simulate
Google's endpoints and assert the correct lifecycle:

  - a valid stored token is used as-is (no needless refresh)
  - an expired stored token triggers a silent refresh BEFORE any API call
  - a mid-flight 401 triggers exactly one forced refresh + retry
  - the refreshed token is persisted via the on_token callback
  - token-endpoint invalid_grant is the ONLY "reconnect" condition
  - token-endpoint invalid_client blames operator config, never the user
"""
import io
import json
import os
import sys
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-secret")

import providers  # noqa: E402
from providers import RealGmailTransport, NeedsReauth, ProviderConfigError  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


class FakeGoogle:
    """Simulates the token endpoint + Gmail API with controllable behaviour."""

    def __init__(self):
        self.valid_tokens = set()
        self.refresh_calls = 0
        self.api_calls = []
        self.refresh_mode = "ok"       # ok | invalid_grant | invalid_client
        self.next_token_id = 0

    def http_error(self, url, code, body: dict):
        payload = json.dumps(body).encode()
        return urllib.error.HTTPError(url, code, "err", {}, io.BytesIO(payload))

    def urlopen(self, req, timeout=15):
        url = req.full_url
        if "oauth2.googleapis.com/token" in url:
            self.refresh_calls += 1
            if self.refresh_mode == "invalid_grant":
                raise self.http_error(url, 400, {"error": "invalid_grant",
                                                 "error_description": "Token has been expired or revoked."})
            if self.refresh_mode == "invalid_client":
                raise self.http_error(url, 401, {"error": "invalid_client",
                                                 "error_description": "The OAuth client was not found."})
            self.next_token_id += 1
            tok = f"access-{self.next_token_id}"
            self.valid_tokens.add(tok)
            return io.BytesIO(json.dumps({"access_token": tok, "expires_in": 3600}).encode())
        if "gmail.googleapis.com" in url:
            auth = req.headers.get("Authorization", "")
            tok = auth.replace("Bearer ", "")
            self.api_calls.append(tok)
            if tok not in self.valid_tokens:
                raise self.http_error(url, 401, {"error": {"code": 401,
                    "message": "Request had invalid authentication credentials. "
                               "Expected OAuth 2 access token, login cookie or other "
                               "valid authentication credential.",
                    "status": "UNAUTHENTICATED"}})
            return io.BytesIO(json.dumps({"messages": [], "nextPageToken": None}).encode())
        raise AssertionError(f"unexpected url {url}")


FAKE = FakeGoogle()
providers.urllib.request.urlopen = lambda req, timeout=15: FAKE.urlopen(req, timeout)

print("== valid stored token: used as-is, zero refreshes ==")
FAKE.valid_tokens.add("stored-valid")
saved = []
t = RealGmailTransport("refresh-tok", query="", access_token="stored-valid",
                       expires=time.time() + 3000,
                       on_token=lambda a, e: saved.append((a, e)))
msgs, cur = t.list_messages("stored-valid", None)
check("no refresh when the stored token is still valid", FAKE.refresh_calls == 0,
      str(FAKE.refresh_calls))
check("stored token used on the wire", FAKE.api_calls[-1] == "stored-valid")

print("== expired stored token: silent refresh BEFORE the API call ==")
FAKE.refresh_calls = 0
FAKE.api_calls = []
t2 = RealGmailTransport("refresh-tok", query="", access_token="stored-expired",
                        expires=time.time() - 100,       # yesterday's token
                        on_token=lambda a, e: saved.append((a, e)))
msgs, cur = t2.list_messages("stored-expired", None)
check("exactly one refresh performed", FAKE.refresh_calls == 1, str(FAKE.refresh_calls))
check("stale token NEVER sent to Gmail",
      "stored-expired" not in FAKE.api_calls, str(FAKE.api_calls))
check("fresh token persisted via on_token",
      saved and saved[-1][0].startswith("access-"), str(saved))
check("no reauth raised for a merely-expired access token", True)

print("== mid-flight 401: one forced refresh + retry ==")
FAKE.refresh_calls = 0
FAKE.api_calls = []
# expiry claims validity but Google disagrees (token revoked server-side)
t3 = RealGmailTransport("refresh-tok", query="", access_token="looks-valid-but-dead",
                        expires=time.time() + 3000)
msgs, cur = t3.list_messages(None, None)
check("401 triggered exactly one refresh", FAKE.refresh_calls == 1, str(FAKE.refresh_calls))
check("retry used the fresh token and succeeded",
      FAKE.api_calls[-1].startswith("access-"), str(FAKE.api_calls))

print("== invalid_grant at the token endpoint: the ONLY reconnect case ==")
FAKE.refresh_mode = "invalid_grant"
t4 = RealGmailTransport("dead-refresh-tok", query="")
try:
    t4.list_messages(None, None)
    check("invalid_grant raises NeedsReauth", False, "no exception")
except NeedsReauth as e:
    check("invalid_grant raises NeedsReauth", True)
    check("message names invalid_grant, not guesswork",
          "invalid_grant" in str(e), str(e))
except Exception as e:
    check("invalid_grant raises NeedsReauth", False, f"{type(e).__name__}: {e}")

print("== invalid_client: operator config error, never 'reconnect' ==")
FAKE.refresh_mode = "invalid_client"
t5 = RealGmailTransport("refresh-tok", query="")
try:
    t5.list_messages(None, None)
    check("invalid_client raises a config error", False, "no exception")
except ProviderConfigError as e:
    check("invalid_client raises a config error", True)
    check("message blames operator config, not the mailbox",
          "reconnecting the account will not help" in str(e)
          and "GOOGLE_CLIENT_ID" in str(e), str(e))
except NeedsReauth as e:
    check("invalid_client raises a config error", False,
          f"WRONGLY told user to reconnect: {e}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
