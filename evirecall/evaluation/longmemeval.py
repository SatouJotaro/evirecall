"""Offline preparation and replay for the pinned LongMemEval QA evaluator."""

import hashlib
import json
from pathlib import Path
import shutil

OFFICIAL_COMMIT = '9e0b455f4ef0e2ab8f2e582289761153549043fc'
OFFICIAL_BASE = f'https://github.com/xiaowu0162/LongMemEval/blob/{OFFICIAL_COMMIT}/src/evaluation/'

CATEGORIES = ('single-session-user', 'single-session-preference',
              'single-session-assistant', 'multi-session',
              'temporal-reasoning', 'knowledge-update')


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rows(path):
    rows = []
    lines = Path(path).read_text(encoding='utf-8-sig').split('\n')
    for number, line in enumerate(lines, 1):
        if not line and number == len(lines):
            continue
        if not line.strip():
            raise ValueError(f'{path}:{number}: blank JSONL record')
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f'{path}:{number}: expected object')
        rows.append(value)
    return rows


def _index(rows, key):
    indexed = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'Invalid {key}')
        if value in indexed:
            raise ValueError(f'Duplicate {key}: {value}')
        indexed[value] = row
    return indexed


def validate_prepared_coverage(manifest, references, predictions):
    """Check the frozen denominator and episode/prediction partition before use."""
    statuses = ('completed', 'abstained', 'failed', 'missing')
    required = {'planned', 'exported', *statuses}
    coverage = manifest.get('coverage')
    if (not isinstance(coverage, dict) or set(coverage) != required
            or any(type(coverage[key]) is not int or coverage[key] < 0 for key in required)):
        raise ValueError('Invalid prepared coverage counts')
    if (coverage['planned'] != len(references) or coverage['planned'] == 0
            or coverage['exported'] != len(predictions)
            or sum(coverage[key] for key in statuses) != coverage['planned']
            or coverage['completed'] + coverage['abstained'] != coverage['exported']):
        raise ValueError('Prepared coverage does not match frozen inputs')
    episodes = manifest.get('episodes')
    if not isinstance(episodes, list) or any(not isinstance(row, dict) for row in episodes):
        raise ValueError('Invalid prepared coverage episodes')
    by_question = _index(episodes, 'question_id')
    _index(episodes, 'task_id')
    if set(by_question) != set(references):
        raise ValueError('Prepared coverage episode IDs differ from references')
    actual_counts = {status: 0 for status in statuses}
    successful = set()
    for qid, episode in by_question.items():
        status = episode.get('status')
        if status not in actual_counts:
            raise ValueError('Invalid prepared coverage episode status')
        actual_counts[status] += 1
        if status in ('completed', 'abstained'):
            successful.add(qid)
    if any(actual_counts[key] != coverage[key] for key in statuses) or successful != set(predictions):
        raise ValueError('Prepared coverage episode states differ from counts/predictions')


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _jsonl(path, rows):
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def export_predictions(run_dir, references_path, output_dir):
    """Export only successful textual outputs; keep failures in coverage metadata.

    Evaluator references define the frozen planned denominator. Raw semantic IDs
    exist only in this evaluator artifact, never in public agent inputs.
    """
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    references = _rows(references_path)
    by_task = _index(references, 'task_id')
    run_manifest_path = Path(run_dir) / 'manifest.json'
    if run_manifest_path.exists():
        run_manifest = json.loads(run_manifest_path.read_text(encoding='utf-8'))
        task_ids = run_manifest.get('task_ids')
        if (not isinstance(task_ids, list) or any(not isinstance(item, str) for item in task_ids)
                or len(task_ids) != len(set(task_ids)) or set(task_ids) != set(by_task)):
            raise ValueError('Run manifest task_ids do not match frozen evaluator references')
    _index(references, 'question_id')
    for row in references:
        if row.get('question_type') not in CATEGORIES:
            raise ValueError('Unknown question_type')
        if not isinstance(row.get('question'), str) or 'answer' not in row:
            raise ValueError('Reference lacks question/answer')
    if not references:
        raise ValueError('No planned references')
    result_path = Path(run_dir) / 'results.jsonl'
    results = _index(_rows(result_path), 'task_id')
    if results.keys() - by_task.keys():
        raise ValueError('Unknown result task_id')
    counts = dict(planned=len(references), exported=0, completed=0, abstained=0, failed=0, missing=0)
    hypotheses, states = [], []
    for task_id, reference in by_task.items():
        result = results.get(task_id)
        status = result.get('status') if result else 'missing'
        if status not in ('completed', 'abstained', 'failed', 'missing'):
            raise ValueError('Unknown episode status')
        counts[status] += 1
        state = dict(task_id=task_id, question_id=reference['question_id'], status=status)
        if result and result.get('error_kind'):
            state['error_kind'] = result['error_kind']
        states.append(state)
        if status in ('completed', 'abstained'):
            prediction = result.get('prediction')
            if not isinstance(prediction, str) or not prediction.strip():
                raise ValueError('Successful/abstained output requires explicit nonempty text')
            hypotheses.append(dict(question_id=reference['question_id'], hypothesis=prediction))
    counts['exported'] = len(hypotheses)
    manifest = dict(schema_version=1, official_commit=OFFICIAL_COMMIT,
                    official_sources=[OFFICIAL_BASE + 'evaluate_qa.py', OFFICIAL_BASE + 'print_qa_metrics.py'],
                    coverage=counts, episodes=states,
                    source_sha256=dict(references=_hash(references_path), results=_hash(result_path)),
                    protocol=dict(label_parser="'yes' in eval_response.lower() (upstream)",
                                  abstention_rule="'_abs' in question_id",
                                  judge_calls_performed=False))
    output.mkdir(parents=True)
    _jsonl(output / 'predictions.jsonl', hypotheses)
    _json(output / 'evaluator_reference.json', [{k: v for k, v in row.items() if k != 'task_id'} for row in references])
    manifest['artifact_sha256'] = {name: _hash(output / name) for name in ('predictions.jsonl', 'evaluator_reference.json')}
    _json(output / 'manifest.json', manifest)
    return manifest


