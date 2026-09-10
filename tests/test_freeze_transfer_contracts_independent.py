"""Independent synthetic approval/freezer boundaries; no real gold or model calls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
READY = 'approved_for_freeze_before_investigator_runs'


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
    return path


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def independent_sample(tmp_path):
    freezer = _load(ROOT / 'docs/experiments/generalization-20260910/freeze_transfer_contracts.py',
                    'transfer_freezer_independent')
    source = tmp_path / 'sources/source-manifest.json'
    pool = source.parent / 'cohort/pool'
    root = _write(pool / 'root.jsonl', '{"timestamp":"2026-01-01T00:00:00Z"}\n')
    attachment = _write(pool / 'root/task.txt', 'synthetic undated original task')
    task_ids = ['C-1', 'C-2']
    cohort = {'id': 'cohort', 'pool': 'cohort/pool', 'root_transcript': root.name,
              'roots': [str(root)], 'sid': str(root),
              'generation_end': '2026-01-01T00:01:00Z',
              'repair_qualification_start': '2026-01-01T00:02:00Z',
              'observation_end': '2026-01-01T00:03:00Z',
              'tasks': [{'id': tid, 'relative_target': f'entry/{tid}.ets'} for tid in task_ids],
              'file_count': 2, 'jsonl_count': 1,
              'files': [{'path': p.relative_to(pool).as_posix(), 'bytes': p.stat().st_size,
                         'sha256': _sha(p)} for p in (root, attachment)]}
    _write(source, {'schema': 'migloop-transfer-source-freeze/1', 'status': 'sources_frozen',
                    'cohorts': [cohort]})
    candidate = tmp_path / 'candidate'
    _write(candidate / 'manifest.json', {'status': 'frozen_ready_for_tools',
                                         'frozen_at': '2026-09-01T00:00:00Z'})
    _write(candidate / 'code/frozen.py', '# only synthetic code\n')
    draft = tmp_path / 'draft'
    units = [tid + '/local' for tid in task_ids]
    bodies = {
        'core.json': {'schema': 'migloop-causal-core-contract/1', 'status': READY,
                      'task_ids': task_ids, 'boundary_gap_reviewed': True,
                      'units': {uid: 'A bounded synthetic local cause.' for uid in units}},
        'reference.json': {'status': READY, 'task_ids': task_ids, 'boundary_gap_reviewed': True,
                           'units': [{'id': uid, 'task_id': uid.split('/')[0]} for uid in units]},
        'inventory.json': {'synthetic_changes': []},
        'notes.md': 'Synthetic author notes only.',
        'review.md': 'Synthetic independent review only.'}
    specs = [('core.json', {'role': 'core'}),
             ('reference.json', {'role': 'reference', 'primary_reference': True}),
             ('inventory.json', {'role': 'reference', 'purpose': 'inventory'}),
             ('notes.md', {'role': 'reference', 'purpose': 'notes'}),
             ('review.md', {'role': 'reference', 'purpose': 'review'})]
    artifacts = []
    for name, meta in specs:
        p = _write(draft / 'cohort' / name, bodies[name])
        artifacts.append({**meta, 'path': 'cohort/' + name, 'sha256': _sha(p)})
    approval = _write(tmp_path / 'approval.json', {
        'schema': 'migloop-transfer-review-approvals/1', 'status': READY,
        'source_manifest_sha256': _sha(source),
        'candidate_manifest_sha256': _sha(candidate / 'manifest.json'),
        'cohorts': [{'id': 'cohort', 'task_ids': task_ids, 'boundary_gap_reviewed': True,
                     'artifacts': artifacts,
                     'reviews': [{'reviewer': 'independent', 'status': 'completed',
                                  'completed_at': '2026-09-02T00:00:00Z',
                                  'path': 'cohort/review.md',
                                  'sha256': _sha(draft / 'cohort/review.md')}]}]})
    args = {'source_manifest': source, 'candidate': candidate,
            'candidate_sha256': _sha(candidate / 'manifest.json'), 'draft_root': draft,
            'review_approvals': approval, 'out': tmp_path / 'sealed'}
    return SimpleNamespace(freezer=freezer, args=args, pool=pool, cohort=cohort,
                           task_ids=task_ids, **args)


def _change_artifact(s, name, change):
    path = s.draft_root / 'cohort' / name
    body = _read(path)
    change(body)
    _write(path, body)
    approval = _read(s.review_approvals)
    for item in approval['cohorts'][0]['artifacts']:
        if item['path'] == 'cohort/' + name:
            item['sha256'] = _sha(path)
    _write(s.review_approvals, approval)


def test_independent_valid_roundtrip_no_input_mutation(independent_sample):
    s = independent_sample
    before = {p: _sha(p) for p in s.source_manifest.parent.parent.rglob('*') if p.is_file()}
    result = s.freezer.freeze(**s.args)
    assert result['status'] == 'frozen'
    assert all(_sha(p) == value for p, value in before.items())
    assert result['cohorts'][0]['task_ids'] == s.task_ids


@pytest.mark.parametrize('name', ['core.json', 'reference.json'])
@pytest.mark.parametrize('field', ['source_manifest_sha256', 'candidate_manifest_sha256'])
def test_explicit_artifact_binding_cannot_conflict_with_approval(independent_sample, name, field):
    s = independent_sample
    _change_artifact(s, name, lambda body: body.update({field: '0' * 64}))
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)
    assert not s.out.exists()


def test_reference_unit_task_id_must_agree_with_its_key(independent_sample):
    s = independent_sample
    _change_artifact(s, 'reference.json', lambda body: body['units'][0].update(task_id='C-2'))
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)
    assert not s.out.exists()


def test_same_task_but_different_unit_set_cannot_be_sealed(independent_sample):
    s = independent_sample
    _change_artifact(s, 'reference.json', lambda body: body['units'][0].update(id='C-1/other'))
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)


@pytest.mark.parametrize('name', ['core.json', 'reference.json'])
def test_explicit_task_order_cannot_disagree_with_approval(independent_sample, name):
    s = independent_sample
    _change_artifact(s, name, lambda body: body['task_ids'].reverse())
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)


@pytest.mark.parametrize('when', ['2026-08-31T00:00:00Z', '2999-01-01T00:00:00Z'])
def test_review_time_must_be_between_candidate_freeze_and_contract_freeze(independent_sample, when):
    s = independent_sample
    approval = _read(s.review_approvals)
    approval['cohorts'][0]['reviews'][0]['completed_at'] = when
    _write(s.review_approvals, approval)
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)


@pytest.mark.parametrize('where', ['approval', 'source'])
def test_midcopy_metadata_drift_keeps_unpublished_partial(independent_sample, monkeypatch, where):
    s = independent_sample
    original = s.freezer._copy
    changed = []
    def drift(src, dst, expected):
        original(src, dst, expected)
        if not changed:
            path = s.review_approvals if where == 'approval' else s.source_manifest
            path.write_bytes(path.read_bytes() + b' ')
            changed.append(path)
    monkeypatch.setattr(s.freezer, '_copy', drift)
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)
    assert s.out.is_dir()
    assert not (s.out / 'contracts-manifest.json').exists()


def test_output_ancestor_of_inputs_is_rejected_before_copy(independent_sample):
    s = independent_sample
    with pytest.raises((ValueError, FileExistsError)):
        s.freezer.freeze(**{**s.args, 'out': s.source_manifest.parent.parent})


def test_linked_draft_parent_is_rejected(independent_sample):
    s = independent_sample
    alias = s.draft_root.parent / 'draft-alias'
    try:
        alias.symlink_to(s.draft_root, target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create directory symlinks')
    with pytest.raises(ValueError):
        s.freezer.freeze(**{**s.args, 'draft_root': alias})


def test_output_cannot_be_below_source_pool_alias(independent_sample):
    s = independent_sample
    alias = s.pool.parent / 'pool-alias'
    try:
        alias.symlink_to(s.pool, target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create directory symlinks')
    with pytest.raises(ValueError):
        s.freezer.freeze(**{**s.args, 'out': alias / 'private'})
    assert not (s.pool / 'private').exists()


def _rebind_public_source(s, source):
    _write(s.source_manifest, source)
    approval = _read(s.review_approvals)
    approval['source_manifest_sha256'] = _sha(s.source_manifest)
    _write(s.review_approvals, approval)


@pytest.mark.parametrize('where', ['source_pool', 'candidate'])
def test_private_input_cannot_already_be_in_model_visible_tree(independent_sample, where):
    s = independent_sample
    target = (s.pool if where == 'source_pool' else s.candidate) / 'private-input'
    shutil.copytree(s.draft_root, target)
    if where == 'source_pool':
        source = _read(s.source_manifest)
        cohort = source['cohorts'][0]
        cohort['files'] = [{'path': p.relative_to(s.pool).as_posix(),
                            'bytes': p.stat().st_size, 'sha256': _sha(p)}
                           for p in sorted(s.pool.rglob('*')) if p.is_file()]
        cohort['file_count'] = len(cohort['files'])
        _rebind_public_source(s, source)
    with pytest.raises(ValueError):
        s.freezer.freeze(**{**s.args, 'draft_root': target})
    assert not s.out.exists()


@pytest.mark.parametrize('case', ['unsafe_task_target', 'wrong_sid', 'bad_anchors'])
def test_freezer_rejects_public_metadata_that_runner_will_reject(independent_sample, case):
    s = independent_sample
    source = _read(s.source_manifest)
    cohort = source['cohorts'][0]
    if case == 'unsafe_task_target':
        cohort['tasks'][0]['relative_target'] = '../outside.ets'
    elif case == 'wrong_sid':
        cohort['sid'] = str(s.pool.parent / 'not-registered.jsonl')
    else:
        cohort['generation_end'] = '2027-01-01T00:00:00Z'
    _rebind_public_source(s, source)
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)
    assert not s.out.exists()


def test_earlier_output_copy_is_rechecked_before_manifest_publication(independent_sample, monkeypatch):
    s = independent_sample
    original = s.freezer._copy
    targets = []
    def drift(src, dst, expected):
        original(src, dst, expected)
        if targets:
            earlier = targets[0]
            earlier.write_bytes(earlier.read_bytes() + b' changed after its own check')
        targets.append(dst)
    monkeypatch.setattr(s.freezer, '_copy', drift)
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)
    assert s.out.exists()
    assert not (s.out / 'contracts-manifest.json').exists()


def test_reference_mapping_task_metadata_cannot_contradict_unit_key(independent_sample):
    s = independent_sample
    def change(body):
        body['units'] = {uid: {'task_id': 'C-2'} for uid in ('C-1/local', 'C-2/local')}
    _change_artifact(s, 'reference.json', change)
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)


@pytest.mark.parametrize('where', ['source', 'private', 'candidate'])
def test_hardlinked_regular_input_is_not_a_frozen_independent_file(independent_sample, where):
    s = independent_sample
    original = {'source': s.pool / 'root.jsonl',
                'private': s.draft_root / 'cohort/core.json',
                'candidate': s.candidate / 'code/frozen.py'}[where]
    alias = s.out.parent / 'hardlink-alias'
    try:
        os.link(original, alias)
    except OSError:
        pytest.skip('Host filesystem cannot create hardlinks')
    assert original.stat().st_nlink > 1
    with pytest.raises(ValueError):
        s.freezer.freeze(**s.args)
    assert not s.out.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Windows reparse-point regression')
def test_windows_junction_parent_cannot_hide_private_input_origin(independent_sample):
    s = independent_sample
    alias = s.draft_root.parent / 'draft-junction'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(alias), str(s.draft_root)],
                            capture_output=True, timeout=10)
    if result.returncode:
        pytest.skip('Host cannot create a temporary directory junction')
    assert alias.is_dir()
    with pytest.raises(ValueError):
        s.freezer.freeze(**{**s.args, 'draft_root': alias})
    assert not s.out.exists()
