"""Copy a completed presentation run into the existing viewer, preserving bytes."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/longchain-hybrid-20260911-member')
RUN = ROOT / 'runs/present/rep1'
VIEW = Path('C:/Users/hongy/projects/_migloop-eval-20260909/file-first-10/preview-latest-20260911-member/runs/posthoc-20260911/rep1')
FILES = ('metrics.json', 'result.json', 'report.md', 'transcript.jsonl', 'events.jsonl',
         'query-trace.json', 'verdict.json', 'system-cost.json', 'command.json', 'prompt.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if VIEW.exists():
        raise FileExistsError('Never overwrite a prior viewer export')
    metric = json.loads((RUN / 'metrics.json').read_text(encoding='utf-8'))
    verdict = json.loads((RUN / 'verdict.json').read_text(encoding='utf-8'))
    if metric['status'] != 'completed' or verdict['errors']:
        raise ValueError('Incomplete/invalid presentation; retain artifacts, do not claim loadable')
    before = {name: sha(RUN / name) for name in FILES}
    VIEW.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(RUN / name, VIEW / name)
    if any(sha(RUN / name) != digest or sha(VIEW / name) != digest for name, digest in before.items()):
        raise ValueError('Artifact changed during export')
    provenance = {'phase': 'posthoc_verification_and_presentation_not_original_investigation',
                  'source_run': str(RUN), 'files': before,
                  'original_report': str(ROOT / 'baseline-report.md'),
                  'original_report_sha256': sha(ROOT / 'baseline-report.md'),
                  'semantic_verification_by_exporter': False,
                  'url': 'http://127.0.0.1:8877/api/insight1/fixchain/ff019d8a?probe=posthoc-20260911%2Frep1'}
    with (VIEW / 'export-provenance.json').open('x', encoding='utf-8') as handle:
        json.dump(provenance, handle, ensure_ascii=False, indent=2)
    print(json.dumps(provenance, ensure_ascii=False))


if __name__ == '__main__':
    main()
