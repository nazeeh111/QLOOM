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
    calls = []
    sleeps = []

    def killpg(pid, sig):
        calls.append((pid, sig))
        if sig == 0 and sum(s == 0 for _, s in calls) > delayed_probes:
            raise ProcessLookupError

    monkeypatch.setattr(baselines.os, "killpg", killpg)
    monkeypatch.setattr(baselines, "monotonic", lambda: 0.0)
    monkeypatch.setattr(baselines, "sleep", sleeps.append)
    process = SimpleNamespace(pid=123, communicate=Mock())

    baselines._terminate_worker(process)

    process.communicate.assert_called_once_with()
    assert calls[0] == (123, signal.SIGKILL)
    assert calls[1:] == [(123, 0)] * (delayed_probes + 1)
    assert sleeps == [0.01] * delayed_probes


def test_reports_unreaped_group_instead_of_claiming_cleanup(monkeypatch):
    clock = iter([0.0, 1.0])
    monkeypatch.setattr(baselines.os, "killpg", lambda *_: None)
    monkeypatch.setattr(baselines, "monotonic", lambda: next(clock))
    sleep = Mock()
    monkeypatch.setattr(baselines, "sleep", sleep)
    process = SimpleNamespace(pid=123, communicate=Mock())

    with pytest.raises(RuntimeError, match="worker group was not reaped"):
        baselines._terminate_worker(process)

    process.communicate.assert_called_once_with()
    sleep.assert_not_called()
