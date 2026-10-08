"""Versioned local memory store: exact dependencies, review gates, derived indexes."""
from __future__ import annotations

import copy
import json
from contextlib import contextmanager
from pathlib import Path

from .common import fields, fingerprint, load, nonempty, now, replace_json, slug, strings, write_new
from .card_contract import require_valid_card, validation_digest
from .case_format import SCHEMA, SHARED_SCHEMA, claims, content, shared_objects, write_shared, validate_formal

STATUSES = {"candidate", "active", "disputed", "needs_review", "retired"}
MEMORY_SCHEMA = "migloop-memory/2"
# Retrieval axes. Stage is a field, never a directory level.
STAGES = ("spec", "plan", "execute", "verify", "repair", "converge")
# Structure limits enforced by apply and export; growth happens by splitting topics.
LEAF_MAX, DESCRIPTION_MAX, SUMMARY_MAX, SIGNALS_MAX, SIGNAL_MAX = 12, 60, 30, 12, 60


# Lowercase tool/format/unit names that are legitimate grep targets despite being plain words.
SIGNAL_ALLOW = {"aapt", "apktool", "hvigor", "hvigorw", "ohpm", "hilog", "lottie", "rawfile", "mipmap", "webp", "xxhdpi",
                "xhdpi", "xldpi", "sips", "varint", "zlib", "strarray", "styleable", "heredoc", "rg", "placeable", "lerp",
                "bigint", "instanceof", "typeof", "dp", "px", "vp", "sp", "fp", "lpx", "gradle", "grep", "inflate",
                "rethrow", "reviver", "replacer", "clickable", "focusable", "selectable", "hypium", "hamock", "jest", "mocha", "junit", "espresso", "robolectric", "hdc", "hilogcat", "arkts", "ets", "hap", "har", "hsp", "ohos"}


def generic_signal(symbol):
    """A bare lowercase word (import, title, loading) matches any codebase; identifiers, dotted
    paths, file names and decorators carry case, punctuation or are on the allow list."""
    import re
    return bool(re.fullmatch(r"[a-z]{1,10}", symbol)) and symbol not in SIGNAL_ALLOW


def structure_errors(lessons, topics, *, require_fields=False, require_descriptions=False):
    """Mechanical structure contract over active lessons; returns messages, raises nothing."""
    errors, leaves = [], {}
    for identity, lesson in sorted(lessons.items()):
        route = "/".join(lesson["topic"])
        if len(lesson["topic"]) < 2:
            errors.append(f"{identity}: topic must be domain/topic[/subtopic], not {route!r}")
        leaves.setdefault(route, []).append(identity)
        if require_fields and not all(lesson.get(k) for k in ("stage", "summary", "signals")):
            errors.append(f"{identity}: missing stage/summary/signals; re-apply the lesson with retrieval fields")
    used = set()
    for route, members in sorted(leaves.items()):
        if any(other.startswith(route + "/") for other in leaves):
            errors.append(f"{route}: holds lessons and subtopics; move its {len(members)} lesson(s) into leaf topics")
        if len(members) > LEAF_MAX:
            errors.append(f"{route}: {len(members)} lessons exceed {LEAF_MAX}; split by mechanism into subtopics")
        parent = ""
        for part in route.split("/"):
            parent = parent + "/" + part if parent else part
            used.add(parent)
            if require_descriptions and not topics.get(parent):
                errors.append(f"Missing topic description: {parent}; supply topic_descriptions via apply")
    # Only topics readers can reach are judged; retired paths keep their history untouched.
    for path in sorted(used):
        errors.extend(description_errors({path: topics[path]}) if path in topics else [])
    return sorted(set(errors))


def description_errors(descriptions):
    return [f"{path}: topic description exceeds {DESCRIPTION_MAX} characters; one defining sentence only"
            for path, description in sorted(descriptions.items())
            if isinstance(description, str) and len(description.strip()) > DESCRIPTION_MAX]


def revision_of(card):
    if card.get("schema") in (SCHEMA, SHARED_SCHEMA):
        return fingerprint({k: v for k, v in card.items() if k not in ("revision", "created_at")})
    payload = copy.deepcopy({k: v for k, v in card.items() if k not in ("revision", "created_at", "validation")})
    if isinstance(payload.get("provenance"), dict):
        payload["provenance"].pop("captured_at", None)
    return fingerprint(payload)


