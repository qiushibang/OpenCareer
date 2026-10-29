import os
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_standalone_mcp_is_read_only_and_has_no_resume_or_shell_tools(tmp_path):
    env = {**os.environ, "DATABASE_URL": "postgresql://invalid.invalid/not-used", "COWORKER_STATE_DIR": str(tmp_path / "state")}
    params = StdioServerParameters(command=sys.executable, args=["-m", "extensions.career_mcp.jobs_mcp", "--data-dir", str(tmp_path / "career")], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            manifest = await client.list_tools()
            assert {t.name for t in manifest.tools} == {"get_job_catalog_schema", "search_job_catalog", "get_job_catalog_status", "get_job"}
            response = await client.call_tool("search_job_catalog", {"condition": {"all": []}})
            assert not response.isError
            assert '"total": 0' in str(response.content)
