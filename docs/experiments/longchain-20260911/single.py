"""One investigator, raw + MCP, mandatory checked-reference submission.

Only `run` launches one model. Postprocessing never invokes a model or rewrites
the submitted draft. The previous raw and tools experiments remain immutable.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PRIOR = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-20260911-member')
OUT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/single-investigator-20260911-member')


def parent():
    spec = importlib.util.spec_from_file_location('single_previous', HERE / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prompt(raw, sid):
    return raw + (
        '\n本轮操作与交付补充（只替换最后表示格式，调查问题和材料不变）：\n'
        '同一个调查员自由使用只读shell与migloop MCP，不要求沿图走或填写via；不要派给第二个模型。\n'
        f'MCP sid={sid}。需要时guide(topic="time")了解接口；原始读取始终保留。\n'
        '调查结束后，由你自己用guide(topic="verdict")的v3模板组织节点原因、原始证据和解释链，'
        '将完整稿交check构建图；你可以根据诊断继续补查修改，但不为连通而编造历史关系。\n'
        '最终仅用一个yaml或json代码块原样返回最后一次check的submission_ref，可附简短摘要，'
        '不重复长稿，不提交未经check的新结论。保留未证断点也可提交；'
        '原文未被工具解析不等于没有发生，定位有效也不证明原文支持你的主张。\n'
    )


POSTPROCESS = r'''
import hashlib, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from migloop import atoms, investigation, probe, recorded_report, service, submission, verdict_v3, via
run, sid, expected = Path(sys.argv[2]), sys.argv[3], json.loads(sys.argv[4])
started = time.perf_counter()
report = (run / 'report.md').read_text(encoding='utf-8')
metadata = json.loads((run / 'metrics.json').read_text(encoding='utf-8'))
ledger = service.session_ledger(sid)
identity = atoms.ledger_identity(ledger)
calls = probe._transcript_calls(str(run)) or []
trace_identity = via.trace_identity(ledger, calls, {'harness_identity': identity})
loaded = submission.load_checked_submission(report, ledger, calls, trace_identity, identity)
errors = list(loaded['errors'])
origin = recorded_report.authenticate(str(run), report, metadata)
if not origin['verified']:
    errors.append('Native final response authentication failed')
if loaded['data'] is not None and not errors:
    target = loaded['data']['target']
    actual, task = target['file'].replace('\\', '/'), expected['file'].replace('\\', '/')
    if actual != task and not actual.endswith('/' + task):
        errors.append('Final target differs from the frozen task')
    def stamp(value):
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc)
    for field, source in (('at', 'observation_end'), ('since_ts', 'generation_end')):
        if target.get(field) is None or stamp(target[field]) != stamp(expected[source]):
            errors.append('Final boundary differs from task: ' + field)
built = verdict_v3.build(ledger, loaded['data'] if not errors else None, errors,
    {'raw': loaded['raw'], 'harness_identity': identity, 'trace_identity': trace_identity})
result = {'schema': 'migloop-single-investigator-final/1', **loaded, 'errors': errors,
    'harness_identity': identity, 'trace_identity': trace_identity, 'native_report': origin,
    'verification': built, 'submission_policy': 'same_investigator_checked_reference',
    'report_sha256': hashlib.sha256((run / 'report.md').read_bytes()).hexdigest(),
    'semantic_checked': False, 'format_repair': False, 'postprocess_model_calls': 0}
def save(name, data):
    with (run / name).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
save('verdict.json', result)
save('query-trace.json', investigation.project_trace(ledger, calls))
if not errors:
    name = 'verdict.yaml' if loaded['kind'] == 'yaml' else 'verdict.document.json'
    with (run / name).open('xb') as stream:
        stream.write(loaded['raw'].encode('utf-8'))
print(json.dumps({'errors': errors, 'native_verified': origin['verified'],
    'nodes': len(built['argument_graph']['nodes']), 'edges': len(built['argument_graph']['edges']),
    'semantic_checked': False, 'elapsed_seconds': time.perf_counter() - started}, ensure_ascii=False))
'''


def prepare(base, old):
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.mkdir(parents=True)
    before = base.tree_manifest(REPO / 'src/migloop')
    package = OUT / 'code/src/migloop'
    shutil.copytree(REPO / 'src/migloop', package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
    if base.tree_manifest(package) != before or base.tree_manifest(REPO / 'src/migloop') != before:
        raise ValueError('Source changed during freeze')
    raw = base.read(PRIOR / 'raw-settings.json')
    config = base.settings(raw, OUT / 'code', old['python'], old['pool'])
    config['features.shell_tool'] = True
    config['mcp_servers']['migloop']['env']['MIGLOOP_FINAL_MODE'] = 'reference'
    if {**config, 'mcp_servers': raw.get('mcp_servers', {})} != raw:
        raise ValueError('Unexpected raw condition change')
    base.save(OUT / 'settings.json', config)
    for file in ('single.py', 'single-protocol.md'):
        shutil.copy2(HERE / file, OUT / file)
    (OUT / 'prompt.md').write_bytes(prompt((PRIOR / 'raw-prompt.md').read_bytes().decode('utf-8'), old['case']['sid']).encode('utf-8'))
    base.save(OUT / 'manifest.json', {'schema': 'migloop-single-investigator-diagnostic/1',
        'frozen_at': base.now(), 'case': old['case'], 'pool': old['pool'], 'python': old['python'],
        'model': old['model'], 'effort': old['effort'], 'timeout_seconds': old['timeout_seconds'],
        'code': before, 'driver_sha256': base.sha(HERE / 'single.py'),
        'prior_manifest_sha256': base.sha(PRIOR / 'manifest.json'),
        'artifacts': {p.name: base.sha(p) for p in OUT.iterdir() if p.is_file()},
        'automatic_retry': False, 'format_repair': False, 'planned_model_sessions': 1})
    return {'prepared': str(OUT), 'model_calls': 0, 'code_digest': before['content_digest']}


def verify(base):
    manifest = base.read(OUT / 'manifest.json')
    for name, sha in manifest['artifacts'].items():
        if base.sha(OUT / name) != sha:
            raise ValueError('Frozen artifact drift: ' + name)
    if base.sha(HERE / 'single.py') != manifest['driver_sha256']:
        raise ValueError('Driver changed after freeze')
    if base.sha(PRIOR / 'manifest.json') != manifest['prior_manifest_sha256']:
        raise ValueError('Parent experiment changed')
    if base.tree_manifest(OUT / 'code/src/migloop') != manifest['code']:
        raise ValueError('Frozen code changed')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    mode = parser.parse_args().mode
    previous = parent()
    base = previous.load()
    old = previous.verify(base)
    if mode == 'prepare':
        print(json.dumps(prepare(base, old)), flush=True)
        return
    manifest = verify(base)
    if mode == 'verify':
        print(json.dumps({'verified': True, 'model_calls': 0}), flush=True)
        return
    run = OUT / 'runs/single/rep1'
    config = base.read(OUT / 'settings.json')
    print(json.dumps({'event': 'start', 'model': manifest['model'], 'effort': manifest['effort'], 'sessions': 1}), flush=True)
    metric = base.RAW.launch(manifest['case']['pool'], run, (OUT / 'prompt.md').read_bytes().decode('utf-8'),
                             config, manifest['timeout_seconds'])
    started = time.perf_counter()
    expected = {k: manifest['case'][k] for k in ('file', 'generation_end', 'observation_end')}
    cmd = [manifest['python'], '-I', '-B', '-X', 'utf8', '-c', POSTPROCESS, str(OUT / 'code/src'),
           str(run), manifest['case']['sid'], json.dumps(expected)]
    with (run / 'postprocess.stdout.txt').open('xb') as out, (run / 'postprocess.stderr.txt').open('xb') as err:
        process = subprocess.run(cmd, cwd=manifest['case']['pool'], env=base._child_env(config['mcp_servers']['migloop']),
            stdout=out, stderr=err, timeout=600, check=False,
            **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}))
    elapsed = time.perf_counter() - started
    base.save(run / 'system-cost.json', {'postprocess': {'status': 'completed' if process.returncode == 0 else 'error',
        'elapsed_seconds': elapsed, 'model_calls': 0}, 'end_to_end_seconds': metric['elapsed_seconds'] + elapsed})
    verify(base)
    print(json.dumps(metric, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
