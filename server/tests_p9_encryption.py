"""P9.1 encryption-at-rest (backup artifacts). Run: python3 tests_p9_encryption.py

Verifies the guarantees P9.1 actually introduces:
- backup artifact encryption is OFF by default (dev stays simple, plaintext .db);
- when enabled, the artifact is ciphertext (no recognizable plaintext), the
  plaintext temp is scrubbed, and restore-verify still works;
- wrong/invalid key material fails safe (cannot decrypt, cannot verify);
- the encryption config is observable and flags an insecure production default;
- an attacker with only the artifact cannot recover the key from it;
- existing OAuth/connector secret encryption (string API) is unchanged.

LIMITATION (labeled): deployment/volume-level DB-at-rest encryption cannot be
exercised in this test environment — it is a deployment requirement, documented,
not code-verified here.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from backups import BackupManager  # noqa: E402
from secrets_provider import LocalSecretsProvider  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ok  {n}")
    else:
        FAIL += 1; print(f"  FAIL {n}  {d}")


def _fresh_db(path):
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("CREATE TABLE ops(id INTEGER PRIMARY KEY, x TEXT);")
    for i in range(50):
        db.execute("INSERT INTO ops(x) VALUES(?)", (f"assertion-content-SECRET-{i}",))
    db.commit()
    return db


DB = "/tmp/omem_p91_src.db"
BK = "/tmp/omem_p91_bk"
os.environ["OMEM_DB"] = DB
os.makedirs(BK, exist_ok=True)
for f in os.listdir(BK):
    os.remove(os.path.join(BK, f))

# a control DB the BackupManager records into (its own bookkeeping)
ctl = _fresh_db(DB)

print("== default: encryption OFF, plaintext .db artifact (dev convenience) ==")
os.environ.pop("OMEM_BACKUP_ENCRYPT", None)
bm = BackupManager(ctl, backup_dir=BK, secrets=LocalSecretsProvider("master-A"))
st = bm.run()
art = st["last_successful"]["path"]
check("default backup completes", st["last_successful"] is not None)
check("default artifact is not encrypted (.db)", art.endswith(".db"), art)
check("status reports encrypted=False", st["encrypted"] is False)
# sanity: plaintext backup indeed contains the content (proves the test can detect plaintext)
with open(art, "rb") as f:
    raw = f.read()
check("plaintext artifact contains recognizable content (control)", b"assertion-content-SECRET" in raw)

print("== enabled: artifact is ciphertext, no plaintext, temp scrubbed ==")
os.environ["OMEM_BACKUP_ENCRYPT"] = "1"
ctl2 = _fresh_db(DB + "2")
os.environ["OMEM_DB"] = DB + "2"
bm2 = BackupManager(ctl2, backup_dir=BK, secrets=LocalSecretsProvider("master-B"))
st2 = bm2.run()
art2 = st2["last_successful"]["path"]
check("encrypted backup completes", st2["last_successful"] is not None)
check("artifact is .enc", art2.endswith(".enc"), art2)
check("status reports encrypted=True", st2["encrypted"] is True)
with open(art2, "rb") as f:
    enc_raw = f.read()
check("encrypted artifact contains NO recognizable plaintext",
      b"assertion-content-SECRET" not in enc_raw and b"SQLite format" not in enc_raw)
# no leftover plaintext temp in the backup dir
leftovers = [f for f in os.listdir(BK) if f.endswith(".tmp")]
check("no plaintext .tmp left in backup dir", leftovers == [], str(leftovers))

print("== restore-verify works with the correct key ==")
v = bm2.verify_restore(art2)
check("verify_restore succeeds on encrypted artifact", v.get("verified") is True, str(v))
check("verify reports encrypted=True", v.get("encrypted") is True)
# and no decrypt temp left behind
check("no .verify.tmp left after verify",
      [f for f in os.listdir(BK) if f.endswith(".verify.tmp")] == [])

print("== wrong key fails safe (no plaintext recovery) ==")
bm_wrong = BackupManager(ctl2, backup_dir=BK, secrets=LocalSecretsProvider("WRONG-KEY"))
vw = bm_wrong.verify_restore(art2)
check("wrong key cannot verify/restore", vw.get("verified") is False, str(vw))
check("wrong-key failure is an auth error, not a silent pass",
      "error" in vw)

print("== attacker with only the artifact cannot recover the key ==")
# the key is derived from the master secret (env), never written into the blob.
check("artifact does not contain the master secret", b"master-B" not in enc_raw)
check("artifact does not contain a raw AES key marker", b"OMEM_MASTER_KEY" not in enc_raw)

print("== config observability + insecure-default detection ==")
os.environ["OMEM_BACKUP_ENCRYPT"] = "1"
bm_def = BackupManager(ctl2, backup_dir=BK, secrets=LocalSecretsProvider("dev-master-key-change-me"))
os.environ["OMEM_ENV"] = "production"
es = bm_def.encryption_status()
check("encryption_status reports enabled + provider", es["enabled"] and es["provider"], str(es))
check("insecure default key in production is flagged", es["insecure_default_key"] is True, str(es))
os.environ["OMEM_ENV"] = "development"
check("dev default key not flagged as insecure in dev",
      bm_def.encryption_status()["insecure_default_key"] is False)
# never leaks key material
check("encryption_status never returns key material",
      "dev-master-key-change-me" not in str(es) and "master" not in {k for k in es})

def _try_fail(fn):
    try:
        fn(); return False
    except Exception:
        return True


print("== existing OAuth/connector string secret encryption unchanged ==")
sp = LocalSecretsProvider("oauth-master")
tok = sp.encrypt("ya29.oauth-access-token")
check("string encrypt/decrypt round-trips (OAuth path intact)",
      sp.decrypt(tok) == "ya29.oauth-access-token")
check("string ciphertext != plaintext", tok != "ya29.oauth-access-token")
check("wrong master cannot decrypt OAuth token",
      _try_fail(lambda: LocalSecretsProvider("other").decrypt(tok)))


print("== engine integrity ==")
import hashlib
h = {f: hashlib.sha256(open(os.path.join(HERE, "omem_engine", f), "rb").read()).hexdigest()
     for f in sorted(os.listdir(os.path.join(HERE, "omem_engine"))) if f.endswith(".py")}
baseline = {}
for line in open(os.path.join(HERE, "omem_engine", "ENGINE_HASHES.txt"),
                 encoding="utf-8"):
    if not line.strip() or line.startswith('#'):
        continue
    hsh, path = line.split()
    baseline[os.path.basename(path)] = hsh
check("frozen engine byte-identical", all(baseline.get(f) == v for f, v in h.items()))

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
