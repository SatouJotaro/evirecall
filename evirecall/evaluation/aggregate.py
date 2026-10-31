"""Recompute execution/score/accounting summaries from saved files, without APIs."""

from collections import Counter
import hashlib
import json
from pathlib import Path

from evirecall.contracts import ContractError
from evirecall.runner.accounting import aggregate_calls
from evirecall.runner.records import read_jsonl


def summarize_run(run_dir, evaluation_dir=None):
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / 'manifest.json').read_text(encoding='utf-8'))
    planned = manifest['task_ids']
    if not planned or len(set(planned)) != len(planned):
        raise ContractError('Invalid planned task IDs')
    warnings = []
    def read(path):
        value = read_jsonl(path, recover_tail=True)
        warnings.extend(value.warnings)
        return value.records
    def indexed(rows):
        result = {}
        for row in rows:
            task_id = row.get('task_id')
            if task_id not in planned or task_id in result:
                raise ContractError('Duplicate or unknown task in saved results')
            result[task_id] = row
        return result
    results = indexed(read(run_dir / 'results.jsonl'))
    schedule = read(run_dir / 'schedule.jsonl')
    started = {r['task_id'] for r in schedule if r.get('state') == 'started'} | set(results)
    if started - set(planned):
        raise ContractError('Unknown scheduled task')
    for row in results.values():
        if row.get('status') not in ('completed', 'abstained', 'failed'):
            raise ContractError('Invalid saved terminal status')
    calls = aggregate_calls(read(run_dir / 'calls.jsonl'))
    read(run_dir / 'trace.jsonl')
    read(run_dir / 'sources.jsonl')
    scores = {}
    if evaluation_dir is not None:
        evaluation_dir = Path(evaluation_dir)
        evaluation = json.loads((evaluation_dir / 'manifest.json').read_text(encoding='utf-8'))
        if evaluation['run_id'] != manifest['run_id']:
            raise ContractError('Scoring run belongs to another execution')
        if evaluation.get('results_sha256') != hashlib.sha256((run_dir / 'results.jsonl').read_bytes()).hexdigest():
            raise ContractError('Execution results changed since scoring')
        if evaluation.get('task_ids') != planned:
            raise ContractError('Scoring task manifest differs from execution')
        scores = indexed(read(evaluation_dir / 'scores.jsonl'))
    statuses = Counter(row['status'] for row in results.values())
    scored = [r for r in scores.values() if r.get('status') == 'scored']
    for row in scored:
        if type(row.get('passed')) is not bool:
            raise ContractError('Score must contain a boolean passed field')
    valid = {k for k, v in results.items() if v['status'] in ('completed', 'abstained')}
    if any(row['task_id'] not in valid for row in scored):
        raise ContractError('Cannot score a missing or failed execution result')
    correct = sum(row['passed'] for row in scored if row['task_id'] in valid)
    scored_ids = {r['task_id'] for r in scored}
    unknown = len(valid - scored_ids)
    counts = {'planned': len(planned), 'started': len(started), 'not_run': len(set(planned) - started),
              'interrupted': len(started - set(results)),
              **{s: statuses[s] for s in ('completed', 'abstained', 'failed')},
              'scored': len(scored), 'judge_error': sum(r.get('status') in ('error', 'timeout') for r in scores.values()),
              'unscored_valid': unknown}
    execution = run_dir / 'execution.json'
    duration = json.loads(execution.read_text(encoding='utf-8')).get('wall_ms') if execution.exists() else None
    return {'schema_version': 2, 'mode': manifest.get('mode'), 'run_id': manifest['run_id'],
            'condition': manifest['condition'], 'counts': counts, 'calls': calls,
            'scored_subset_accuracy': correct / len(scored) if scored else None,
            'score_coverage': len(scored) / len(planned),
            'success_lower_bound': correct / len(planned),
            'success_upper_bound': (correct + unknown) / len(planned),
            'wall_ms': duration, 'terminal_episodes_per_second': len(results) / (duration / 1000) if duration else None,
            'warnings': warnings,
            'notice': 'Missing judge results are unknown; fixture results are not benchmark accuracy.'}
