"""Export exact single-investigator artifacts to the existing local viewer."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/single-investigator-20260911-member')
RUN = ROOT / 'runs/single/rep1'
VIEW = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/preview-latest-20260911-member/runs/single-20260911/rep1')
FILES = ('metrics.json', 'result.json', 'report.md', 'transcript.jsonl', 'events.jsonl', 'query-trace.json',
         'verdict.json', 'verdict.yaml', 'system-cost.json', 'command.json', 'prompt.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    result = json.loads((RUN / 'verdict.json').read_text(encoding='utf-8'))
    if result['errors'] or result['submission']['status'] != 'accepted' or not result['native_report']['verified']:
        raise ValueError('Submission provenance failed; do not export as accepted')
    if VIEW.exists():
        raise FileExistsError('Never overwrite prior viewer artifacts')
    original = {name: sha(RUN / name) for name in FILES}
    VIEW.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(RUN / name, VIEW / name)
    if any(sha(VIEW / name) != value or sha(RUN / name) != value for name, value in original.items()):
        raise ValueError('Artifact changed during export')
    provenance = {'phase': 'same_investigator_free_investigation_and_checked_graph', 'source': str(RUN),
                  'files': original, 'semantic_checked_by_exporter': False,
                  'note': 'Accepted provenance is not accepted attribution accuracy; model assertions remain unchanged.',
                  'url': 'http://127.0.0.1:8877/api/insight1/fixchain/ff019d8a?probe=single-20260911%2Frep1'}
    with (VIEW / 'export-provenance.json').open('x', encoding='utf-8') as handle:
        json.dump(provenance, handle, ensure_ascii=False, indent=2)
    print(json.dumps(provenance, ensure_ascii=False))


if __name__ == '__main__':
    main()
