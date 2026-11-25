"""verify 的设备 / 装包 / 截图识别要认 shell 变量与引号写法。

移植自 hmigbot-plus tests/web/test_insight1_audit.py(9bf4d4be、c70d9154)。codex 资源包写的是
`HDC=…/hdc; "$HDC" install -r …`、`BM=/x/bm; "$BM" install -p …`,命令里没有字面 `hdc install`,
真装了两次的 run 被判成「未装包」。migloop 的审计引擎按调用回执认能力(audit_events.capabilities),
这里钉住同一批写法;证据不足时它报 info「证据不足」,不再是 warn。
"""

from __future__ import annotations

from typing import Any

from migloop.audit import build_audit
from migloop.audit_events import capabilities

#: 走完整条管线的阶段序 —— verify 深检要评就得先走到 verify。
_PIPELINE_DONE = [{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"},
                  {"stage": "a2h-execute"}, {"stage": "a2h-verify"}]


def _trace(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"stages": _PIPELINE_DONE, "agents": [],
                            "lineage": {"agents": [], "specs": [], "files": []}}
    base.update(over)
    return base


def _verify_hits(*cmds: str) -> set[str]:
    trace = _trace(tools=[{"name": "Bash", "brief": c, "ok": True, "stage": "a2h-verify"} for c in cmds])
    return {f["rule"] for f in build_audit(trace)["findings"]}


def _caps(cmd: str) -> set[str]:
    return set(capabilities("Bash", {"command": cmd}))


def test_verify_install_via_hdc_variable() -> None:
    """codex 资源包把 hdc 放进 shell 变量调(#319 实录):命令里没有字面
    `hdc install`,真装真截图的 run 不能被判成「未装包 / 未截图」。"""
    hit = _verify_hits(
        'HDC=/x/hdc; "$HDC" target boot; '
        '"$HDC" install -r entry/build/default/outputs/default/entry-default-unsigned.hap; '
        '"$HDC" shell snapshot_display -f /tmp/a.jpeg')
    assert not {"verify-no-emulator", "verify-no-install", "verify-no-screenshot"} & hit


def test_verify_no_install_still_fires_without_install() -> None:
    """变量形式认得出设备,但确实没装包时照报 —— 不能为了消误报放水。"""
    hit = _verify_hits('HDC=/x/hdc; "$HDC" target boot')
    assert "verify-no-emulator" not in hit
    assert "verify-no-install" in hit


def test_verify_install_via_bm_variable() -> None:
    """#336:装包动词谁调的都算 —— bm 也常放进 shell 变量调(codex 实录
    `"$BM" install -p …`),bm 后面是引号不是空白,字面 `bm install` 认不出。"""
    for cmd in ('BM=/x/bm; "$BM" install -p /data/out.hap', "${BM} install -p /data/out.hap",
                "$bm install -p /data/out.hap", "'bm' install -p /data/out.hap"):
        assert "install" in _caps(cmd), cmd
        assert "verify-no-install" not in _verify_hits("hdc target boot", cmd), cmd


def test_verify_no_install_not_fooled_by_non_device_install() -> None:
    """放宽 bm 的写法不能把非装包的 install 也放进来:ohpm/npm/安装脚本都不算。"""
    for cmd in ("ohpm install", "npm install", "./install.sh", "$OHPM install",
                'BM=/x/bm; "$BM" list', "hdc target boot"):
        assert "install" not in _caps(cmd), cmd
        assert "verify-no-install" in _verify_hits("hdc target boot", cmd), cmd


def test_verify_screenshot_via_variable_hdc() -> None:
    """截图一族与装包同口径:`"$HDC" shell screenCap` / `${HDC} shell snapshot_display`
    这类变量调法也要认;没截图照报。"""
    for cmd in ('"$HDC" shell uitest screenCap -p /tmp/a.png',
                "${HDC} shell snapshot_display -f /tmp/a.jpeg",
                "$HDC shell screencap -p a.png"):
        assert "verify-no-screenshot" not in _verify_hits("hdc target boot", cmd), cmd
    assert "verify-no-screenshot" in _verify_hits("hdc target boot", '"$HDC" shell ls /data')


def test_verify_install_and_screenshot_vocabulary() -> None:
    """装包看 install 动词(谁调的不重要),截图认 snapshot/screencap 一族。"""
    for cmd in ('"$HDC" install -r out.hap', "${HDC} install out.hap", "hdc install out.hap",
                "bm install -p /data/out.hap", "hvigorw install-hap --mode module"):
        assert "verify-no-install" not in _verify_hits("hdc target boot", cmd), cmd
    for cmd in ("hdc shell uitest screenCap -p /tmp/a.png", "hdc shell screencap -p a.png",
                '"$HDC" shell snapshot_display -f a.jpeg', "hdc shell screenshot > a.png"):
        assert "verify-no-screenshot" not in _verify_hits("hdc target boot", cmd), cmd


def test_spec_main_write_is_not_a_migloop_policy() -> None:
    """9bf4d4be 让 spec-main-write 不对 codex 包报警;migloop 的审计引擎整条规则都不评
    (由谁写规格是流水线策略,不是通用缺陷),两种格式都不出项。"""
    lineage = {"agents": [{"agent_id": "an1", "stage": "a2h-spec",
                           "type": "a2h-android-analyzer", "n_spec_w": 0}],
               "specs": [], "files": []}
    stages = [{"stage": "a2h-run"}, {"stage": "a2h-spec"}, {"stage": "a2h-plan"}]
    for meta in ({}, {"session_format": "codex"}):
        result = build_audit(_trace(stages=stages, lineage=lineage, meta=meta))
        assert "spec-main-write" not in {f["rule"] for f in result["findings"]}
        assert {"rule": "spec-main-write", "status": "not_applicable",
                "reason": "由谁写规格是流水线策略，不是通用缺陷"} in result["assessments"]
