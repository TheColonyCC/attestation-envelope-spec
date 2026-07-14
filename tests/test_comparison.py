"""Tests for §18j ranking attack / comparison admissibility (tools/comparison.py).

Witnessed-red. The load-bearing test is TestSelectiveFilingIsACompleteAttack: an adversary who
forges NOTHING, files only TRUE forks, and files them only against a rival. Under the naive
"let anyone lower it" rule that attack works perfectly. Under the common-draw gate it does not
move the ranking at all.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import comparison as cmp  # noqa: E402


def _arm(aid, results, drawn=None, committed=True):
    a = {"id": aid, "results": results, "drawn": drawn or [r["probe_id"] for r in results]}
    if committed:
        a["commitment_sig"] = f"sig-{aid}"
    return a


def _r(pid, refuted=False, settled=True, sig=True):
    d = {"probe_id": pid, "settled": settled, "refuted": refuted}
    if sig:
        d["sig"] = f"sig-{pid}"
    return d


def _doc(arms):
    return {"domain": cmp.DOMAIN, "arms": arms}


class TestSelectiveFilingIsACompleteAttack:
    """THE tests. No forgery anywhere — every artifact below is genuine."""

    def test_filing_true_forks_only_against_a_rival_does_not_move_the_ranking(self):
        # Both arms answered p1 and p2. On the COMMON DRAW they are dead level: one fork each.
        # The adversary now files three MORE real forks against `rival` on probes it alone was
        # asked (p8, p9, p10) — every one of them true. Naively, rival now looks far worse.
        rival = _arm("rival", [_r("p1", refuted=True), _r("p2"),
                               _r("p8", refuted=True), _r("p9", refuted=True), _r("p10", refuted=True)])
        quiet = _arm("quiet", [_r("p1"), _r("p2", refuted=True)])
        r = cmp.check_comparison(_doc([rival, quiet]))

        assert r["state"] == "ranked"
        assert r["common_draw"] == ["p1", "p2"]
        # Dead level on the common draw — the three extra true forks bought the attacker NOTHING.
        by_arm = {s["arm"]: s["refuted_on_common"] for s in r["ranked"]}
        assert by_arm == {"rival": 1, "quiet": 1}
        # And the discarded evidence is NAMED, not silently dropped.
        assert r["discarded"]["rival"]["count"] == 3
        assert sorted(r["discarded"]["rival"]["probe_ids"]) == sorted(["p8", "p9", "p10"])

    def test_the_skew_is_reported_so_a_narrow_ranking_cannot_pass_as_a_broad_one(self):
        rival = _arm("rival", [_r("p1"), _r("p8", refuted=True), _r("p9", refuted=True)])
        quiet = _arm("quiet", [_r("p1")])
        r = cmp.check_comparison(_doc([rival, quiet]))
        assert r["draw_skew"] == round(1 - 1 / 3, 4)          # 2 of 3 probes were aimed
        assert any("SELECTIVE-" in n or "SELECTIVE" in n for n in r["notes"])

    def test_an_arm_cannot_improve_its_rank_by_refusing_to_answer(self):
        # `dodger` simply never answers p2, where it would have been refuted.
        # It does not thereby win — p2 leaves the common draw, and it gains nothing.
        honest = _arm("honest", [_r("p1"), _r("p2")])
        dodger = _arm("dodger", [_r("p1"), _r("p2", settled=False, sig=False)])
        r = cmp.check_comparison(_doc([honest, dodger]))
        assert r["common_draw"] == ["p1"]
        by_arm = {s["arm"]: s["refuted_on_common"] for s in r["ranked"]}
        assert by_arm == {"honest": 0, "dodger": 0}   # dodging buys a NARROWER rank, not a better one


class TestTheRefusal:
    """Not a warning. Not a down-weight. A refusal."""

    def test_no_common_draw_means_no_comparison_at_all(self):
        a = _arm("a", [_r("p1"), _r("p2")])
        b = _arm("b", [_r("p3"), _r("p4")])
        r = cmp.check_comparison(_doc([a, b]))
        assert r["state"] == "incomparable"
        assert r["ranked"] is None
        assert any("REFUSING TO EMIT A COMPARISON" in n for n in r["notes"])

    def test_the_refusal_says_not_refuted_is_not_passed(self):
        r = cmp.check_comparison(_doc([_arm("a", [_r("p1")]), _arm("b", [_r("p2")])]))
        joined = " ".join(r["notes"])
        assert "'Not refuted' is not 'passed'" in joined
        assert "not examined" in joined

    def test_the_verifier_can_never_say_fine(self):
        cases = [
            _doc([_arm("a", [_r("p1")]), _arm("b", [_r("p1")])]),
            _doc([_arm("a", [_r("p1")]), _arm("b", [_r("p2")])]),
            _doc([_arm("a", [_r("p1")])]),
            {"domain": "wrong", "arms": []},
        ]
        for d in cases:
            assert cmp.check_comparison(d)["state"] in {"incomparable", "ranked"}
            assert cmp.check_comparison(d)["state"] != "fine"


class TestObscurityEarnsNoRank:
    """The answer to 'it rewards obscurity'. The quiet arm is not ranked well — it is not ranked."""

    def test_an_uncommitted_arm_is_unrankable_not_lowered(self):
        good = _arm("committed-a", [_r("p1")])
        also = _arm("committed-b", [_r("p1")])
        lurker = _arm("lurker", [_r("p1")], committed=False)
        r = cmp.check_comparison(_doc([good, also, lurker]))
        assert r["state"] == "ranked"
        assert [u["arm"] for u in r["unrankable"]] == ["lurker"]
        assert "lurker" not in [s["arm"] for s in r["ranked"]]      # EXCLUDED, not scored
        assert any("Obscurity earns no rank" in u["reason"] for u in r["unrankable"])

    def test_a_lurker_cannot_win_a_leaderboard_by_having_no_enemies(self):
        # Only one arm ever committed. There is no leaderboard to win.
        r = cmp.check_comparison(_doc([
            _arm("committed", [_r("p1", refuted=True)]),
            _arm("lurker", [_r("p1")], committed=False),
        ]))
        assert r["state"] == "incomparable"
        assert r["ranked"] is None
        assert any("difference in FILING, not in QUALITY" in n for n in r["notes"])


class TestRankingItself:
    def test_on_a_common_draw_more_forks_ranks_worse(self):
        clean = _arm("clean", [_r("p1"), _r("p2")])
        forked = _arm("forked", [_r("p1", refuted=True), _r("p2", refuted=True)])
        r = cmp.check_comparison(_doc([clean, forked]))
        assert [s["arm"] for s in r["ranked"]] == ["clean", "forked"]

    def test_the_ranking_is_still_not_a_certificate(self):
        r = cmp.check_comparison(_doc([_arm("a", [_r("p1")]), _arm("b", [_r("p1")])]))
        assert any("divergence does not confirm" in n for n in r["notes"])

    def test_an_unsigned_result_does_not_enter_the_common_draw(self):
        a = _arm("a", [_r("p1"), _r("p2", sig=False)])
        b = _arm("b", [_r("p1"), _r("p2")])
        r = cmp.check_comparison(_doc([a, b]))
        assert r["common_draw"] == ["p1"]           # an unsigned answer is not an answer
