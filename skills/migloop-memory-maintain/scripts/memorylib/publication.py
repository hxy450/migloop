"""Publish a frozen, file-readable view of active memory; never rewrite the store.

Layout (all generated from one snapshot; the store stays the only source of truth):

    index.md                 root: recall protocol, domains, stages, structured entries
    catalog.jsonl            one line per lesson: id, summary, topic, stage, signals, support
    signals.json             symbol -> lesson IDs
    by-stage/<stage>.md      stage x domain/topic view
    topics/<path>/index.md   domain / topic / subtopic browsing view (direct children only)
    topics/<path>/<id>.lesson.md   lesson bodies next to their topic index, so maintainers browse a
                             topic as one folder; moving a lesson moves the file (git tracks renames)
    manifest.json            revision, file hashes, exact source bindings
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from . import VERSION
from .case_format import context, shared_objects
from .common import slug
from .registry import STAGES, structure_errors

FILES_SCHEMA = "migloop-memory-files/2"
STAGE_LABELS = {"spec": "规格提取", "plan": "计划与派工", "execute": "执行与实现", "verify": "验证与判读",
                "repair": "修复", "converge": "收敛与移交"}
LEAF_SPARSE, LEAF_CROWDED = 4, 9   # navigation hints only; LEAF_MAX is the contract
RELATED_MAX, INDEX_SIGNALS = 5, 4


def _inline(text):
    text = html.escape(" ".join(text.split()), quote=False)
    return text.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _link(label, target, current):
    relative = os.path.relpath(target, current.parent).replace(os.sep, "/")
    return f"[{_inline(label)}]({quote(relative, safe='/.-_')})"


def _lesson_path(lesson):
    # Identity is the ID; the folder is the topic so a maintainer sees index and bodies together.
    return PurePosixPath("topics", *lesson["topic"], lesson["id"] + ".lesson.md")


def _topic_path(topic):
    return PurePosixPath("topics", *topic.split("/"), "index.md")


def _stage_path(stage):
    return PurePosixPath("by-stage", stage + ".md")


def _support_counts(lesson, migrations):
    """Count recorded historical support, not claims, agents or successful reuses."""
    refs = {ref["case"]: ref["revision"] for ref in lesson["evidence"]}
    migration_ids, projects = set(), set()
    missing_migrations = missing_projects = 0
    for identity, revision in refs.items():
        migration = migrations[(identity, revision)]
        labels = {key: value.strip() for key, value in migration.items()
                  if isinstance(value, str) and value.strip()}
        migration_id = labels.get("server_session_id") or labels.get("id")
        if migration_id:
            migration_ids.add(migration_id)
        else:
            missing_migrations += 1
        if labels.get("project"):
            projects.add(labels["project"].casefold())
        else:
            missing_projects += 1
    return {"cards": len(refs), "migrations": len(migration_ids), "applications": len(projects),
            "missing_migration_cards": missing_migrations, "missing_application_cards": missing_projects}


def _support_line(counts):
    parts = [f"{counts['cards']} 张卡"]
    for key, missing_key, unit, label in (("migrations", "missing_migration_cards", "次迁移", "迁移数"),
                                          ("applications", "missing_application_cards", "个应用", "应用数")):
        count, missing = counts[key], counts[missing_key]
        parts.append((f"已知 {count} {unit}（部分未记录）" if count else label + "未记录")
                     if missing else f"{count} {unit}")
    return "来源支持：" + " · ".join(parts)


def _related(lessons):
    """Lessons distilled from the same cards, strongest overlap first; derived, never authored."""
    cases = {key: {ref["case"] for ref in value["evidence"]} for key, value in lessons.items()}
    result = {}
    for key, mine in cases.items():
        shared = [(len(mine & theirs), other) for other, theirs in cases.items() if other != key and mine & theirs]
        result[key] = [(other, count) for count, other in sorted(shared, key=lambda x: (-x[0], x[1]))[:RELATED_MAX]]
    return result


def _stage_text(lesson):
    return "/".join(lesson["stage"])


def _entry(lesson, output, paths, current, *, with_stage=True):
    line = "- " + _link(lesson["summary"], output / paths[lesson["id"]], current)
    if with_stage:
        line += " · 阶段：" + _stage_text(lesson)
    line += " · 信号：" + _inline(", ".join(lesson["signals"][:INDEX_SIGNALS]))
    return line


def _lesson_text(lesson, state, memory, output, paths, link_cards, support, related):
    current = output / paths[lesson["id"]]
    topic = "/".join(lesson["topic"])
    lines = [f"# {lesson['title']}", "",
             f"ID：`{lesson['id']}` · 版本：{lesson['version']} · 阶段：{_stage_text(lesson)} · 主题："
             + _link(topic, output / _topic_path(topic), current), "",
             f"概要：{lesson['summary']}", "",
             "信号：" + ", ".join(f"`{s}`" for s in lesson["signals"]), "",
             "## 何时使用", "", lesson["when"], ""]
    if lesson.get("description"):
        lines += ["## 适用情境", "", lesson["description"], ""]
    if lesson["unless"]:
        lines += ["## 例外与边界", "", *[f"- {x}" for x in lesson["unless"]], ""]
    lines += ["## 原因", "", lesson["why"], "", "## 做法", "",
              *[f"{i}. {x}" for i, x in enumerate(lesson["how"], 1)], ""]
    if lesson.get("check"):
        lines += ["## 可选检查", "", *[f"- {x}" for x in lesson["check"]], ""]
    if lesson["requires"]:
        lines += ["## 依赖经验", ""]
        for identity in lesson["requires"]:
            lines.append("- " + _link(state["lessons"][identity]["summary"], output / paths[identity], current))
        lines.append("")
    if related:
        lines += ["## 同源经验", "", "由相同来源卡提炼的其他经验，按共享卡数排序；不是依赖关系。", ""]
        for identity, count in related:
            lines.append("- " + _link(state["lessons"][identity]["summary"], output / paths[identity], current)
                         + f"（共享 {count} 张卡）")
        lines.append("")
    # Deployment readers need the lesson, not an expanding evidence ledger.
    # Exact bindings remain in the manifest; development exports can link cards.
    lines += [_support_line(support), ""]
    if not link_cards:
        return "\n".join(lines) + "\n"
    lines += ["## 来源（按需复核）", ""]
    sources = {}
    for ref in lesson["evidence"]:
        sources.setdefault((ref["case"], ref["revision"]), []).append(ref["claim"])
    for (identity, revision), claims in sorted(sources.items()):
        label = _link(identity, memory.root / "cases" / identity / (revision + ".json"), current)
        lines += [f"- {label} · 结论：{', '.join(dict.fromkeys(claims))}", f"  卡片版本：`{revision}`"]
    return "\n".join(lines) + "\n"


def _root_text(state, output, directories, counts_by_stage, link_cards):
    current = output / "index.md"
    lines = ["# 迁移经验", "", f"经验库版本：`{state['revision']}`", "",
             "## 怎样召回", "",
             "1. 先写下当前任务的阶段、输入里出现的符号（API、组件、装饰器、文件名）和领域猜测。",
             "2. 用 `catalog.jsonl`（每行一条经验：id、summary、topic、stage、signals、support、path）或 "
             "`signals.json`（符号 → 经验 id）按这三者过滤出候选；也可从下面的领域或阶段入口浏览，目录索引只列下一层。",
             "3. 只读 3 到 5 条候选的正文（catalog 的 path 列，位于 `topics/<主题>/<id>.lesson.md`），核对适用条件后回到任务；"
             "无关分支可跳过，任务已获足够指导即可继续。", "",
             "这是发布时的 active 快照，不会自动追踪之后的撤回；新任务应使用维护者提供的最新阅读包。", "",
             "## 领域", ""]
    for domain in sorted(d for d in directories if d and "/" not in d):
        lines.append("- " + _link(domain, output / _topic_path(domain), current)
                     + " — " + _inline(state["topics"][domain]) + f"（{directories[domain]['total']} 条）")
    lines += ["", "## 阶段", ""]
    for stage in STAGES:
        lines.append("- " + _link(stage, output / _stage_path(stage), current)
                     + f" — {STAGE_LABELS[stage]}（{counts_by_stage[stage]} 条）")
    lines += ["", "## 阅读约定", "",
              ("经验是有适用范围的历史建议。核查来源时同时看结论与 unknown；来源卡未随阅读包复制。"
               if link_cards else "经验是有适用范围的历史建议；来源绑定由维护端保留，正常使用无需读取。")
              + " 来源计数按卡片、迁移身份与项目标识去重，表示历史样本覆盖，不是正确概率或成功复用次数；适用条件优先。", "",
              "可选检查仅在适用条件不确定、与当前输入冲突或需要验证关键假设时按需执行；优先复用已有证据和正常测试。",
              "不因读取经验而额外启动验证流程；项目原有必需测试照常执行。", ""]
    return "\n".join(lines)


def _topic_text(topic, state, output, directories, paths):
    current = output / _topic_path(topic)
    directory = directories[topic]
    parent = topic.rsplit("/", 1)[0] if "/" in topic else ""
    up = output / (_topic_path(parent) if parent else "index.md")
    lines = [f"# {topic}", "", state["topics"][topic], "", _link("上一级", up, current), ""]
    if directory["children"]:
        lines += ["## 子主题", ""]
        for child in sorted(directory["children"]):
            lines.append("- " + _link(child.rsplit("/", 1)[-1], output / _topic_path(child), current)
                         + " — " + _inline(state["topics"][child]) + f"（{directories[child]['total']} 条）")
        lines.append("")
    if directory["lessons"]:
        lines += ["## 本级经验", ""]
        for lesson in sorted(directory["lessons"], key=lambda x: (x["summary"], x["id"])):
            lines.append(_entry(lesson, output, paths, current))
        lines.append("")
    return "\n".join(lines)


def _stage_text_file(stage, lessons, state, output, paths):
    current = output / _stage_path(stage)
    members = sorted((l for l in lessons.values() if stage in l["stage"]), key=lambda x: (x["topic"], x["summary"], x["id"]))
    lines = [f"# 阶段：{STAGE_LABELS[stage]}（{stage}）", "",
             f"本阶段可用的 {len(members)} 条经验，按领域与主题分组；一条经验可属于多个阶段。", "",
             _link("返回根索引", output / "index.md", current), ""]
    domain = topic = None
    for lesson in members:
        route = "/".join(lesson["topic"])
        if lesson["topic"][0] != domain:
            domain = lesson["topic"][0]
            lines += [f"## {domain} — {_inline(state['topics'][domain])}", ""]
            topic = None
        if route != topic:
            topic = route
            if lines[-1].startswith("- "):
                lines.append("")
            lines += [f"### {_link(route, output / _topic_path(route), current)} — {_inline(state['topics'][route])}", ""]
        lines.append(_entry(lesson, output, paths, current, with_stage=False))
    lines.append("")
    return "\n".join(lines)


def _render(memory, state, output, link_cards):
    lessons = {key: value for key, value in state["lessons"].items() if value["status"] == "active"}
    errors = structure_errors(lessons, state["topics"], require_fields=True, require_descriptions=True)
    if errors:
        raise ValueError("Structure contract violated; nothing exported: " + " | ".join(errors))
    directories, migrations = {"": {"children": set(), "lessons": [], "total": 0}}, {}
    for identity, lesson in lessons.items():
        slug(identity, "lesson ID")
        if identity != lesson["id"]:
            raise ValueError("Lesson key does not match its ID")
        parent = ""
        for part in lesson["topic"]:
            slug(part, "topic segment")
            child = parent + "/" + part if parent else part
            directories.setdefault(child, {"children": set(), "lessons": [], "total": 0})
            directories[parent]["children"].add(child)
            directories[child]["total"] += 1
            parent = child
        directories[parent]["lessons"].append(lesson)
        for dependency in lesson["requires"]:
            if dependency not in lessons:
                raise ValueError("Active lesson has an unpublished dependency: " + dependency)
        for ref in lesson["evidence"]:
            head = state["cases"].get(ref["case"])
            if (not head or head["status"] != "available" or ref["revision"] != head["revision"]
                    or ref["claim"] not in head["claims"] or ref["claim"] in head["withdrawn_claims"]):
                raise ValueError("Active lesson has stale or withdrawn evidence: " + identity)
            source = (ref["case"], ref["revision"])
            if source not in migrations:
                card = memory.case(ref["case"], ref["revision"], state=state)
                if card["id"] != ref["case"] or card["revision"] != ref["revision"]:
                    raise ValueError("Source card identity/version mismatch")
                details = context(card, shared_objects(card, memory.root / "sessions"))
                migrations[source] = details.get("provenance", {}).get("migration", {})
    paths = {key: _lesson_path(value) for key, value in lessons.items()}
    support = {key: _support_counts(value, migrations) for key, value in lessons.items()}
    related = _related(lessons)
    counts_by_stage = {stage: sum(stage in l["stage"] for l in lessons.values()) for stage in STAGES}
    files = {"index.md": _root_text(state, output, directories, counts_by_stage, link_cards)}
    for topic in sorted(directories):
        if topic:
            files[str(_topic_path(topic))] = _topic_text(topic, state, output, directories, paths)
    for stage in STAGES:
        files[str(_stage_path(stage))] = _stage_text_file(stage, lessons, state, output, paths)
    for identity, lesson in sorted(lessons.items()):
        files[str(paths[identity])] = _lesson_text(lesson, state, memory, output, paths, link_cards,
                                                  support[identity], related[identity])
    catalog = []
    for identity, lesson in sorted(lessons.items(), key=lambda kv: (kv[1]["topic"], kv[0])):
        catalog.append(json.dumps({
            "id": identity, "summary": lesson["summary"], "topic": "/".join(lesson["topic"]),
            "stage": lesson["stage"], "signals": lesson["signals"], "title": lesson["title"],
            "cards": support[identity]["cards"], "apps": support[identity]["applications"],
            "path": str(paths[identity])}, ensure_ascii=False))
    files["catalog.jsonl"] = "\n".join(catalog) + "\n"
    signals = {}
    for identity, lesson in lessons.items():
        for symbol in lesson["signals"]:
            signals.setdefault(symbol, []).append(identity)
    files["signals.json"] = json.dumps({k: sorted(v) for k, v in sorted(signals.items())},
                                       ensure_ascii=False, indent=0) + "\n"
    warnings = []
    for topic, row in sorted(directories.items()):
        if not topic or not row["lessons"]:
            continue
        if len(row["lessons"]) < LEAF_SPARSE:
            warnings.append({"topic": topic, "entries": len(row["lessons"]), "code": "sparse_topic",
                             "next_step": f"Fewer than {LEAF_SPARSE} lessons; merge into a sibling mechanism unless it is new. Navigation hint only."})
        elif len(row["lessons"]) > LEAF_CROWDED:
            warnings.append({"topic": topic, "entries": len(row["lessons"]), "code": "crowded_topic",
                             "next_step": f"More than {LEAF_CROWDED} lessons; plan a split by sub-mechanism in the next proposal. Navigation hint only."})
    manifest = {"schema": FILES_SCHEMA, "publisher_version": VERSION,
                "memory_revision": state["revision"], "card_links": "local" if link_cards else "references_only",
                "sources_in_body": bool(link_cards), "navigation_warnings": warnings,
                "entries": {"root": "index.md", "catalog": "catalog.jsonl", "signals": "signals.json",
                            "by_stage": "by-stage/", "topics": "topics/"},
                "counts": {"lessons": len(lessons), "topics": len(directories) - 1,
                           "domains": len(directories[""]["children"]), "signals": len(signals),
                           "stages": counts_by_stage},
                "lessons": {key: {"path": str(paths[key]), "version": value["version"],
                                  "topic": "/".join(value["topic"]), "stage": value["stage"],
                                  "summary": value["summary"], "signals": value["signals"],
                                  "evidence": value["evidence"]} for key, value in sorted(lessons.items())},
                "files": {path: hashlib.sha256(body.encode("utf-8")).hexdigest() for path, body in sorted(files.items())}}
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return files, manifest


def export_memory(memory, directory, *, link_cards=False):
    """Create a new complete reading directory; retain prior releases, never merge/overwrite."""
    supplied = Path(directory).absolute()
    if supplied.is_symlink():
        raise ValueError("Output must be a new directory, not a symlink")
    output = supplied.resolve()
    if output == memory.root or output in memory.root.parents or memory.root in output.parents:
        raise ValueError("Output and memory store must not overlap")
    if output.exists():
        raise ValueError("Output already exists; choose a new release directory (existing files are preserved)")
    with memory.lock():
        state = memory.current()
        files, manifest = _render(memory, state, output, link_cards)
        output.parent.mkdir(parents=True, exist_ok=True)
        # A unique sibling staging directory owns only files generated by this call.
        with tempfile.TemporaryDirectory(prefix=".memory-export-", dir=output.parent) as temporary:
            stage = Path(temporary)
            for relative, body in files.items():
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8", newline="\n")
            if output.exists():
                raise ValueError("Output was created during export; choose a new release directory")
            stage.rename(output)
    return {"revision": state["revision"], "entry": str(output / "index.md"),
            "manifest": str(output / "manifest.json"), **manifest["counts"],
            "card_links": manifest["card_links"], "warnings": manifest["navigation_warnings"], "store_changed": False}
