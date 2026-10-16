"""Ordered stage signals, without duration thresholds or global 'seen' suppression."""
import re


PIPELINE = {"a2h-run", "a2h-init", "a2h-build", "mig-arch", "a2h-arch-scaffold",
            "a2h-spec", "a2h-plan", "a2h-execute", "a2h-verify", "a2h-retrospect",
            "arkts-visual-verify", "ecat-refine"}


def normalize(value):
    name = str(value or "").split(":")[-1]
    if name.endswith("-zh"):
        name = name[:-3]
    return name if name in PIPELINE else None


def claude_boundaries(records, calls):
    explicit = {}
    for idx, _, skill, _ in calls:
        if normalize(skill):
            explicit[idx] = normalize(skill)
    boundaries, current, last_attr = [], None, None
    for idx, record in enumerate(records):
        attr = normalize(record.get("attributionSkill"))
        changed_attr = attr and attr != last_attr
        if attr:
            last_attr = attr
        # A native Skill invocation wins at the same coordinate. Repeated stale
        # attribution does not bounce back after that invocation.
        candidate = explicit.get(idx) or (attr if changed_attr else None)
        if candidate is None and record.get("type") == "user":
            content = (record.get("message") or {}).get("content")
            if isinstance(content, str):
                match = re.search(r"<command-name>\s*/?([^<]+)</command-name>", content)
                candidate = normalize(match[1].strip()) if match else None
        if candidate and candidate != current:
            boundaries.append((idx, candidate))
            current = candidate
    return boundaries
