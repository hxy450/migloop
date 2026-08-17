"""Build the provider-neutral, self-contained MigLoop report."""
import json
import os
from importlib import resources


def load_asset(name):
    return resources.files("migloop.render.templates").joinpath(name).read_text(encoding="utf-8")


def load_template():
    return load_asset("viewer.html")


def page_title(trace):
    meta = trace.get("meta") or {}
    label = os.path.basename((meta.get("cwd") or "").rstrip("\\/")) or "Trace"
    sid8 = (meta.get("session_id") or "")[:8]
    return ("%s · %s" % (label, sid8)) if sid8 else label


def build_html(trace, template=None):
    template = template or load_template()
    payload = json.dumps(trace, ensure_ascii=False,
                         separators=(",", ":")).replace("</", "<\\/")
    payload = payload.replace("�", "?")
    if "__TRACE_JSON__" not in template:
        raise ValueError("viewer template is missing __TRACE_JSON__")
    html = template.replace("__TRACE_JSON__", payload)
    return html.replace("<title>MigLoop Trace</title>",
                        "<title>%s</title>" % page_title(trace), 1)

