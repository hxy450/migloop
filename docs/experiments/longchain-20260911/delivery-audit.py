"""Audit service packets and model-visible wrappers separately; never score causes."""
import argparse
import json
import re


def audit(run):
    from migloop import investigation, probe

    calls = probe._transcript_calls(run) or []
    wrappers = []
    for index, call in enumerate(calls):
        if call['tool'] not in ('exec', 'wait'):
            continue
        body = call.get('text') or ''
        total = re.search(r'Warning: truncated output \(original token count: (\d+)\)', body)
        removed = re.search(r'(\d+) tokens truncated', body)
        wrappers.append({
            'call_index': index, 'tool': call['tool'], 'chars': len(body),
            'truncated': bool(total),
            'original_tokens_reported': int(total[1]) if total else None,
            'omitted_tokens_reported': int(removed[1]) if removed else None,
            'slice8_id_present': 'agent-aslice8-pay-80bbb1f44b77da0f' in body,
            'slice8_source_ref_present': 'raw:513197d2aa749cf1d75a055a7ff31697a747cadc' in body,
        })
    batches = []
    for call in calls:
        if call['tool'] != 'batch':
            continue
        args = call['input']
        packet = investigation.parse_receipt('batch', args, probe._unwrap_result(call['text']))['data']
        items = []
        for item in packet['items']:
            body = item.get('data') or {}
            sections = {}
            for name, section in body.get('sections', {}).items():
                if section.get('mode') != 'count_only':
                    sections[name] = {
                        'total': section['total'], 'returned_rows': len(section['rows']),
                        'next_offset': section['next_offset'],
                    }
            items.append({'tool': item['tool'], 'args': item['args'], 'status': item['status'],
                          'budget_adjusted': item['budget_adjusted'], 'sections': sections})
        batches.append({'number': len(batches) + 1, 'max_chars': args.get('max_chars'),
                        'server_response_chars': len(call['text']), 'items': items})
    return {'basis': 'Recorded service returns and separately recorded exec/wait visible text; no replay substituted',
            'run': run, 'wrappers': wrappers, 'batches': batches,
            'warning': 'Successful service receipts do not prove complete delivery through a truncated wrapper.',
            'model_calls': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    args = parser.parse_args()
    print(json.dumps(audit(args.run), ensure_ascii=False, indent=2))
