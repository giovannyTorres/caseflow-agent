"""Optional reviewed definitions. Case evidence and effects stay application-owned."""
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OntologyError(ValueError):
    """Bounded error; never expose credentials or external payloads."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def term_digest(value: dict) -> str:
    fields = {key: value[key] for key in (
        'id', 'name', 'description', 'name_certified', 'description_certified')}
    fields['synonyms'] = sorted(set(value.get('synonyms') or []))
    return digest(fields)


def strict_json(content: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid number')))


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Term(Strict):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=3000)
    synonyms: list[str] = Field(default_factory=list, max_length=30)
    name_certified: bool = Field(strict=True)
    description_certified: bool = Field(strict=True)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def reviewed(self):
        if (not self.name_certified or not self.description_certified or
                any(not word.strip() or len(word) > 160 for word in self.synonyms) or
                term_digest(self.model_dump()) != self.sha256):
            raise ValueError('Term is not the reviewed certified revision')
        return self


class Scope(Strict):
    mode: Literal['DEMO', 'LIVE']


class Policy(Strict):
    id: str = Field(min_length=1, max_length=200)
    version: int = Field(strict=True, ge=1)
    text: str = Field(min_length=1, max_length=10000)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def content(self):
        if hashlib.sha256(self.text.encode()).hexdigest() != self.sha256:
            raise ValueError('Policy content changed')
        return self


def policy_binding(policy: dict) -> Policy:
    return Policy(id=policy['id'], version=policy['version'], text=policy['text'],
                  sha256=hashlib.sha256(policy['text'].encode()).hexdigest())


class ReviewedPolicy(Strict):
    id: str = Field(min_length=1, max_length=200)
    version: int = Field(strict=True, ge=1)
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


class Snapshot(Strict):
    schema_version: Literal[1]
    application: Literal['caseflow-agent']
    snapshot_id: str = Field(min_length=1, max_length=160)
    source: Literal['glossary', 'auto_ontology']
    source_commit: str = Field(min_length=1, max_length=200)
    scope: Scope
    certified: bool = Field(strict=True)
    approved_by: str = Field(min_length=1, max_length=160)
    policy: ReviewedPolicy
    terms: list[Term] = Field(max_length=30)

    @field_validator('schema_version', mode='before')
    @classmethod
    def exact_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Unsupported snapshot schema')
        return value

    @model_validator(mode='after')
    def approved(self):
        ids = [term.id for term in self.terms]
        if not self.certified or len(ids) != len(set(ids)):
            raise ValueError('Application approval and unique terms required')
        return self


def load_snapshot(path: str, sha256: str, mode: str, policy: dict) -> Snapshot:
    try:
        file = Path(path)
        if file.stat().st_size > 256000:
            raise ValueError('Snapshot too large')
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha256:
            raise ValueError('Snapshot digest mismatch')
        snapshot = Snapshot.model_validate(strict_json(raw))
        binding = policy_binding(policy)
        if snapshot.scope.mode != mode or snapshot.policy.model_dump() != binding.model_dump(exclude={'text'}):
            raise ValueError('Snapshot scope or policy mismatch')
        return snapshot
    except (OSError, ValueError, KeyError, TypeError):
        raise OntologyError('Reviewed ontology snapshot is unavailable or invalid') from None


def case_revision(case: dict) -> str:
    return digest({key: case[key] for key in ('id', 'mode', 'amount', 'currency', 'movements', 'evidence')})


class ContextBinding(Strict):
    schema_version: Literal[1] = 1
    application: Literal['caseflow-agent'] = 'caseflow-agent'
    case_id: str
    mode: Literal['DEMO', 'LIVE']
    case_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    case_evidence: dict
    policy: Policy
    strategy: Literal['baseline', 'glossary', 'auto_ontology'] = 'baseline'
    status: Literal['disabled', 'verified', 'unavailable_baseline_fallback'] = 'disabled'
    snapshot_id: str | None = None
    snapshot_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
    source_commit: str | None = None
    approved_by: str | None = None
    terms: list[Term] = Field(default_factory=list, max_length=30)

    @field_validator('schema_version', mode='before')
    @classmethod
    def exact_schema(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('Unsupported context schema')
        return value

    @model_validator(mode='after')
    def provenance(self):
        if digest(self.case_evidence) != self.case_sha256:
            raise ValueError('Captured case evidence does not match its revision')
        if self.strategy != 'baseline':
            if (self.status != 'verified' or not self.snapshot_id or not self.snapshot_sha256
                    or not self.source_commit or not self.approved_by):
                raise ValueError('Verified semantic context needs a reviewed snapshot')
        elif self.terms or self.snapshot_id or self.snapshot_sha256 or self.status == 'verified':
            raise ValueError('Baseline cannot claim semantic enrichment')
        return self


def bind_context(case: dict, policy: dict, **semantic) -> ContextBinding:
    return ContextBinding(case_id=case['id'], mode=case['mode'], case_sha256=case_revision(case),
                          case_evidence={key: case[key] for key in (
                              'id', 'mode', 'amount', 'currency', 'movements', 'evidence')},
                          policy=policy_binding(policy), **semantic)


def validate_binding(raw: dict, case: dict, policy: dict) -> ContextBinding:
    try:
        context = ContextBinding.model_validate(raw)
        if (context.case_id != case['id'] or context.mode != case['mode'] or
                context.case_sha256 != case_revision(case) or
                context.policy != policy_binding(policy)):
            raise ValueError('Case or policy changed')
        return context
    except (ValueError, KeyError, TypeError):
        raise OntologyError('Proposal evidence context changed or belongs to another case') from None


def verify_application_review(context: ContextBinding, config) -> None:
    """Recheck app certification at proposal creation; remote flags alone are insufficient."""
    if context.strategy == 'baseline':
        if config.ontology_required and config.ontology_mode != 'off' and context.mode == 'LIVE':
            raise OntologyError('Required semantic context is missing')
        return
    snapshot = load_snapshot(config.ontology_snapshot_path, config.ontology_snapshot_sha256,
                             context.mode, context.policy.model_dump())
    if (context.strategy != config.ontology_mode or snapshot.source != context.strategy or
            context.snapshot_sha256 != config.ontology_snapshot_sha256 or
            context.snapshot_id != snapshot.snapshot_id or context.source_commit != snapshot.source_commit or
            context.approved_by != snapshot.approved_by or context.terms != snapshot.terms):
        raise OntologyError('Semantic context is not the application-approved snapshot')


def public_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in {'', '/'} or not parsed.hostname or
            (parsed.scheme != 'https' and not (parsed.scheme == 'http' and
             parsed.hostname in {'localhost', '127.0.0.1', '::1'}))):
        raise OntologyError('Auto Ontology requires an HTTPS origin or loopback HTTP')
    return value.rstrip('/')


class AutoOntologyClient:
    def __init__(self, origin, token, timeout, transport=None):
        self.client = httpx.AsyncClient(base_url=public_origin(origin), timeout=timeout,
            follow_redirects=False, headers={'x-api-key': token} if token else {}, transport=transport)
        self.requests = 0

    async def aclose(self):
        await self.client.aclose()

    async def _get(self, path, params=None):
        self.requests += 1
        try:
            async with self.client.stream('GET', path, params=params) as response:
                response.raise_for_status()
                content = bytearray()
                async for part in response.aiter_bytes():
                    content.extend(part)
                    if len(content) > 256000:
                        raise ValueError('Response too large')
                value = strict_json(bytes(content))
                if not isinstance(value, dict):
                    raise ValueError('Invalid envelope')
                return value
        except (httpx.HTTPError, ValueError, TypeError):
            raise OntologyError('Auto Ontology request failed or returned an invalid contract') from None

    async def verify(self, term: Term):
        found = False
        for skip in range(0, 150, 50):
            page = await self._get('/api/terms', {'query': term.name, 'skip': skip, 'limit': 50})
            rows, total = page.get('terms'), page.get('total')
            if not isinstance(rows, list) or len(rows) > 50 or type(total) is not int or total < 0:
                raise OntologyError('Auto Ontology returned an invalid terms page')
            if any(isinstance(row, dict) and row.get('id') == term.id for row in rows):
                found = True
                break
            if not rows or skip + len(rows) >= total:
                break
        if not found:
            raise OntologyError('Approved term absent from Auto Ontology')
        envelope = await self._get('/api/terms/' + quote(term.id, safe=''))
        try:
            data = envelope['data']
            fields = {key: data[key] for key in (
                'id', 'name', 'description', 'name_certified', 'description_certified')}
            fields['synonyms'] = data.get('synonyms') or []
            remote = Term(**fields, sha256=term_digest(fields))
            if remote.sha256 != term.sha256:
                raise ValueError('Reviewed term changed')
        except (ValueError, KeyError, TypeError):
            raise OntologyError('Auto Ontology term differs from the reviewed revision') from None


async def resolve_context(case: dict, policy: dict, config, *, strategy=None, strict=False,
                          transport=None) -> tuple[ContextBinding, dict]:
    strategy = strategy or config.ontology_mode
    base = bind_context(case, policy)
    if strategy in {'off', 'baseline'} or case['mode'] != 'LIVE':
        return base, {'strategy': 'off', 'status': 'disabled'}
    try:
        snapshot = load_snapshot(config.ontology_snapshot_path, config.ontology_snapshot_sha256,
                                 case['mode'], policy)
        if snapshot.source != strategy:
            raise OntologyError('Snapshot source differs from the selected strategy')
        requests = 0
        if strategy == 'auto_ontology':
            if not config.auto_ontology_url:
                raise OntologyError('Auto Ontology public gateway is not configured')
            client = AutoOntologyClient(config.auto_ontology_url, config.auto_ontology_api_token,
                                        config.ontology_timeout, transport)
            try:
                async with asyncio.timeout(config.ontology_timeout):
                    for term in snapshot.terms:
                        await client.verify(term)
                    if not snapshot.terms:
                        await client._get('/api/terms', {'skip': 0, 'limit': 1})
            except TimeoutError:
                raise OntologyError('Auto Ontology exceeded the total request budget') from None
            finally:
                await client.aclose()
            requests = client.requests
        context = bind_context(case, policy, strategy=strategy, status='verified',
            snapshot_id=snapshot.snapshot_id, snapshot_sha256=config.ontology_snapshot_sha256,
            source_commit=snapshot.source_commit, approved_by=snapshot.approved_by, terms=snapshot.terms)
        return context, {'strategy': strategy, 'status': 'verified', 'snapshot_id': snapshot.snapshot_id,
                         'context_sha256': digest(context.model_dump()), 'remote_requests': requests}
    except OntologyError:
        if strict or config.ontology_required:
            raise
        base.status = 'unavailable_baseline_fallback'
        return base, {'strategy': strategy, 'status': base.status}


def project_evidence(case: dict, policy: dict) -> dict:
    """Small source projection for an isolated read-only catalog; no operational SQL access."""
    return {'case_summary': {'case_id': case['id'], 'mode': case['mode'], 'amount': case['amount'],
                             'currency': case['currency']},
            'movements': [{key: row.get(key) for key in (
                'id', 'merchant', 'amount', 'currency', 'posted_at', 'status', 'purchase_id')}
                for row in case['movements']],
            'policy_version': policy_binding(policy).model_dump()}
