"""Tests for the threshold alert state machine (core.alerts)."""
from core.alerts import (HeldStates, classify, evaluate, evaluate_offline,
                         evaluate_rate, format_event, threshold_for)


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


def test_classify_hysteresis_holds_breach_inside_deadband():
    thr = {"max": 30}
    # Entering a breach uses the raw threshold (deadband only affects clearing).
    assert classify(29.9, thr, prev_condition="ok", hysteresis=0.5) == ("ok", None)
    assert classify(30.1, thr, prev_condition="ok", hysteresis=0.5) == ("high", 30)
    # While already high, stay high until the reading clears 30 - 0.5 = 29.5.
    assert classify(29.7, thr, prev_condition="high", hysteresis=0.5) == ("high", 30)
    assert classify(29.4, thr, prev_condition="high", hysteresis=0.5) == ("ok", None)


def test_classify_hysteresis_low_side():
    thr = {"min": 10}
    assert classify(9.4, thr, prev_condition="ok", hysteresis=0.5) == ("low", 10)
    assert classify(10.3, thr, prev_condition="low", hysteresis=0.5) == ("low", 10)   # within deadband
    assert classify(10.6, thr, prev_condition="low", hysteresis=0.5) == ("ok", None)  # cleared


def test_hysteresis_prevents_recovery_flap():
    thr = {"p": {"max": 30}}
    # Breach, then hover just below the limit but within the deadband.
    _, states = evaluate({"p": 31}, thr, {}, now=1000, hysteresis=0.5)
    events, states = evaluate({"p": 29.8}, thr, states, now=1100, hysteresis=0.5)
    assert events == []                                  # no flap to "recovery"
    # Drop clearly past the deadband -> a single recovery.
    events, _ = evaluate({"p": 29.0}, thr, states, now=1200, hysteresis=0.5)
    assert len(events) == 1 and events[0]["kind"] == "recovery"


def test_zero_hysteresis_matches_legacy_behaviour():
    thr = {"p": {"max": 30}}
    _, states = evaluate({"p": 31}, thr, {}, now=1000)            # default hysteresis 0.0
    events, _ = evaluate({"p": 29.9}, thr, states, now=1100)
    assert len(events) == 1 and events[0]["kind"] == "recovery"   # clears at the raw limit


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


def test_events_carry_transition_flag():
    # Transition into breach -> True; cooldown reminder -> False; recovery -> True.
    thresholds = {"p": {"max": 30}}
    events, states = evaluate({"p": 35}, thresholds, {}, now=1000, cooldown_sec=600)
    assert events[0]["transition"] is True
    events, states = evaluate({"p": 35}, thresholds, states, now=1700, cooldown_sec=600)
    assert events[0]["transition"] is False          # reminder, not a new incident
    events, _ = evaluate({"p": 20}, thresholds, states, now=1800)
    assert events[0]["kind"] == "recovery" and events[0]["transition"] is True


def test_evaluate_offline_per_probe_thresholds():
    # A dict threshold judges each probe against its own window; a probe missing
    # from the mapping falls back to the 300 s default.
    now = 10_000
    last = {"fast": now - 400, "sleepy": now - 400, "unmapped": now - 400}
    thr = {"fast": 300, "sleepy": 1500}
    events, states = evaluate_offline(
        last, {"fast": "online", "sleepy": "online", "unmapped": "online"},
        now=now, offline_after_sec=thr)
    kinds = {e["probe_id"]: e["kind"] for e in events}
    assert kinds == {"fast": "offline", "unmapped": "offline"}  # sleepy still fresh
    assert states == {"fast": "offline", "sleepy": "online", "unmapped": "offline"}
    # The same sleepy probe silent past its own window does go offline.
    events2, _ = evaluate_offline({"sleepy": now - 1600}, {"sleepy": "online"},
                                  now=now, offline_after_sec=thr)
    assert [e["kind"] for e in events2] == ["offline"]


def test_evaluate_rate_triggers_and_cooldown():
    # 5 degree rise over the window with a 2 degree limit -> one event, then the
    # cooldown suppresses repeats until it expires.
    events, states = evaluate_rate({"p": (25.0, 20.0)}, 2.0, 10, {}, now=1000, cooldown_sec=600)
    assert len(events) == 1
    ev = events[0]
    assert ev["kind"] == "rate" and ev["delta_c"] == 5.0 and ev["window_min"] == 10
    assert ev["transition"] is True
    events2, states2 = evaluate_rate({"p": (26.0, 21.0)}, 2.0, 10, states, now=1100, cooldown_sec=600)
    assert events2 == []                                      # still excessive, cooling down
    events3, _ = evaluate_rate({"p": (27.0, 22.0)}, 2.0, 10, states2, now=1700, cooldown_sec=600)
    assert len(events3) == 1 and events3[0]["transition"] is False  # reminder


def test_evaluate_rate_below_limit_and_disabled():
    events, states = evaluate_rate({"p": (21.0, 20.0)}, 2.0, 10, {}, now=1000)
    assert events == [] and states["p"]["condition"] == "ok"
    # rate_limit_c = 0 disables the check entirely (and clears any state).
    events2, states2 = evaluate_rate({"p": (99.0, 0.0)}, 0.0, 10, states, now=1000)
    assert events2 == [] and states2 == {}


def test_evaluate_rate_detects_falls_too():
    # A fast DROP (e.g. freezer probe pulled into ambient) also alerts.
    events, _ = evaluate_rate({"p": (15.0, 20.0)}, 2.0, 10, {}, now=1000)
    assert len(events) == 1 and events[0]["delta_c"] == -5.0


def test_format_event_rate_wording():
    subj, msg = format_event({"probe_id": "p", "kind": "rate", "temperature_c": 25.0,
                              "limit": 2.0, "delta_c": 5.0, "window_min": 10},
                             {"p": "Freezer"})
    assert "Freezer" in subj and "rose 5.0 °C in 10 min" in msg
    _, msg2 = format_event({"probe_id": "p", "kind": "rate", "temperature_c": 15.0,
                            "limit": 2.0, "delta_c": -5.0, "window_min": 10})
    assert "fell 5.0 °C in 10 min" in msg2


def test_format_event_held_breach_reminder_wording():
    # A reminder for a breach HELD by the hysteresis deadband: the reading is
    # back inside the raw limit, so the text must not claim it is "above the
    # maximum" — it has just not yet cleared the limit by the deadband.
    _, msg = format_event({"probe_id": "p", "kind": "high",
                           "temperature_c": 29.7, "limit": 30.0})
    assert "above the" not in msg and "deadband" in msg
    _, msg_low = format_event({"probe_id": "p", "kind": "low",
                               "temperature_c": 10.3, "limit": 10.0})
    assert "below the" not in msg_low and "deadband" in msg_low
    # A genuine breach reading keeps the plain wording.
    _, msg2 = format_event({"probe_id": "p", "kind": "high",
                            "temperature_c": 35.0, "limit": 30.0})
    assert "above the 30.0°C maximum" in msg2


def test_held_states_registry():
    held = HeldStates()
    assert held.get("p1") is None
    held.set_states({"p1": "high", "p2": "low", "p3": "ok", "p4": None})
    assert held.get("p1") == "high"
    assert held.get("p2") == "low"
    assert held.get("p3") is None       # only high/low are held conditions
    assert held.get("p4") is None
    # set_states replaces the registry, so cleared breaches are forgotten.
    held.set_states({"p2": "low"})
    assert held.get("p1") is None and held.get("p2") == "low"
    held.set_states({})
    assert held.get("p2") is None