def validate_case(card):
    if not isinstance(card, dict) or card.get("schema") not in {"migloop-case/1", "migloop-case/2", SHARED_SCHEMA, SCHEMA}:
        raise ValueError("Expected a packaged migloop-case/1, /2, /3 or /4, not a bare draft or UI graph")
    slug(card.get("id"), "case.id")
    if card.get("revision") != revision_of(card):
        raise ValueError("Case content differs from its revision hash; repack the source draft")
    if card["schema"] in (SCHEMA, SHARED_SCHEMA):
        validate_formal(card)
        return
    # Legacy records remain readable under their original revision algorithm.
    # New admissions require this binding through require_valid_card.
    if "validation_sha256" in card and card["validation_sha256"] != validation_digest(card.get("validation", {})):
        raise ValueError("Card validation summary differs from its revision-bound hash; repack the source draft")
    draft = card.get("draft", {})
    expected = {"diagnosis": {"text": draft.get("summary"), "kind": "diagnosis", "status": "model_claim"}}
    expected.update({f"recommendation:{i}": {"text": text, "kind": "recommendation", "status": "model_claim"}
                     for i, text in enumerate(draft.get("recommendations", []), 1)})
    # Legacy cards embed their claim table; positional names and stable IDs are both revision-bound.
    from .case_format import claim_map
    stable = {claim_map({"schema": "migloop-case/1", "draft": draft})[key]: value for key, value in expected.items()}
    if card.get("claims") not in (expected, stable):
        raise ValueError("Claims must match the packaged draft, not a separately edited assertion list")
    for claim in expected.values():
        nonempty(claim["text"], "case claim")
    if card["schema"] == "migloop-case/2":
        if card.get("provenance", {}).get("schema") != "migloop-case-provenance/1":
            raise ValueError("Compact card requires compact provenance")
        if not isinstance(card["provenance"].get("sources"), dict) or "node_provenance" in card:
            raise ValueError("Compact card cannot embed a full session inventory")
        for checked in card.get("validation", {}).get("graph_checks", []):
            if {"document", "submitted_document", "nodes", "edges", "coverage", "tree"} & set(checked["receipt"]):
                raise ValueError("Full checker replies belong in optional debug output, not a compact card")


