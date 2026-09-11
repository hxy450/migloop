"""Summarize actual saved wire replies; never query history or call a model."""
import json
import sys
from pathlib import Path

ROOT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-20260911-member')
sys.path.insert(0, str(ROOT / 'code/src'))
from migloop import batch_wire


def main():
    report = {'basis': 'saved MCP wire, not reconstructed hypothetical delivery', 'files': [], 'agents': []}
    requests = []
    for line in (ROOT / 'runs/tools/rep1/events.jsonl').read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        item = event.get('item', {})
        if event['type'] != 'item.completed' or item.get('tool') not in ('changes', 'batch'):
            continue
        text = '\n'.join(p['text'] for p in item['result']['content'] if p.get('type') == 'text')
        if item['tool'] == 'changes':
            data = json.JSONDecoder().raw_decode(text)[0]
            unknown = data['unclassified_related']
            report['changes'] = {'confirmed': data['total'], 'complete': data['complete'],
                'unclassified_total': unknown['total'], 'unclassified_shown': len(unknown['rows']),
                'unclassified_remaining': unknown['remaining'],
                'unclassified_entries': [{'call_id': r.get('call_id'),
                    'pointers': [{'source': r.get('source'), 'line': p.get('line')} for p in r.get('pointers', [])]}
                    for r in unknown['rows']]}
            continue
        queries = item['arguments']['requests']
        requests.extend(queries)
        data = batch_wire.unpack(text.split('\nMIGLOOP_BATCH_WIRE_RECEIPT ')[0], queries)
        for entry in data['items']:
            body = entry.get('data') or {}
            if entry['tool'] == 'file':
                report['files'].append({'args': entry.get('args'), 'status': entry['status'],
                    'sections': {k: {'total': v['total'], 'shown': len(v['rows']), 'remaining': v['remaining'],
                        'actors': list(dict.fromkeys(r.get('agent') for r in v['rows']))}
                        for k, v in body.get('sections', {}).items()},
                    'body_sources': {'total': body.get('body_sources', {}).get('total'),
                        'shown': [{'source': r['source'], 'line': r['line']} for r in body.get('body_sources', {}).get('entries', [])]}})
            if entry['tool'] == 'agent':
                report['agents'].append({'args': entry.get('args'), 'status': entry['status'],
                    'dispatches': body.get('sections', {}).get('dispatches')})
    report['requests'] = requests
    report['request_count'] = len(requests)
    with (ROOT / 'delivery-audit.json').open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({'saved': str(ROOT / 'delivery-audit.json'), 'requests': len(requests)}))


if __name__ == '__main__':
    main()
