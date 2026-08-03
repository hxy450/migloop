# -*- coding: utf-8 -*-
"""Provider-agnostic chat support for the MigLoop live lineage viewer.

The browser never receives API credentials.  It sends a bounded conversation
to the local live server; the server adds a compact, deterministic digest of
the current lineage snapshot and delegates only the model call to a provider.

The default provider is the locally authenticated Codex CLI.  Anthropic and
OpenAI-compatible HTTP providers are deliberately small stdlib adapters so the
single-file ``migloop-lineage.pyz`` keeps its zero-third-party-dependency
property.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from typing import Optional


SYSTEM_PROMPT = """你是 MigLoop Session 技术分析助手。你的事实源是完整 session 记录，包括主线程 JSONL、子 Agent transcript、Workflow 元数据及其实际工具调用；血缘快照只是便于定位的确定性索引，不是回答边界。

回答规则：
1. 区分原始 session 事实、血缘聚合事实、推断和未知；发生冲突时以原始 session 记录为准。
2. 优先回答用户真正问的结论，再给最少但足够的证据。
3. 不要因为文件名或阶段名猜测源码行为；需要具体结论时追查对应原始记录。记录也没有提供的信息要明确说无法确认。
4. 涉及数量时尽量给出分子、分母或对应阶段，避免只给模糊评价。
5. 你只做只读分析，不修改工程、会话或 Spec。
"""


class ChatError(RuntimeError):
    """Base class for user-facing chat failures."""


class ChatConfigurationError(ChatError):
    """The selected provider cannot run with the supplied configuration."""


class ChatProviderError(ChatError):
    """A configured provider failed to produce a response."""


@dataclasses.dataclass(frozen=True)
class ChatConfig:
    provider: str = "codex"
    model: Optional[str] = None
    api_key_env: Optional[str] = None
    base_url: Optional[str] = None
    timeout: float = 180.0
    max_context_chars: int = 32000
    max_conversation_chars: int = 40000


class SessionCorpus:
    """Read-only description and retrieval facade over one complete session."""

    def __init__(self, main_jsonl):
        self.main_jsonl = os.path.abspath(main_jsonl)
        self.session_dir = os.path.splitext(self.main_jsonl)[0]
        self.root_dir = os.path.dirname(self.main_jsonl)

    def files(self):
        found = [self.main_jsonl] if os.path.isfile(self.main_jsonl) else []
        if os.path.isdir(self.session_dir):
            for root, _, names in os.walk(self.session_dir):
                for name in names:
                    low = name.lower()
                    if low.endswith((".jsonl", ".meta.json", ".json", ".js")):
                        found.append(os.path.join(root, name))
        return sorted(set(found))

    def manifest(self):
        files = self.files()
        rows = []
        for path in files:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = None
            rows.append({
                "path": path.replace(os.sep, "/"),
                "relative_path": os.path.relpath(path, self.root_dir).replace(os.sep, "/"),
                "bytes": size,
            })
        return {
            "main_transcript": self.main_jsonl.replace(os.sep, "/"),
            "session_directory": self.session_dir.replace(os.sep, "/"),
            "record_files": rows,
            "record_file_count": len(rows),
        }

    @staticmethod
    def _query_terms(query):
        terms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_./:\-]{2,}", query or ""))
        for seq in re.findall(r"[\u3400-\u9fff]{2,}", query or ""):
            terms.update(seq[i:i + 2] for i in range(len(seq) - 1))
        return {term.lower() for term in terms if term.strip()}

    @staticmethod
    def _record_text(record):
        parts = []

        def walk(value, depth=0):
            if depth > 8 or len(parts) > 180:
                return
            if isinstance(value, str):
                if value.strip():
                    parts.append(value.strip())
            elif isinstance(value, dict):
                for key, item in value.items():
                    if key not in ("thinking", "signature"):
                        walk(item, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    walk(item, depth + 1)

        walk(record)
        return "\n".join(parts)

    def retrieve(self, query, max_chars=14000):
        """Retrieve raw evidence from every JSONL in the complete session.

        HTTP providers cannot open local files themselves.  This deterministic
        retrieval keeps them provider-compatible while Codex can additionally
        inspect any record file directly with read-only tools.
        """
        terms = self._query_terms(query)
        ranked, recent = [], []
        for path in self.files():
            if not path.lower().endswith(".jsonl"):
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as stream:
                    for lineno, line in enumerate(stream, 1):
                        try:
                            record = json.loads(line)
                        except (ValueError, TypeError):
                            continue
                        text = self._record_text(record)
                        if not text:
                            continue
                        excerpt = text[:5000]
                        recent.append((path, lineno, excerpt))
                        if len(recent) > 24:
                            recent.pop(0)
                        low = text.lower()
                        score = sum(min(5, low.count(term)) for term in terms)
                        if score:
                            ranked.append((score, path, lineno, excerpt))
            except OSError:
                continue
        ranked.sort(key=lambda row: (-row[0], row[1], row[2]))
        chosen = [(p, n, text) for _, p, n, text in ranked[:28]]
        if not chosen:
            chosen = recent
        pieces = ["<session_manifest>\n%s\n</session_manifest>" % json.dumps(
            self.manifest(), ensure_ascii=False, indent=2
        )]
        if chosen:
            pieces.append("<retrieved_raw_session_records>")
            for path, lineno, text in chosen:
                pieces.append("[%s:%d]\n%s" % (
                    os.path.relpath(path, self.root_dir).replace(os.sep, "/"), lineno, text
                ))
            pieces.append("</retrieved_raw_session_records>")
        result = "\n\n".join(pieces)
        max_chars = max(4000, int(max_chars))
        return result[:max_chars]


def _short_list(values, limit=80):
    values = list(values or [])
    return values[:limit] + (["… %d more" % (len(values) - limit)] if len(values) > limit else [])


def _agent_digest(agent):
    return {
        "agent_id": agent.get("agent_id"),
        "type": agent.get("type"),
        "role": agent.get("role"),
        "stage": agent.get("stage"),
        "workflow_phase": agent.get("wf_phase"),
        "description": agent.get("desc"),
        "android_files_read": agent.get("n_android", 0),
        "android_lines_read": agent.get("lines_android_dedup", agent.get("lines_android", 0)),
        "spec_files_read": agent.get("n_spec_read", 0),
        "spec_lines_read": agent.get("lines_spec", 0),
        "project_files_read": agent.get("n_proj", 0),
        "output_files": agent.get("n_out", 0),
        "spec_files_written": agent.get("n_spec_w", 0),
        "ets_files_written": agent.get("n_ets", 0),
        "aborted": bool(agent.get("aborted")),
    }


def build_lineage_context(trace, max_chars=32000):
    """Turn the full extractor result into a bounded model-facing digest.

    The digest contains counts and explicit file/agent relationships, not the
    original prompts or source contents.  This keeps chat context predictable
    and prevents a long session transcript from becoming the model prompt.
    """
    trace = trace or {}
    lineage = trace.get("lineage") or {}
    meta = trace.get("meta") or {}
    totals = trace.get("totals") or {}
    specs = []
    for item in lineage.get("specs") or []:
        specs.append({
            "path": item.get("path"),
            "kind": item.get("kind"),
            "produced_by": _short_list(item.get("authors"), 12),
            "read_by": _short_list(item.get("read_by"), 12),
        })
    outputs = []
    for item in lineage.get("files") or []:
        outputs.append({
            "path": item.get("path"),
            "kind": item.get("kind"),
            "written_lines": item.get("lines", 0),
            "final_lines": item.get("final_lines", 0),
            "writers": _short_list(item.get("writers"), 12),
        })
    outputs.sort(key=lambda row: (-int(row.get("final_lines") or 0), str(row.get("path") or "")))
    unread = [
        item.get("path") for item in (lineage.get("android") or [])
        if not item.get("readers") and not item.get("oos")
    ]
    digest = {
        "snapshot_contract": "MigLoop deterministic lineage digest; counts are facts, interpretation is not ground truth",
        "session": {
            "id": meta.get("session_id"),
            "project": meta.get("cwd"),
            "model": meta.get("model"),
            "started_at": meta.get("started_at"),
            "ended_at": meta.get("ended_at"),
            "records": meta.get("record_count"),
        },
        "session_totals": totals,
        "pipeline_stages": trace.get("stages") or [],
        "workflows": trace.get("workflows") or [],
        "lineage_totals": lineage.get("stats") or {},
        "android_inventory": lineage.get("android_total") or {},
        "android_visibility_by_stage": lineage.get("stage_view") or {},
        "output_by_stage": lineage.get("by_stage") or {},
        "agents": [_agent_digest(a) for a in (lineage.get("agents") or [])],
        "spec_and_analysis_files": specs,
        "produced_files": outputs,
        "unread_android_files_sample": _short_list(unread, 80),
    }
    text = json.dumps(digest, ensure_ascii=False, indent=2, default=str)
    max_chars = max(4000, int(max_chars or 32000))
    if len(text) <= max_chars:
        return text

    # Preserve denominators and stage/agent relationships first.  Large file
    # lists are useful examples, but they are the first thing to trim.
    digest["produced_files"] = outputs[:40]
    digest["unread_android_files_sample"] = _short_list(unread, 30)
    digest["context_truncated"] = True
    text = json.dumps(digest, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    digest["spec_and_analysis_files"] = specs[:50]
    text = json.dumps(digest, ensure_ascii=False, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 80] + "\n… [context truncated by MigLoop]\n"


def normalize_messages(messages, max_chars=40000):
    if not isinstance(messages, list):
        raise ChatConfigurationError("messages 必须是数组")
    clean = []
    total = 0
    for item in messages[-20:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        content = content[:12000]
        total += len(content)
        clean.append({"role": item["role"], "content": content})
    if not clean or clean[-1]["role"] != "user":
        raise ChatConfigurationError("最后一条消息必须来自用户")
    if total > int(max_chars):
        raise ChatConfigurationError("对话过长，请清空对话后重试")
    return clean


def _render_prompt(messages, context, session_manifest=None):
    turns = []
    for item in messages:
        turns.append(("用户" if item["role"] == "user" else "助手") + "：" + item["content"])
    source = ""
    if session_manifest:
        source = """
