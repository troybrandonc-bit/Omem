"""Who may approve what.

The MIT gate already answers "was this approved, by a principal that is not the
agent". That is the property an auditor asks about, and it ships free.

What an organisation asks next is narrower and is what this adds: not everyone
who CAN approve SHOULD approve everything. The person who may clear a cache is
not the person who may move money, and in most companies that separation
already exists on paper long before any software enforces it. This turns the
paper version into the enforced version.

A policy is a list of rules, each naming what it covers and who may approve it:

    {"default": "deny",
     "rules": [
       {"action_type": "issue_refund", "approvers": ["finance@acme.com"]},
       {"risk_class": "high", "approvers": ["key:key_abc", "user:usr_7"]},
       {"risk_class": "medium", "approvers": ["*"]}
     ]}

An approver is matched against the principal the authentication layer
resolved, and against the name the credential holder supplied, because both are
recorded and an organisation may reasonably write its policy in terms of either.
The verified principal is tried first, and a policy that only ever names
principals is the stronger one to write.

The first matching rule decides. `default` applies when no rule matches, and
defaults to "allow" so that adding a policy for refunds does not silently
freeze every other action in the system at 3am.

This module knows nothing about licensing. The caller decides whether policy
applies at all, which keeps the gate's own logic free of commercial concerns
and makes both halves testable on their own.

Copyright 2026 Michael Brandon Clifford. Commercial licence required for
production use. See LICENSE-enterprise.
"""
from __future__ import annotations

import json

MAX_RULES = 200
RISK_CLASSES = ("low", "medium", "high")


class PolicyError(ValueError):
    """A policy that cannot be applied. Raised when a policy is WRITTEN rather
    than when an action is approved, because the failure a policy must never
    have is being discovered during an incident."""


def parse(raw) -> dict:
    """Validate a policy document and return it normalised.

    Everything is checked here so that evaluation later cannot fail: an
    approval path that can raise is an approval path that can block a repair
    at the worst possible moment."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception as e:
            raise PolicyError("policy is not valid JSON: %s" % e)
    if not isinstance(raw, dict):
        raise PolicyError("policy must be an object")

    default = str(raw.get("default", "allow")).lower()
    if default not in ("allow", "deny"):
        raise PolicyError("default must be 'allow' or 'deny'")

    rules_in = raw.get("rules")
    if rules_in is None:
        rules_in = []
    if not isinstance(rules_in, list):
        raise PolicyError("rules must be a list")
    if len(rules_in) > MAX_RULES:
        raise PolicyError("too many rules (max %d)" % MAX_RULES)

    rules = []
    for i, r in enumerate(rules_in):
        where = "rule %d" % (i + 1)
        if not isinstance(r, dict):
            raise PolicyError("%s must be an object" % where)
        action_type = r.get("action_type")
        risk_class = r.get("risk_class")
        if not action_type and not risk_class:
            raise PolicyError("%s must name an action_type or a risk_class" % where)
        if action_type is not None and not isinstance(action_type, str):
            raise PolicyError("%s: action_type must be a string" % where)
        if risk_class is not None and str(risk_class).lower() not in RISK_CLASSES:
            raise PolicyError("%s: risk_class must be one of %s"
                              % (where, ", ".join(RISK_CLASSES)))
        approvers = r.get("approvers")
        if not isinstance(approvers, list) or not approvers:
            raise PolicyError("%s must list at least one approver" % where)
        if not all(isinstance(a, str) and a.strip() for a in approvers):
            raise PolicyError("%s: approvers must be non-empty strings" % where)
        rules.append({
            "action_type": action_type or None,
            "risk_class": (str(risk_class).lower() if risk_class else None),
            "approvers": [a.strip() for a in approvers],
            "note": str(r.get("note") or "") or None,
        })
    return {"default": default, "rules": rules}


def _matches(rule: dict, action_type: str, risk_class: str) -> bool:
    if rule["action_type"] is not None and rule["action_type"] != action_type:
        return False
    if rule["risk_class"] is not None and rule["risk_class"] != risk_class:
        return False
    return True


def evaluate(policy: dict, action_type: str, risk_class: str,
             principal: str, claimed_name: str = "") -> tuple:
    """(permitted, reason). Reason is empty when permitted, and names the rule
    that refused when not, because "denied by policy" sends someone reading
    their own configuration to find out which line did it."""
    if not policy:
        return True, ""
    for i, rule in enumerate(policy.get("rules") or []):
        if not _matches(rule, action_type, risk_class):
            continue
        allowed = rule["approvers"]
        if "*" in allowed:
            return True, ""
        # The verified principal first: a policy written in terms of principals
        # cannot be satisfied by typing somebody's name into a request.
        if principal and principal in allowed:
            return True, ""
        if claimed_name and claimed_name in allowed:
            return True, ""
        covers = rule["action_type"] or ("%s-risk actions" % rule["risk_class"])
        return False, ("approval policy rule %d covers %s and does not list %s"
                       % (i + 1, covers, principal or claimed_name or "this approver"))
    if policy.get("default") == "deny":
        return False, ("approval policy has no rule for %s and defaults to deny"
                       % action_type)
    return True, ""


def describe(policy: dict) -> str:
    """A policy in one readable line per rule, for the operator who has to
    explain it to an auditor without opening a JSON file."""
    if not policy or not policy.get("rules"):
        return "no policy: any permitted approver may approve"
    out = []
    for r in policy["rules"]:
        covers = r["action_type"] or ("any %s-risk action" % r["risk_class"])
        who = "anyone permitted" if "*" in r["approvers"] else ", ".join(r["approvers"])
        out.append("%s may be approved by %s" % (covers, who))
    out.append("anything not listed: %s" % policy.get("default", "allow"))
    return "\n".join(out)
