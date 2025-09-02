"""录音线程，负责捕获音频并生成有效WAV文件"""
import wave
import pyaudio
import os
import time
import threading
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker

class RecordThread(QThread):
    """录音线程，避免阻塞主线程"""
    update_text = Signal(str)          # 录音状态更新信号
    recording_finished = Signal(str)   # 录音完成信号（返回文件信息）

    def __init__(self, device_index=None):
        super().__init__()
        self.device_index = device_index
        self.recording = False
        self.audio = None
        self.stream = None
        self.mutex = QMutex()
        self._stop_requested = False

        # 录音参数（严格匹配火山引擎ASR要求）
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 16000

        # 防止重复初始化
        self._initialized = False

    def run(self):
        """核心录音逻辑"""
        frames = []

        try:
            # 使用互斥锁保护状态
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return

            # 初始化音频
            self.audio = pyaudio.PyAudio()

            # 打开音频流（增加异常重试机制）
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.stream = self.audio.open(
                        format=self.FORMAT,
                        channels=self.CHANNELS,
                        rate=self.RATE,
                        input=True,
                        frames_per_buffer=self.CHUNK,
                        input_device_index=self.device_index
                    )
                    break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(0.1)

            self.recording = True
            self.update_text.emit("🎙️ 开始录音...（请对着麦克风说话）")

            # 录音主循环
            while self.recording:
                with QMutexLocker(self.mutex):
                    if self._stop_requested:
                        break

                try:
                    # 使用非阻塞读取，避免卡死
                    data = self.stream.read(self.CHUNK, exception_on_overflow=False)
                    frames.append(data)
                except Exception as e:
                    # 忽略溢出错误，继续录音
                    if "overflow" not in str(e).lower():
                        self.update_text.emit(f"⚠️ 录音警告：{str(e)}")

        except Exception as e:
            self.update_text.emit(f"❌ 录音设备错误：{str(e)}")
        finally:
            # 确保资源释放
            self._cleanup_resources()

            # 保存录音文件
            if frames:
                self._save_recording(frames)
            else:
                self.recording_finished.emit("❌ 录音失败：未捕获到音频数据")

    def _cleanup_resources(self):
        """安全清理音频资源"""
        try:
            if self.stream:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
                self.stream = None
        except:
            pass

        try:
            if self.audio:
                self.audio.terminate()
                self.audio = None
        except:
            pass

    def _save_recording(self, frames):
        """保存录音文件并校验有效性"""
        try:
            file_path = "recording.wav"

            # 使用临时文件避免写入冲突
            temp_path = f"{file_path}.tmp"

            with wave.open(temp_path, "wb") as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(2)  # 16位音频 = 2字节
                wf.setframerate(self.RATE)
                wf.writeframes(b''.join(frames))

            # 校验文件有效性
            file_size = os.path.getsize(temp_path)
            if file_size < 1024:  # 小于1KB视为无效录音
                os.remove(temp_path)
                self.recording_finished.emit(f"❌ 录音无效：文件太小（{file_size}字节）")
            else:
                # 原子性替换文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rename(temp_path, file_path)
                self.recording_finished.emit(f"✅ 录音已保存（文件：{file_path}，大小：{file_size}字节）")

        except Exception as e:
            self.recording_finished.emit(f"❌ 录音保存失败：{str(e)}")

    def stop(self):
        """停止录音"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True
            self.recording = False
        # arecord 的停止在 _record_with_arecord 内通过 SIGINT/terminate 实现