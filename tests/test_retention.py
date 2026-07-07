import datetime

import pandas as pd

from core.storage import retain_df, apply_retention, ensure_csv, append_row


def _mk(ts_list, pid="P1"):
    return pd.DataFrame({
        "timestamp": [t.isoformat(timespec="seconds") for t in ts_list],
        "temperature_c": [20.0] * len(ts_list),
        "temperature_f": [68.0] * len(ts_list),
        "humidity_pct": [""] * len(ts_list),
        "vpd_kpa": [""] * len(ts_list),
        "probe_id": [pid] * len(ts_list),
    })


NOW = datetime.datetime(2026, 1, 31, 12, 0, 0)


def test_keeps_recent_full_resolution_and_drops_ancient():
    recent = [NOW - datetime.timedelta(hours=i) for i in range(3)]        # < raw_days → keep all
    ancient = [NOW - datetime.timedelta(days=400)]                        # > downsample_days → drop
    kept = retain_df(_mk(recent + ancient), NOW, raw_days=14, downsample_days=365, interval_min=15)
    assert len(kept) == 3


def test_downsamples_older_rows_to_one_per_bucket():
    base = NOW - datetime.timedelta(days=20)  # older than raw_days → downsample tier
    same_bucket = [base + datetime.timedelta(seconds=30 * i) for i in range(10)]  # all within one 15-min bucket
    other_bucket = [base + datetime.timedelta(minutes=30)]                        # a different bucket
    kept = retain_df(_mk(same_bucket + other_bucket), NOW,
                     raw_days=14, downsample_days=365, interval_min=15)
    assert len(kept) == 2  # 10 collapse to 1, plus the other bucket


def test_downsample_is_per_probe():
    base = NOW - datetime.timedelta(days=20)
    a = _mk([base, base + datetime.timedelta(seconds=60)], pid="A")  # same bucket → 1
    b = _mk([base, base + datetime.timedelta(seconds=60)], pid="B")  # same bucket → 1
    kept = retain_df(pd.concat([a, b]), NOW, raw_days=14, downsample_days=365, interval_min=15)
    assert len(kept) == 2  # one per probe, not one total


def test_unparseable_timestamps_are_kept():
    df = _mk([NOW])
    df.loc[len(df)] = ["not-a-date", 20.0, 68.0, "", "", "P1"]
    kept = retain_df(df, NOW, raw_days=14, downsample_days=365, interval_min=15)
    assert (kept["timestamp"] == "not-a-date").any()


def test_apply_retention_rewrites_file(tmp_path):
    p = tmp_path / "log.csv"
    ensure_csv(p)
    now = datetime.datetime.now()
    append_row(p, now.isoformat(timespec="seconds"), 20, 68, probe_id="P1")
    append_row(p, (now - datetime.timedelta(days=400)).isoformat(timespec="seconds"), 5, 41, probe_id="P1")
    before, after = apply_retention(p, raw_days=14, downsample_days=365, interval_min=15, now=now)
    assert before == 2 and after == 1
    df = pd.read_csv(p)
    assert len(df) == 1
    assert list(df.columns)[0] == "timestamp"  # header intact


def test_apply_retention_noop_when_nothing_to_prune(tmp_path):
    p = tmp_path / "log.csv"
    ensure_csv(p)
    now = datetime.datetime.now()
    append_row(p, now.isoformat(timespec="seconds"), 20, 68, probe_id="P1")
    mtime_before = p.stat().st_mtime_ns
    before, after = apply_retention(p, raw_days=14, downsample_days=365, interval_min=15, now=now)
    assert before == after == 1
    assert p.stat().st_mtime_ns == mtime_before  # file not rewritten
