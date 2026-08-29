"""OMEM on the stand, through its public SDK against a running server.

Events map onto the same verbs any OMEM caller uses: remember, retract,
supersede, declare_rule + infer. Sources ride in `because` as "event:<id>",
which is exactly what the field is for, so provenance is read back from the
same /why every user sees rather than from anything private to the benchmark.
"""
from . import Adapter


class OmemAdapter(Adapter):
    name = "omem"
    capabilities = frozenset(
        {"holdings", "state", "history", "conflicts", "rules", "provenance"})

    def __init__(self, mem):
        """`mem` is an omem.Memory bound to a project this run may write to."""
        self.mem = mem
        self._aid = {}   # event id -> assertion id, for retract/update targets

    # -- events ----------------------------------------------------------
    def tell(self, event):
        about = event["subjects"]
        if len(about) == 1:
            about = about[0]
        r = self.mem.remember(event["speaker"], about, event["claim"],
                              label="event:" + event["id"])
        self._aid[event["id"]] = r["id"]

    def retract(self, event):
        self.mem.retract(self._aid[event["refers_to"]], agent=event["speaker"])

    def update(self, event):
        target = self._aid[event["refers_to"]]
        r = self.mem._req(
            "POST", "/v1/assertions/%s/supersede" % target,
            {"new": {"agent": event["speaker"], "subjects": event["subjects"],
                     "proposition": event["claim"],
                     "because": "event:" + event["id"]}})
        self._aid[event["id"]] = r.get("id", target)

    def rule(self, event):
        self.mem.declare_rule(
            when=[tuple(p) for p in event["when"]],
            then=tuple(event["then"]), agent=event["speaker"])
        self.mem.infer()

    # -- probes ----------------------------------------------------------
    def _rows(self, about, only_open):
        entities = set([about] if isinstance(about, str) else about)
        rows = self.mem._req("GET", "/v1/assertions").get("data", [])
        out = []
        for a in rows:
            if not entities & set(a.get("subjects") or []):
                continue
            if only_open and not a.get("open"):
                continue
            if only_open and a.get("is_retraction"):
                continue    # a retraction record is bookkeeping, not testimony
            out.append(a)
        return out

    @staticmethod
    def _sources(row):
        lbl = row.get("label") or ""
        return [lbl[len("event:"):]] if lbl.startswith("event:") else []

    def holdings(self, about):
        return [{"text": a["proposition"], "sources": self._sources(a)}
                for a in self._rows(about, only_open=True)]

    def state(self, about, claim):
        s = self.mem.believes(about, claim)
        return "BELIEVED" if s == "BELIEVED_TRUE" else "NOT_HELD"

    def history(self, about):
        return [{"text": a["proposition"], "sources": self._sources(a)}
                for a in self._rows(about, only_open=False)]

    def conflict_visible(self, about):
        entities = set([about] if isinstance(about, str) else about)
        for c in self.mem.conflicts().get("data", []):
            for side in c.get("sides", []):
                if entities & set(side.get("subjects") or []):
                    return True
        return False
