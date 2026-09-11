"""One paired development diagnostic. Only run-raw/run-tools call Luna."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASELINE = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/baseline-v1')
OUT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-20260911-member')


def load():
    spec = importlib.util.spec_from_file_location('longchain_base', HERE.parent / 'file-first-10/run_tools10.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(base):
    if OUT.exists():
        raise FileExistsError(OUT)
    old = base.RAW.verify_manifest(BASELINE)
    pools = base.verify_pools(old)
    original = next(c for c in old['cases'] if c['id'] == 'F10-01')
    pool = next(p for p in pools if Path(p['pool']) == Path(original['pool']))
    case = {**original, 'pool': pool['pool'], 'sid': pool['anchor'],
            'generation_end': '2026-07-24T22:16:20.102Z', 'observation_end': '2026-07-26T21:48:57.793Z',
            'settings': 'tools-settings.json'}
    OUT.mkdir(parents=True)
    for name in ('task.md', 'protocol.md', 'run.py'):
        shutil.copy2(HERE / name, OUT / name)
    for name in ('reference-units.json', 'scoring-core.json'):
        shutil.copy2(HERE.parent / 'file-first-10' / name, OUT / name)
    common = (OUT / 'task.md').read_text(encoding='utf-8')
    (OUT / 'raw-prompt.md').write_text(common + '\n操作面：只读 shell，自行解析原始 JSONL。中文输出；解释链可用表格或列表，不要求工具专用坐标。\n', encoding='utf-8')
    (OUT / 'tools-prompt.md').write_text(base.prompt(common, case['sid']), encoding='utf-8')
    shutil.copy2(BASELINE / 'runtime-settings.json', OUT / 'raw-settings.json')
    artifacts = {p.name: base.sha(p) for p in OUT.iterdir() if p.is_file()}
    base.save(OUT / 'manifest.json', {'schema': 'migloop-longchain-diagnostic/1', 'frozen_at': base.now(),
        'case': case, 'pool': pool, 'artifacts': artifacts, 'model': base.MODEL, 'effort': base.EFFORT,
        'timeout_seconds': 1800, 'python': str(base.DEFAULT_PYTHON),
        'raw_manifest_sha256': base.sha(BASELINE / 'manifest.json'),
        'runners': {str(p): base.sha(p) for p in (HERE / 'run.py', HERE.parent / 'file-first-10/run_tools10.py',
                    HERE.parent / 'file-first-10/run_raw10.py', base.RAW.OLD_RUNNER)},
        'automatic_retry': False, 'format_repair': False, 'planned_runs': {'raw': 1, 'tools': 1}})
    return {'prepared': str(OUT), 'model_calls': 0}


def verify(base):
    m = base.read(OUT / 'manifest.json')
    for name, digest in m['artifacts'].items():
        if base.sha(OUT / name) != digest:
            raise ValueError('Frozen artifact drift: ' + name)
    for path, digest in m['runners'].items():
        if base.sha(path) != digest:
            raise ValueError('Runner drift: ' + path)
    if base.tree_manifest(m['pool']['pool'])['content_digest'] != m['pool']['content_digest']:
        raise ValueError('Original pool changed')
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run-raw', 'freeze-tools', 'run-tools', 'verify'))
    mode = parser.parse_args().mode
    base = load()
    if mode == 'prepare':
        print(json.dumps(prepare(base)), flush=True)
        return
    m = verify(base)
    if mode == 'freeze-tools':
        package = OUT / 'code/src/migloop'
        if package.exists() or (OUT / 'tools-freeze.json').exists():
            raise FileExistsError('Tool package already frozen')
        before = base.tree_manifest(REPO / 'src/migloop')
        shutil.copytree(REPO / 'src/migloop', package, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        if base.tree_manifest(package) != before:
            raise ValueError('Source changed while freezing')
        base.save(OUT / 'tools-settings.json', base.settings(base.read(OUT / 'raw-settings.json'), OUT / 'code', m['python'], m['pool']))
        base.save(OUT / 'tools-freeze.json', {'time': base.now(), 'code': before, 'settings_sha256': base.sha(OUT / 'tools-settings.json')})
        print(json.dumps({'frozen': before['content_digest'], 'model_calls': 0}), flush=True)
        return
    if mode == 'verify':
        print(json.dumps({'verified': True, 'model_calls': 0}))
        return
    arm = mode.removeprefix('run-')
    if arm == 'tools':
        frozen = base.read(OUT / 'tools-freeze.json')
        if base.tree_manifest(OUT / 'code/src/migloop') != frozen['code'] or base.sha(OUT / 'tools-settings.json') != frozen['settings_sha256']:
            raise ValueError('Frozen tools changed')
    run = OUT / 'runs' / arm / 'rep1'
    print(json.dumps({'event': 'start', 'arm': arm, 'model': m['model'], 'effort': m['effort']}), flush=True)
    metric = base.RAW.launch(m['case']['pool'], run, (OUT / f'{arm}-prompt.md').read_text(encoding='utf-8'),
                           base.read(OUT / f'{arm}-settings.json'), m['timeout_seconds'])
    if arm == 'tools':
        result = base.postprocess(OUT, m, m['case'], run)
        base.save(run / 'system-cost.json', {'postprocess': result,
            'end_to_end_seconds': metric['elapsed_seconds'] + result['elapsed_seconds']})
    verify(base)
    print(json.dumps(metric, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
