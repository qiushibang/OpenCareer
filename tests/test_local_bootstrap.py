"""Opt-in fresh-source installation; downloads dependencies, never uses model keys."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest

from test_local_installation import ROOT, free_port, request, running


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_LOCAL_BOOTSTRAP") != "1",
                    reason="opt-in fresh dependency installation")
@pytest.mark.parametrize("interrupted_setup", [False, True])
def test_new_user_can_install_and_retry_through_a_python_symlink(tmp_path, interrupted_setup):
    source = tmp_path / "source"
    # Only versioned source, never the maintainer's environments, state or credentials.
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    for name in filter(None, files):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    interpreter = tmp_path / ("python.exe" if os.name == "nt" else "python")
    if os.name == "nt":
        pytest.skip("symlinked interpreter regression is for macOS/Linux")
    interpreter.symlink_to(Path(sys.executable).resolve())
    if interrupted_setup:
        # A first run interrupted before ensurepip leaves Python present but no pip.
        subprocess.run([str(interpreter), "-m", "venv", "--without-pip",
                        str(source / ".venv-local")], check=True)
    port, backend_port = free_port(), free_port()
    with running(tmp_path, port, backend_port, root=source, install=True, python=str(interpreter)):
        assert request(f"http://127.0.0.1:{port}")[0] == 200
        assert (source / ".venv-local" / ".opencareer-dependencies").is_file()
