#!/usr/bin/env python3
"""Bootstrap and run an isolated, loopback-only OpenCareer browser installation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import venv
import webbrowser
from pathlib import Path
from urllib.request import build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parent


def local_environment(data: Path, port: int, backend_port: int) -> dict[str, str]:
    """Do not inherit a maintainer's hosted identities, databases, keys or build flags."""
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith(("OPENCAR_", "CAREER_", "COWORKER_", "VITE_", "TAURI_", "AIDEN_", "AWS_",
                               "OPENAI_", "ANTHROPIC_", "GOOGLE_", "GEMINI_", "AZURE_",
                               "DEEPSEEK_", "OPENROUTER_", "OLLAMA_", "MISTRAL_", "COHERE_"))
        and not key.endswith(("_API_KEY", "_TOKEN"))
        and key not in {"DATABASE_URL", "REDIS_URL", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
    }
    env.update({
        "COWORKER_STATE_DIR": str(data / "state"),
        "CAREER_DATA_DIR": str(data / "career"),
        "CAREER_PRIVATE_DIR": str(data / "private"),
        "OPENCAR_ALPHA_WORKSPACE": str(data / "workspace"),
        "OPENCAR_ALPHA_TEST": "1", "OPENCAR_HEADLESS": "1",
        "OPENCAR_EXTRA_ORIGINS": f"http://127.0.0.1:{port}",
        "COWORKER_EXIT_WITH_PARENT": "1", "COWORKER_PARENT_PID": str(os.getpid()),
        "VITE_ALPHA_UI_PORT": str(port), "VITE_ALPHA_BACKEND_PORT": str(backend_port),
        "PYTHONUNBUFFERED": "1", "PYTHONNOUSERSITE": "1",
    })
    return env


def install_dependencies(env: dict[str, str]) -> Path:
    python = ROOT / ".venv-local" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    marker = ROOT / ".venv-local" / ".opencareer-dependencies"
    fingerprint = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    if not python.exists():
        print("首次启动：创建独立 Python 环境…", flush=True)
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv-local")
    if not marker.exists() or marker.read_text() != fingerprint:
        subprocess.run([str(python), "-m", "pip", "install", "-e", str(ROOT)], env=env, check=True)
        marker.write_text(fingerprint)
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("请先安装 Node.js 22 LTS（包含 npm），然后重新运行。")
    gui = ROOT / "surfaces" / "gui"
    node_marker = gui / "node_modules" / ".opencareer-lock"
    node_fingerprint = hashlib.sha256((gui / "package-lock.json").read_bytes()).hexdigest()
    if not node_marker.exists() or node_marker.read_text() != node_fingerprint:
        print("首次启动或依赖更新：安装前端依赖…", flush=True)
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=gui, env=env, check=True)
        node_marker.write_text(node_fingerprint)
    return python


def prepare_workspace(data: Path, python: Path) -> None:
    marker = data / ".opencareer-local"
    if data.exists() and any(data.iterdir()) and not marker.is_file():
        raise RuntimeError("数据目录不是本启动器创建的目录。请选一个空目录；不会覆盖已有文件。")
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker.touch(mode=0o600, exist_ok=True)
    for name in ("state", "career", "private", "workspace"):
        (data / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    managed = data / "workspace" / ".coworker"
    managed.mkdir(exist_ok=True, mode=0o700)
    config = {"mcpServers": {"career": {"command": str(python), "args": ["-m", "extensions.career_mcp.server"], "enabled": True}}}
    config_path = managed / "mcp.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise RuntimeError("本地专用工作区的 MCP 配置已被修改。请备份并使用新的 --data-dir；不会覆盖已有配置。")
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    for skill in (ROOT / ".coworker" / "skills").iterdir():
        if (skill / "SKILL.md").is_file():
            shutil.copytree(skill, managed / "skills" / skill.name, dirs_exist_ok=True)


def wait_ready(url: str, processes: list[subprocess.Popen], timeout: int = 40) -> None:
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError("本地服务提前退出，请检查上方错误信息。")
        try:
            with opener.open(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("本地服务启动超时。数据已保留，请检查错误后重试。")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def run_local(args: argparse.Namespace) -> int:
    if sys.version_info < (3, 11):
        raise RuntimeError("请使用 Python 3.11 或更新版本；推荐 Python 3.12。")
    node = shutil.which("node")
    if not node:
        raise RuntimeError("请先安装 Node.js 22 LTS，然后重新运行。")
    data = args.data_dir.expanduser().resolve()
    env = local_environment(data, args.port, args.backend_port)
    python = Path(sys.executable) if args.skip_install else install_dependencies(env)
    prepare_workspace(data, python)
    gui = ROOT / "surfaces" / "gui"
    vite = gui / "node_modules" / "vite" / "bin" / "vite.js"
    dist = data / "web"
    # Build output is per installation, never deploy/web or the production alpha bundle.
    subprocess.run([node, str(vite), "build", "--mode", "standalone", "--outDir", str(dist), "--emptyOutDir"], cwd=gui, env=env, check=True)
    processes: list[subprocess.Popen] = []
    try:
        processes.append(subprocess.Popen(
            [str(python), "-m", "coworker.server.run", "--cwd", str(data / "workspace"),
             "--host", "127.0.0.1", "--port", str(args.backend_port), "--model", "deepseek:deepseek-v4-flash"],
            cwd=ROOT, env=env, start_new_session=os.name == "posix",
        ))
        wait_ready(f"http://127.0.0.1:{args.backend_port}/v1/health", processes)
        processes.append(subprocess.Popen(
            [node, str(vite), "preview", "--mode", "standalone", "--host", "127.0.0.1",
             "--port", str(args.port), "--strictPort", "--outDir", str(dist)],
            cwd=gui, env=env, start_new_session=os.name == "posix",
        ))
        url = f"http://127.0.0.1:{args.port}"
        wait_ready(url, processes)
        print(f"\nOpenCareer 本地版已启动：{url}\n数据目录：{data}\n仅本机可访问。请在页面配置你自己的模型；Ctrl+C 停止，数据会保留。", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        raise RuntimeError("本地服务意外退出，已停止本次启动的其他进程。")
    finally:
        for process in reversed(processes):
            stop_process(process)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".local-state" / "local-user")
    parser.add_argument("--port", type=int, default=1422, help="Local browser port")
    parser.add_argument("--backend-port", type=int, default=8767)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--skip-install", action="store_true", help="Use the current Python and installed Node dependencies (development/CI only)")
    args = parser.parse_args()
    if args.port == args.backend_port or not all(1024 <= p <= 65535 for p in (args.port, args.backend_port)):
        parser.error("Choose two different ports between 1024 and 65535")
    for port in (args.port, args.backend_port):
        with socket.socket() as sock:
            if os.name == "posix":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                print(f"Port {port} is already in use. Choose another port; no process was stopped.", file=sys.stderr)
                return 1
    try:
        return run_local(args)
    except KeyboardInterrupt:
        print("\n本地服务已停止，数据已保留。", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"启动失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    def interrupted(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(main())
