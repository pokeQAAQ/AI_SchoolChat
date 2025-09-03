"""录音线程，负责捕获音频并生成有效WAV文件"""
import os
import time
import signal
import shutil
import subprocess
import threading
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

class RecordThread(QThread):
    """录音线程，避免阻塞主线程"""
    update_text = Signal(str)          # 录音状态更新信号
    recording_finished = Signal(str)   # 录音完成信号（返回文件信息）

    def __init__(self, device_index=None):
        super().__init__()
        self.device_index = device_index
        self.device = None  # arecord 的 -D 设备名，可选
        self.recording = False
        self._proc = None  # arecord 子进程句柄
        self.mutex = QMutex()
        self._stop_requested = False

        # 录音参数（严格匹配火山引擎ASR要求）
        self.CHUNK = 1024  # 保持兼容性，实际不用于arecord
        self.CHANNELS = 1
        self.RATE = 16000
        self.sample_fmt = "S16_LE"  # 16-bit
        self.out_path = "recording.wav"

        # 防止重复初始化
        self._initialized = False

    def run(self):
        """核心录音逻辑 - 使用arecord"""
        try:
            # 使用互斥锁保护状态
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return

            # 检查arecord命令是否可用
            if not self._has_arecord():
                self.update_text.emit("❌ 系统没有arecord命令")
                self.recording_finished.emit("❌ 录音失败：系统没有arecord命令")
                return

            # 先删除旧文件
            try:
                if os.path.exists(self.out_path):
                    os.remove(self.out_path)
            except:
                pass

            # 构建arecord命令
            cmd = [
                "arecord",
                "-q",                    # 静默
                "-t", "wav",             # 输出 wav
                "-f", self.sample_fmt,   # S16_LE
                "-r", str(self.RATE),    # 16000 Hz
                "-c", str(self.CHANNELS) # 单声道
            ]
            
            if self.device:
                cmd += ["-D", self.device]
            cmd += [self.out_path]

            self.recording = True
            self.update_text.emit("🎙️ 开始录音...（请对着麦克风说话）")

            # 启动arecord进程
            with QMutexLocker(self.mutex):
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # 等待录音进程运行或停止请求
            while self.recording:
                with QMutexLocker(self.mutex):
                    if self._stop_requested:
                        break
                
                # 检查进程是否意外退出
                if self._proc and self._proc.poll() is not None:
                    break
                    
                time.sleep(0.1)

        except Exception as e:
            self.update_text.emit(f"❌ 录音设备错误：{str(e)}")
            self.recording_finished.emit(f"❌ 录音失败：{str(e)}")
        finally:
            # 确保资源释放
            self._cleanup_resources()

            # 检查录音文件
            self._check_recording_result()

    def _has_arecord(self):
        """检查系统是否有arecord命令"""
        return shutil.which("arecord") is not None

    def _cleanup_resources(self):
        """安全清理录音资源"""
        try:
            if self._proc and self._proc.poll() is None:
                # 优先发 SIGINT 让 arecord 写好 WAV 头
                self._proc.send_signal(signal.SIGINT)
                for _ in range(40):  # 最多等 2 秒
                    if self._proc.poll() is not None:
                        break
                    time.sleep(0.05)
                
                # 兜底：如果还没退出就强制终止
                if self._proc.poll() is None:
                    try:
                        self._proc.terminate()
                        self._proc.wait(timeout=1)
                    except:
                        try:
                            self._proc.kill()
                        except:
                            pass
        except:
            pass

    def _check_recording_result(self):
        """检查录音结果并发送信号"""
        try:
            if os.path.exists(self.out_path):
                file_size = os.path.getsize(self.out_path)
                if file_size >= 1024:  # 至少1KB视为有效录音
                    self.recording_finished.emit(f"✅ 录音已保存（文件：{self.out_path}，大小：{file_size}字节）")
                else:
                    # 删除无效文件
                    os.remove(self.out_path)
                    self.recording_finished.emit(f"❌ 录音无效：文件太小（{file_size}字节）")
            else:
                self.recording_finished.emit("❌ 录音失败：未生成录音文件")
        except Exception as e:
            self.recording_finished.emit(f"❌ 录音检查失败：{str(e)}")

    def stop(self):
        """停止录音"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True
            self.recording = False
        # arecord 进程的停止在 _cleanup_resources 内通过 SIGINT/terminate 实现