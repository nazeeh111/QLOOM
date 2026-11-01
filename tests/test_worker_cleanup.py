"""Worker cleanup contracts with no real processes or process-group signals."""
import os
import signal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import qloom.baselines as baselines


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX worker-group contract")


@pytest.mark.parametrize("delayed_probes", [0, 3])
def test_waits_for_all_terminated_descendants(monkeypatch, delayed_probes):
    group = {"alive": True, "probes": 0}
    signals = []

    def killpg(pid, sig):
        assert pid == 123
        if sig == signal.SIGKILL:
            signals.append(sig)
        else:
            assert sig == 0
            group["probes"] += 1
            if group["probes"] > delayed_probes:
                group["alive"] = False
                raise ProcessLookupError

    monkeypatch.setattr(baselines.os, "killpg", killpg)
    monkeypatch.setattr(baselines, "monotonic", lambda: 0.0)
    monkeypatch.setattr(baselines, "sleep", lambda _: None)
    process = SimpleNamespace(pid=123, communicate=Mock())

    baselines._terminate_worker(process)

    process.communicate.assert_called_once_with()
    assert signals == [signal.SIGKILL]
    assert not group["alive"], "cleanup returned while descendants still existed"


def test_reports_unreaped_group_instead_of_claiming_cleanup(monkeypatch):
    clock = [0.0]

    def monotonic():
        clock[0] += 0.25
        return clock[0]

    monkeypatch.setattr(baselines.os, "killpg", lambda *_: None)
    monkeypatch.setattr(baselines, "monotonic", monotonic)
    monkeypatch.setattr(baselines, "sleep", lambda _: None)
    process = SimpleNamespace(pid=123, communicate=Mock())

    with pytest.raises(RuntimeError, match="worker group was not reaped"):
        baselines._terminate_worker(process)

    process.communicate.assert_called_once_with()
    assert clock[0] <= 1.5, "cleanup must remain bounded when reaping never completes"
