"""Private, approved reference freezer. No runtime imports or model calls.

Approvals schema: migloop-transfer-review-approvals/1; status must be
approved_for_freeze_before_investigator_runs, with source_manifest_sha256 and
candidate_manifest_sha256. Cohorts must follow the source manifest's exact order.
Each has id, ordered task_ids, boundary_gap_reviewed=true, artifacts, reviews.
Artifacts: {role: core|reference, path: draft-relative POSIX, sha256}; exactly one
core and one reference with primary_reference=true. Reference artifacts must also
include purpose=inventory, purpose=notes, purpose=review (other is permitted).
Reviews: {reviewer, status: completed, path, sha256, completed_at}; every review
points to a listed purpose=review artifact. All times require explicit timezone.
All referenced private bytes must be approved, including independent reviews.
Private inputs must be outside candidate/source pools. Symlinks, reparse points
and multiply linked regular files are rejected, including ancestors of outputs.
Declared candidate code/helper inventories are checked without importing them;
the runner separately enforces its model/runtime protocol and registry gates.

No causal claims are auto-graded. The primary reference accepts units as an ID
mapping or list of {id, optional task_id}; its schema label is not prescribed.
Partial output directories are retained on failure, never deleted or reused.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat


APPROVED = 'approved_for_freeze_before_investigator_runs'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


LOADED_SHA256 = _sha(Path(__file__).read_bytes())


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError('Explicit timezone required')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Explicit timezone required')
    return result.astimezone(timezone.utc)


def _relative(value):
    if not isinstance(value, str) or not value or re.search(r'[\\:\x00<>|?*]', value):
        raise ValueError('Unsafe relative path')
    p = PurePosixPath(value)
    if p.is_absolute() or any(s in ('', '.', '..') or s.endswith((' ', '.')) for s in value.split('/')):
        raise ValueError('Unsafe relative path')
    return value


def _no_links(path):
    path = Path(path)
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked/reparse path is not a frozen input: ' + str(part))
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError('Multiply linked input is not isolated: ' + str(part))


def _path(value):
    p = Path(value).absolute()
    _no_links(p)
    return p.resolve()


def _read_bytes(path):
    _no_links(path)
    if not Path(path).is_file():
        raise ValueError('Expected regular input file: ' + str(path))
    return Path(path).read_bytes()


def _entry(path):
    data = _read_bytes(path)
    return {'bytes': len(data), 'sha256': _sha(data)}


def _tree(root):
    _no_links(root)
    if not root.is_dir():
        raise ValueError('Expected input directory: ' + str(root))
    rows = {}
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            _no_links(Path(folder) / name)
        for name in files:
            path = Path(folder) / name
            key = _relative(path.relative_to(root).as_posix())
            if key.casefold() in {k.casefold() for k in rows}:
                raise ValueError('Ambiguous case-folded source paths')
            rows[key] = _entry(path)
    return rows


def _json(path, tracked, expected=None):
    data = _read_bytes(path)
    digest = _sha(data)
    if expected is not None and digest != expected:
        raise ValueError('Approved bytes changed: ' + str(path))
    observed = {'bytes': len(data), 'sha256': digest}
    if path in tracked and tracked[path] != observed:
        raise ValueError('Input changed during read: ' + str(path))
    tracked[path] = observed
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('JSON duplicate object key: ' + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('JSON non-finite number: ' + value)

    def finite_float(value):
        number = float(value)
        return number if math.isfinite(number) else nonfinite(value)

    return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=nonfinite, parse_float=finite_float)


def _boundary(document):
    flags = [document['boundary_gap_reviewed']] if 'boundary_gap_reviewed' in document else []
    for key in ('boundaries', 'anchors'):
        if isinstance(document.get(key), dict) and 'boundary_gap_reviewed' in document[key]:
            flags.append(document[key]['boundary_gap_reviewed'])
    if not flags or any(v is not True for v in flags):
        raise ValueError('Boundary gap must be explicitly reviewed')


def _approved(document):
    if document.get('status') != APPROVED:
        raise ValueError('Reference/core must be approved before freeze')
    if document.get('pending_task_ids', []) != []:
        raise ValueError('Pending tasks cannot be frozen')
    _boundary(document)


def _check_binding(document, cohort, source_sha, candidate_sha, candidate):
    expected = {'source_manifest_sha256': source_sha,
                'candidate_manifest_sha256': candidate_sha, 'cohort': cohort['id']}
    if 'code_digest' in candidate:
        expected['candidate_code_digest'] = candidate['code_digest']
    for key, value in expected.items():
        if key in document and document[key] != value:
            raise ValueError('Explicit reference/core binding mismatch: ' + key)
    containers = [document] + [document[key] for key in ('boundaries', 'anchors')
                                if isinstance(document.get(key), dict)]
    for container in containers:
        for key in ('generation_end', 'repair_qualification_start', 'observation_end'):
            if key in container and container[key] != cohort[key]:
                raise ValueError('Explicit reference/core boundary mismatch: ' + key)


def _source_metadata(cohort, pool, expected_sources):
    """Same source metadata invariants as run_transfer.source_cases; no imports."""
    times = [_stamp(cohort[key]) for key in
             ('generation_end', 'repair_qualification_start', 'observation_end')]
    if not times[0] <= times[1] < times[2]:
        raise ValueError('Invalid generation/qualification/observation order')
    root = _path(pool / _relative(cohort['root_transcript']))
    names = {_path(pool / name) for name in expected_sources if name.endswith('.jsonl')}
    roots = [_path(value) for value in cohort['roots']]
    if root != _path(cohort['sid']) or root not in roots or not set(roots) <= names:
        raise ValueError('Root/sid outside complete source registry')
    targets = set()
    for task in cohort['tasks']:
        target = _relative(task['relative_target']).casefold()
        if not isinstance(task['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]+', task['id']) or target in targets:
            raise ValueError('Invalid/duplicate source task or target')
        targets.add(target)


def _inventory_entries(entries):
    expected = {}
    for row in entries:
        name = _relative(row['path'])
        if name.casefold() in {key.casefold() for key in expected}:
            raise ValueError('Duplicate inventory path')
        if type(row.get('bytes')) is not int or row['bytes'] < 0 or not isinstance(row.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
            raise ValueError('Inventory requires integer byte counts and SHA-256 digests')
        expected[name] = {key: row[key] for key in ('bytes', 'sha256')}
    return expected


def _candidate_inventories(candidate, seed, tracked):
    """Check any declared immutable inventory before using it as a freeze input."""
    code_path = candidate / 'code-manifest.json'
    if 'code_digest' in seed or code_path.exists():
        code = _json(code_path, tracked)
        entries = code['entries']
        digest = _sha(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode())
        if code.get('algorithm') != 'sha256' or digest != code.get('content_digest') or digest != seed.get('code_digest'):
            raise ValueError('Candidate code digest mismatch')
        expected = {'src/migloop/' + name: row for name, row in _inventory_entries(entries).items()}
        if not expected or _tree(candidate / 'code') != expected:
            raise ValueError('Candidate code bytes drift')
    if 'helper_entries' in seed and _tree(candidate / 'helpers') != _inventory_entries(seed['helper_entries']):
        raise ValueError('Candidate helper bytes drift')
    if 'transfer_runner' in seed:
        row = seed['transfer_runner']
        expected = _inventory_entries([row])
        if _entry(candidate / row['path']) != expected[row['path']]:
            raise ValueError('Candidate runner bytes drift')


def _reference_ids(reference):
    units = reference.get('units')
    if isinstance(units, dict):
        ids = list(units)
        for key, value in units.items():
            if isinstance(value, dict) and value.get('id', key) != key:
                raise ValueError('Reference unit key/id mismatch')
            if isinstance(value, dict) and 'task_id' in value and value['task_id'] != key.split('/', 1)[0]:
                raise ValueError('Reference task/unit mismatch')
    elif isinstance(units, list):
        ids = []
        for unit in units:
            if not isinstance(unit, dict) or not isinstance(unit.get('id'), str):
                raise ValueError('Reference unit needs a stable ID')
            uid = unit['id']
            if '/' not in uid and isinstance(unit.get('task_id'), str):
                uid = unit['task_id'] + '/' + uid
            if 'task_id' in unit and unit['task_id'] != uid.split('/', 1)[0]:
                raise ValueError('Reference task/unit mismatch')
            ids.append(uid)
    else:
        raise ValueError('Reference units must be a list or mapping')
    if len(ids) != len(set(ids)) or not ids:
        raise ValueError('Empty/duplicate reference units')
    return set(ids)


def _check_units(core, reference, task_ids):
    _approved(core)
    _approved(reference)
    units = core.get('units')
    if core.get('schema') != 'migloop-causal-core-contract/1' or not isinstance(units, dict) or not units:
        raise ValueError('Frozen causal core mapping required')
    for doc in (core, reference):
        if 'task_ids' in doc and doc['task_ids'] != task_ids:
            raise ValueError('Full ordered task IDs required')
    seen = set()
    for uid, definition in units.items():
        if not isinstance(uid, str) or uid.count('/') != 1 or not uid.split('/')[1] or not definition:
            raise ValueError('Malformed/empty core unit')
        tid = uid.split('/', 1)[0]
        if tid not in task_ids:
            raise ValueError('Unknown core unit task')
        seen.add(tid)
    if seen != set(task_ids) or set(units) != _reference_ids(reference):
        raise ValueError('Missing task or core/reference unit mismatch')
    mappings = reference.get('file_reconciliation', [])
    for row in mappings:
        if row.get('task_id') not in task_ids or set(row.get('reference_family_ids', [])) != {u for u in units if u.startswith(row['task_id'] + '/')}:
            raise ValueError('Reference file reconciliation mismatch')
    files = reference.get('files', {})
    if isinstance(files, dict):
        for tid, row in files.items():
            if isinstance(row, dict) and 'core_unit_ids' in row:
                if tid not in task_ids or set(row['core_unit_ids']) != {u for u in units if u.startswith(tid + '/')}:
                    raise ValueError('Reference per-file core mapping mismatch')


def _copy(source, target, expected):
    data = _read_bytes(source)
    if {'bytes': len(data), 'sha256': _sha(data)} != expected:
        raise ValueError('Input changed while copying: ' + str(source))
    _no_links(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    _no_links(target)
    with target.open('xb') as handle:
        handle.write(data)
    if _entry(target) != expected:
        raise ValueError('Copied bytes differ: ' + str(target))


def freeze(*, source_manifest, candidate, candidate_sha256, draft_root, review_approvals, out):
    source_manifest, candidate, draft_root, review_approvals, out = map(_path, (source_manifest, candidate, draft_root, review_approvals, out))
    if out.exists():
        raise FileExistsError('Private freeze requires a new output directory')
    tracked = {}
    freezer_path = _path(__file__)
    tracked[freezer_path] = _entry(freezer_path)
    if tracked[freezer_path]['sha256'] != LOADED_SHA256:
        raise ValueError('Freezer source changed since module load')
    source = _json(source_manifest, tracked)
    seed = _json(candidate / 'manifest.json', tracked, candidate_sha256)
    approval = _json(review_approvals, tracked)
    source_sha = tracked[source_manifest]['sha256']
    if source.get('schema') != 'migloop-transfer-source-freeze/1' or source.get('status') != 'sources_frozen':
        raise ValueError('Frozen source manifest required')
    if seed.get('status') != 'frozen_ready_for_tools':
        raise ValueError('Frozen candidate required')
    frozen_at = datetime.now(timezone.utc).isoformat()
    candidate_time = _stamp(seed.get('frozen_at'))
    if _stamp(frozen_at) < candidate_time:
        raise ValueError('Candidate freeze is in the future')
    if approval.get('schema') != 'migloop-transfer-review-approvals/1' or approval.get('status') != APPROVED:
        raise ValueError('Completed approved review manifest required')
    if approval.get('source_manifest_sha256') != source_sha or approval.get('candidate_manifest_sha256') != candidate_sha256:
        raise ValueError('Review approval binding mismatch')
    cohorts = source.get('cohorts', [])
    wanted = [c['id'] for c in cohorts]
    if not wanted or len(set(wanted)) != len(wanted) or [c['id'] for c in approval.get('cohorts', [])] != wanted:
        raise ValueError('Full ordered cohort approval required')
    pools = [source_manifest.parent / _relative(c['pool']) for c in cohorts]
    if any(private.is_relative_to(public) or public.is_relative_to(private)
           for private in (draft_root, review_approvals) for public in (candidate, *pools)):
        raise ValueError('Private inputs must be separate from model-visible pools/candidate')
    protected = [source_manifest.parent, candidate, draft_root, *pools]
    if any(out.is_relative_to(root) or root.is_relative_to(out) for root in protected):
        raise ValueError('Output must be outside source/pool/candidate/draft trees')
    before_trees = {candidate: _tree(candidate)}
    if before_trees[candidate].get('manifest.json') != tracked[candidate / 'manifest.json']:
        raise ValueError('Candidate changed while checking')
    _candidate_inventories(candidate, seed, tracked)
    all_tasks, all_paths, copies, output_cohorts = set(), set(), [], []
    for src, approved, pool in zip(cohorts, approval['cohorts'], pools):
        cid = src['id']
        if not isinstance(cid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', cid):
            raise ValueError('Unsafe cohort ID')
        expected_sources = _inventory_entries(src['files'])
        before_trees[pool] = _tree(pool)
        if before_trees[pool] != expected_sources or type(src.get('file_count')) is not int or src['file_count'] != len(expected_sources):
            raise ValueError('Complete source tree drift')
        if type(src.get('jsonl_count')) is not int or src['jsonl_count'] < 1 or src['jsonl_count'] != sum(n.lower().endswith('.jsonl') for n in expected_sources):
            raise ValueError('Source JSONL counts differ')
        _source_metadata(src, pool, expected_sources)
        task_ids = [t['id'] for t in src['tasks']]
        if not task_ids or len(set(task_ids)) != len(task_ids) or all_tasks.intersection(task_ids):
            raise ValueError('Empty/duplicate source task IDs')
        all_tasks.update(task_ids)
        if approved.get('task_ids') != task_ids or approved.get('boundary_gap_reviewed') is not True:
            raise ValueError('Full ordered task approval and boundary review required')
        artifacts = approved.get('artifacts', [])
        if sum(a.get('role') == 'core' for a in artifacts) != 1:
            raise ValueError('Exactly one core artifact required')
        primary = [a for a in artifacts if a.get('primary_reference') is True]
        if len(primary) != 1 or primary[0].get('role') != 'reference':
            raise ValueError('Exactly one primary reference required')
        if not {'inventory', 'notes', 'review'} <= {a.get('purpose') for a in artifacts if a.get('role') == 'reference'}:
            raise ValueError('Inventory, notes and independent review artifacts required')
        sealed, by_name, parsed = [], {}, {}
        for item in artifacts:
            if item.get('role') not in ('reference', 'core'):
                raise ValueError('Unknown private artifact role')
            name = _relative(item['path'])
            if name.casefold() in all_paths or name.casefold() in ('contracts-manifest.json', 'review-approvals.json'):
                raise ValueError('Duplicate/reserved private artifact path')
            all_paths.add(name.casefold())
            path = draft_root / name
            info = _entry(path)
            if info['sha256'] != item.get('sha256'):
                raise ValueError('Approved artifact changed: ' + name)
            tracked[path] = info
            by_name[name] = item
            if item['role'] == 'core' or item.get('primary_reference') is True:
                parsed[item['role']] = _json(path, tracked, item['sha256'])
            sealed.append({'role': item['role'], 'path': name, **info})
            copies.append((path, out / name, info))
        _check_units(parsed['core'], parsed['reference'], task_ids)
        for document in parsed.values():
            _check_binding(document, src, source_sha, candidate_sha256, seed)
        reviews = approved.get('reviews', [])
        if not reviews:
            raise ValueError('Independent completed review required')
        for review in reviews:
            name = _relative(review['path'])
            artifact = by_name.get(name, {})
            if (not isinstance(review.get('reviewer'), str) or not review['reviewer'].strip()
                    or review.get('status') != 'completed' or artifact.get('purpose') != 'review'
                    or artifact.get('sha256') != review.get('sha256')):
                raise ValueError('Completed review must bind its actual review artifact')
            if not candidate_time <= _stamp(review.get('completed_at')) <= _stamp(frozen_at):
                raise ValueError('Review must follow candidate and precede contract freeze')
        output_cohorts.append({'id': cid, 'task_ids': task_ids, 'boundary_gap_reviewed': True, 'artifacts': sealed})
    out.mkdir(parents=True, exist_ok=False)
    for origin, target, expected in copies:
        _copy(origin, target, expected)
    _copy(review_approvals, out / 'review-approvals.json', tracked[review_approvals])
    for path, info in tracked.items():
        if _entry(path) != info:
            raise ValueError('Input drift after copying; partial directory retained: ' + str(path))
    for root, before in before_trees.items():
        if _tree(root) != before:
            raise ValueError('Source/candidate tree changed; partial directory retained: ' + str(root))
    expected_output = {target.relative_to(out).as_posix(): info for _, target, info in copies}
    expected_output['review-approvals.json'] = tracked[review_approvals]
    if _tree(out) != expected_output:
        raise ValueError('Output drift before publication; partial directory retained')
    frozen_at = datetime.now(timezone.utc).isoformat()
    manifest = {'schema': 'migloop-transfer-contract-freeze/1', 'status': 'frozen', 'frozen_at': frozen_at,
                'source_manifest_sha256': source_sha, 'candidate_manifest_sha256': candidate_sha256,
                'cohorts': output_cohorts,
                'approval': {'path': 'review-approvals.json', **tracked[review_approvals]},
                'freezer_sha256': LOADED_SHA256,
                'input_audit': {'source_path': str(source_manifest), 'candidate_path': str(candidate),
                                'draft_root': str(draft_root), 'tracked_input_files': len(tracked),
                                'source_candidate_trees_checked_before_after': len(before_trees),
                                'all_input_hashes_stable': True},
                'scope': 'Private byte freeze after explicit review. No model execution or causal auto-grading.'}
    data = (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    _no_links(out / 'contracts-manifest.json')
    with (out / 'contracts-manifest.json').open('xb') as handle:
        handle.write(data)
    return manifest


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('source-manifest', 'candidate', 'candidate-sha256', 'draft-root', 'review-approvals', 'out'):
        ap.add_argument('--' + name, required=True)
    print(json.dumps(freeze(**vars(ap.parse_args())), ensure_ascii=False, indent=2))
