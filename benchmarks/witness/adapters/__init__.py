"""The adapter contract: how a memory system takes the stand.

An adapter maps the benchmark's events onto ONE system's own, native way of
doing things -- its normal write path, its normal correction path, its normal
query path. Nothing is routed around a system's design to make it look better
or worse; if its design has no way to express an operation, the adapter says
so by leaving the capability out, and every probe needing that capability is
reported UNSUPPORTED rather than silently passed or failed.

Capabilities a probe may require:

    holdings     what the system currently asserts about an entity
    state        a direct yes/no on one claim about one entity
    history      what was ever asserted, including what no longer holds
    conflicts    whether the system can SHOW a disagreement it holds
    rules        declared inference with truth maintenance
    provenance   each held memory can name the source event it came from

`holdings` is the floor: a memory system that cannot say what it holds about
an entity is not measurable at all.
"""


class AdapterUnavailable(RuntimeError):
    """The adapter's system cannot run here (missing package, missing keys).

    Raised at construction, never mid-run: a benchmark that dies halfway
    through produces numbers nobody should trust.
    """


class Adapter:
    name = "base"
    capabilities = frozenset()

    # -- events ----------------------------------------------------------
    def tell(self, event):
        raise NotImplementedError

    def retract(self, event):
        raise NotImplementedError

    def update(self, event):
        raise NotImplementedError

    def rule(self, event):
        raise NotImplementedError

    # -- probes ----------------------------------------------------------
    def holdings(self, about):
        """Currently asserted content about the entity (or entity set).
        Returns [{"text": str, "sources": [event_id, ...]}]."""
        raise NotImplementedError

    def state(self, about, claim):
        """'BELIEVED' or 'NOT_HELD' for one claim about one entity."""
        raise NotImplementedError

    def history(self, about):
        """Everything ever asserted about the entity, open or closed.
        Same shape as holdings()."""
        raise NotImplementedError

    def conflict_visible(self, about):
        """True when the system can show an open disagreement about the
        entity."""
        raise NotImplementedError
