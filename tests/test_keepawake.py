"""Keeping the hub PC from idling into sleep.

A sleeping hub raises no alarms — not even "probe went silent", because the
thing that would notice is asleep — and a default Windows install sleeps after a
stretch with no mouse or keyboard, which describes a back-office PC exactly.
"""
import ctypes
import subprocess

from core.keepawake import ES_SYSTEM_REQUIRED, KeepAwake, supported


class _Cfg(dict):
    def get(self, k, d=None):
        return super().get(k, d)


def test_windows_resets_the_idle_timer_without_a_lasting_assertion(monkeypatch):
    calls = []

    class _K32:
        def SetThreadExecutionState(self, flags):
            calls.append(flags)
            return 1
    monkeypatch.setattr(ctypes, "windll", type("W", (), {"kernel32": _K32()})(),
                        raising=False)
    ka = KeepAwake(_Cfg(), platform="win32")
    ka.apply()
    # ES_SYSTEM_REQUIRED alone, never ES_CONTINUOUS: a one-shot reset that is
    # repeated, so a hub that crashes cannot leave the PC pinned awake.
    assert calls == [ES_SYSTEM_REQUIRED]
    assert ka.active


def test_macos_holds_caffeinate_tied_to_this_process_and_releases_it(monkeypatch):
    spawned = []

    class _Proc:
        def __init__(self, argv, **_kw):
            spawned.append(argv)
            self.terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True
    monkeypatch.setattr(subprocess, "Popen", _Proc)
    cfg = _Cfg()
    ka = KeepAwake(cfg, platform="darwin")
    ka.apply()
    ka.apply()                                   # still running: not spawned twice
    assert len(spawned) == 1
    assert spawned[0][:3] == ["caffeinate", "-i", "-w"]
    proc = ka._caffeinate

    cfg["keep_awake"] = False                    # turned off in Settings
    ka.apply()
    assert proc.terminated and not ka.active


def test_off_in_config_does_nothing(monkeypatch):
    monkeypatch.setattr(ctypes, "windll", None, raising=False)  # would raise if used
    ka = KeepAwake(_Cfg(keep_awake=False), platform="win32")
    ka.apply()
    assert not ka.active


def test_linux_is_left_to_the_os():
    assert not supported("linux")
    ka = KeepAwake(_Cfg(), platform="linux")
    ka.apply()
    assert not ka.active


def test_a_platform_error_does_not_end_the_thread(monkeypatch):
    ka = KeepAwake(_Cfg(), platform="win32", interval=0)
    rounds = []

    def boom():
        rounds.append(1)
        if len(rounds) >= 2:
            ka.stop()
        raise OSError("no windll here")
    monkeypatch.setattr(ka, "apply", boom)
    ka.run()
    assert len(rounds) == 2
