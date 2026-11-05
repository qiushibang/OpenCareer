"""Local Career extensions. Public deployments keep the original default-deny policy.

Only registered connector tools and scoped document tools are added. No command,
package-install, generic MCP configuration or file-deletion surface is exposed.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

FILE_TOOLS = frozenset({'list_files','read_file','read_file_lines','search_files','write_file','apply_unified_diff','apply_patch','replace_in_file'})
WEB_TOOLS = frozenset({'web_search','web_fetch'})
HOST_EXEC_TOOLS = frozenset({'github_clone','github_pull'})
LOCAL_ROUTES = (
    ('GET',r'/v1/connectors'),
    ('GET',r'/v1/connectors/[A-Za-z0-9_-]+/status'),
    ('GET',r'/v1/connectors/[A-Za-z0-9_-]+/(workspaces|accounts|installations|portals)/[A-Za-z0-9_-]+/(directory|channels)'),
    ('POST',r'/v1/connectors/[A-Za-z0-9_-]+/(workspaces|accounts|installations|portals)/[A-Za-z0-9_-]+/(disconnect|default)'),
    ('PATCH',r'/v1/connectors/[A-Za-z0-9_-]+/(filters|hidden-fields)'),
    ('POST',r'/v1/connectors/[A-Za-z0-9_-]+/(connect|disconnect|mcp-connect)'),
    ('PATCH',r'/v1/connectors/[A-Za-z0-9_-]+/tools'),
    ('GET',r'/v1/cloud/status'),
    ('GET',r'/mcp/oauth/callback'),
    ('GET',r'/v1/browser/state'),('POST',r'/v1/browser/(screenshot|close)'),
    ('GET',r'/v1/sessions/[A-Za-z0-9_-]+/roots'),
    ('GET',r'/v1/sessions/[A-Za-z0-9_-]+/artifacts(/read)?'),
    ('POST',r'/v1/sessions/[A-Za-z0-9_-]+/(roots|connections)'),
    ('DELETE',r'/v1/sessions/[A-Za-z0-9_-]+/roots'),
    ('POST',r'/v1/workspaces/pick'),
)


def enabled() -> bool:
    return all(os.environ.get(key)=='1' for key in ('OPENCAR_ALPHA_TEST','OPENCAR_LOCAL_MODE','OPENCAR_LOCAL_ACCESS'))


def permits_http(method:str,path:str) -> bool:
    return enabled() and any((method.upper()==verb or method.upper()=='OPTIONS') and re.fullmatch(pattern+'/?',path) for verb,pattern in LOCAL_ROUTES)


def protected_folder(path:Path) -> bool:
    """Do not let a model rewrite its executable/configuration through a folder grant."""
    from ..secrets import state_dir
    from . import alpha
    protected=[Path(__file__).resolve().parents[2],state_dir()]
    protected.extend(Path(value) for value in (alpha.workspace(),os.environ.get('CAREER_DATA_DIR'),os.environ.get('CAREER_PRIVATE_DIR')) if value)
    candidate=path.expanduser().resolve()
    return any(candidate.is_relative_to(p.resolve()) or p.resolve().is_relative_to(candidate) for p in protected)


def connector_tool(name:str,metadata:Any) -> bool:
    if name in HOST_EXEC_TOOLS:return False
    if getattr(metadata,'category',None)=='connector':
        return True
    if name.startswith('mcp__'):
        from ..connectors.descriptors import get_descriptor
        from ..connectors.tool_defs import mcp_tool_defs
        parts=name.split('__',2)
        descriptor=get_descriptor(parts[1]) if len(parts)==3 else None
        return bool(descriptor and descriptor.mcp_url and name in {t.name for t in mcp_tool_defs(parts[1])})
    return False


def tool_names(registry:Any,*,browser:bool=True) -> set[str]:
    from . import alpha
    allowed=alpha.conversation_tools() | set(FILE_TOOLS)
    if browser:allowed.update(WEB_TOOLS)
    for name in registry.names():
        spec=registry.get(name)
        if connector_tool(name,spec.metadata):allowed.add(name)
    return allowed


async def refresh(manager:Any,session_id:str) -> None:
    """Reuse existing factories so per-session and per-tool switches stay authoritative."""
    if not enabled():return
    engine=manager._engines.get(session_id)
    if engine is None:return
    from ..agent import _enabled_connector_tools
    from ..connectors.integration_tools import make_integration_tools
    from . import alpha
    effective=manager.effective_connectors(session_id,'career')
    connected,tools=_enabled_connector_tools(manager.secrets)
    engine.registry.retain({n for n in engine.registry.names() if not connector_tool(n,engine.registry.get(n).metadata)})
    engine.registry.register_all(make_integration_tools(manager.secrets,enabled_connectors=connected & effective,enabled_tools=tools,roots=engine.roots))
    engine.registry.register_all(await manager.prepare_mcp_tools(session_id,workspace=alpha.workspace(),agent='career',refresh=True))
    if 'browser' in effective:
        from ..web import make_web_fetch_tool,make_web_search_tool
        engine.registry.register_all([make_web_fetch_tool(),make_web_search_tool(manager.secrets)])
    engine.registry.retain(tool_names(engine.registry,browser='browser' in effective))


async def refresh_all(manager:Any) -> None:
    if enabled():
        for session_id in list(manager._engines):
            await refresh(manager,session_id)
