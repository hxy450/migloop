"""第 4 步验收:在 0723 上跑四个带起点的查找,看能不能到原始组多追的那几跳。"""
from __future__ import annotations

import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

p = service.locate_session("ff019d8a")
CASES = [
    ("conv-aboutus ≤v1 找 app_name", "search", {"q": "app_name", "agent": "conv-aboutus", "v": "1"}),
    ("conv-home ≤v1 找 @color/white", "search", {"q": "@color/white", "agent": "conv-home", "v": "1"}),
    ("主会话 生成→修复区间 找 执行疏漏", "search",
     {"q": "执行疏漏", "agent": "__main__:9b3105a2", "since_ts": "2026-07-24T06:28:00Z", "until_ts": "2026-07-26T20:00:00Z"}),
    ("主会话 同区间 找 icon_autofix", "search",
     {"q": "icon_autofix", "agent": "__main__:9b3105a2", "since_ts": "2026-07-24T06:28:00Z", "until_ts": "2026-07-26T20:00:00Z"}),
    ("file AboutUsPage 找 appInfo.label", "search", {"q": "appInfo.label", "file": "AboutUsPage.ets"}),
    ("没有起点", "search", {"q": "x"}),
]
for label, tool, args in CASES:
    text = service.atom_text(p, tool, args)
    print(f"\n===== {label}: {len(text)} 字")
    print("\n".join(text.splitlines()[:14]))
