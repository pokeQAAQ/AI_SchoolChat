"""音频播放线程"""
import time
import wave
import os
import sys
from contextlib import contextmanager
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker


@contextmanager
def suppress_stderr_fd():
    """Context manager to temporarily redirect stderr to /dev/null to suppress ALSA/JACK initialization messages"""
    try:
        fd = sys.stderr.fileno()
    except Exception:
        # If sys.stderr has no fileno (e.g. some GUIs), just run without suppression
        yield
        return
    with open(os.devnull, 'w') as devnull:
        old = os.dup(fd)
        try:
            os.dup2(devnull.fileno(), fd)
            yield
        finally:
            os.dup2(old, fd)
            os.close(old)


class AudioPlayThread(QThread):
    """音频播放线程（支持WAV和PCM）"""
    finished_signal = Signal()
    stopped_signal = Signal()

    def __init__(self, audio_path, sample_rate=16000, channels=1, bit_depth=16):
        super().__init__()
        self.audio_path = audio_path
        self.sample_rate = sample_rate
        self.channels = channels
        self.bit_depth = bit_depth
        self._is_running = True
        self._p = None
        self._stream = None
        self._wf = None
        self._buffer_size = 512  # 优化缓冲区大小
        self.mutex = QMutex()
        self._stop_requested = False

    def run(self):
        """播放音频主函数"""
        try:
            # 检查文件
            if not self.audio_path or not os.path.exists(self.audio_path):
                raise FileNotFoundError(f"音频文件不存在: {self.audio_path}")

            # 判断文件类型
            if self.audio_path.endswith('.wav'):
                self._play_wav()
            elif self.audio_path.endswith('.pcm') or self.audio_path.endswith('.raw'):
                self._play_pcm()
            else:
                raise ValueError(f"不支持的音频格式: {self.audio_path}")

        except Exception as e:
            print(f"音频播放错误: {str(e)}")
        finally:
            self._cleanup()

            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    self.stopped_signal.emit()
                else:
                    self.finished_signal.emit()

    def _play_wav(self):
        """播放WAV文件"""
        self._wf = wave.open(self.audio_path, 'rb')
        
        # Lazy import and suppress stderr during PyAudio initialization
        with suppress_stderr_fd():
            import pyaudio
            self._p = pyaudio.PyAudio()

        # 获取设备信息
        device_info = self._get_device_info()

        # 打开音频流 - also suppress stderr during stream opening
        with suppress_stderr_fd():
            self._stream = self._p.open(
                format=self._p.get_format_from_width(self._wf.getsampwidth()),
                channels=self._wf.getnchannels(),
                rate=self._wf.getframerate(),
                output=True,
                output_device_index=device_info["index"],
                frames_per_buffer=self._buffer_size
            )

        # 播放数据
        data = self._wf.readframes(self._buffer_size)
        while data:
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    break

            try:
                self._stream.write(data)
            except Exception as e:
                if "stream stopped" not in str(e).lower():
                    print(f"播放写入错误: {str(e)}")
                break

            data = self._wf.readframes(self._buffer_size)

    def _play_pcm(self):
        """播放PCM文件"""
        with open(self.audio_path, 'rb') as f:
            # Lazy import and suppress stderr during PyAudio initialization
            with suppress_stderr_fd():
                import pyaudio
                self._p = pyaudio.PyAudio()

            # PCM格式映射
            format = pyaudio.paInt16 if self.bit_depth == 16 else pyaudio.paInt32

            # 获取设备信息
            device_info = self._get_device_info()

            # 打开音频流 - also suppress stderr during stream opening
            with suppress_stderr_fd():
                self._stream = self._p.open(
                    format=format,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    output_device_index=device_info["index"],
                    frames_per_buffer=self._buffer_size
                )

            # 播放数据
            chunk_size = self._buffer_size * self.channels * (self.bit_depth // 8)
            data = f.read(chunk_size)

            while data:
                with QMutexLocker(self.mutex):
                    if self._stop_requested:
                        break

                try:
                    self._stream.write(data)
                except Exception as e:
                    if "stream stopped" not in str(e).lower():
                        print(f"PCM播放错误: {str(e)}")
                    break

                data = f.read(chunk_size)

    def _get_device_info(self):
        """获取默认输出设备信息"""
        try:
            default_device = self._p.get_default_output_device_info()
            print(f"使用输出设备: {default_device['name']}")
            return default_device
        except Exception as e:
            print(f"获取设备信息失败: {str(e)}")
            # 返回默认设备索引
            return {"index": None}

    def stop(self):
        """停止播放"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True
            self._is_running = False

        # 等待线程结束
        if self.isRunning():
            self.wait(500)

    def _cleanup(self):
        """清理资源"""
        try:
            if self._stream:
                if self._stream.is_active():
                    self._stream.stop_stream()
                self._stream.close()
                self._stream = None
        except:
            pass

        try:
            if self._wf:
                self._wf.close()
                self._wf = None
        except:
            pass

        try:
            if self._p:
                time.sleep(0.05)  # 短暂延迟
                self._p.terminate()
                self._p = None
        except:
            pass