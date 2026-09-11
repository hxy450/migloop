"""Optional MCP augmentation of a frozen raw investigation; no baseline rerun."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-20260911-member')
OUT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-hybrid-20260911-member')


def old():
    spec = importlib.util.spec_from_file_location('hybrid_frozen_parent', HERE / 'run.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def hybrid_settings(raw, tools):
    config = deepcopy(raw)
    config['mcp_servers'] = deepcopy(tools['mcp_servers'])
    if {**config, 'features.shell_tool': False} != tools:
        raise ValueError('Unexpected setting difference beyond optional MCP/shell')
    return config


def hybrid_prompt(raw_prompt, sid):
    return raw_prompt + (
        '\n可选辅助：除上面的只读 shell，你还可使用 migloop MCP，两者可自由混用。'
        '不是必须走 MCP，也不必沿固定链路调查。\n'
        f'MCP 的 sid={sid}\n'
        '需要时用 guide(topic="time") 看接口；batch 可批量查询 file/agent/search/diff/blame/events/expand。'
        'MCP 信息不足或不顺手就直接读取池内原始转录，不必绕回工具。\n'
        '本阶段最终仍交上文要求的中文普通报告，不需要 YAML、check 或 via；'
        'guide 中有关最终 YAML 提交的要求本轮不适用。后续展示链路由另一个阶段处理。\n')


def prepare(base, prior):
    if OUT.exists():
        raise FileExistsError(OUT)
    frozen = base.read(PRIOR / 'tools-freeze.json')
    if base.tree_manifest(PRIOR / 'code/src/migloop') != frozen['code']:
        raise ValueError('Prior frozen code changed')
    config = hybrid_settings(base.read(PRIOR / 'raw-settings.json'), base.read(PRIOR / 'tools-settings.json'))
    OUT.mkdir(parents=True)
    for source, name in ((HERE / 'hybrid.py', 'driver.py'), (HERE / 'hybrid-protocol.md', 'protocol.md'),
                         (PRIOR / 'runs/raw/rep1/report.md', 'baseline-report.md')):
        shutil.copy2(source, OUT / name)
    base.save(OUT / 'settings.json', config)
    raw_prompt = (PRIOR / 'raw-prompt.md').read_bytes().decode('utf-8')
    (OUT / 'prompt.md').write_bytes(hybrid_prompt(raw_prompt, prior['case']['sid']).encode('utf-8'))
    base.save(OUT / 'manifest.json', {'schema': 'migloop-optional-mcp-diagnostic/1', 'frozen_at': base.now(),
        'prior': str(PRIOR), 'prior_manifest_sha256': base.sha(PRIOR / 'manifest.json'),
        'code_manifest_sha256': base.sha(PRIOR / 'tools-freeze.json'), 'code_digest': frozen['code']['content_digest'],
        'driver_sha256': base.sha(HERE / 'hybrid.py'), 'case': prior['case'],
        'model': prior['model'], 'effort': prior['effort'], 'timeout_seconds': prior['timeout_seconds'],
        'artifacts': {p.name: base.sha(p) for p in OUT.iterdir() if p.is_file()},
        'baseline_report_sha256': base.sha(PRIOR / 'runs/raw/rep1/report.md'),
        'planned_investigations': 1, 'conditional_presentations': 1, 'automatic_retry': False})
    return {'prepared': str(OUT), 'model_calls': 0}


def verify(base, prior):
    manifest = base.read(OUT / 'manifest.json')
    for name, digest in manifest['artifacts'].items():
        if base.sha(OUT / name) != digest:
            raise ValueError('Frozen hybrid artifact drift: ' + name)
    if base.sha(HERE / 'hybrid.py') != manifest['driver_sha256']:
        raise ValueError('Driver changed after freeze')
    if base.sha(PRIOR / 'manifest.json') != manifest['prior_manifest_sha256'] or base.sha(PRIOR / 'tools-freeze.json') != manifest['code_manifest_sha256']:
        raise ValueError('Prior manifest changed')
    if base.tree_manifest(PRIOR / 'code/src/migloop') != base.read(PRIOR / 'tools-freeze.json')['code']:
        raise ValueError('Frozen MCP package changed')
    expected = hybrid_settings(base.read(PRIOR / 'raw-settings.json'), base.read(PRIOR / 'tools-settings.json'))
    if base.read(OUT / 'settings.json') != expected:
        raise ValueError('Not an additive configuration')
    if manifest['case'] != prior['case']:
        raise ValueError('Case drift')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'run', 'present'))
    mode = parser.parse_args().mode
    previous = old()
    base = previous.load()
    prior = previous.verify(base)
    if mode == 'prepare':
        print(json.dumps(prepare(base, prior)), flush=True)
        return
    m = verify(base, prior)
    if mode == 'verify':
        print(json.dumps({'verified': True, 'model_calls': 0}))
        return
    arm = 'hybrid' if mode == 'run' else 'present'
    config = base.read(OUT / 'settings.json')
    if mode == 'run':
        prompt = (OUT / 'prompt.md').read_bytes().decode('utf-8')
    else:
        if not (OUT / 'runs/hybrid/rep1/metrics.json').exists():
            raise ValueError('Finish hybrid first')
        decision = base.read(OUT / 'presentation-decision.json')
        if decision.get('proceed') is not True or not decision.get('reason'):
            raise ValueError('Explicit recorded condition review required')
        presentation = HERE / 'presentation-task.md'
        prompt = presentation.read_text(encoding='utf-8').replace('{sid}', m['case']['sid'])
        prompt += '\n\n以下是冻结的原始组报告，不是参考答案，其断言可能不成立：\n\n'
        prompt += (OUT / 'baseline-report.md').read_text(encoding='utf-8')
        base.save(OUT / 'presentation-freeze.json', {'time': base.now(), 'decision_sha256': base.sha(OUT / 'presentation-decision.json'),
            'task_sha256': base.sha(presentation), 'baseline_sha256': m['baseline_report_sha256']})
    run = OUT / 'runs' / arm / 'rep1'
    print(json.dumps({'event': 'start', 'arm': arm, 'model': m['model'], 'effort': m['effort']}), flush=True)
    result = base.RAW.launch(m['case']['pool'], run, prompt, config, m['timeout_seconds'])
    if mode == 'present':
        verification = base.postprocess(PRIOR, prior, m['case'], run)
        base.save(run / 'system-cost.json', {'postprocess': verification,
            'end_to_end_seconds': result['elapsed_seconds'] + verification['elapsed_seconds']})
    verify(base, prior)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
