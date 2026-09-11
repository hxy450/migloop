"""Restore existing parent/child navigation without certifying heuristic links."""
import json
from copy import deepcopy

import pytest

from migloop import (
    atom_queries,
    atoms,
    dispatch_scope,
    temporal,
    temporal_atom,
    verdict_v3,
)
from tests.test_atoms import MAIN_ID, _call, _ledger, _rec

EARLY = '2026-01-01T00:00:10Z'
END = '2026-01-01T00:00:30Z'


def pool(tmp_path, *, explicit=True, failed=False, child_time='2026-01-01T00:00:11Z'):
    main = _call(EARLY, 'dispatch', 'Task', {'name': 'worker', 'prompt': 'Build A'},
                 is_error=failed, **({'toolUseResult': {'agentId': 'worker123'}} if explicit else {}))
    child = [_rec(child_time, 'user', 'Build A')]
    return _ledger(tmp_path, main, {'agent-worker123': child})


def test_both_directions_share_native_dispatch_and_expandable_source(tmp_path):
    ledger = pool(tmp_path)
    for aid, target in ((MAIN_ID, 'agent-worker123'), ('agent-worker123', MAIN_ID)):
        data = atom_queries.json_data(ledger, 'agent', {'id': aid, 'at': END, 'view': 'dispatches'})
        row, = data['sections']['dispatches']['rows']
        assert row['operation']['kind'] == 'dispatch'
        assert row['operation']['status'] == 'confirmed'
        assert row['agent_query']['args']['id'] == target
        assert row['expand_query']['args']['refs']
        assert row['operation']['delivery'] == 'task_assignment_not_full_context'


def test_legacy_prompt_match_remains_candidate_not_native_identity(tmp_path):
    ledger = pool(tmp_path, explicit=False)
    row, = dispatch_scope.rows(ledger, 'agent-worker123', temporal.Window.parse(END))
    assert row['operation']['status'] == 'candidate'
    assert row['operation']['operation_basis'] == 'ledger_dispatch_match_not_native_identity'


@pytest.mark.parametrize('mode', ['early', 'failed', 'future_child', 'stale', 'later_window', 'ambiguous'])
def test_non_evidence_never_creates_dispatch_edge(tmp_path, mode):
    ledger = pool(tmp_path, failed=mode == 'failed',
                  child_time='2026-01-01T00:00:50Z' if mode == 'future_child' else '2026-01-01T00:00:11Z')
    if mode == 'stale':
        from pathlib import Path
        p = Path(ledger.agents[MAIN_ID].sources[0])
        p.write_text(p.read_text(encoding='utf-8') + '\n', encoding='utf-8')
    if mode == 'ambiguous':
        # Duplicate native use identity is not rescued by the ledger's link.
        from pathlib import Path
        p = Path(ledger.agents[MAIN_ID].sources[0])
        lines = p.read_text(encoding='utf-8').splitlines()
        collision = json.loads(lines[0])
        collision['message']['content'][0]['input']['prompt'] = 'Conflicting different task'
        p.write_text('\n'.join(lines + [json.dumps(collision)]) + '\n', encoding='utf-8')
        stat = p.stat()
        import os
        ledger.source_stats[os.path.normcase(str(p))] = (stat.st_mtime_ns, stat.st_size)
    window = temporal.Window.parse(EARLY if mode == 'early' else END,
                                    '2026-01-01T00:00:20Z' if mode == 'later_window' else None)
    assert dispatch_scope.rows(ledger, MAIN_ID, window) == []


@pytest.mark.parametrize('explicit', [True, False])
def test_verdict_dispatch_uses_same_proof_as_atom_not_model_story(tmp_path, explicit):
    ledger = pool(tmp_path, explicit=explicit)
    row, = dispatch_scope.rows(ledger, MAIN_ID, temporal.Window.parse(END))
    ref = row['result']['ref']
    nodes = [{'id': key, 'kind': 'agent', 'key': aid, 'at': END,
              'role': 'context', 'reason': 'A recorded assignment, not proven cause', 'evidence': [ref]}
             for key, aid in [('parent', MAIN_ID), ('child', 'agent-worker123')]]
    doc = {'schema': verdict_v3.SCHEMA, 'ledger': atoms.ledger_identity(ledger),
           'target': {'file': '/proj/A.ets', 'at': END}, 'findings': [
               {'id': 'F', 'title': 'dispatch', 'reason': 'assignment', 'status': 'unknown', 'nodes': nodes,
                'edges': [{'from': 'parent', 'to': 'child', 'relation': 'dispatch', 'evidence': [ref], 'claim': 'assigned'}]}]}
    assert verdict_v3.validate(doc) == []
    built = verdict_v3.build(ledger, doc)
    edge, = built['argument_graph']['edges']
    assert edge['binding']['status'] == ('confirmed' if explicit else 'candidate')
    assert not edge['binding']['semantic_checked']
    reverse = deepcopy(doc)
    reverse['findings'][0]['edges'][0].update({'from': 'child', 'to': 'parent'})
    assert verdict_v3.build(ledger, reverse)['argument_graph']['edges'][0]['binding']['status'] == 'not_observed'


def test_dispatches_is_not_a_file_view(tmp_path):
    with pytest.raises(ValueError):
        temporal_atom.query(pool(tmp_path), kind='file', key='/proj/A.ets', at=END, view='dispatches')
