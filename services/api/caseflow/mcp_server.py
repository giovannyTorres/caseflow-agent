"""MCP stdio server: one subprocess per bounded capability, no listener or external clients."""
import os
from mcp.server.fastmcp import FastMCP
from pydantic import Field
from typing import Annotated
from .config import settings
from .execution import capability, require_execution
from .db import connection
from .domain import (DomainError, ProposalInput, get_case, require_actor, proposal, request_evidence as domain_evidence,
                     register_resolution as domain_resolve)

mcp = FastMCP('Caseflow Simulator')
if os.environ.get('MCP_JOB_ID'):
    capability.set({'id': os.environ['MCP_JOB_ID'], 'attempts': int(os.environ['MCP_JOB_ATTEMPT']), 'case_id': os.environ['MCP_CASE_ID']})

def context(case_id):
    if case_id != os.environ.get('MCP_CASE_ID'):
        raise DomainError('Capability is scoped to another case', 403)
    actor = os.environ['MCP_ACTOR']
    with connection() as conn:
        require_actor(conn, actor)
        get_case(conn, case_id)
        require_execution(conn, case_id)
    return actor, os.environ['MCP_CORRELATION_ID']

@mcp.tool()
def get_movements(case_id: str) -> dict:
    """Read synthetic movements for the authorized case."""
    context(case_id)
    with connection() as conn:
        case = get_case(conn, case_id)
        if settings.mode == 'DEMO' and case['scenario'] == 'tool_failure' and not case['recovery_enabled']:
            raise DomainError('Synthetic merchant feed unavailable; resume to restore it', 503)
        return {'movements': case['movements'], 'amount': case['amount'], 'source': 'synthetic-simulator'}

@mcp.tool()
def get_policy(case_id: str) -> dict:
    """Get the original fictional reimbursement policy."""
    context(case_id)
    return {'id': 'juniper-policy-v1', 'version': 1, 'text': 'Duplicate settled charges may be reimbursed once after supervisor approval. Missing evidence requires an evidence request. Confirmed legitimate purchases are rejected. Never exceed the disputed amount.'}

@mcp.tool()
def request_evidence(case_id: str, reason: Annotated[str, Field(min_length=10, max_length=1000)]) -> dict:
    """Record an evidence request; never send external messages."""
    actor, correlation = context(case_id)
    return domain_evidence(case_id, actor, reason, correlation)

@mcp.tool()
def prepare_proposal(case_id: str, amount: Annotated[int, Field(strict=True, gt=0, le=100000)], reason: Annotated[str, Field(min_length=10, max_length=1000)]) -> dict:
    """Prepare a versioned proposal and invalidate any previous approval."""
    actor, correlation = context(case_id)
    return proposal(case_id, actor, ProposalInput(amount=amount, reason=reason), correlation,
                    operation_key='graph-initial-proposal')

@mcp.tool()
def register_resolution(case_id: str, version: Annotated[int, Field(strict=True, gt=0)]) -> dict:
    """Record a simulator resolution only with the exact current supervisor approval."""
    actor, correlation = context(case_id)
    return domain_resolve(case_id, actor, version, correlation)

if __name__ == '__main__':
    mcp.run(transport='stdio')
