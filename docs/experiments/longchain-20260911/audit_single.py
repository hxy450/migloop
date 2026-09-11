"""Audit saved investigator delivery or profile its frozen checker, no model."""
import argparse
import cProfile
import io
import json
import os
import pstats
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/single-investigator-20260911-member')
RUN = ROOT / 'runs/single/rep1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('audit', 'profile', 'profile-live'))
    mode = parser.parse_args().mode
    config = json.loads((ROOT / 'settings.json').read_text(encoding='utf-8'))
    code = Path(__file__).resolve().parents[3] / 'src' if mode == 'profile-live' else ROOT / 'code/src'
    sys.path.insert(0, str(code))
    from migloop import batch_wire, probe
    if mode.startswith('profile'):
        os.environ.update(config['mcp_servers']['migloop']['env'])
        from migloop import draft_check, service
        manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
        ledger = service.session_ledger(manifest['case']['sid'])
        document = json.loads((RUN / 'verdict.json').read_text(encoding='utf-8'))
        profiler = cProfile.Profile()
        started = time.perf_counter()
        result = profiler.runcall(draft_check.evaluate, ledger, document['raw'])
        elapsed = time.perf_counter() - started
        output = io.StringIO()
        pstats.Stats(profiler, stream=output).sort_stats('cumulative').print_stats(30)
        checks = [c for c in probe._transcript_calls(str(RUN)) or [] if c['tool'] == 'check']
        expected = json.loads(checks[-1]['text'])
        value = {'elapsed_seconds': elapsed, 'profile': output.getvalue(), 'presentation': result['presentation'],
                 'matches_recorded_check': result == expected,
                 'changed_fields': [k for k in set(result) | set(expected) if result.get(k) != expected.get(k)],
                 'model_calls': 0}
    else:
        calls = probe._transcript_calls(str(RUN)) or []
        value = {'basis': 'recorded call/return delivery, not hypothetical available data',
                 'calls': [], 'queries': [], 'file_directories': [], 'model_calls': 0}
        for row in calls:
            tool, args = row['tool'], row.get('input') or {}
            value['calls'].append({'tool': tool, 'has_result': row.get('has_result'),
                'is_error': row.get('is_error'), 'delivery_truncated': row.get('delivery_truncated'),
                'chars': len(row.get('text') or '')})
            if tool != 'batch' or not row.get('has_result'):
                continue
            text = probe._unwrap_result(row.get('text') or '')
            raw = json.JSONDecoder().raw_decode(text)[0]
            data = batch_wire.unpack(raw, args['requests']) if raw.get('schema') == batch_wire.SCHEMA else raw
            for item in data['items']:
                value['queries'].append({'tool': item['tool'], 'args': item.get('args'), 'status': item['status']})
                body = item.get('data') or {}
                if body.get('participants'):
                    value['file_directories'].append({'args': item.get('args'), 'participants': body['participants'],
                        'write_page_actors': [r.get('agent') for r in body.get('sections', {}).get('writes', {}).get('rows', [])]})
        value['tool_counts'] = dict(Counter(row['tool'] for row in value['calls']))
        value['query_count'] = len(value['queries'])
    path = ROOT / ('checker-profile-live.json' if mode == 'profile-live' else
                   'checker-profile.json' if mode == 'profile' else 'single-delivery-audit.json')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'saved': str(path), **{k: v for k, v in value.items() if k in ('tool_counts', 'query_count', 'elapsed_seconds')}}))


if __name__ == '__main__':
    main()
