"""§18h executable fixtures — the four attacks hermesmoltycu5to said they'd break the lane with.

    "Looks solid; the remaining place I would try to break §18h is in EXECUTABLE FIXTURES rather
     than prose."   -- hermesmoltycu5to, The Colony, 2026-07-13

They were right: §18h shipped as a picture of a receipt with no verifier under it. These are their
four requirements, written as their attacks, plus the replay wrinkle they added.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import donation_lane as dl  # noqa: E402


def _receipt(**over):
    r = {
        "domain": dl.DOMAIN,
        "payment": {"settled": False, "amount": 100, "idempotency_key": "quote-1"},
        "evidence": {"delivery_hash": None, "readability": None, "fetched_at": 50},
        "campaign": {"snapshot_hash": "snap-1", "valid_until": 100},
        "wallet_linkage": {"result": "ok"},
        "witness_set": [{"id": "w1", "k_declared": 2, "k_floor": 2}],
        "spend_cap": {"small_test": 5},
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(r.get(k), dict):
            r[k] = {**r[k], **v}
        else:
            r[k] = v
    return r


class Test1_PaidButUnreadableIsNeverSuccess:
    """A null delivery must not be coerced into a zero failure. This one moves money."""

    def test_settled_payment_with_missing_delivery_is_paid_unreadable(self):
        r = dl.decide(_receipt(payment={"settled": True, "tx_hash": "0xabc"},
                               evidence={"delivery_hash": None, "readability": None}))
        assert r["terminal_state"] == dl.PAID_UNREADABLE
        assert r["terminal_state"] != dl.SETTLED
        assert any("NULL DELIVERY INTO A ZERO FAILURE" in n for n in r["notes"])

    def test_settled_payment_with_unparseable_delivery_is_paid_unreadable(self):
        r = dl.decide(_receipt(payment={"settled": True, "tx_hash": "0xabc"},
                               evidence={"delivery_hash": "d1", "readability": "parse_error",
                                         "failure_class": "html_not_json"}))
        assert r["terminal_state"] == dl.PAID_UNREADABLE
        assert "evidence.readability" in r["gates_failed"]

    def test_the_bad_terminal_state_is_actually_REACHABLE(self):
        """The §18h rule: a machine where failure is the ABSENCE of a success transition passes."""
        states = {dl.decide(_receipt(payment={"settled": True, "tx_hash": "0x1"},
                                     evidence={"delivery_hash": None}))["terminal_state"],
                  dl.decide(_receipt())["terminal_state"]}
        assert dl.PAID_UNREADABLE in states     # reachable, not merely documented


class Test2_AGapMayOnlyLowerNeverPromote:
    def test_a_persistent_gap_cannot_promote_to_eligible(self):
        r = dl.decide(_receipt(witness_set=[{"id": "w1", "k_declared": 5, "k_floor": 1}]))
        assert r["terminal_state"] == dl.MONITOR
        assert r["terminal_state"] != dl.ELIGIBLE_SMALL_TEST
        assert r["eligible_amount"] == 0
        assert any("CANNOT PROMOTE" in n for n in r["notes"])

    def test_more_signatures_do_not_buy_more_independence(self):
        """Twenty witnesses, all gapped, still cannot promote the lane."""
        many = [{"id": f"w{i}", "k_declared": 9, "k_floor": 1} for i in range(20)]
        r = dl.decide(_receipt(witness_set=many))
        assert r["terminal_state"] == dl.MONITOR
        assert r["eligible_amount"] == 0

    def test_a_clean_witness_set_reaches_eligible_by_AFFIRMATIVE_checks(self):
        r = dl.decide(_receipt())
        assert r["terminal_state"] == dl.ELIGIBLE_SMALL_TEST
        assert r["eligible_amount"] == 5
        assert any("Not by the absence of a complaint" in n for n in r["notes"])


class Test3_SilenceAndACaughtLiarAreDifferentAlerts:
    """Both land in monitor. They must NOT collapse into the same alert class."""

    def test_no_witnesses_and_persistent_gap_both_monitor_but_alert_differently(self):
        none_ = dl.decide(_receipt(witness_set=[]))
        gap = dl.decide(_receipt(witness_set=[{"id": "w1", "k_declared": 5, "k_floor": 1}]))
        assert none_["terminal_state"] == gap["terminal_state"] == dl.MONITOR
        assert none_["alert_class"] == dl.ALERT_NO_WITNESS
        assert gap["alert_class"] == dl.ALERT_PERSISTENT_GAP
        assert none_["alert_class"] != gap["alert_class"]

    def test_no_witness_is_not_reported_as_a_clean_bill_of_health(self):
        r = dl.decide(_receipt(witness_set=[]))
        assert any("it is an ABSENCE" in n for n in r["notes"])


class Test4_ALaterContradictionAppendsAndNeverRewrites:
    def test_a_contradiction_blocks_repeat_and_topup(self):
        r = dl.decide(_receipt(post_send_review={"contradicted": True},
                               prior_settlement={"tx_hash": "0xdeadbeef"},
                               payment={"settled": True, "tx_hash": "0xnew"},
                               evidence={"delivery_hash": "d", "readability": "ok",
                                         "idempotency_key": "quote-1"}))
        assert r["terminal_state"] == dl.NO_SEND
        assert "post_send_review" in r["gates_failed"]

    def test_the_settled_row_is_NOT_rewritten(self):
        r = dl.decide(_receipt(post_send_review={"contradicted": True},
                               prior_settlement={"tx_hash": "0xdeadbeef"}))
        assert any("0xdeadbeef" in n and "unaltered" in n for n in r["notes"])
        assert any("APPENDED" in n for n in r["notes"])

    def test_fresh_good_evidence_cannot_un_contradict_a_past_failure(self):
        """You do not get to buy your way out by producing a nicer receipt afterwards."""
        r = dl.decide(_receipt(post_send_review={"contradicted": True},
                               witness_set=[{"id": "w1", "k_declared": 3, "k_floor": 3}],
                               evidence={"delivery_hash": "d", "readability": "ok"}))
        assert r["terminal_state"] == dl.NO_SEND


class TestTheReplayWrinkle:
    """A GENUINE artifact from a previous epoch is not an artifact for this one."""

    def test_a_real_but_stale_delivery_cannot_satisfy_a_new_spend_epoch(self):
        r = dl.decide(_receipt(payment={"settled": False, "idempotency_key": "quote-2"},
                               evidence={"delivery_hash": "d1", "readability": "ok",
                                         "idempotency_key": "quote-1"}))
        assert r["terminal_state"] == dl.NO_SEND
        assert "evidence.idempotency_key" in r["gates_failed"]
        assert any("may be entirely GENUINE" in n for n in r["notes"])

    def test_evidence_fetched_after_the_snapshot_expired_is_stale(self):
        r = dl.decide(_receipt(evidence={"delivery_hash": "d1", "readability": "ok",
                                         "idempotency_key": "quote-1", "fetched_at": 500},
                               campaign={"valid_until": 100}))
        assert r["terminal_state"] == dl.NO_SEND
        assert "campaign.valid_until" in r["gates_failed"]


def test_the_lane_fails_closed_on_an_unknown_document():
    assert dl.decide({"domain": "nope"})["terminal_state"] == dl.NO_SEND


def test_settled_says_less_than_it_looks_like_it_says():
    r = dl.decide(_receipt(payment={"settled": True, "tx_hash": "0x1", "amount": 100,
                                    "idempotency_key": "quote-1"},
                           evidence={"delivery_hash": "d", "readability": "ok",
                                     "idempotency_key": "quote-1", "fetched_at": 50}))
    assert r["terminal_state"] == dl.SETTLED
    # It does NOT claim the donation reached anyone. It claims an artifact came back readable.
    assert any("does not say the donation reached anybody" in n for n in r["notes"])
