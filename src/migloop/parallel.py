"""把一批互不依赖的纯函数任务分给几个子进程并行跑,结果与任务同序。

子进程用 ``python -c`` 直接起 worker,不走 multiprocessing —— 后者在 Windows(spawn)上会
重跑调用方的主模块,调用脚本没写 ``if __name__ == "__main__"`` 就会整个重跑一遍。任务与结果
经管道 pickle 往返,只适合内置类型组成的数据。

``Jobs(...).start()`` 立即返回(调用方继续干别的),``results()`` 收结果。任务总权重不够、
单核、冻结打包、``MIGLOOP_NO_POOL=1``,或某个子进程失败时,那一份在本进程串行补算。
"""
from __future__ import annotations

import importlib
import os
import pickle
import subprocess
import sys
import threading
import weakref
from typing import Any, Callable, List, Optional, Sequence

MAX_WORKERS = 12


def _resolve(target: str) -> Callable[..., Any]:
    module, name = target.split(":", 1)
    return getattr(importlib.import_module(module), name)


def worker() -> None:
    """子进程入口:stdin 读 pickle 的 (target, 任务表),stdout 写 pickle 的结果表。"""
    target, tasks = pickle.load(sys.stdin.buffer)
    fn = _resolve(target)
    out = [fn(*t) for t in tasks]
    sys.stdout.buffer.write(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
    sys.stdout.buffer.flush()


class Jobs:
    def __init__(self, target: str, tasks: Sequence[tuple], weights: Optional[Sequence[int]] = None,
                 min_weight: int = 0):
        self.target = target
        self.tasks = list(tasks)
        self.weights = list(weights) if weights is not None else [1] * len(self.tasks)
        self.min_weight = min_weight
        self.procs: List[tuple] = []
        self.feeder: Optional[threading.Thread] = None
        # 调用方中途抛错、没人来收结果时,子进程会卡在写管道上 —— 对象回收时一并结束
        weakref.finalize(self, Jobs._reap, self.procs)

    @staticmethod
    def _reap(procs: List[tuple]) -> None:
        for _bucket, proc in procs:
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass

    def start(self) -> "Jobs":
        tasks = self.tasks
        workers = min(MAX_WORKERS, os.cpu_count() or 1, len(tasks))
        if (workers < 2 or sum(self.weights) < self.min_weight or os.environ.get("MIGLOOP_NO_POOL")
                or getattr(sys, "frozen", False) or not sys.executable):
            return self
        buckets: List[List[int]] = [[] for _ in range(workers)]
        load = [0] * workers
        for k in sorted(range(len(tasks)), key=lambda i: -self.weights[i]):   # 重的先分、每次给最轻的那份
            w = load.index(min(load))
            buckets[w].append(k)
            load[w] += self.weights[k] or 1
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(here))       # migloop 包所在目录(或 .pyz)
        code = "import sys; sys.path.insert(0, %r); from migloop.parallel import worker; worker()" % root
        env = dict(os.environ, MIGLOOP_NO_POOL="1")
        flags = 0x08000000 if os.name == "nt" else 0        # CREATE_NO_WINDOW
        payloads = []
        for bucket in buckets:
            if not bucket:
                continue
            try:
                proc = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        env=env, creationflags=flags)
            except OSError:
                proc = None
            self.procs.append((bucket, proc))
            if proc is not None:
                payloads.append((proc, pickle.dumps((self.target, [tasks[k] for k in bucket]),
                                                    protocol=pickle.HIGHEST_PROTOCOL)))

        def feed() -> None:   # 子进程起来要零点几秒,写管道放后台,不挡调用方
            for proc, data in payloads:
                try:
                    proc.stdin.write(data)
                    proc.stdin.close()
                except OSError:
                    pass
        self.feeder = threading.Thread(target=feed, daemon=True)
        self.feeder.start()
        return self

    def results(self) -> List[Any]:
        tasks = self.tasks
        if not self.procs:
            fn = _resolve(self.target)
            return [fn(*t) for t in tasks]
        out: List[Any] = [None] * len(tasks)
        fn = None
        for bucket, proc in self.procs:
            got = None
            if proc is not None:
                try:
                    data = proc.stdout.read()
                    proc.stdout.close()
                    proc.wait()
                    if proc.returncode == 0:
                        got = pickle.loads(data)
                except (OSError, EOFError, pickle.UnpicklingError, ValueError):
                    got = None
            if got is None or len(got) != len(bucket):
                fn = fn or _resolve(self.target)
                got = [fn(*tasks[k]) for k in bucket]
            for k, item in zip(bucket, got):
                out[k] = item
        if self.feeder is not None:
            self.feeder.join()
        return out
