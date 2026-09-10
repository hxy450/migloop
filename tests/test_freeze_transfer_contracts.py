"""Synthetic private-freeze gates; never runs a model or historical command."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'docs/experiments/generalization-20260910/freeze_transfer_contracts.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


f = load(MODULE, 'transfer_private_freezer')
APPROVED = 'approved_for_freeze_before_investigator_runs'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if not isinstance(value, str) else value, encoding='utf-8')
    return path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def sample(tmp_path):
    source = tmp_path / 'source/source-manifest.json'
    candidate = tmp_path / 'candidate'
    draft = tmp_path / 'draft'
    approval = tmp_path / 'review-approvals.json'
    out = tmp_path / 'sealed'
    cohorts, approvals = [], []
    write(candidate / 'manifest.json', {'status': 'frozen_ready_for_tools', 'frozen_at': '2026-09-01T00:00:00Z'})
    write(candidate / 'code/src/migloop/source.py', '# frozen synthetic code')
    for index, count in enumerate((1, 2)):
        cid = f'c{index}'
        pool = source.parent / cid / 'pool'
        root = write(pool / f'root{index}.jsonl', '{"timestamp":"2026-01-01T00:00:00Z"}\n')
        side = write(pool / 'root/attachment.txt', 'undated attachment')
        tasks = [{'id': f'C{index}-{n}', 'relative_target': f'entry/F{n}.ets'} for n in range(count)]
        cohorts.append({'id': cid, 'pool': f'{cid}/pool', 'root_transcript': root.name,
                        'roots': [str(root)], 'sid': str(root), 'generation_end': '2026-01-01T00:01:00Z',
                        'repair_qualification_start': '2026-01-01T00:02:00Z', 'observation_end': '2026-01-01T00:03:00Z',
                        'tasks': tasks, 'file_count': 2, 'jsonl_count': 1,
                        'files': [{'path': p.relative_to(pool).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)} for p in (root, side)]})
        ids = [t['id'] for t in tasks]
        unit_ids = [tid + '/local' for tid in ids]
        core = {'schema': 'migloop-causal-core-contract/1', 'status': APPROVED,
                'task_ids': ids, 'boundary_gap_reviewed': True, 'pending_task_ids': [],
                'units': {uid: 'synthetic local cause' for uid in unit_ids}}
        reference = {'schema': 'different-reference-shape' if index else 'reference-shape', 'status': APPROVED,
                     'boundaries': {'boundary_gap_reviewed': True}, 'pending_task_ids': [],
                     'units': [{'id': uid, 'task_id': uid.split('/')[0]} for uid in unit_ids] if index else {uid: {} for uid in unit_ids}}
        paths = [(f'{cid}/core.json', core, {'role': 'core'}),
                 (f'{cid}/reference.json', reference, {'role': 'reference', 'primary_reference': True}),
                 (f'{cid}/inventory.json', {'changes': []}, {'role': 'reference', 'purpose': 'inventory'}),
                 (f'{cid}/notes.md', 'source review notes', {'role': 'reference', 'purpose': 'notes'}),
                 (f'{cid}/independent-review.md', 'independent raw-evidence review', {'role': 'reference', 'purpose': 'review'})]
        artifacts = []
        for name, body, meta in paths:
            p = write(draft / name, body)
            artifacts.append({**meta, 'path': name, 'sha256': sha(p)})
        reviews = [{'reviewer': 'independent-reviewer', 'status': 'completed',
                    'path': paths[-1][0], 'sha256': sha(draft / paths[-1][0]),
                    'completed_at': '2026-09-02T00:00:00Z'}]
        approvals.append({'id': cid, 'task_ids': ids, 'boundary_gap_reviewed': True,
                          'artifacts': artifacts, 'reviews': reviews})
    write(source, {'schema': 'migloop-transfer-source-freeze/1', 'status': 'sources_frozen', 'cohorts': cohorts})
    write(approval, {'schema': 'migloop-transfer-review-approvals/1', 'status': APPROVED,
                     'source_manifest_sha256': sha(source), 'candidate_manifest_sha256': sha(candidate / 'manifest.json'),
                     'cohorts': approvals})
    args = dict(source_manifest=source, candidate=candidate, candidate_sha256=sha(candidate / 'manifest.json'),
                draft_root=draft, review_approvals=approval, out=out)
    return SimpleNamespace(**args, args=args, cohorts=cohorts)


def update_artifact(sample, name, change):
    path = sample.draft_root / name
    data = read(path)
    change(data)
    write(path, data)
    approval = read(sample.review_approvals)
    for cohort in approval['cohorts']:
        for item in cohort['artifacts']:
            if item['path'] == name:
                item['sha256'] = sha(path)
    write(sample.review_approvals, approval)


def test_complete_freeze_copies_bytes_order_and_roles(sample):
    result = f.freeze(**sample.args)
    saved = read(sample.out / 'contracts-manifest.json')
    assert result == saved
    assert saved['schema'] == 'migloop-transfer-contract-freeze/1' and saved['status'] == 'frozen'
    assert [c['id'] for c in saved['cohorts']] == ['c0', 'c1']
    assert saved['cohorts'][1]['task_ids'] == ['C1-0', 'C1-1']
    for cohort in saved['cohorts']:
        assert sum(a['role'] == 'core' for a in cohort['artifacts']) == 1
        for item in cohort['artifacts']:
            target = sample.out / item['path']
            assert sha(target) == item['sha256'] and target.stat().st_size == item['bytes']
            assert target.read_bytes() == (sample.draft_root / item['path']).read_bytes()


@pytest.mark.parametrize('artifact', ['c0/core.json', 'c0/reference.json'])
def test_pending_status_rejected(sample, artifact):
    update_artifact(sample, artifact, lambda d: d.update(status='draft_pending_independent_review'))
    with pytest.raises(ValueError, match='approved'):
        f.freeze(**sample.args)
    assert not sample.out.exists()


@pytest.mark.parametrize('case', ['missing_cohort', 'order', 'pending', 'boundary', 'review_pending', 'review_hash', 'candidate_sha', 'source_sha', 'missing_notes', 'missing_inventory', 'missing_review'])
def test_approval_hard_gates(sample, case):
    data = read(sample.review_approvals)
    c = data['cohorts'][0]
    if case == 'missing_cohort': data['cohorts'].pop()
    elif case == 'order': data['cohorts'].reverse()
    elif case == 'pending': data['status'] = 'pending'
    elif case == 'boundary': c['boundary_gap_reviewed'] = False
    elif case == 'review_pending': c['reviews'][0]['status'] = 'pending'
    elif case == 'review_hash': c['reviews'][0]['sha256'] = '0' * 64
    elif case == 'candidate_sha': data['candidate_manifest_sha256'] = '0' * 64
    elif case == 'source_sha': data['source_manifest_sha256'] = '0' * 64
    else:
        purpose = case.removeprefix('missing_')
        c['artifacts'] = [a for a in c['artifacts'] if a.get('purpose') != purpose]
    write(sample.review_approvals, data)
    with pytest.raises(ValueError): f.freeze(**sample.args)
    assert not sample.out.exists()


@pytest.mark.parametrize('change', ['unknown_unit', 'missing_task', 'duplicate_unit', 'pending_task', 'unreviewed_boundary'])
def test_unit_mapping_and_full_task_coverage(sample, change):
    if change == 'unknown_unit':
        update_artifact(sample, 'c0/core.json', lambda d: d['units'].update({'OTHER/local': 'x'}))
    elif change == 'missing_task':
        update_artifact(sample, 'c1/core.json', lambda d: d['units'].pop('C1-1/local'))
    elif change == 'duplicate_unit':
        update_artifact(sample, 'c1/reference.json', lambda d: d['units'].append(d['units'][0]))
    elif change == 'pending_task':
        update_artifact(sample, 'c0/reference.json', lambda d: d.update(pending_task_ids=['C0-0']))
    else:
        update_artifact(sample, 'c0/reference.json', lambda d: d['boundaries'].update(boundary_gap_reviewed=False))
    with pytest.raises(ValueError): f.freeze(**sample.args)


@pytest.mark.parametrize('field', ['draft', 'candidate', 'source_pool'])
def test_drift_before_freeze_rejected(sample, field):
    target = sample.draft_root / 'c0/core.json' if field == 'draft' else sample.candidate / 'manifest.json' if field == 'candidate' else sample.source_manifest.parent / 'c0/pool/root0.jsonl'
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(ValueError): f.freeze(**sample.args)


def test_source_new_unlisted_attachment_is_rejected(sample):
    write(sample.source_manifest.parent / 'c0/pool/new.txt', 'not listed')
    with pytest.raises(ValueError): f.freeze(**sample.args)


@pytest.mark.parametrize('bad', ['../escape.json', '/absolute.json', 'c0/../core.json', 'C:/outside.json', 'c0\\core.json'])
def test_unsafe_artifact_paths_rejected(sample, bad):
    data = read(sample.review_approvals)
    data['cohorts'][0]['artifacts'][0]['path'] = bad
    write(sample.review_approvals, data)
    with pytest.raises(ValueError): f.freeze(**sample.args)


@pytest.mark.parametrize('where', ['draft', 'candidate', 'pool'])
def test_output_cannot_enter_protected_tree(sample, where):
    root = sample.draft_root if where == 'draft' else sample.candidate if where == 'candidate' else sample.source_manifest.parent / 'c0/pool'
    with pytest.raises(ValueError): f.freeze(**{**sample.args, 'out': root / 'new-freeze'})


def test_no_overwrite_and_failure_directory_retained(sample, monkeypatch):
    sample.out.mkdir()
    write(sample.out / 'keep.txt', 'keep')
    with pytest.raises(FileExistsError): f.freeze(**sample.args)
    assert (sample.out / 'keep.txt').read_text() == 'keep'
    fresh = sample.out.parent / 'partial'
    original = f._copy
    calls = []
    def drift(source, target, expected):
        original(source, target, expected)
        if not calls:
            write(sample.candidate / 'code/added.py', 'drift during copying')
        calls.append(str(target))
    monkeypatch.setattr(f, '_copy', drift)
    with pytest.raises(ValueError, match='drift|changed'):
        f.freeze(**{**sample.args, 'out': fresh})
    assert fresh.is_dir() and list(fresh.rglob('*'))
    assert not (fresh / 'contracts-manifest.json').exists()


def test_linked_artifact_rejected(sample):
    target = sample.draft_root / 'c0/notes.md'
    other = write(sample.draft_root / 'original.md', 'source review notes')
    target.unlink()
    try:
        target.symlink_to(other)
    except OSError:
        pytest.skip('Host cannot create test symlinks')
    with pytest.raises(ValueError, match='link'):
        f.freeze(**sample.args)


@pytest.mark.parametrize('binding', ['source_manifest_sha256', 'candidate_manifest_sha256', 'cohort', 'anchor'])
def test_reference_cannot_declare_a_different_source_or_window(sample, binding):
    def change(data):
        if binding == 'anchor':
            data['boundaries']['generation_end'] = '2026-01-01T00:00:30Z'
        else:
            data[binding] = 'wrong'
    update_artifact(sample, 'c0/reference.json', change)
    with pytest.raises(ValueError, match='binding|boundary|cohort'):
        f.freeze(**sample.args)


def test_copied_artifact_drift_before_manifest_is_rejected(sample, monkeypatch):
    original = f._copy
    copied = []
    def corrupt(source, target, expected):
        original(source, target, expected)
        if copied:
            copied[0].write_bytes(b'changed after earlier copy check')
        copied.append(target)
    monkeypatch.setattr(f, '_copy', corrupt)
    with pytest.raises(ValueError, match='Output|Copied|drift'):
        f.freeze(**sample.args)
    assert sample.out.exists() and not (sample.out / 'contracts-manifest.json').exists()


def declared_candidate(sample):
    code_file = sample.candidate / 'code/src/migloop/source.py'
    entries = [{'path': 'source.py', 'bytes': code_file.stat().st_size, 'sha256': sha(code_file)}]
    digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    write(sample.candidate / 'code-manifest.json', {'algorithm': 'sha256', 'entries': entries, 'content_digest': digest})
    helper = write(sample.candidate / 'helpers/adapter.py', '# synthetic helper')
    runner = write(sample.candidate / 'run_transfer.py', '# synthetic runner')
    seed = read(sample.candidate / 'manifest.json')
    seed.update(code_digest=digest,
                helper_entries=[{'path': 'adapter.py', 'bytes': helper.stat().st_size, 'sha256': sha(helper)}],
                transfer_runner={'path': 'run_transfer.py', 'bytes': runner.stat().st_size, 'sha256': sha(runner)})
    write(sample.candidate / 'manifest.json', seed)
    sample.args['candidate_sha256'] = sha(sample.candidate / 'manifest.json')
    approval = read(sample.review_approvals)
    approval['candidate_manifest_sha256'] = sample.args['candidate_sha256']
    write(sample.review_approvals, approval)


def test_declared_candidate_inventory_is_validated_without_execution(sample):
    declared_candidate(sample)
    assert f.freeze(**sample.args)['status'] == 'frozen'


@pytest.mark.parametrize('where', ['source', 'candidate'])
def test_inventory_bytes_bool_is_not_an_integer(sample, where):
    if where == 'source':
        target = sample.source_manifest.parent / 'c0/pool/root0.jsonl'
        target.write_bytes(b'x')
        body = read(sample.source_manifest)
        body['cohorts'][0]['files'][0].update(bytes=True, sha256=sha(target))
        write(sample.source_manifest, body)
        approval = read(sample.review_approvals)
        approval['source_manifest_sha256'] = sha(sample.source_manifest)
    else:
        (sample.candidate / 'code/src/migloop/source.py').write_bytes(b'x')
        declared_candidate(sample)
        path = sample.candidate / 'code-manifest.json'
        body = read(path)
        body['entries'][0]['bytes'] = True
        body['content_digest'] = hashlib.sha256(json.dumps(body['entries'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        write(path, body)
        seed = read(sample.candidate / 'manifest.json')
        seed['code_digest'] = body['content_digest']
        write(sample.candidate / 'manifest.json', seed)
        sample.args['candidate_sha256'] = sha(sample.candidate / 'manifest.json')
        approval = read(sample.review_approvals)
        approval['candidate_manifest_sha256'] = sample.args['candidate_sha256']
    write(sample.review_approvals, approval)
    with pytest.raises(ValueError, match='Inventory'):
        f.freeze(**sample.args)


@pytest.mark.parametrize('where', ['source', 'candidate', 'approval', 'core', 'reference'])
@pytest.mark.parametrize('tail', ['"status":"approved_for_freeze_before_investigator_runs"', '"extra":NaN', '"extra":Infinity', '"extra":1e999'])
def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(sample, where, tail):
    path = {'source': sample.source_manifest, 'candidate': sample.candidate / 'manifest.json',
            'approval': sample.review_approvals, 'core': sample.draft_root / 'c0/core.json',
            'reference': sample.draft_root / 'c0/reference.json'}[where]
    # Keep duplicate values valid for their individual schemas: only duplicate
    # member syntax itself should reject, not a coincidental changed status.
    if tail.startswith('"status"'):
        tail = '"status":' + json.dumps(read(path)['status'])
    path.write_text(path.read_text(encoding='utf-8').rstrip()[:-1] + ',' + tail + '}', encoding='utf-8')
    approval = read(sample.review_approvals)
    if where == 'source': approval['source_manifest_sha256'] = sha(path)
    elif where == 'candidate':
        sample.args['candidate_sha256'] = sha(path)
        approval['candidate_manifest_sha256'] = sample.args['candidate_sha256']
    elif where in ('core', 'reference'):
        for item in approval['cohorts'][0]['artifacts']:
            if item['path'] == 'c0/' + where + '.json':
                item['sha256'] = sha(path)
    if where != 'approval': write(sample.review_approvals, approval)
    with pytest.raises(ValueError, match='JSON'):
        f.freeze(**sample.args)
    assert not sample.out.exists()


@pytest.mark.parametrize('target', ['code/src/migloop/source.py', 'helpers/adapter.py', 'run_transfer.py', 'code-manifest.json'])
def test_declared_candidate_drift_before_freeze_is_rejected(sample, target):
    declared_candidate(sample)
    path = sample.candidate / target
    if target == 'code-manifest.json':
        body = read(path)
        body['content_digest'] = '0' * 64
        write(path, body)
    else:
        path.write_bytes(path.read_bytes() + b' changed before freeze')
    with pytest.raises(ValueError, match='Candidate'):
        f.freeze(**sample.args)
    assert not sample.out.exists()


def test_freezer_source_change_during_copy_cannot_publish_new_code_hash(sample, monkeypatch):
    executable = sample.out.parent / 'test-freezer.py'
    executable.write_bytes(MODULE.read_bytes())
    monkeypatch.setattr(f, '__file__', str(executable))
    original = f._copy
    changed = []
    def drift(source, target, expected):
        original(source, target, expected)
        if not changed:
            executable.write_bytes(executable.read_bytes() + b'\n# changed during freeze\n')
            changed.append(True)
    monkeypatch.setattr(f, '_copy', drift)
    with pytest.raises(ValueError, match='drift|changed'):
        f.freeze(**sample.args)
    assert not (sample.out / 'contracts-manifest.json').exists()


def test_frozen_container_is_accepted_by_real_run_transfer_gates(sample, monkeypatch):
    saved = f.freeze(**sample.args)
    runner = load(ROOT / 'docs/experiments/generalization-20260910/run_transfer.py', 'freeze_gate_compat')
    candidate = read(sample.candidate / 'manifest.json')
    code = {'entries': [], 'content_digest': 'synthetic'}
    monkeypatch.setattr(runner, 'candidate_check', lambda *_: (candidate, code))
    registry = write(sample.out.parent / 'registry.json', {
        'schema': 'migloop-transfer-registry-validation/1', 'source_manifest_sha256': sha(sample.source_manifest),
        'code_digest': 'synthetic', 'passed': True, 'runtime_stable': True, 'runtime_before': code, 'runtime_after': code,
        'cohorts': [{'id': c['id'], 'passed': True, 'missing': [], 'unexpected': [], 'registered_count': 2,
                     'registered': [x['path'] for x in c['files']]} for c in sample.cohorts]})
    result = runner.gates(sample.source_manifest, sample.candidate, sample.candidate_sha256, registry, sample.out / 'contracts-manifest.json')
    assert len(result[-1]) == sum(len(c['artifacts']) for c in saved['cohorts'])
