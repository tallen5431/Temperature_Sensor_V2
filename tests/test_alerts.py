"""Tests for the threshold alert state machine (core.alerts)."""
from core.alerts import classify, evaluate, evaluate_offline, format_event, threshold_for


def test_classify():
    assert classify(35, {"max": 30}) == ("high", 30)
    assert classify(5, {"min": 10}) == ("low", 10)
    assert classify(20, {"min": 10, "max": 30}) == ("ok", None)
    assert classify(100, {}) == ("ok", None)  # no thresholds -> never alerts


def test_threshold_fallback_to_default():
    thresholds = {"default": {"max": 25}, "p2": {"max": 40}}
    assert threshold_for(thresholds, "p1") == {"max": 25}   # falls back
    assert threshold_for(thresholds, "p2") == {"max": 40}   # specific wins


def test_transition_into_breach_emits_once():
    thresholds = {"p": {"max": 30}}
    events, states = evaluate({"p": 35}, thresholds, {}, now=1000)
    assert len(events) == 1 and events[0]["kind"] == "high"
    # Still in breach, before cooldown -> no repeat
    events2, states2 = evaluate({"p": 36}, thresholds, states, now=1100, cooldown_sec=1800)
    assert events2 == []


def test_cooldown_reminder():
    thresholds = {"p": {"max": 30}}
    _, states = evaluate({"p": 35}, thresholds, {}, now=1000, cooldown_sec=600)
    events, _ = evaluate({"p": 35}, thresholds, states, now=1700, cooldown_sec=600)  # 700s later
    assert len(events) == 1 and events[0]["kind"] == "high"  # reminder fired


def test_recovery_event():
    thresholds = {"p": {"max": 30}}
    _, states = evaluate({"p": 35}, thresholds, {}, now=1000)
    events, states2 = evaluate({"p": 20}, thresholds, states, now=1100)
    assert len(events) == 1 and events[0]["kind"] == "recovery"
    # Once recovered, staying normal emits nothing
    events2, _ = evaluate({"p": 20}, thresholds, states2, now=1200)
    assert events2 == []


def test_recovery_can_be_disabled():
    thresholds = {"p": {"min": 10}}
    _, states = evaluate({"p": 5}, thresholds, {}, now=1000)
    events, _ = evaluate({"p": 20}, thresholds, states, now=1100, notify_recovery=False)
    assert events == []


def test_probe_without_threshold_never_alerts():
    events, states = evaluate({"p": 999}, {}, {}, now=1000)
    assert events == []


def test_format_event_uses_friendly_name():
    subj, msg = format_event({"probe_id": "p1", "kind": "high", "temperature_c": 35.0, "limit": 30.0},
                             {"p1": "Freezer"})
    assert "Freezer" in subj and "HIGH" in subj
    assert "35.0" in msg and "30.0" in msg


def test_offline_transition_and_recovery():
    now = 10_000
    # p1 silent for 10 min (> 300s) -> offline; p2 fresh -> online
    last = {"p1": now - 600, "p2": now - 10}
    events, states = evaluate_offline(last, {}, now=now, offline_after_sec=300)
    kinds = {e["probe_id"]: e["kind"] for e in events}
    assert kinds["p1"] == "offline"
    assert "p2" not in kinds  # p2 started online; no transition emitted
    assert states == {"p1": "offline", "p2": "online"}
    # p1 reports again -> back online
    events2, states2 = evaluate_offline({"p1": now, "p2": now}, states, now=now, offline_after_sec=300)
    assert {e["probe_id"]: e["kind"] for e in events2} == {"p1": "online"}


def test_offline_probe_drops_out_of_window():
    # A probe absent from last_epochs (aged out) is forgotten, not alerted forever.
    events, states = evaluate_offline({}, {"old": "offline"}, now=10_000, offline_after_sec=300)
    assert events == [] and states == {}


def test_format_event_offline_and_online():
    subj, msg = format_event({"probe_id": "p", "kind": "offline", "age_sec": 660}, {"p": "Garage"})
    assert "OFFLINE" in subj and "Garage" in subj and "11" in msg  # 660s -> 11 min
    subj2, _ = format_event({"probe_id": "p", "kind": "online"}, {"p": "Garage"})
    assert "back online" in subj2.lower()
