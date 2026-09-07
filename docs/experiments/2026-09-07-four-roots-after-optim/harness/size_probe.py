"""第 3 步验收:同一组调用在 0723 上的字数(对照 §4.8 的 33315 / 18832 / 12333)。"""
from __future__ import annotations

import sys

sys.path.insert(0, "C:/Users/hongy/projects/migloop/src")
from migloop import service  # noqa: E402

p = service.locate_session("ff019d8a")
CALLS = [("agent slice6 v14", "agent", {"id": "agent-aslice6-risk-d4a26e5b9d8d7364", "v": "14"}),
         ("agent conv-aboutus v4", "agent", {"id": "agent-aconv-aboutus-02480823d9520ea1", "v": "4"}),
         ("agent fixer-r1 v18 since15", "agent", {"id": "agent-a68daf720e780b4c2", "v": "18", "since": "15"}),
         ("agent slice6 v14 seen", "agent", {"id": "agent-aslice6-risk-d4a26e5b9d8d7364", "v": "14", "seen": "1"}),
         ("agent 主会话 v82 since81", "agent", {"id": "__main__:9b3105a2", "v": "82", "since": "81"}),
         ("agent 按名字 conv-aboutus", "agent", {"id": "conv-aboutus", "v": "4"}),
         ("file AboutUsPage", "file", {"path": "AboutUsPage.ets"}),
         ("sessions file=AboutUsPage", "sessions", {"path": "AboutUsPage.ets"}),
         ("blame changed v12", "blame", {"path": "AboutUsPage.ets", "v": "12", "changed": "1"})]
for label, tool, args in CALLS:
    text = service.atom_text(p, tool, args)
    print(f"{label:<30} {len(text):>7} 字 / {text.count(chr(10)) + 1:>4} 行")
text = service.atom_text(p, "agent", {"id": "agent-aslice6-risk-d4a26e5b9d8d7364", "v": "14"})
i = text.find("### v1")
print("\n--- slice6 v14 时间线开头 12 行:")
print("\n".join(text[i:].splitlines()[:12]))
