"""shell 命令读写解析 —— 纯 session、零磁盘的行为契约。

原则:分段优先(heredoc/引号/命令替换先摘干净),再按「命令词 + 实参」白名单认;
认不准一律放弃。每条用例都来自 0723/pod730 真实命令或本轮实测踩过的误判。
"""

from __future__ import annotations

from migloop.shellparse import parse_shell


# ---- 内容读取:输出就是文件内容,进上下文 ----

def test_cat_simple() -> None:
    r = parse_shell("cat spec/baseline/feature-plan.md")
    assert r.content_reads == ["spec/baseline/feature-plan.md"]
    assert r.writes == []


def test_sed_range_read() -> None:
    r = parse_shell("sed -n '1814,2012p' spec/ref/AIPPT_spec.md")
    assert r.content_reads == ["spec/ref/AIPPT_spec.md"]


def test_head_in_chain() -> None:
    r = parse_shell('echo "=== registry 前 40 行 ===" && head -40 spec/placeholder-registry.md && echo done')
    assert r.content_reads == ["spec/placeholder-registry.md"]


def test_pipe_left_side_still_read() -> None:
    # cat a | grep b:a 的命中行经管道进了上下文 —— 文件级读成立
    r = parse_shell("cat spec/ui-manifest.md | grep -n 'P-ID'")
    assert "spec/ui-manifest.md" in r.content_reads


def test_grep_content_mode() -> None:
    r = parse_shell("grep -n TODO spec/x.md")
    assert r.content_reads == ["spec/x.md"]


def test_powershell_get_content() -> None:
    r = parse_shell("Get-Content -LiteralPath 'spec\\x.md' -Raw")
    assert r.content_reads == ["spec/x.md"]


def test_command_substitution_inner_read() -> None:
    r = parse_shell('echo "$(cat inner.md)"')
    assert r.content_reads == ["inner.md"]


def test_quoted_path_with_space() -> None:
    r = parse_shell("cat 'spec/with space.md'")
    assert r.content_reads == ["spec/with space.md"]


# ---- 不是读:名字/存在性/统计/中性命令(全部来自实测误判) ----

def test_git_commit_message_path_is_not_read() -> None:
    r = parse_shell('git add -A && git commit -q -m "feat: spec/x.md 完成双 PASS"')
    assert r.content_reads == [] and r.writes == []


def test_existence_polling_is_not_read() -> None:
    r = parse_shell('for i in $(seq 1 70); do if [ -f spec/baseline/plans/handoffs/batch_01_handoff.md ]; '
                    'then echo PRODUCED; fi; sleep 5; done')
    assert r.content_reads == []


def test_grep_names_only_not_read() -> None:
    r = parse_shell("grep -l pattern spec/x.md && grep -c foo spec/y.md")
    assert r.content_reads == []


def test_ls_probe_not_read() -> None:
    r = parse_shell("ls -la CLAUDE.md 2>/dev/null && wc -l spec/x.md")
    assert r.content_reads == []


def test_variable_path_skipped() -> None:
    r = parse_shell('cat "$SPEC_DIR/x.md" && cat $f')
    assert r.content_reads == []


def test_glob_arg_skipped() -> None:
    r = parse_shell("cat spec/baseline/features/F*.md")
    assert r.content_reads == []


def test_unknown_command_args_ignored() -> None:
    # python 脚本的实参语义未知 —— 不猜(实测:synthesize_meta_json.py 的参数被当成读)
    r = parse_shell("python3 scripts/synthesize_meta_json.py spec/ui/page_0001/meta.json")
    assert r.content_reads == []


# ---- heredoc:体内路径不是本命令的实参(实测误判) ----

def test_heredoc_body_paths_not_reads() -> None:
    cmd = ("python3 - <<'PYEOF'\n"
           "from pathlib import Path\n"
           'p = Path("spec/baseline/api-inventory/data-chains/chain-auth.md")\n'
           "print(p.read_text()[:200])\n"
           "PYEOF")
    r = parse_shell(cmd)
    assert r.content_reads == []
    assert any("chain-auth.md" in b for b in r.scripts.values())  # 体交给脚本层解析


