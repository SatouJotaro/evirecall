"""Offline LongMemEval preparation with a separate evaluator-only inventory."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import tempfile


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value


def _identifier(value, name):
    _string(value, name)
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f'{name} contains whitespace or control characters')
    return value


def _date(value):
    _string(value, 'date')
    # Upstream dates have no timezone. Validate calendar fields without inventing one.
    for pattern in ('%Y/%m/%d (%a) %H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            parsed = datetime.strptime(value, pattern)
            if pattern.startswith('%Y/%m') and parsed.strftime('%a') != re.search(r'\((\w+)\)', value).group(1):
                raise ValueError('weekday mismatch')
            return value
        except ValueError:
            pass
    raise ValueError(f'unsupported or malformed date: {value!r}')


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def _publish(output_dir, writer):
    target = Path(output_dir)
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.lme-', dir=target.parent))
    try:
        result = writer(staging)
        if target.exists():
            raise FileExistsError(target)
        staging.rename(target)
        return result
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _groups(items):
    parents = list(range(len(items)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]; i = parents[i]
        return i
    evidence_hashes = {value for item in items for value in item['evidence_fingerprints']}
    seen = {}
    for i, item in enumerate(items):
        keys = [('history', item['history_fingerprint']), ('family', item['question_family'])]
        keys += [('evidence', value) for value in item['session_fingerprints'] if value in evidence_hashes]
        for key in keys:
            if key in seen:
                parents[root(i)] = root(seen[key])
            else:
                seen[key] = i
    components = defaultdict(list)
    for i in range(len(items)):
        components[root(i)].append(i)
    for members in components.values():
        group = f'lme-g{min(members):06d}'
        for i in members:
            items[i]['split_group_id'] = group
    return len(components)


def prepare_dataset(source_path, output_dir, *, revision, expected_sha256=None):
    """Prepare local source JSON; refuse existing output and any malformed row."""
    _string(revision, 'revision')
    raw = Path(source_path).read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ValueError('source SHA-256 mismatch')
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise ValueError('source must be a nonempty JSON list')
    tasks, references, inventory, qids = [], [], [], set()
    repeated_sessions = 0
    ambiguous_answer_ids = 0
    for ordinal, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('question must be an object')
        try:
            qid = _identifier(row['question_id'], 'question_id')
            if qid in qids:
                raise ValueError('duplicate question_id')
            qids.add(qid)
            for field in ('question_type', 'question'):
                _string(row[field], field)
            if type(row['answer']) not in (str, int, float) or (isinstance(row['answer'], str) and not row['answer'].strip()) or (type(row['answer']) is float and not math.isfinite(row['answer'])):
                raise ValueError('answer must be a nonempty string or number')
            _date(row['question_date'])
            ids, dates, sessions, answers = (row[k] for k in ('haystack_session_ids', 'haystack_dates', 'haystack_sessions', 'answer_session_ids'))
            if not all(isinstance(v, list) for v in (ids, dates, sessions, answers)) or not ids or not len(ids) == len(dates) == len(sessions):
                raise ValueError('misaligned session arrays')
            for sid in ids + answers:
                _identifier(sid, 'session ID')
            if len(set(answers)) != len(answers) or not set(answers) <= set(ids):
                raise ValueError('duplicate or unresolved session ID')
            repeated_sessions += len(ids) - len(set(ids))
            ambiguous_answer_ids += sum(ids.count(sid) > 1 for sid in answers)
            task_id = f'lme-q{ordinal:06d}'
            events, mapping, fingerprints, evidence = [], {}, [], []
            for session_index, (sid, date, turns) in enumerate(zip(ids, dates, sessions)):
                _date(date)
                if not isinstance(turns, list) or not turns:
                    raise ValueError('session must contain turns')
                clean = []
                for turn_index, turn in enumerate(turns):
                    if not isinstance(turn, dict) or turn.get('role') not in ('user', 'assistant', 'system', 'tool'):
                        raise ValueError('invalid turn role')
                    if not isinstance(turn.get('content'), str):
                        raise ValueError('turn content must be text')
                    clean.append({'role': turn['role'], 'content': turn['content']})
                    source_id = f'{task_id}-s{session_index:06d}-t{turn_index:06d}'
                    events.append(dict(source_id=source_id, text=turn['content'], writer_role=turn['role'], timestamp=None, source_time_raw=date, kind='observation'))
                    mapping[source_id] = dict(session_id=sid, session_index=session_index, turn_index=turn_index)
                fingerprint = _digest(clean)
                fingerprints.append(fingerprint)
                if sid in answers:
                    evidence.append(fingerprint)
            tasks.append(dict(task_id=task_id, dataset='longmemeval', group_id=task_id, session_id=f'{task_id}-query', query=row['question'], query_time=row['question_date'], events=events, tools=[]))
            references.append(dict(task_id=task_id, question_id=qid, question_type=row['question_type'], question=row['question'], question_date=row['question_date'], answer=row['answer'], answer_session_ids=answers, source_id_mapping=mapping, abstention=qid.endswith('_abs')))
            inventory.append(dict(task_id=task_id, original_ordinal=ordinal, question_id=qid, question_family=qid.removesuffix('_abs'), question_type=row['question_type'], history_fingerprint=_digest(fingerprints), evidence_fingerprints=sorted(set(evidence)), session_fingerprints=sorted(set(fingerprints))))
        except KeyError as exc:
            raise ValueError(f'missing source field {exc}') from exc
    group_count = _groups(inventory)
    manifest = dict(format_version=1, dataset='longmemeval', revision=revision, source_sha256=source_hash, task_count=len(tasks), split_group_count=group_count, audit=dict(repeated_session_id_occurrences=repeated_sessions, answer_ids_with_multiple_occurrences=ambiguous_answer_ids), timezone_policy='unknown; original strings retained', public_tasks='public/tasks.jsonl', evaluator_references='evaluator/references.jsonl', inventory='inventory.json')
    def write(directory):
        _jsonl(directory / 'public/tasks.jsonl', tasks)
        _jsonl(directory / 'evaluator/references.jsonl', references)
        _json(directory / 'inventory.json', dict(source_sha256=source_hash, items=inventory))
        manifest['artifact_sha256'] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in ('public/tasks.jsonl', 'evaluator/references.jsonl', 'inventory.json')}
        _json(directory / 'manifest.json', manifest)
        return manifest
    return _publish(output_dir, write)


def build_split(prepared_dir, output_dir, *, dev_units=10, test_questions=100, seed=0):
    """Freeze a local grouped split; whole groups can exceed a requested count."""
    if any(type(value) is not int or value < 0 for value in (dev_units, test_questions)) or type(seed) is not int:
        raise ValueError('split counts must be nonnegative integers and seed an integer')
    prepared = Path(prepared_dir)
    manifest = json.loads((prepared / 'manifest.json').read_text(encoding='utf-8'))
    for name in ('public/tasks.jsonl', 'evaluator/references.jsonl', 'inventory.json'):
        expected = manifest.get('artifact_sha256', {}).get(name)
        if not expected or hashlib.sha256((prepared / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'prepared artifact SHA-256 mismatch: {name}')
    inventory_raw = (prepared / 'inventory.json').read_bytes()
    items = json.loads(inventory_raw)['items']
    groups = defaultdict(list)
    for item in items:
        groups[item['split_group_id']].append(item)
    order = sorted(groups)
    random.Random(seed).shuffle(order)
    # Greedy coverage favors categories not yet represented; randomized ties are fixed by seed.
    dev, covered = [], set()
    while order and len(dev) < dev_units:
        choice = max(order, key=lambda g: len({x['question_type'] for x in groups[g]} - covered))
        order.remove(choice); dev.append(choice)
        covered.update(x['question_type'] for x in groups[choice])
    test, count = [], 0
    while order and count < test_questions:
        group = order.pop(0); test.append(group); count += len(groups[group])
    assignments = {item['task_id']: ('dev' if g in dev else 'test' if g in test else 'unused') for g, members in groups.items() for item in members}
    evidence_hashes = {value for item in items for value in item['evidence_fingerprints']}
    overlap = {}
    for category, field in [('history', 'history_fingerprint'), ('evidence', 'evidence_fingerprints'), ('family', 'question_family'), ('all_sessions', 'session_fingerprints')]:
        memberships = defaultdict(set)
        for item in items:
            values = item[field] if isinstance(item[field], list) else [item[field]]
            if category == 'evidence':
                values = [value for value in item['session_fingerprints'] if value in evidence_hashes]
            for value in values:
                memberships[value].add(assignments[item['task_id']])
        overlap[category] = sorted(value for value, splits in memberships.items() if len(splits) > 1)
    report = dict(format_version=1, official_split=False, strategy='connected full-history/evidence/family groups; all-session overlap audited only', seed=seed, inventory_sha256=hashlib.sha256(inventory_raw).hexdigest(), requested_dev_units=dev_units, actual_dev_units=len(dev), requested_test_questions=test_questions, actual_test_questions=count, insufficient_dev_units=len(dev) < dev_units, insufficient_test_questions=count < test_questions, assignments=assignments, cross_split_overlap=overlap)
    tasks = [json.loads(line) for line in (prepared / 'public/tasks.jsonl').read_text(encoding='utf-8').split('\n') if line.strip()]
    references = [json.loads(line) for line in (prepared / 'evaluator/references.jsonl').read_text(encoding='utf-8').split('\n') if line.strip()]
    def write(directory):
        for split in ('dev', 'test', 'unused'):
            _jsonl(directory / split / 'tasks.jsonl', [x for x in tasks if assignments[x['task_id']] == split])
            _jsonl(directory / 'evaluator' / split / 'references.jsonl', [x for x in references if assignments[x['task_id']] == split])
        report['artifact_sha256'] = {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.rglob('*.jsonl'))}
        _json(directory / 'manifest.json', report)
        return report
    return _publish(output_dir, write)
