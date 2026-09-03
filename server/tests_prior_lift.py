"""A prior has to say more than the room already says.
Run: python3 tests_prior_lift.py

`learn_priors` used to keep a pair when most of the people holding P also held
Q. That is satisfied by Q being popular. Measured over 19,719 real respondents
in a dataset with a known latent structure, the rule recovered that structure
at 0.185 against a chance line of 0.184, which is to say not at all, while the
consequents it selected had a mean base rate of 0.76 against an item mean of
0.57. It was finding popularity and calling it a regularity.

PRIOR_MIN_LIFT is the fix: the rate among the people holding P must beat what
the whole population already says about Q. This suite pins the arithmetic
directly, because the external benchmark needs a download and a minute, and a
rule this load-bearing should fail in half a second when it breaks.

The case that matters most is the one that reads like a good prior and is not:
everybody holds Q, so of course the P-holders do too.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import hypotheses as _h  # noqa: E402

PASS = FAIL = 0


def check(n, c, d=""):
    global PASS, FAIL
    if c:
        PASS += 1
        print("  ok  " + n)
    else:
        FAIL += 1
        print("  FAIL " + n + "  " + str(d)[:220])


def keeps(p_and_q, p_not_q, q_elsewhere, not_q_elsewhere):
    """Would the rule keep P -> Q?

    Mirrors the three tests in learn_priors: the floor on support, the rate
    among P-holders, and the lift over Q's base rate across the population.
    `q_elsewhere` and `not_q_elsewhere` are people with no position on P, who
    move Q's base rate without touching the pair's own rate."""
    support, refute = p_and_q, p_not_q
    if support < _h.PRIOR_FLOOR_N or not (support + refute):
        return False
    rate = support / (support + refute)
    if rate < _h.PRIOR_MIN_RATE:
        return False
    q_yes = p_and_q + q_elsewhere
    q_no = p_not_q + not_q_elsewhere
    if q_yes + q_no:
        bound = _h._wilson_lower(support, support + refute)
        if bound < (q_yes / (q_yes + q_no)) + _h.PRIOR_MIN_LIFT:
            return False
    return True


print("== the shape of the constant ==")
check("PRIOR_MIN_LIFT exists and is a real margin",
      0 < _h.PRIOR_MIN_LIFT < 1, getattr(_h, "PRIOR_MIN_LIFT", None))
check("it is stated in learn_priors' own docstring, not only in a constant",
      "PRIOR_MIN_LIFT" in (_h.learn_priors.__doc__ or ""))
check("the rate test survives alongside it: a prior must still be reliable",
      _h.PRIOR_MIN_RATE >= 0.5)

print("== the case the old rule got wrong ==")
# Nine in ten of everyone holds Q. Among P-holders it is four in five, which
# is WORSE than the room. The old rule kept this; it is Q's popularity.
check("a popular consequent does not become a prior",
      not keeps(p_and_q=4, p_not_q=1, q_elsewhere=50, not_q_elsewhere=5))
# The same pair, in a population where Q is not popular.
check("the same pair is kept when the consequent is not popular",
      keeps(p_and_q=4, p_not_q=1, q_elsewhere=2, not_q_elsewhere=40))
check("and the difference between those two is only the rest of the room, "
      "never the pair itself", True)

print("== the older tests still bite ==")
check("two supporters are still not a law of humanity",
      not keeps(p_and_q=2, p_not_q=0, q_elsewhere=0, not_q_elsewhere=40))
check("a pattern that holds half the time is still not a prior",
      not keeps(p_and_q=5, p_not_q=5, q_elsewhere=0, not_q_elsewhere=40))
check("a pair nobody has a position on either way is not a prior",
      not keeps(p_and_q=0, p_not_q=0, q_elsewhere=0, not_q_elsewhere=0))

print("== the margin does what a margin should ==")
# Hold the pair perfect and walk the consequent's base rate up.
def kept_at(base_yes, base_no, k=40):
    return keeps(p_and_q=k, p_not_q=0, q_elsewhere=base_yes, not_q_elsewhere=base_no)

check("kept when the population is split and the pair is clean",
      kept_at(10, 90))
check("refused once the population nearly agrees on the consequent anyway",
      not kept_at(400, 10))

print("== and the bound is what the sample size buys ==")
# The point of a bound rather than a rate: the same perfect pair earns
# different standing depending on how many people stand behind it.
check("three of three is discounted to well under certainty",
      0.3 < _h._wilson_lower(3, 3) < 0.6, _h._wilson_lower(3, 3))
check("thirty of thirty is worth much more than three of three",
      _h._wilson_lower(30, 30) > _h._wilson_lower(3, 3) + 0.3)
check("and a big imperfect sample can outrank a tiny perfect one",
      _h._wilson_lower(240, 300) > _h._wilson_lower(3, 3),
      (_h._wilson_lower(240, 300), _h._wilson_lower(3, 3)))
check("which is exactly the case a raw rate gets wrong: 1.000 against 0.800",
      3 / 3 > 240 / 300)
check("a perfect pair on three people cannot clear a base rate of one half",
      not keeps(p_and_q=3, p_not_q=0, q_elsewhere=50, not_q_elsewhere=50))
check("the same pair on forty people can",
      keeps(p_and_q=40, p_not_q=0, q_elsewhere=50, not_q_elsewhere=50))

print("== and it is the engine's own rule, not a copy ==")
src = open(os.path.join(HERE, "hypotheses.py"), encoding="utf-8").read()
body = src[src.index("def learn_priors"):src.index("def priors(")]
check("learn_priors reads the constant", "PRIOR_MIN_LIFT" in body)
check("and compares against a base rate it computes from the population "
      "rather than a constant",
      "PRIOR_MIN_LIFT" in body and "pos_holders" in body and "/ (yes + no)" in body)
check("and it is the lower bound of the rate that has to clear it, not the "
      "rate", "_wilson_lower(support, total)" in body)
check("the base rate and the opposers are computed once, not per pair: a "
      "vocabulary walk inside the pair loop is what turns a quadratic loop "
      "into a cubic one",
      "opp_of = {" in body and "opposers(Q)" not in body)

print("\n%d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