def test_heredoc_write_target_counted() -> None:
    cmd = "cat > spec/notes.md <<'EOF'\n# notes\ncat fake.md\nEOF"
    r = parse_shell(cmd)
    assert r.writes == ["spec/notes.md"]
    assert r.content_reads == []          # 体内的 cat 不算


# ---- 写侧 ----

def test_redirect_write() -> None:
    r = parse_shell("python3 gen.py > spec/report.md 2>/dev/null")
    assert r.writes == ["spec/report.md"]


def test_tee_write() -> None:
    r = parse_shell("run_audit | tee -a spec/audit.log.md")
    assert "spec/audit.log.md" in r.writes


def test_sed_inplace_is_write_not_read() -> None:
    r = parse_shell("sed -i 's/OLD/NEW/' spec/registry.md")
    assert r.writes == ["spec/registry.md"] and r.content_reads == []


def test_cp_dep_read_and_write() -> None:
    r = parse_shell("cp spec/tpl.md spec/baseline/ui/page_0001.md")
    assert r.dep_reads == ["spec/tpl.md"]
    assert r.writes == ["spec/baseline/ui/page_0001.md"]


def test_stdin_redirect_is_dep_read() -> None:
    r = parse_shell("python3 - < scripts/fill.py")
    assert r.dep_reads == ["scripts/fill.py"]


def test_grep_pattern_not_a_path() -> None:
    # 模式串带点号/管道符,长得像路径 —— 0723 实测两类
    r = parse_shell('grep -viE "schemas.android|w3.org|apache.org"')
    assert r.content_reads == []
    r2 = parse_shell('grep -n -B4 -A2 "HomeActivity::class.java" app/page/HomeActivity.kt')
    assert r2.content_reads == ["app/page/HomeActivity.kt"]


# ---- 行级区间:命令自带的才记,不编造 ----

def test_sed_range_span() -> None:
    r = parse_shell("sed -n '1814,2012p' spec/ref/AIPPT_spec.md")
    assert r.spans == {"spec/ref/AIPPT_spec.md": (1814, 199)}


def test_head_span_two_forms() -> None:
    assert parse_shell("head -40 spec/registry.md").spans == {"spec/registry.md": (1, 40)}
    assert parse_shell("head -n 8 spec/x.md").spans == {"spec/x.md": (1, 8)}


def test_get_content_totalcount_span() -> None:
    r = parse_shell("Get-Content -TotalCount 8 -LiteralPath spec/x.md")
    assert r.spans == {"spec/x.md": (1, 8)}


def test_tail_read_but_no_span() -> None:
    r = parse_shell("tail -20 spec/x.md")
    assert r.content_reads == ["spec/x.md"] and r.spans == {}


# ---- 词表第二圈 + 结构补漏(全部来自 0723 覆盖率探针) ----

def test_line_continuation_joined() -> None:
    # 续行反斜杠:之前 "--output-json spec/x.json" 被切成独立段(×10)
    cmd = "python3 gen.py " + chr(92) + "\n  --output-json spec/x.json > spec/out.md"
    r = parse_shell(cmd)
    assert r.content_reads == []           # python 实参不猜
    assert r.writes == ["spec/out.md"]     # 重定向照常


def test_timeout_prefix() -> None:
    r = parse_shell("timeout 30 cat spec/x.md")
    assert r.content_reads == ["spec/x.md"]


def test_second_ring_readers() -> None:
    assert parse_shell("strings app/libs/native.bin").content_reads == ["app/libs/native.bin"]
    assert parse_shell("diff spec/a.md spec/b.md").content_reads == ["spec/a.md", "spec/b.md"]
    assert parse_shell("jq '.summary' spec/api-inventory.json").content_reads == ["spec/api-inventory.json"]

