"""Frozen Luna iterations on existing cases. No raw rerun or automatic retry."""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BASELINE = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/baseline-v1')
PRIOR = BASELINE.parent / 'longchain-20260911-member'
ROOT = BASELINE.parent / 'inquiry-iterations-20260911'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load(HERE.parent / 'file-first-10/run_tools10.py', 'inquiry_iteration_base')


def command(root, db):
    return [str(BASE.DEFAULT_PYTHON), '-I', '-B', '-X', 'utf8', '-c',
            f"import sys;sys.path.insert(0,{str(root / 'code/src')!r});from migloop.inquiry.__main__ import main;main()",
            '--db', str(db)]


def prepare(root, effort='medium'):
    if root.exists():
        raise FileExistsError(root)
    old = BASE.RAW.verify_manifest(BASELINE)
    root.mkdir(parents=True)
    package = root / 'code/src/migloop'
    package.mkdir(parents=True)
    shutil.copy2(REPO / 'src/migloop/__init__.py', package / '__init__.py')
    shutil.copytree(REPO / 'src/migloop/inquiry', package / 'inquiry', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('iterate.py', 'luna-audit.py', 'iteration-plan.md'):
        shutil.copy2(HERE / name, root / name)
    raw = BASE.read(BASELINE / 'runtime-settings.json')
    pools = {}
    for pool in sorted({c['pool'] for c in old['cases']}):
        identity = BASE.tree_manifest(pool)
        db = root / ('pool-' + identity['content_digest'][:12] + '.sqlite')
        imported = subprocess.run(command(root, db) + ['import', '--pool', pool], check=True,
                                  capture_output=True, text=True, encoding='utf-8', timeout=180)
        pools[pool] = {'index_path': str(db), 'inventory': identity, **json.loads(imported.stdout)}
    # Fetch only the frozen package's generic guide, no case reference material.
    guide = subprocess.run(command(root, next(iter(pools.values()))['index_path'])[:6] +
        [f"import sys;sys.path.insert(0,{str(root / 'code/src')!r});from migloop.inquiry.interfaces import GUIDE;print(GUIDE)"],
        capture_output=True, text=True, encoding='utf-8', check=True).stdout
    cases = []
    for original in old['cases']:
        out = root / original['id']
        out.mkdir()
        task = (BASELINE / original['prompt']).read_text(encoding='utf-8')
        if original['id'] == 'F10-01':
            task = (PRIOR / 'raw-prompt.md').read_text(encoding='utf-8')
        generation = re.search(r'生成结束：([^，\s]+)', task)[1]
        end = re.search(r'观察截止：([^，\s]+)', task)[1]
        case = {**original, 'generation_end': generation, 'observation_end': end}
        pool = pools[case['pool']]
        cmd = command(root, pool['index_path'])
        config = {**raw, 'model_reasoning_effort': effort, 'mcp_servers': {'inquiry': {'command': cmd[0], 'args': cmd[1:] + ['mcp'],
                   'required': True, 'startup_timeout_sec': 45, 'tool_timeout_sec': 120}}}
        BASE.RAW.command(case['pool'], config)
        BASE.save(out / 'settings.json', config)
        prompt = task + ('\n本轮操作面与交付补充：保留只读shell，额外提供inquiry MCP。不要调用第二模型；'
            '由你自己调查并submit完整inquiry/1原稿，查看诊断，必要时自行补查。最终只返回最后一次submit的report_id、source_sha256两个字段，'
            '原因和摘要只放submit原稿，不另写散文结论，避免交付两份不同的原因。以下通用GUIDE不含本题答案。\n\n') + guide
        (out / 'prompt.md').write_text(prompt, encoding='utf-8')
        BASE.save(out / 'manifest.json', {'schema': 'inquiry-iteration-case/1', 'case': case,
            'code_root': str(root / 'code/src'), 'index_path': pool['index_path'], 'import_seconds': pool['seconds'],
            'model': BASE.MODEL, 'effort': effort, 'timeout_seconds': 1800,
            'prompt_sha256': BASE.sha(out / 'prompt.md'), 'settings_sha256': BASE.sha(out / 'settings.json'),
            'automatic_retry': False, 'format_repair': False})
        cases.append(case)
    BASE.save(root / 'manifest.json', {'schema': 'inquiry-iteration/1', 'created': BASE.now(), 'cases': cases, 'effort': effort,
        'code': BASE.tree_manifest(package), 'pools': pools, 'raw_manifest_sha256': BASE.sha(BASELINE / 'manifest.json'),
        'driver_sha256': BASE.sha(HERE / 'iterate.py'),
        'artifacts': {str(p.relative_to(root)): BASE.sha(p) for p in root.rglob('*')
                      if p.is_file() and p.suffix != '.sqlite' and 'code' not in p.relative_to(root).parts}})
    print(json.dumps({'prepared': str(root), 'cases': len(cases), 'model_calls': 0}), flush=True)


def verify(root):
    manifest = BASE.read(root / 'manifest.json')
    if BASE.tree_manifest(root / 'code/src/migloop') != manifest['code']:
        raise ValueError('Frozen code drift')
    for path, digest in manifest['artifacts'].items():
        if BASE.sha(root / path) != digest:
            raise ValueError('Frozen artifact drift: ' + path)
    if BASE.sha(HERE / 'iterate.py') != manifest['driver_sha256']:
        raise ValueError('Driver drift')
    for pool, value in manifest['pools'].items():
        if BASE.tree_manifest(pool) != value['inventory']:
            raise ValueError('Source pool drift')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run'))
    parser.add_argument('round')
    parser.add_argument('--case')
    parser.add_argument('--effort', choices=('medium', 'high'), default='medium', help='prepare only; frozen per round')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z0-9-]+', args.round):
        raise ValueError('Simple round label required')
    root = ROOT / args.round
    if args.mode == 'prepare':
        prepare(root, args.effort)
        return
    manifest = verify(root)
    if args.mode == 'verify':
        print(json.dumps({'verified': True, 'model_calls': 0}), flush=True)
        return
    case = next(c for c in manifest['cases'] if c['id'] == args.case)
    out = root / case['id']
    BASE.RAW.EFFORT = BASE.read(out / 'manifest.json')['effort']
    print(json.dumps({'started': case['id'], 'round': args.round, 'model': BASE.MODEL}), flush=True)
    metrics = BASE.RAW.launch(case['pool'], out / 'runs/inquiry/rep1',
                             (out / 'prompt.md').read_text(encoding='utf-8'), BASE.read(out / 'settings.json'), 1800)
    audited = subprocess.run([str(BASE.DEFAULT_PYTHON), '-B', '-X', 'utf8', str(root / 'luna-audit.py'), str(out)],
                              capture_output=True, text=True, encoding='utf-8', timeout=180)
    (out / 'audit.stdout.txt').write_text(audited.stdout, encoding='utf-8')
    (out / 'audit.stderr.txt').write_text(audited.stderr, encoding='utf-8')
    verify(root)
    print(json.dumps({'metrics': metrics, 'audit_exit_code': audited.returncode, 'audit': audited.stdout}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
