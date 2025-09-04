# -*- coding: utf-8 -*-
import os
import sys
import time
import socket
import signal
import atexit
import subprocess
from pathlib import Path
from typing import Optional, Tuple

_DEFAULT_HOST = "0.0.0.0"
_DEFAULT_PORT = int(os.environ.get("UPLOAD_SERVER_PORT", "8080"))

_proc: Optional[subprocess.Popen] = None
_started: bool = False
_server_url: str = ""

def _script_path() -> Path:
    # 与本文件同目录的 upload_server.py
    return Path(__file__).with_name("upload_server.py")

def _is_port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except Exception:
        return False

def _wait_for_port(host: str, port: int, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_port_open(host, port):
            return True
        time.sleep(0.2)
    return False

def ensure_upload_server_running(host: str = _DEFAULT_HOST,
                                 port: int = _DEFAULT_PORT,
                                 project_root: Optional[Path] = None) -> Tuple[Optional[subprocess.Popen], str]:
    """
    确保上传服务在运行。
    - 若端口已被占用，视为已有实例在运行，不再拉起，只返回 URL。
    - 若未运行，则启动 test1/upload_server.py 并返回 Popen 句柄与 URL。
    """
    global _proc, _started, _server_url

    script = _script_path()
    if not script.exists():
        print(f"⚠️ 未找到上传服务脚本: {script}")
        return None, ""

    # 访问 URL 使用本机 IP（供二维码/日志显示）
    display_host = _detect_ip_for_display() or "127.0.0.1"
    _server_url = f"http://{display_host}:{port}"

    # 如果端口已开放，直接返回
    if _is_port_open("127.0.0.1", port):
        print(f"📎 上传服务已在运行: {_server_url}")
        return None, _server_url

    # 启动子进程（工作目录设为脚本目录，保证静态/模板路径可用）
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd = [sys.executable, "-u", str(script)]

    cwd = str(script.parent)
    creationflags = 0
    preexec_fn = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # noqa: attr-defined
    else:
        preexec_fn = os.setsid  # 将子进程置于新会话，便于回收

    try:
        _proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
        )
        _started = True

        # 稍等端口开放
        if _wait_for_port("127.0.0.1", port, timeout=10.0):
            print(f"🚀 已启动上传服务: {_server_url}")
        else:
            print("⚠️ 上传服务启动超时（端口未开放），请检查 upload_server.py 日志。")

        # 进程退出自动清理
        atexit.register(stop_upload_server)
        return _proc, _server_url
    except Exception as e:
        print(f"❌ 启动上传服务失败: {e}")
        _proc = None
        _started = False
        return None, _server_url

def stop_upload_server():
    """在应用退出时尝试停止我们自己拉起的上传服务。"""
    global _proc, _started
    if not _started or not _proc:
        return
    try:
        if _proc.poll() is None:
            if os.name == "nt":
                _proc.send_signal(signal.CTRL_BREAK_EVENT)  # 优先温和结束
                time.sleep(0.5)
                _proc.terminate()
            else:
                try:
                    os.killpg(os.getpgid(_proc.pid), signal.SIGTERM)
                except Exception:
                    _proc.terminate()
            _proc.wait(timeout=3)
    except Exception:
        try:
            _proc.kill()
        except Exception:
            pass
    finally:
        _proc = None
        _started = False

def _detect_ip_for_display() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return None
