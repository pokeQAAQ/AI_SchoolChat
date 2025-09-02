"""TTS语音合成线程"""
import requests
import json
import base64
import uuid
import os
import time
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker


class TTSModel(QThread):
    finished = Signal(str, str)  # 输出音频文件路径和原始文本

    def __init__(self, text):
        super().__init__()
        self.original_text = text
        self.text = self._clean_text(text)
        self.output_path = "ai_reply.pcm"
        self.mutex = QMutex()
        self._stop_requested = False

        # 确保输出目录存在
        output_dir = os.path.dirname(self.output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # 火山引擎配置
        self.app_id = "6505759856"
        self.access_token = "eLnTRrJoZpztOD_hP4AO4m4mJaD0eQH2"
        self.cluster = "volcano_tts"
        self.voice_type = "BV700_streaming"
        self.host = "openspeech.bytedance.com"
        self.api_url = f"https://{self.host}/api/v1/tts"

        # 重试配置
        self.max_retries = 3
        self.retry_delay = 1.0

        self._debug(f"初始化TTSModel - 文本长度: {len(self.text)} 字符")

    def _debug(self, msg):
        """安全打印调试信息"""
        try:
            print(f"[TTS] {msg}")
        except UnicodeEncodeError:
            print(f"[TTS] {msg.encode('utf-8', errors='replace').decode('utf-8')}")

    def _clean_text(self, text):
        """清理输入文本"""
        if not isinstance(text, str):
            try:
                text = str(text)
            except:
                return "文本转换失败"

        # 移除控制字符，保留标点
        cleaned = ''.join([c for c in text if c.isprintable() or c in '\n\t,.!?;，。！？；'])

        # 限制长度
        MAX_TTS_LENGTH = 300
        if len(cleaned) > MAX_TTS_LENGTH:
            cleaned = cleaned[:MAX_TTS_LENGTH] + "..."

        return cleaned

    def run(self):
        """执行TTS合成"""
        try:
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return

            # 检查文本
            if not self.text.strip():
                self.finished.emit("错误：空文本无法转换语音", self.original_text)
                return

            # 合成音频（带重试）
            result = self._synthesize_with_retry()

            if result and os.path.exists(result) and os.path.getsize(result) > 0:
                self.finished.emit(result, self.original_text)
            else:
                self.finished.emit("TTS合成失败或音频文件为空", self.original_text)

        except Exception as e:
            safe_msg = str(e).encode('utf-8', errors='replace').decode('utf-8')
            self.finished.emit(f"TTS错误：{safe_msg}", self.original_text)

    def _synthesize_with_retry(self):
        """带重试机制的音频合成"""
        for attempt in range(self.max_retries):
            try:
                with QMutexLocker(self.mutex):
                    if self._stop_requested:
                        return None

                result = self._synthesize_audio()
                if result:
                    return result

            except Exception as e:
                self._debug(f"合成尝试 {attempt + 1} 失败: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        return None

    def _synthesize_audio(self):
        """使用火山引擎HTTP接口合成音频"""
        header = {
            "Authorization": f"Bearer;{self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        request_json = {
            "app": {
                "appid": self.app_id,
                "token": self.access_token,
                "cluster": self.cluster
            },
            "user": {
                "uid": "388808087185088"
            },
            "audio": {
                "rate": 16000,
                "voice_type": self.voice_type,
                "encoding": "pcm",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": self.text,
                "text_type": "plain",
                "operation": "query"
            }
        }

        try:
            self._debug(f"开始TTS合成")

            response = requests.post(
                self.api_url,
                data=json.dumps(request_json, ensure_ascii=False).encode('utf-8'),
                headers=header,
                timeout=30
            )

            result = response.json()
            self._debug(f"响应状态码: {response.status_code}")

            if response.status_code == 200 and "data" in result:
                data = result["data"]

                try:
                    # 解码音频数据
                    audio_data = base64.b64decode(data)

                    # 使用临时文件避免写入冲突
                    temp_path = f"{self.output_path}.tmp"
                    with open(temp_path, "wb") as f:
                        f.write(audio_data)

                    # 原子性替换
                    if os.path.exists(self.output_path):
                        os.remove(self.output_path)
                    os.rename(temp_path, self.output_path)

                    self._debug(f"音频合成完成，大小: {os.path.getsize(self.output_path)} bytes")
                    return self.output_path

                except Exception as e:
                    self._debug(f"音频处理失败: {str(e)}")
                    return None
            else:
                err_msg = result.get('message', '未知错误')
                self._debug(f"合成失败: {err_msg}")
                return None

        except requests.exceptions.Timeout:
            self._debug("请求超时")
            return None
        except Exception as e:
            self._debug(f"合成异常: {str(e)}")
            return None

    def stop(self):
        """停止线程"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True