class Memory:
    def __init__(self, directory):
        self.root = Path(directory).resolve()

    @contextmanager
    def lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".publish.lock"
        try:
            stream = path.open("x", encoding="utf-8")
        except FileExistsError as exc:
            raise ValueError("Another publisher owns the store lock; retry later. Do not auto-delete its lock.") from exc
        try:
            with stream:
                stream.write(now())
            yield
        finally:
            path.unlink()

    def current(self, revision=None):
        if revision is None:
            if not (self.root / "HEAD.json").is_file():
                raise ValueError("Memory is not initialized; run init")
            revision = load(self.root / "HEAD.json")["revision"]
        if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("Invalid memory revision")
        result = load(self.root / "snapshots" / (revision + ".json"))
        if fingerprint({k: v for k, v in result.items() if k != "revision"}) != revision:
            raise ValueError("Snapshot hash mismatch; do not use a mutated memory snapshot")
        return result

    def _base(self, expected):
        state = self.current()
        if not expected or expected != state["revision"]:
            raise ValueError("Stale/missing base_revision; inspect the current snapshot and rebase the proposal")
        return copy.deepcopy(state)

    def _publish(self, state, changes):
        previous = state.pop("revision", None)
        state.update(parent=previous, sequence=state.get("sequence", -1) + 1,
                     created_at=now(), changes=changes)
        state["revision"] = fingerprint(state)
        write_new(self.root / "snapshots" / (state["revision"] + ".json"), state)
        replace_json(self.root / "HEAD.json", {"revision": state["revision"]})
        return {"revision": state["revision"], "sequence": state["sequence"], "changes": changes}

    def init(self):
        with self.lock():
            if (self.root / "HEAD.json").exists():
                return {"revision": self.current()["revision"], "initialized": False}
            if (self.root / "snapshots").exists():
                raise ValueError("Snapshots without HEAD: recover deliberately instead of overwriting history")
            return self._publish({"schema": MEMORY_SCHEMA, "cases": {}, "lessons": {}, "topics": {}}, ["initialized"])

    def case(self, identity, revision=None, state=None):
        slug(identity, "case ID")
        state = state or self.current()
        if identity not in state["cases"]:
            raise ValueError("Unknown case ID")
        revision = revision or state["cases"][identity]["revision"]
        if not isinstance(revision, str) or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("Invalid case revision")
        value = load(self.root / "cases" / identity / (revision + ".json"))
        validate_case(value)
        shared_objects(value, self.root / "sessions")
        return value

    @staticmethod
    def _invalidate(state, cases=(), lessons=()):
        """Conservative invalidation: even alternate support needs explicit re-review."""
        changed_cases, affected = set(cases), set(lessons)
        for identity, lesson in state["lessons"].items():
            for ref in lesson["evidence"]:
                head = state["cases"].get(ref["case"])
                bad = (not head or head["status"] != "available" or ref["revision"] != head["revision"]
                       or ref["claim"] in head["withdrawn_claims"])
                if ref["case"] in changed_cases and bad:
                    affected.add(identity)
        changed = True
        while changed:
            before = len(affected)
            for identity, lesson in state["lessons"].items():
                if set(lesson.get("requires", [])) & affected:
                    affected.add(identity)
            changed = len(affected) != before
        for identity in affected:
            lesson = state["lessons"][identity]
            if lesson["status"] != "retired":
                lesson["status"] = "needs_review"
                lesson["invalidated_by"] = sorted(changed_cases | set(lessons))
        return sorted(affected)

    def ingest(self, paths, base_revision=None):
        cards = [load(p) for p in paths]
        if not cards:
            raise ValueError("No cards supplied")
        for card in cards:
            validate_case(card)
            require_valid_card(card)
        objects = {}
        for card, path in zip(cards, paths):
            objects.update(shared_objects(card, Path(path).parent / "sessions"))
        if len({c["id"] for c in cards}) != len(cards):
            raise ValueError("One version per case per ingest; do not pick an arbitrary winner")
        with self.lock():
            state = self.current()
            if base_revision is None and not state["cases"] and not state["lessons"]:
                base_revision = state["revision"]
            state = self._base(base_revision)
            write_shared(self.root / "sessions", objects)
            changed = []
            for card in cards:
                old = state["cases"].get(card["id"])
                if old and old["revision"] == card["revision"]:
                    continue  # Re-ingest cannot silently resurrect a withdrawn case/claim.
                path = self.root / "cases" / card["id"] / (card["revision"] + ".json")
                if path.exists():
                    validate_case(load(path))
                else:
                    write_new(path, card)
                state["cases"][card["id"]] = {
                    "revision": card["revision"], "title": content(card)["title"], "status": "available",
                    "withdrawn_claims": [], "claims": sorted(claims(card))}
                changed.append(card["id"])
            if not changed:
                return {"revision": state["revision"], "changes": [], "affected": []}
            affected = self._invalidate(state, cases=changed)
            result = self._publish(state, [{"ingested": changed, "needs_review": affected}])
            return {**result, "affected": affected}

    def impact(self, identity, claim=None):
        state, affected = self.current(), set()
        if identity in state["cases"]:
            if claim and claim not in state["cases"][identity]["claims"]:
                raise ValueError("Unknown claim")
            for key, lesson in state["lessons"].items():
                if any(ref["case"] == identity and (claim is None or ref["claim"] == claim) for ref in lesson["evidence"]):
                    affected.add(key)
        elif identity in state["lessons"]:
            affected.add(identity)
        else:
            raise ValueError("Unknown case/lesson ID")
        direct = sorted(affected)
        changed = True
        while changed:
            size = len(affected)
            for key, lesson in state["lessons"].items():
                if set(lesson["requires"]) & affected:
                    affected.add(key)
            changed = size != len(affected)
        return {"revision": state["revision"], "direct": direct, "all": sorted(affected),
                "topics": sorted({"/".join(state["lessons"][x]["topic"]) for x in affected})}

    def migrate(self, base_revision):
        """Rebind positional claim names to stable IDs and mark the memory schema.

        Cards are not rewritten: formal cards derive claim IDs at read time, so
        only the snapshot's claim lists and lesson evidence change.
        """
        from .case_format import claim_map
        with self.lock():
            state = self._base(base_revision)
            maps, cases, rebound = {}, 0, 0

            def names(identity, revision):
                key = (identity, revision)
                if key not in maps:
                    maps[key] = claim_map(self.case(identity, revision, state=state))
                return maps[key]

            for identity, head in sorted(state["cases"].items()):
                mapping = names(identity, head["revision"])
                if all(old == new for old, new in mapping.items()):
                    continue
                head["claims"] = sorted(mapping.get(c, c) for c in head["claims"])
                head["withdrawn_claims"] = sorted(mapping.get(c, c) for c in head["withdrawn_claims"])
                cases += 1
            for lesson in state["lessons"].values():
                for ref in lesson["evidence"]:
                    if ref["case"] not in state["cases"]:
                        continue
                    new = names(ref["case"], ref["revision"]).get(ref["claim"], ref["claim"])
                    if new != ref["claim"]:
                        ref["claim"] = new
                        rebound += 1
            state["schema"] = MEMORY_SCHEMA
            return self._publish(state, [{"migrated": MEMORY_SCHEMA, "cases_with_stable_claims": cases,
                                          "claim_bindings_rebound": rebound}])

    def withdraw(self, identity, reason, base_revision, claim=None):
        nonempty(reason, "withdraw reason")
        with self.lock():
            state = self._base(base_revision)
            if identity not in state["cases"]:
                raise ValueError("Unknown case ID")
            head = state["cases"][identity]
            if claim:
                if claim not in head["claims"]:
                    raise ValueError("Unknown claim; use the system-generated claim ID")
                head["withdrawn_claims"] = sorted(set(head["withdrawn_claims"]) | {claim})
            else:
                head["status"] = "withdrawn"
            head["withdrawal_reason"] = reason
            affected = self._invalidate(state, cases=[identity])
            return {**self._publish(state, [{"withdrawn": identity, "claim": claim, "reason": reason,
                                           "needs_review": affected}]), "affected": affected}

    @staticmethod
    def _lesson(item, state):
        allowed = {"id", "title", "topic", "stage", "summary", "signals", "when", "description", "unless", "why",
                   "how", "check", "evidence", "requires", "status"}
        fields(item, allowed, allowed - {"id", "requires", "unless", "status", "description", "check"}, "lesson")
        value = copy.deepcopy(item)
        value.setdefault("requires", [])
        value.setdefault("unless", [])
        value.setdefault("check", [])
        value.setdefault("status", "active")
        for field in ("title", "when", "why", "summary"):
            nonempty(value[field], "lesson." + field)
        if "description" in value:
            nonempty(value["description"], "lesson.description")
        if len(value["summary"].strip()) > SUMMARY_MAX:
            raise ValueError(f"lesson.summary: at most {SUMMARY_MAX} characters; it is the index line")
        stage = value["stage"]
        if (not isinstance(stage, list) or not stage or len(set(stage)) != len(stage)
                or any(s not in STAGES for s in stage)):
            raise ValueError("lesson.stage: expected a nonempty list drawn from " + "/".join(STAGES))
        strings(value["signals"], "lesson.signals", empty=False)
        signals = value["signals"]
        if len(signals) > SIGNALS_MAX or len(set(signals)) != len(signals):
            raise ValueError(f"lesson.signals: 1–{SIGNALS_MAX} distinct symbols")
        if any(s != s.strip() or len(s) > SIGNAL_MAX or "\n" in s for s in signals):
            raise ValueError("lesson.signals: each entry is one trimmed API/component/file symbol")
        generic = [s for s in signals if generic_signal(s)]
        if generic:
            raise ValueError("lesson.signals: plain words are not grep targets, use identifiers/file names: " + ", ".join(generic))
        strings(value["how"], "lesson.how", empty=False)
        for field in ("unless", "requires", "check"):
            strings(value[field], "lesson." + field)
        if not isinstance(value["topic"], list) or not 2 <= len(value["topic"]) <= 3:
            raise ValueError("topic must contain 2–3 path segments: domain/topic[/subtopic]")
        for part in value["topic"]:
            slug(part, "topic segment")
        if value["status"] not in {"candidate", "active", "disputed"}:
            raise ValueError("Proposals set candidate/active/disputed; needs_review is computed")
        if not isinstance(value["evidence"], list) or not value["evidence"]:
            raise ValueError("Every lesson needs specific case-claim evidence")
        for ref in value["evidence"]:
            fields(ref, ("case", "claim", "revision"), ("case", "claim", "revision"), "evidence")
            head = state["cases"].get(ref["case"])
            if not head or ref["revision"] != head["revision"] or ref["claim"] not in head["claims"]:
                raise ValueError("Evidence must identify an existing claim at the current case revision")
            if head["status"] != "available" or ref["claim"] in head["withdrawn_claims"]:
                raise ValueError("Withdrawn evidence cannot support a new/republished lesson")
        value.setdefault("id", "lesson-" + fingerprint([value["title"], value["evidence"]])[:20])
        slug(value["id"], "lesson ID")
        return value

    @staticmethod
    def _acyclic(lessons):
        incoming = {key: len(set(value["requires"])) for key, value in lessons.items()}
        reverse = {key: [] for key in lessons}
        for key, lesson in lessons.items():
            for dep in set(lesson["requires"]):
                if dep not in lessons:
                    raise ValueError("Unknown required lesson: " + dep)
                reverse[dep].append(key)
        queue, visited = [key for key, n in incoming.items() if n == 0], 0
        while queue:
            key = queue.pop()
            visited += 1
            for child in reverse[key]:
                incoming[child] -= 1
                if incoming[child] == 0:
                    queue.append(child)
        if visited != len(lessons):
            raise ValueError("Lesson dependency cycle; topics are navigation, not dependency edges")

    def apply(self, proposal):
        fields(proposal, ("base_revision", "upsert", "retire", "topic_descriptions"), ("base_revision",), "proposal")
        with self.lock():
            state = self._base(proposal["base_revision"])
            previous = copy.deepcopy(state["lessons"])
            updates = [self._lesson(x, state) for x in proposal.get("upsert", [])]
            # Existing stores remain readable. New proposals use the same final
            # card contract as ingest, not a second lesson approval process.
            for identity, revision in {(r["case"], r["revision"]) for x in updates for r in x["evidence"]}:
                require_valid_card(self.case(identity, revision, state))
            if len({x["id"] for x in updates}) != len(updates):
                raise ValueError("Duplicate lesson ID in proposal")
            updated, changed = {x["id"] for x in updates}, set()
            for value in updates:
                old = previous.get(value["id"])
                if old and {k: v for k, v in old.items() if k not in ("version", "invalidated_by")} != value:
                    changed.add(value["id"])
                value["version"] = (old or {}).get("version", 0) + 1
                state["lessons"][value["id"]] = value
            for item in proposal.get("retire", []):
                fields(item, ("id", "reason"), ("id", "reason"), "retire")
                nonempty(item["reason"], "retire.reason")
                if item["id"] not in state["lessons"] or item["id"] in updated:
                    raise ValueError("Retire must target a known lesson not also upserted")
                state["lessons"][item["id"]]["status"] = "retired"
                state["lessons"][item["id"]]["retirement_reason"] = item["reason"]
                changed.add(item["id"])
            self._acyclic(state["lessons"])
            # Revised dependencies invalidate consumers, unless explicitly reviewed in this same plan.
            affected = set(changed)
            while True:
                next_set = affected | {key for key, x in state["lessons"].items() if set(x["requires"]) & affected}
                if next_set == affected:
                    break
                affected = next_set
            for key in affected - updated - changed:
                if state["lessons"][key]["status"] != "retired":
                    state["lessons"][key]["status"] = "needs_review"
                    state["lessons"][key]["invalidated_by"] = sorted(changed)
            for key, lesson in state["lessons"].items():
                if lesson["status"] == "active" and any(state["lessons"][dep]["status"] != "active" for dep in lesson["requires"]):
                    if key in updated:
                        raise ValueError("Active lesson depends on an inactive/review-pending lesson: " + key)
                    lesson["status"] = "needs_review"
            descriptions = proposal.get("topic_descriptions", {})
            if not isinstance(descriptions, dict):
                raise ValueError("topic_descriptions must be a path-to-description object")
            for path, description in descriptions.items():
                if not 1 <= len(path.split("/")) <= 3:
                    raise ValueError("Topic depth must be 1–3")
                for part in path.split("/"):
                    slug(part, "topic path")
                state["topics"][path] = nonempty(description, "topic description")
            active = {k: v for k, v in state["lessons"].items() if v["status"] == "active"}
            errors = description_errors(descriptions) + structure_errors(active, state["topics"])
            if errors:
                raise ValueError("Structure contract violated; nothing published: " + " | ".join(errors))
            return self._publish(state, [{"upserted": sorted(updated), "changed_dependencies": sorted(changed),
                                          "needs_review": sorted(k for k, x in state["lessons"].items() if x["status"] == "needs_review")}])


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Maintain versioned memory; no automatic causal judgment or model calls.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "snapshot", "ingest", "apply", "impact", "withdraw", "export", "compact", "record-analysis", "migrate"):
        sub = commands.add_parser(name)
        sub.add_argument("--store", required=True)
        if name == "snapshot":
            sub.add_argument("--full", action="store_true", help="Explicitly expand the complete stored snapshot")
        elif name == "ingest":
            sub.add_argument("--cards", nargs="+", required=True)
            sub.add_argument("--base-revision")
        elif name == "apply":
            sub.add_argument("--plan", required=True)
        elif name == "export":
            sub.add_argument("--out", required=True, help="New Markdown reading directory; existing output is never overwritten")
            sub.add_argument("--link-cards", action="store_true", help="Development view: link to exact local card versions without copying them")
        elif name == "record-analysis":
            sub.add_argument("--records", required=True, help="Host-observed case-ID to analysis-label mapping")
            sub.add_argument("--base-revision", required=True)
        elif name == "compact":
            sub.add_argument("--out", required=True, help="New compact store; the original store is preserved")
        elif name == "migrate":
            sub.add_argument("--base-revision", required=True, help="Rebind claims to stable IDs under migloop-memory/2")
        elif name in ("impact", "withdraw"):
            sub.add_argument("--case" if name == "withdraw" else "--id", required=True)
            sub.add_argument("--claim")
            if name == "withdraw":
                sub.add_argument("--reason", required=True)
                sub.add_argument("--base-revision", required=True)
    args = parser.parse_args()
    memory = Memory(args.store)
    if args.command == "init":
        result = memory.init()
    elif args.command == "snapshot":
        state = memory.current()
        result = state if args.full else {
            **{k: state[k] for k in ("revision", "sequence", "parent")},
            "counts": {"cases": len(state["cases"]), "lessons": len(state["lessons"]),
                       "statuses": {status: sum(x["status"] == status for x in state["lessons"].values())
                                    for status in sorted(STATUSES)}},
            "view": "summary", "next": "Use recall browse/search --all-statuses; --full explicitly expands all stored data."}
    elif args.command == "ingest":
        result = memory.ingest(args.cards, args.base_revision)
    elif args.command == "apply":
        result = memory.apply(load(args.plan))
    elif args.command == "impact":
        result = memory.impact(args.id, args.claim)
    elif args.command == "export":
        from .publication import export_memory
        result = export_memory(memory, args.out, link_cards=args.link_cards)
    elif args.command == "record-analysis":
        from .analysis import record_analysis
        result = record_analysis(memory, load(args.records), args.base_revision)
    elif args.command == "compact":
        from .card_storage import compact_store
        result = compact_store(memory, args.out)
    elif args.command == "migrate":
        result = memory.migrate(args.base_revision)
    else:
        result = memory.withdraw(args.case, args.reason, args.base_revision, args.claim)
    print(json.dumps(result, ensure_ascii=False, indent=2))
