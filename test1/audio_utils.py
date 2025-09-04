"""音频工具模块，提供音频播放的辅助功能"""
import os
import sys
from contextlib import contextmanager


@contextmanager
def suppress_stderr_fd():
    """
    上下文管理器，用于临时将 stderr 重定向到 /dev/null，
    抑制 ALSA/JACK 等音频库的错误消息输出。
    """
    # 保存原始的 stderr 文件描述符
    original_stderr_fd = os.dup(sys.stderr.fileno())
    
    try:
        # 打开 /dev/null
        with open(os.devnull, 'w') as devnull:
            # 将 stderr 重定向到 /dev/null
            os.dup2(devnull.fileno(), sys.stderr.fileno())
        
        yield
        
    finally:
        # 恢复原始的 stderr
        os.dup2(original_stderr_fd, sys.stderr.fileno())
        os.close(original_stderr_fd)