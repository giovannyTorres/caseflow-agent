import asyncio
import json
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from opentelemetry import trace
from .execution import capability

ALLOWED = {'get_movements', 'get_policy', 'request_evidence', 'prepare_proposal', 'register_resolution'}

async def call_tool(name, arguments, *, case_id, actor, correlation):
    if name not in ALLOWED or arguments.get('case_id') != case_id:
        raise ValueError('Tool capability denied')
    # Credentials and network proxy variables are not required by this DB-only server.
    env = {k: v for k, v in os.environ.items() if k in {
        'PATH', 'PYTHONPATH', 'DATABASE_URL', 'APP_MODE', 'SYSTEMROOT',
        'ONTOLOGY_MODE', 'ONTOLOGY_SNAPSHOT_PATH', 'ONTOLOGY_SNAPSHOT_SHA256', 'ONTOLOGY_REQUIRED'}}
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    env.update(MCP_ACTOR=actor, MCP_CASE_ID=case_id, MCP_CORRELATION_ID=correlation)
    current = capability.get()
    if current:
        env.update(MCP_JOB_ID=str(current['id']), MCP_JOB_ATTEMPT=str(current['attempts']))
    params = StdioServerParameters(command=sys.executable, args=['-m', 'caseflow.mcp_server'], env=env)
    with trace.get_tracer('caseflow.mcp').start_as_current_span('mcp.' + name):
        async with asyncio.timeout(25):
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError('MCP tool failed; consult the safe case timeline')
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(next(x.text for x in result.content if x.type == 'text'))
