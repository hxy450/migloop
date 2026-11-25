"""parallel.Jobs:子进程并行与本进程串行结果一致、同序;子进程失败时退回串行。"""

from __future__ import annotations

from migloop import parallel


def test_pool_matches_serial_and_keeps_order(monkeypatch) -> None:
    tasks = [("a2h-spec-zh",), ("nope",), ("migbot:a2h-plan",), ("a2h-execute",)] * 3
    monkeypatch.setattr(parallel.os, "cpu_count", lambda: 4)
    pooled = parallel.Jobs("migloop.stage_signals:normalize", tasks, [1] * len(tasks), 0).start()
    assert pooled.procs, "权重够、多核时应当真的起子进程"
    got = pooled.results()
    serial = parallel.Jobs("migloop.stage_signals:normalize", tasks, [1] * len(tasks), 10 ** 9).start()
    assert not serial.procs
    assert got == serial.results() == ["a2h-spec", None, "a2h-plan", "a2h-execute"] * 3


def test_failed_worker_falls_back_to_serial(monkeypatch) -> None:
    monkeypatch.setattr(parallel.os, "cpu_count", lambda: 2)
    jobs = parallel.Jobs("migloop.stage_signals:normalize", [("a2h-verify",), ("x",)], [1, 1], 0)
    monkeypatch.setattr(parallel.sys, "executable", parallel.sys.executable + "-missing")
    assert jobs.start().results() == ["a2h-verify", None]