def import_scores(prepared_dir, official_results_path, output_dir, *, allow_partial=False):
    """Replay complete upstream boolean labels without invoking a judge.

    Upstream itself maps raw judge text using substring parsing. This importer
    accepts its boolean artifact, never reinterprets arbitrary text as failure.
    """
    output, prepared = Path(output_dir), Path(prepared_dir)
    if output.exists():
        raise FileExistsError(output)
    manifest = json.loads((prepared / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['official_commit'] != OFFICIAL_COMMIT:
        raise ValueError('Unexpected official revision')
    for name, digest in manifest['artifact_sha256'].items():
        if _hash(prepared / name) != digest:
            raise ValueError('Prepared artifact hash mismatch')
    hypotheses = _index(_rows(prepared / 'predictions.jsonl'), 'question_id')
    references = _index(json.loads((prepared / 'evaluator_reference.json').read_text(encoding='utf-8')), 'question_id')
    validate_prepared_coverage(manifest, references, hypotheses)
    scores = _index(_rows(official_results_path), 'question_id')
    if scores.keys() - hypotheses.keys() or (not allow_partial and scores.keys() != hypotheses.keys()):
        raise ValueError('Scored IDs must exactly match exported prediction IDs')
    models, per_category, abstention, rows = set(), {category: [] for category in CATEGORIES}, [], []
    for qid, prediction in hypotheses.items():
        if qid not in scores:
            continue
        score = scores[qid]
        if score.get('hypothesis') != prediction['hypothesis']:
            raise ValueError('Scored hypothesis differs from prepared prediction')
        label = score.get('autoeval_label')
        if not isinstance(label, dict) or type(label.get('label')) is not bool:
            raise ValueError('Expected official boolean autoeval_label')
        model = label.get('model')
        if not isinstance(model, str) or not model.strip():
            raise ValueError('Missing judge model')
        models.add(model)
        correct = int(label['label'])
        per_category[references[qid]['question_type']].append(correct)
        if '_abs' in qid:
            abstention.append(correct)
        rows.append(dict(question_id=qid, correct=bool(correct), question_type=references[qid]['question_type'], judge_model=model))
    if len(models) > 1:
        raise ValueError('Mixed judge models')
    def mean(values):
        return sum(values) / len(values) if values else None
    available = [mean(values) for values in per_category.values() if values]
    all_values = [value for values in per_category.values() for value in values]
    planned, exported = manifest['coverage']['planned'], len(hypotheses)
    correct = sum(all_values)
    summary = dict(schema_version=1, coverage=dict(manifest['coverage'], scored=len(scores), judge_unknown=exported-len(scores)),
                   judge_model=next(iter(models), None),
                   official=dict(overall_accuracy=mean(all_values),
                                 per_category={category: dict(n=len(values), accuracy=mean(values)) for category, values in per_category.items()},
                                 category_macro_accuracy=mean(available) if len(available) == len(CATEGORIES) else None,
                                 available_category_macro_accuracy=mean(available),
                                 abstention_n=len(abstention), abstention_accuracy=mean(abstention)),
                   end_to_end=dict(planned=planned, correct=correct, success_lower_bound=correct/planned,
                                   success_upper_bound=(correct+exported-len(scores))/planned),
                   provenance=dict(official_commit=OFFICIAL_COMMIT, official_results_sha256=_hash(official_results_path),
                                   allow_partial=allow_partial,
                                   prepared_manifest_sha256=_hash(prepared / 'manifest.json'),
                                   official_print_metrics_compatible=models == {'gpt-4o-2024-08-06'}, judge_calls_performed=False))
    output.mkdir(parents=True)
    (output / 'inputs').mkdir()
    for name in ('manifest.json', 'predictions.jsonl', 'evaluator_reference.json'):
        shutil.copyfile(prepared / name, output / 'inputs' / name)
    shutil.copyfile(official_results_path, output / 'official-results.jsonl')
    _jsonl(output / 'scores.jsonl', rows)
    _json(output / 'summary.json', summary)
    return summary
