"""Bounded, independently archived LongMemEval judge invocation.

Prompt protocol: xiaowu0162/LongMemEval, pinned revision below. Only the verified
pure prompt function is compiled; the upstream SDK module is never imported.
"""

import ast
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
from urllib import error, request
from urllib.parse import urlsplit
from uuid import uuid4

from evirecall.contracts import (AgentOutput, ContractError, EvidencePacket,
                                TaskInput, check_fields, require_text)
from evirecall.evaluation.longmemeval import (CATEGORIES, OFFICIAL_COMMIT, import_scores,
                                            validate_prepared_coverage)
from evirecall.memory.fixture import FixtureMemory
from evirecall.runner.core import execute_tasks
from evirecall.runner.records import append_jsonl, read_jsonl, write_json
from evirecall.runner.runtime import ExecutionLimits

OFFICIAL_SOURCE_SHA256 = 'ecce9c4c79dc89d99534ac17b383a5cbb5b9f0c69ee98adaf0684742e3d95251'
OFFICIAL_CRLF_SHA256 = '5085eb9ae08b91c6c4f97c6bea9b8c2d6e55f9ec72c27734cafa0a04f00a430a'
OFFICIAL_MODEL = 'gpt-4o-2024-08-06'


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_official_prompt(official_source_dir):
    """Verify pinned bytes before compiling only get_anscheck_prompt's AST."""
    path = Path(official_source_dir) / 'src/evaluation/evaluate_qa.py'
    if _hash(path) not in (OFFICIAL_SOURCE_SHA256, OFFICIAL_CRLF_SHA256):
        raise ContractError('Pinned official evaluate_qa.py SHA-256 mismatch')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'get_anscheck_prompt')
    scope = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), scope)
    return scope['get_anscheck_prompt']


def official_label(response):
    return 'yes' in response.strip().lower()


def _finite(value, name, *, positive=False):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or value < 0 or (positive and value == 0)):
        raise ContractError(f'{name} must be finite and {"positive" if positive else "nonnegative"}')