<complete_session_access>
%s
你拥有上述 session 文件的只读访问权。血缘摘要只能用于定位；如果用户的问题涉及判断过程、工具调用、具体输入输出或摘要未能直接证明的结论，请使用只读搜索/读取工具追查主 transcript 和相关子 Agent transcript 后再回答。无需机械读取所有文件，但不能把未查证的快照推断写成 session 事实。
</complete_session_access>
""" % json.dumps(session_manifest, ensure_ascii=False, indent=2)
    return "%s\n%s\n<lineage_navigation_index>\n%s\n</lineage_navigation_index>\n\n<conversation>\n%s\n</conversation>\n\n请回答最后一个用户问题。" % (
        SYSTEM_PROMPT, source, context, "\n\n".join(turns)
    )


def _http_json(url, payload, headers, timeout):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/json",
        **headers,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise ChatProviderError("模型 API 返回 HTTP %s：%s" % (exc.code, detail)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ChatProviderError("无法连接模型 API：%s" % exc) from exc


class BaseProvider:
    name = "base"

    def __init__(self, config):
        self.config = config

    @property
    def model_label(self):
        return self.config.model or "default"

    def complete(self, messages, context, session=None):
        raise NotImplementedError


class CodexCLIProvider(BaseProvider):
    name = "codex"

    def __init__(self, config):
        super().__init__(config)
        self.executable = shutil.which("codex") or shutil.which("codex.cmd")
        if not self.executable:
            raise ChatConfigurationError("找不到 codex CLI；请安装并登录 Codex，或切换 --chat-provider")

    @property
    def model_label(self):
        return self.config.model or "Codex configured default"

    def complete(self, messages, context, session=None):
        prompt = _render_prompt(messages, context, session.manifest() if session else None)
        with tempfile.TemporaryDirectory(prefix="migloop-chat-") as workdir:
            output_path = os.path.join(workdir, "answer.txt")
            cmd = [
                self.executable, "exec", "--ephemeral", "--skip-git-repo-check",
                "--ignore-rules", "--sandbox", "read-only", "--color", "never",
                "-C", session.root_dir if session else workdir, "-o", output_path,
            ]
            if self.config.model:
                cmd.extend(["--model", self.config.model])
            cmd.append("-")
            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                result = subprocess.run(
                    cmd, input=prompt, text=True, capture_output=True,
                    timeout=float(self.config.timeout), cwd=session.root_dir if session else workdir,
                    encoding="utf-8", errors="replace", **kwargs
                )
            except subprocess.TimeoutExpired as exc:
                raise ChatProviderError("Codex 分析超过 %.0f 秒" % self.config.timeout) from exc
            except OSError as exc:
                raise ChatProviderError("无法启动 Codex：%s" % exc) from exc
            reply = ""
            try:
                with open(output_path, encoding="utf-8") as stream:
                    reply = stream.read().strip()
            except OSError:
                pass
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "unknown error").strip()[-1600:]
                raise ChatProviderError("Codex 调用失败：%s" % detail)
            if not reply:
                reply = (result.stdout or "").strip()
            if not reply:
                raise ChatProviderError("Codex 没有返回分析结果")
            return reply


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, config):
        super().__init__(config)
        if not config.model:
            raise ChatConfigurationError("Anthropic provider 需要 --chat-model")
        self.key_env = config.api_key_env or "ANTHROPIC_API_KEY"
        self.api_key = os.environ.get(self.key_env)
        if not self.api_key:
            raise ChatConfigurationError("环境变量 %s 未设置" % self.key_env)
        self.url = (config.base_url or "https://api.anthropic.com/v1/messages").rstrip("/")

    def complete(self, messages, context, session=None):
        payload = {
            "model": self.config.model,
            "max_tokens": 1600,
            "system": SYSTEM_PROMPT + "\n\n<current_lineage_snapshot>\n" + context + "\n</current_lineage_snapshot>",
            "messages": messages,
        }
        data = _http_json(self.url, payload, {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }, self.config.timeout)
        reply = "\n".join(
            str(block.get("text") or "") for block in (data.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        if not reply:
            raise ChatProviderError("Anthropic API 没有返回文本")
        return reply


class OpenAICompatibleProvider(BaseProvider):
    name = "openai-compatible"

    def __init__(self, config):
        super().__init__(config)
        if not config.model:
            raise ChatConfigurationError("OpenAI-compatible provider 需要 --chat-model")
        self.key_env = config.api_key_env or "OPENAI_API_KEY"
        self.api_key = os.environ.get(self.key_env, "")
        self.base_url = (config.base_url or "https://api.openai.com/v1").rstrip("/")
        if not self.api_key and not self.base_url.startswith(("http://127.0.0.1", "http://localhost")):
            raise ChatConfigurationError("环境变量 %s 未设置" % self.key_env)

    def complete(self, messages, context, session=None):
        model_messages = [{
            "role": "system",
            "content": SYSTEM_PROMPT + "\n\n<current_lineage_snapshot>\n" + context + "\n</current_lineage_snapshot>",
        }] + messages
        headers = {"Authorization": "Bearer " + self.api_key} if self.api_key else {}
        data = _http_json(self.base_url + "/chat/completions", {
            "model": self.config.model,
            "messages": model_messages,
            "temperature": 0.2,
        }, headers, self.config.timeout)
        try:
            reply = str(data["choices"][0]["message"]["content"]).strip()
        except (KeyError, IndexError, TypeError):
            reply = ""
        if not reply:
            raise ChatProviderError("OpenAI-compatible API 没有返回文本")
        return reply


def create_provider(config):
    name = (config.provider or "off").strip().lower()
    if name == "codex":
        return CodexCLIProvider(config)
    if name == "anthropic":
        return AnthropicProvider(config)
    if name in ("openai", "openai-compatible"):
        return OpenAICompatibleProvider(config)
    if name == "off":
        return None
    raise ChatConfigurationError("未知 chat provider：%s" % name)


class ChatService:
    """Bounded, serialized access to one provider and one complete session."""

    def __init__(self, config, context_builder, session=None):
        self.config = config
        self.context_builder = context_builder
        self.session = session
        self.provider = create_provider(config)
        self.lock = threading.Lock()

    def info(self):
        return {
            "enabled": self.provider is not None,
            "provider": self.provider.name if self.provider else "off",
            "model": self.provider.model_label if self.provider else None,
            "context": "complete session record + deterministic lineage index",
        }

    def chat(self, messages):
        if self.provider is None:
            raise ChatConfigurationError("分析助手未启用")
        clean = normalize_messages(messages, self.config.max_conversation_chars)
        with self.lock:
            context = self.context_builder()
            if not isinstance(context, str):
                context = build_lineage_context(context, self.config.max_context_chars)
            # Codex can inspect the complete local record with read-only tools.
            # HTTP-only providers receive deterministic evidence retrieved from
            # every JSONL, preserving the provider abstraction without claiming
            # that the compact lineage index is the whole session.
            if self.session and self.provider.name != "codex":
                query = "\n".join(item["content"] for item in clean[-4:])
                evidence = self.session.retrieve(query, max_chars=16000)
                context = context + "\n\n" + evidence
            return self.provider.complete(clean, context, self.session)
