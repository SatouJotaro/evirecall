"""Independent, immutable fixture scoring runs; execution never invokes a judge."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from evirecall.contracts import ContractError, EpisodeResult, EvidencePacket, EvidenceItem, Usage
from evirecall.evaluation.aggregate import summarize_run
from evirecall.evaluation.fixtures import load_expectations, score_fixture
from evirecall.runner.records import read_jsonl, append_jsonl, write_json


def _fixture_saved(result, expectation):
    packet = EvidencePacket(tuple(EvidenceItem(**{**i, 'source_ids': tuple(i['source_ids'])})
                                  for i in result['evidence']['items']), result['evidence']['route'])
    episode = EpisodeResult(result['task_id'], result['dataset'], result['group_id'], result['session_id'],
                            result['status'], result['prediction'], packet, Usage(),
                            result['elapsed_ms'], result['trace_file'], result.get('error'))
    return score_fixture(episode, expectation)


def score_run(run_dir, expectations_path, *, output_dir=None, scorer=_fixture_saved):
    run_dir, expectations_path = Path(run_dir), Path(expectations_path)
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    expectations = load_expectations(expectations_path)
    if set(expectations) != set(manifest['task_ids']):
        raise ContractError('Evaluator IDs must match the frozen execution manifest')
    # Validate the source run before creating evaluation output.
    summarize_run(run_dir)
    results = {r['task_id']: r for r in read_jsonl(run_dir / 'results.jsonl', recover_tail=True).records}
    directory = Path(output_dir) if output_dir else run_dir / 'evaluations' / uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / 'manifest.json', {'schema_version': 2, 'run_id': manifest['run_id'],
        'eval_run_id': uuid4().hex, 'scorer': f'{scorer.__module__}.{scorer.__qualname__}',
        'task_ids': manifest['task_ids'], 'usage': None,
        'results_sha256': hashlib.sha256((run_dir / 'results.jsonl').read_bytes()).hexdigest(),
        'expectations_sha256': hashlib.sha256(expectations_path.read_bytes()).hexdigest(),
        'notice': 'Fixture scorer only; no model calls.'})
    for task_id in manifest['task_ids']:
        result = results.get(task_id)
        if result is None or result['status'] == 'failed':
            row = {'task_id': task_id, 'status': 'not_applicable', 'passed': None,
                   'reason': 'not_run' if result is None else 'execution_failed'}
        else:
            try:
                score = scorer(result, expectations[task_id])
                if not isinstance(score, dict) or type(score.get('passed')) is not bool:
                    raise ContractError('Scorer must return a boolean passed value')
                row = {**score, 'task_id': task_id, 'status': 'scored'}
            except Exception as exc:
                row = {'task_id': task_id, 'status': 'error', 'passed': None, 'error_kind': type(exc).__name__}
        append_jsonl(directory / 'scores.jsonl', row)
    summary = summarize_run(run_dir, directory)
    write_json(directory / 'summary.json', summary)
    return directory, summary
