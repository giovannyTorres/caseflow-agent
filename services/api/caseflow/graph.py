from typing import TypedDict
from langgraph.graph import StateGraph, END, START
from langgraph.types import interrupt
from .config import settings
from .db import connection, event, scenario_fixtures
from .domain import Decision, get_case
from .execution import require_execution
from .mcp_client import call_tool
from .providers import provider
from .ontology import OntologyError, resolve_context, validate_binding
from .policy import current_policy

class State(TypedDict, total=False):
    case_id: str
    actor: str
    correlation: str
    movements: dict
    policy: dict
    decision: dict
    proposal: dict
    version: int
    context_binding: dict
    context_refresh_required: bool

async def tool(state, name, **args):
    return await call_tool(name, {'case_id': state['case_id'], **args}, case_id=state['case_id'],
                           actor=state['actor'], correlation=state['correlation'])

def progress(state, name, detail):
    with connection() as conn:
        get_case(conn, state['case_id'], True)
        require_execution(conn, state['case_id'])
        event(conn, state['case_id'], state['actor'], name, detail, state['correlation'])

async def gather(state):
    movements = await tool(state, 'get_movements')
    policy = await tool(state, 'get_policy')
    with connection() as conn:
        case = get_case(conn, state['case_id'])
    if movements.get('movements') != case['movements'] or movements.get('amount') != case['amount']:
        raise OntologyError('Case evidence changed while gathering; retry the investigation')
    if policy != current_policy():
        raise OntologyError('Policy changed while gathering; retry the investigation')
    context, audit = await resolve_context(case, policy, settings)
    progress(state, 'evidence_gathered', {'movement_count': len(movements['movements']), 'policy': policy['id']})
    progress(state, 'semantic_context', audit)
    return {'movements': movements, 'policy': policy, 'context_binding': context.model_dump(),
            'context_refresh_required': False}

async def decide(state):
    with connection() as conn:
        case = get_case(conn, state['case_id'])
    if settings.mode == 'DEMO' and case['scenario'] == 'interruption':
        interrupt({'kind': 'interruption', 'message': 'Synthetic interruption: resume from the persisted checkpoint.'})
    if settings.mode == 'DEMO':
        fixture = next(x for x in scenario_fixtures() if x['scenario'] == case['scenario'])
        decision = Decision.model_validate(fixture['decision'])
    else:
        context = {'case': {'id': case['id'], 'amount': case['amount'], 'evidence': case['evidence']},
                   'movements': state['movements'], 'policy': state['policy']}
        binding = state.get('context_binding')
        if binding and binding['strategy'] != 'baseline':
            context['semantic_context'] = {'snapshot_id': binding['snapshot_id'], 'terms': binding['terms']}
        decision = await provider().decide(context)
    progress(state, 'decision_prepared', {'action': decision.action, 'mode': settings.mode})
    with connection() as conn:
        get_case(conn, state['case_id'], True)
        require_execution(conn, state['case_id'])
        conn.execute('INSERT INTO messages(case_id,role,content) VALUES(%s,%s,%s)', (case['id'], 'assistant', decision.reason))
    return {'decision': decision.model_dump()}

async def act(state):
    with connection() as conn:
        case = get_case(conn, state['case_id'])
    # A legacy/stale checkpoint cannot attach today's evidence to yesterday's decision.
    # Repeat gathering AND model decision instead, including when an operator has
    # prepared a proposal since this checkpoint was saved.
    try:
        validate_binding(state.get('context_binding'), case, current_policy())
    except OntologyError:
        progress(state, 'context_refresh_required', {'reason': 'Case or policy context needs a new decision'})
        return {'context_refresh_required': True}
    decision = Decision.model_validate(state['decision'])
    if decision.action == 'propose':
        return {'proposal': await tool(state, 'prepare_proposal', amount=decision.amount, reason=decision.reason,
                                       context_binding=state.get('context_binding'))}
    await tool(state, 'request_evidence', reason=decision.reason)
    if decision.action == 'reject':
        progress(state, 'rejection_recommended', {'message': 'Supervisor must review and reject this case.'})
    return {}

async def gate(state):
    resume = interrupt({'kind': 'approval', 'message': 'A supervisor must approve the current proposal and request resolution.'})
    # The resume payload is created only by the authenticated backend.
    return {'actor': resume['actor'], 'version': resume['version']}

async def resolve(state):
    await tool(state, 'register_resolution', version=state['version'])
    return {}


def graph(checkpointer):
    builder = StateGraph(State)
    for name, fn in [('gather', gather), ('decide', decide), ('act', act), ('gate', gate), ('resolve', resolve)]:
        builder.add_node(name, fn)
    builder.add_edge(START, 'gather')
    builder.add_edge('gather', 'decide')
    builder.add_edge('decide', 'act')
    builder.add_conditional_edges('act', lambda s: 'gather' if s.get('context_refresh_required') else (
        'gate' if s['decision']['action'] == 'propose' else END))
    builder.add_edge('gate', 'resolve')
    builder.add_edge('resolve', END)
    return builder.compile(checkpointer=checkpointer)
