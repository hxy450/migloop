"""Time-scoped dispatch navigation shared by atom queries and argument checks.

Keep the existing ledger links, but do not certify its prompt/name heuristics as
native identity. A dispatch is an agent-to-agent relation, never a file effect.
"""
from __future__ import annotations

import os
from collections import Counter

from . import atoms, raw_events, temporal
from . import transcript_store as store
from .time_scope import _iso, _time


def rows(ledger, aid, window):
    from .temporal_atom import _expand, _pointer

    scope = {'kind': 'agent', 'key': aid, 'at': window.at, 'since_ts': window.since}
    selected = []
    for parent in ledger.agents.values():
        actions = [a for a in parent.actions if a.kind == 'dispatch'
                   and (parent.id == aid or a.detail.get('child') == aid)
                   and a.src and a.tuid and a.ok is True and window.contains(a.done_ts)]
        if not actions:
            continue
        native = raw_events._scan(ledger, parent.id)
        use_counts = Counter((event.source, event.call_id)
                             for event in native['events'] for p in event.parts if p.direction == 'use')
        by_use = {(event.source, p.record.line, p.block, event.call_id): (event, p)
                  for event in native['events'] for p in event.parts if p.direction == 'use'}
        for action in actions:
            child = ledger.agents.get(action.detail.get('child'))
            if child is None or child.id == parent.id:
                continue
            path, first, last = action.src
            path = os.path.normcase(os.path.abspath(path))
            if type(first) is not int or type(last) is not int or min(first, last) < 0:
                continue
            try:
                involved = [os.path.normcase(os.path.abspath(p)) for p in [path, *child.sources]]
                if any((os.stat(p).st_mtime_ns, os.stat(p).st_size) != ledger.source_stats.get(p)
                       for p in involved):
                    continue
            except OSError:
                continue
            pair = by_use.get((path, first + 1, action.blk, action.tuid)) or by_use.get((path, first + 1, None, action.tuid))
            if not pair:
                continue
            event, use = pair
            results = [p for p in event.parts if p.direction == 'result']
            if not event.addressable or len(results) != 1 or use_counts[(event.source, event.call_id)] != 1:
                continue
            result = results[0]
            start, end = use.record.ts, result.record.ts
            if (not start or not end or start > end or not window.contains(end)
                    or result.record.line != last + 1 or raw_events._failed(result.payload)
                    or start != _iso(_time(action.ts)) or end != _iso(_time(action.done_ts))):
                continue
            # Avoid disclosing a child inferred only from future transcript text.
            first_seen = []
            for source in child.sources:
                for record in store.records(source, source=store.source_spec(ledger, source)):
                    if record.ts:
                        first_seen.append(record.ts)
                        break
            if not first_seen or not window.ended(min(first_seen)):
                continue
            sidecar = result.record.value.get('toolUseResult', {})
            native_id = sidecar.get('agentId') if isinstance(sidecar, dict) else None
            confirmed = bool(native_id and child.id == 'agent-' + str(native_id))
            status = 'confirmed' if confirmed else 'candidate'
            basis = 'native_result_agent_id' if confirmed else 'ledger_dispatch_match_not_native_identity'
            up, rp = _pointer(use, window), _pointer(result, window)
            # This relation is known at the result, not an invented snapshot of
            # the parent's context at request. Narrow pre-request inputs freely.
            target = child.id if parent.id == aid else parent.id
            selected.append({'id': atoms.event_id_for_action(parent, action), 'agent': parent.id,
                'seq': action.seq, 'call_id': action.tuid, 'tool': action.tool,
                'ts': end, 'use_ts': start, 'done_ts': end, 'call_state': 'returned',
                'reference_status': 'addressable', 'use': up, 'result': rp,
                'operation': {'kind': 'dispatch', 'parent': parent.id, 'child': child.id,
                    'status': status, 'execution': 'confirmed', 'operation_basis': basis,
                    'delivery': 'task_assignment_not_full_context'},
                'agent_query': {'tool': 'agent', 'args': {'id': target, 'at': end,
                    'since_ts': None, 'view': 'overview'}},
                'expand_query': _expand([up, rp], scope),
                'semantic_checked': False, 'current_state_certified': False})
    selected.sort(key=lambda r: (r['ts'], r['id']))
    return selected


def binding(ledger, parent, child, refs, cutoff):
    """Check only cited dispatches, using exactly the navigation proof policy."""
    supports = []
    for row in rows(ledger, parent, temporal.Window.parse(cutoff)):
        if row['operation']['child'] != child:
            continue
        action = next(a for a in ledger.agents[parent].actions if a.seq == row['seq'])
        path = os.path.normcase(os.path.abspath(action.src[0]))
        if not any(r['status'] == 'ok' and os.path.normcase(os.path.abspath(r.get('source_path') or '')) == path
                   and r['line'] in (action.src[1] + 1, action.src[2] + 1)
                   and (r['type'] != 'legacy' or r.get('action_seq') == action.seq) for r in refs):
            continue
        supports.append({'event_id': row['id'], 'status': row['operation']['status'],
                         'use_ts': row['use_ts'], 'done_ts': row['done_ts'],
                         'proof': row['operation'], 'source': row['result']})
    return {'status': 'confirmed' if any(r['status'] == 'confirmed' for r in supports) else 'candidate' if supports else 'not_observed',
            'evidence': supports, 'state_binding': 'not_proven', 'semantic_checked': False,
            'diag': '派发身份/候选按原始回执核验；不证明子代理理解或执行了任务' if supports else '引用未核出这两个代理间的派发；不等于证明未发生'}