def _configuration(config_path):
    path = Path(config_path).resolve()
    config = json.loads(path.read_text(encoding='utf-8-sig'))
    check_fields(config, {'endpoint', 'model', 'official_source_dir', 'request_timeout_s', 'limits'},
                 {'api_key_env', 'pricing'})
    endpoint = require_text(config['endpoint'], 'endpoint')
    parsed = urlsplit(endpoint)
    try:
        parsed.port
    except ValueError as exc:
        raise ContractError('Invalid endpoint port') from exc
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or not parsed.path
            or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment):
        raise ContractError('Expected an explicit HTTP(S) endpoint without credentials/query/fragment')
    local = parsed.hostname in ('localhost', '127.0.0.1', '::1')
    if parsed.scheme == 'http' and not local:
        raise ContractError('HTTP is permitted only for literal loopback offline services')
    require_text(config['model'], 'model')
    _finite(config['request_timeout_s'], 'request_timeout_s', positive=True)
    check_fields(config['limits'], {'max_calls', 'max_attempts', 'max_cost_usd'},
                 {field.name for field in fields(ExecutionLimits)})
    _finite(config['limits']['max_cost_usd'], 'max_cost_usd')
    limits = ExecutionLimits(**config['limits'])
    env = config.get('api_key_env')
    if env is not None and (not isinstance(env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', env)):
        raise ContractError('api_key_env must be an environment variable name')
    if parsed.scheme == 'https' and env is None:
        raise ContractError('HTTPS requires an explicit api_key_env name')
    if config.get('pricing') is not None:
        check_fields(config['pricing'], {'source', 'input_usd_per_million', 'output_usd_per_million'})
        require_text(config['pricing']['source'], 'pricing.source')
        for name in ('input_usd_per_million', 'output_usd_per_million'):
            _finite(config['pricing'][name], 'pricing.' + name)
    require_text(config['official_source_dir'], 'official_source_dir')
    config['official_source_dir'] = str((path.parent / config['official_source_dir']).resolve())
    load_official_prompt(config['official_source_dir'])
    return config, limits, local, bool(env and os.environ.get(env, '').strip())


def _prepared(prepared_dir):
    directory = Path(prepared_dir).resolve()
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('official_commit') != OFFICIAL_COMMIT:
        raise ContractError('Unexpected prepared official revision')
    hashes = manifest.get('artifact_sha256')
    if not isinstance(hashes, dict) or set(hashes) != {'predictions.jsonl', 'evaluator_reference.json'}:
        raise ContractError('Expected exact prepared prediction/reference hashes')
    for name, digest in hashes.items():
        if _hash(directory / name) != digest:
            raise ContractError('Prepared artifact hash mismatch')
    predictions = read_jsonl(directory / 'predictions.jsonl').records
    refs = json.loads((directory / 'evaluator_reference.json').read_text(encoding='utf-8'))
    if not isinstance(refs, list):
        raise ContractError('Expected reference array')
    from evirecall.evaluation.longmemeval import _index
    indexed = _index(refs, 'question_id')
    prediction_index = _index(predictions, 'question_id')
    validate_prepared_coverage(manifest, indexed, prediction_index)
    for row in refs:
        if row.get('question_type') not in CATEGORIES or not isinstance(row.get('question'), str) or 'answer' not in row:
            raise ContractError('Invalid evaluator reference')
    for row in predictions:
        if row['question_id'] not in indexed:
            raise ContractError('Prediction lacks evaluator reference')
        require_text(row.get('hypothesis'), 'hypothesis')
    return directory, manifest, predictions, indexed


def inspect_judge_config(prepared_dir, config_path):
    """Validate locally, report secret presence only, never create output or HTTP."""
    config, limits, local, credential = _configuration(config_path)
    _, _, predictions, _ = _prepared(prepared_dir)
    return dict(ready=(urlsplit(config['endpoint']).scheme == 'http' or credential) and limits.max_cost_usd > 0,
                credential_present=credential, local_service=local,
                prediction_count=len(predictions), endpoint=config['endpoint'], model=config['model'],
                limits=asdict(limits), pricing=config.get('pricing'),
                official_commit=OFFICIAL_COMMIT, official_source_sha256=_hash(Path(config['official_source_dir']) / 'src/evaluation/evaluate_qa.py'),
                official_blob_sha256=OFFICIAL_SOURCE_SHA256,
                protocol_variant=config['model'] != OFFICIAL_MODEL,
                official_print_metrics_compatible=config['model'] == OFFICIAL_MODEL,
                judge_calls_performed=False)


class JudgeRetriableError(RuntimeError):
    """Safe status class; contains no provider body, headers, or credentials."""


class JudgeHTTPError(RuntimeError):
    pass


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _usage(payload, pricing):
    raw = payload.get('usage')
    if not isinstance(raw, dict):
        return None
    prompt, completion = raw.get('prompt_tokens'), raw.get('completion_tokens')
    if any(type(n) is not int or n < 0 for n in (prompt, completion)):
        return None
    cached = raw.get('prompt_tokens_details')
    cache_unknown = cached is not None and (not isinstance(cached, dict) or cached.get('cached_tokens', 0) != 0)
    cost = None
    if pricing is not None and not cache_unknown:
        cost = (prompt * pricing['input_usd_per_million'] + completion * pricing['output_usd_per_million']) / 1_000_000
    return dict(input_tokens=prompt, output_tokens=completion, cost_usd=cost,
                cost_basis='declared_estimate' if cost is not None else 'unknown',
                provider_billed_cost_usd=None, pricing_source=pricing['source'] if pricing else None)


@dataclass
class JudgeFactory:
    config: dict
    evaluator_dir: str
    predictions: dict

    def __call__(self):
        return self

    def run(self, task, memory, budget, context):
        directory = Path(self.evaluator_dir)
        payload = dict(model=self.config['model'], messages=[dict(role='user', content=task.query)],
                       n=1, temperature=0, max_tokens=10)
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        request_id = uuid4().hex
        raw = directory / 'judge' / 'raw'; raw.mkdir(parents=True, exist_ok=True)
        req_path = raw / (request_id + '.request.json')
        req_path.write_bytes(encoded)
        append_jsonl(directory / 'judge/artifacts.jsonl', dict(kind='request', task_id=task.task_id,
                     path=req_path.relative_to(directory).as_posix(), sha256=_hash(req_path)))

        def invoke():
            secret = os.environ.get(self.config.get('api_key_env') or '')
            headers = {'Content-Type': 'application/json'}
            if secret:
                headers['Authorization'] = 'Bearer ' + secret
            http = request.Request(self.config['endpoint'], data=encoded, headers=headers, method='POST')
            local = urlsplit(self.config['endpoint']).hostname in ('localhost', '127.0.0.1', '::1')
            opener = request.build_opener(request.ProxyHandler({}) if local else request.ProxyHandler(), _NoRedirect())
            try:
                with opener.open(http, timeout=min(self.config['request_timeout_s'], context.remaining_seconds)) as stream:
                    body = stream.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise JudgeHTTPError('response_size_limit')
            except error.HTTPError as exc:
                status = exc.code
                exc.close()
                append_jsonl(directory / 'judge/http.jsonl', dict(task_id=task.task_id, status_class=f'http_{status}'))
                if status == 429 or status >= 500:
                    raise JudgeRetriableError(f'http_{status}') from None
                raise JudgeHTTPError(f'http_{status}') from None
            except (error.URLError, TimeoutError, socket.timeout):
                append_jsonl(directory / 'judge/http.jsonl', dict(task_id=task.task_id, status_class='network_or_timeout'))
                raise JudgeRetriableError('network_or_timeout') from None
            # Auth headers are never persisted. Redact any unexpected credential echo.
            saved = body.replace(secret.encode(), b'[REDACTED]') if secret else body
            path = raw / (uuid4().hex + '.response.json')
            path.write_bytes(saved)
            append_jsonl(directory / 'judge/artifacts.jsonl', dict(kind='response', task_id=task.task_id,
                         path=path.relative_to(directory).as_posix(), sha256=_hash(path),
                         credential_echo_redacted=saved != body))
            try:
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise ValueError
                return result
            except (ValueError, UnicodeDecodeError):
                raise JudgeHTTPError('invalid_response_json') from None

        def actual_model(value):
            model = require_text(value.get('model'), 'actual_model')
            secret = os.environ.get(self.config.get('api_key_env') or '')
            if secret and secret in model:
                raise ContractError('Credential echo in model metadata')
            return model

        completion = context.call(invoke, role='judge', operation='chat.completions', phase='evaluation',
                                  provider='openai-compatible', model=self.config['model'],
                                  usage_fn=lambda value: _usage(value, self.config.get('pricing')),
                                  actual_model_fn=actual_model,
                                  retry_on=(JudgeRetriableError,),
                                  metadata=dict(request_sha256=_hash(req_path),
                                      request_ref=req_path.relative_to(directory).as_posix(),
                                      prompt_template_sha256=OFFICIAL_SOURCE_SHA256,
                                      price_ref=self.config['pricing']['source'] if self.config.get('pricing') else 'unpriced'))
        try:
            content = completion['choices'][0]['message']['content']
            if not isinstance(content, str):
                raise ValueError
        except (KeyError, IndexError, TypeError, ValueError):
            raise JudgeHTTPError('invalid_completion_content') from None
        original = self.predictions[task.task_id]
        judged = dict(original, autoeval_label=dict(model=completion['model'], label=official_label(content)))
        # Atomic independent files cannot create an interior truncated JSONL tail
        # if the supervisor terminates this worker during persistence.
        write_json(directory / 'judge/judgments' / (task.task_id + '.json'), judged)
        return AgentOutput('judgment saved', 'completed', EvidencePacket((), 'evaluation'))


def run_judge(prepared_dir, config_path, output_dir):
    """Run bounded judge workers and replay durable boolean labels independently."""
    config, limits, local, credential = _configuration(config_path)
    prepared, _, predictions, references = _prepared(prepared_dir)
    if urlsplit(config['endpoint']).scheme == 'https' and not credential:
        raise ContractError('Configured judge credential environment variable is absent or empty')
    output = Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError(output)
    prompt = load_official_prompt(config['official_source_dir'])
    tasks, mapping = [], {}
    for index, prediction in enumerate(predictions):
        identity = f'judge-{index:06d}'
        ref = references[prediction['question_id']]
        text = prompt(ref['question_type'], ref['question'], ref['answer'], prediction['hypothesis'],
                      abstention='_abs' in prediction['question_id'])
        tasks.append(TaskInput('longmemeval-judge', identity, identity, identity, text, ()))
        mapping[identity] = prediction
    output.mkdir(parents=True)
    (output / 'inputs').mkdir()
    for name in ('manifest.json', 'predictions.jsonl', 'evaluator_reference.json'):
        shutil.copyfile(prepared / name, output / 'inputs' / name)
    (output / 'judge').mkdir()
    source_path = Path(config['official_source_dir']) / 'src/evaluation/evaluate_qa.py'
    shutil.copyfile(source_path, output / 'judge/official-evaluate_qa.py')
    license_path = Path(__file__).resolve().parent / 'longmemeval-MIT-LICENSE.txt'
    shutil.copyfile(license_path, output / 'judge/official-MIT-LICENSE.txt')
    manifest = dict(schema_version=1, mode='judge', evaluator_only=True,
                    official_commit=OFFICIAL_COMMIT, official_source_sha256=_hash(source_path),
                    official_blob_sha256=OFFICIAL_SOURCE_SHA256,
                    official_source_url=f'https://github.com/xiaowu0162/LongMemEval/blob/{OFFICIAL_COMMIT}/src/evaluation/evaluate_qa.py',
                    config=config, prepared_manifest_sha256=_hash(prepared / 'manifest.json'),
                    local_service=local, protocol_variant=config['model'] != OFFICIAL_MODEL,
                    protocol=dict(n=1, temperature=0, max_tokens=10,
                                  label_parser="'yes' in response.strip().lower()"),
                    cost_policy='Declared estimates only; provider-billed actual unavailable; unknown charges stop subsequent calls.')
    write_json(output / 'judge/manifest.json', manifest)
    (output / 'official-results.jsonl').touch()
    execution_error = None
    try:
        if tasks:
            execute_tasks(tasks, output / 'execution', condition='longmemeval-official-judge', limits=limits,
                          history_mode='independent', agent_factory=JudgeFactory(config, str(output), mapping),
                          memory_factory=FixtureMemory,
                          provenance=dict(evaluator_only=True, official_source_sha256=OFFICIAL_SOURCE_SHA256))
    except Exception as exc:
        execution_error = type(exc).__name__
        write_json(output / 'judge/wrapper-failure.json', dict(error_kind=execution_error))
    # Only the parent appends the official-compatible stream. Completed results
    # acknowledge the worker returned after the atomic judgment was durable.
    completed = {row['task_id'] for row in read_jsonl(output / 'execution/results.jsonl', recover_tail=True).records
                 if row.get('status') == 'completed'}
    for task in tasks:
        path = output / 'judge/judgments' / (task.task_id + '.json')
        if task.task_id in completed and path.is_file():
            append_jsonl(output / 'official-results.jsonl', json.loads(path.read_text(encoding='utf-8')))
    from evirecall.runner.accounting import aggregate_calls
    call_records = read_jsonl(output / 'execution/calls.jsonl', recover_tail=True).records
    usage = aggregate_calls(call_records)
    observed_variant = any(row.get('actual_model') not in (None, OFFICIAL_MODEL) for row in call_records)
    summary = import_scores(output / 'inputs', output / 'official-results.jsonl', output / 'scores', allow_partial=True)
    summary['usage'] = usage
    summary['judge'] = dict(local_service=local, requested_model=config['model'],
                           protocol_variant=config['model'] != OFFICIAL_MODEL or observed_variant,
                           requested_protocol_variant=config['model'] != OFFICIAL_MODEL,
                           wrapper_error=execution_error, official_source_sha256=_hash(source_path),
                           cost_basis='declared_estimate' if config.get('pricing') else 'unknown')
    summary['provenance']['judge_calls_performed'] = bool(usage['requests'])
    summary['provenance']['official_print_metrics_compatible'] &= config['model'] == OFFICIAL_MODEL
    write_json(output / 'summary.json', summary)
    return summary
