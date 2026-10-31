"""Offline bounded dev pilots with unchanged public task payloads."""
import hashlib
import json
from pathlib import Path
import random

from evirecall.contracts import TaskInput
from evirecall.tasks.longmemeval import _json, _jsonl, _publish


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _verified(directory, manifest, names):
    result = {}
    for name in names:
        raw = (directory / name).read_bytes()
        if _sha(raw) != manifest.get('artifact_sha256', {}).get(name):
            raise ValueError(f'artifact SHA-256 mismatch: {name}')
        result[name] = raw
    return result


def _rows(raw):
    rows = [json.loads(line) for line in raw.decode('utf-8').split('\n') if line.strip()]
    if any(not isinstance(row, dict) or not isinstance(row.get('task_id'), str) for row in rows):
        raise ValueError('invalid task rows')
    if len({row['task_id'] for row in rows}) != len(rows):
        raise ValueError('duplicate task IDs')
    return {row['task_id']: row for row in rows}


def prepare_pilot(prepared_dir, split_dir, output_dir, *, max_questions=1, seed=0):
    """Select one neutral-ID query per sampled dev group; never execute models."""
    if type(max_questions) is not int or max_questions <= 0 or type(seed) is not int:
        raise ValueError('count must be a positive integer and seed an integer')
    if Path(output_dir).exists():
        raise FileExistsError(output_dir)
    prepared, split = Path(prepared_dir), Path(split_dir)
    source_raw = (prepared / 'manifest.json').read_bytes()
    split_raw = (split / 'manifest.json').read_bytes()
    source_manifest, split_manifest = json.loads(source_raw), json.loads(split_raw)
    artifacts = _verified(prepared, source_manifest, ('public/tasks.jsonl', 'evaluator/references.jsonl', 'inventory.json'))
    split_names = tuple(name for part in ('dev', 'test', 'unused') for name in (f'{part}/tasks.jsonl', f'evaluator/{part}/references.jsonl'))
    split_artifacts = _verified(split, split_manifest, split_names)
    if split_manifest.get('inventory_sha256') != _sha(artifacts['inventory.json']):
        raise ValueError('split inventory SHA-256 mismatch')
    tasks = _rows(artifacts['public/tasks.jsonl'])
    refs = _rows(artifacts['evaluator/references.jsonl'])
    items = json.loads(artifacts['inventory.json'])['items']
    inventory = _rows(''.join(json.dumps(item) + '\n' for item in items).encode())
    assignments = split_manifest.get('assignments', {})
    if not tasks or set(tasks) != set(refs) or set(tasks) != set(inventory) or set(tasks) != set(assignments):
        raise ValueError('prepared and split task IDs must match exactly')
    groups, memberships = {}, {}
    for task_id, task in tasks.items():
        TaskInput.from_dict(task)
        part = assignments[task_id]
        if part not in ('dev', 'test', 'unused'):
            raise ValueError('unknown split assignment')
        group = inventory[task_id].get('split_group_id')
        if not isinstance(group, str) or not group:
            raise ValueError('missing protected group')
        memberships.setdefault(group, set()).add(part)
        if part == 'dev':
            groups.setdefault(group, []).append(task_id)
    if any(len(parts) != 1 for parts in memberships.values()):
        raise ValueError('protected group crosses split assignments')
    for part in ('dev', 'test', 'unused'):
        expected = {tid for tid, value in assignments.items() if value == part}
        for name, originals in ((f'{part}/tasks.jsonl', tasks), (f'evaluator/{part}/references.jsonl', refs)):
            rows = _rows(split_artifacts[name])
            if set(rows) != expected or any(row != originals[tid] for tid, row in rows.items()):
                raise ValueError('split payloads differ from prepared assignments')
    if max_questions > len(groups):
        raise ValueError('count exceeds available dev protected groups')
    order = sorted(groups)
    random.Random(seed).shuffle(order)
    selected_groups = order[:max_questions]
    selected = []
    for group in selected_groups:
        candidates = sorted(groups[group])
        # A separate stable stream keeps candidate choice independent of group size/order.
        random.Random(f'{seed}:{group}').shuffle(candidates)
        selected.append(candidates[0])
    manifest = dict(format_version=1, dataset=source_manifest.get('dataset'), source_manifest_sha256=_sha(source_raw), split_manifest_sha256=_sha(split_raw), strategy='seeded uniform dev groups; one seeded query per protected group', seed=seed, max_questions=max_questions, task_count=len(selected), task_ids=selected, selected_split_group_ids=selected_groups, public_tasks='public/tasks.jsonl', evaluator_references='evaluator/references.jsonl')
    def write(directory):
        _jsonl(directory / 'public/tasks.jsonl', [tasks[tid] for tid in selected])
        _jsonl(directory / 'evaluator/references.jsonl', [refs[tid] for tid in selected])
        manifest['artifact_sha256'] = {name: _sha((directory / name).read_bytes()) for name in ('public/tasks.jsonl', 'evaluator/references.jsonl')}
        _json(directory / 'manifest.json', manifest)
        return manifest
    return _publish(output_dir, write)
