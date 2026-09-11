"""Compare exact query data across two kernels, without model calls or raw output."""

import argparse
import json
import subprocess
import sys

WORKER = """
import hashlib, json, sys, time
sys.path.insert(0, sys.argv[1])
from migloop.inquiry.store import Store
from migloop.inquiry.engine import Engine
store = Store(sys.argv[2])
engine = Engine(store)
measurements = []
for query in json.loads(sys.argv[3]):
    started = time.perf_counter()
    data = engine.query(query)
    measurements.append({
        'seconds': time.perf_counter() - started,
        'total': data['total'],
        'digest': hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    })
print(json.dumps(measurements))
store.close()
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', required=True)
    parser.add_argument('--after', required=True)
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    queries = [
        {'op': 'search', 'at': '2026-07-26T21:48:57.793Z', 'terms': ['priceDigits', 'priceSuffix', 'AbsoluteSizeSpan'], 'limit': 20},
        {'op': 'file', 'key': 'MemberCenterPage.ets', 'at': '2026-07-26T21:48:57.793Z', 'since': '2026-07-24T22:16:20.102Z', 'view': 'calls', 'terms': ['mask', 'image', 'price'], 'limit': 20},
        {'op': 'search', 'kind': 'agent', 'key': '9b3105a2-85ec-4889-9786-b3c220f06754:aslice8-pay-80bbb1f44b77da0f', 'at': '2026-07-24T22:16:20.102Z', 'terms': ['AbsoluteSizeSpan', 'priceText', 'stripCurrency'], 'limit': 20},
    ]
    results = []
    for root in (args.before, args.after):
        run = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', WORKER, root, args.db, json.dumps(queries)],
                             capture_output=True, text=True, encoding='utf-8', timeout=60, check=True)
        results.append(json.loads(run.stdout))
    equal = [a['digest'] == b['digest'] for a, b in zip(*results)]
    print(json.dumps({'model_calls': 0, 'before': results[0], 'after': results[1], 'identical': equal}))
    if not all(equal):
        raise SystemExit('Query output drift')


if __name__ == '__main__':
    main()
