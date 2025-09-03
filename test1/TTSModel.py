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
        """清理输入文本 - 不再限制长度，支持完整文本"""
        if not isinstance(text, str):
            try:
                text = str(text)
            except:
                return "文本转换失败"

        # 移除控制字符，保留标点
        cleaned = ''.join([c for c in text if c.isprintable() or c in '\n\t,.!?;，。！？；'])

        return cleaned

    def run(self):
        """执行TTS合成 - 支持长文本分块合成"""
        try:
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return

            # 检查文本
            if not self.text.strip():
                self.finished.emit("错误：空文本无法转换语音", self.original_text)
                return

            # 如果文本较短，直接合成
            MAX_CHUNK_SIZE = 280  # 稍小于API限制，为标点符号留空间
            if len(self.text) <= MAX_CHUNK_SIZE:
                result = self._synthesize_with_retry()
                if result and os.path.exists(result) and os.path.getsize(result) > 0:
                    self.finished.emit(result, self.original_text)
                else:
                    self.finished.emit("TTS合成失败或音频文件为空", self.original_text)
                return

            # 长文本分块合成
            self._debug(f"长文本分块合成 - 文本长度: {len(self.text)} 字符")
            result = self._synthesize_chunked()
            
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

    def _synthesize_chunked(self):
        """分块合成长文本"""
        MAX_CHUNK_SIZE = 280
        chunks = self._split_text_into_chunks(self.text, MAX_CHUNK_SIZE)
        self._debug(f"文本分为 {len(chunks)} 块")
        
        audio_chunks = []
        for i, chunk in enumerate(chunks):
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return None
                    
            self._debug(f"合成第 {i+1}/{len(chunks)} 块")
            
            # 临时保存当前文本，替换为块文本
            original_text = self.text
            self.text = chunk
            
            try:
                chunk_audio = self._synthesize_with_retry()
                if chunk_audio and os.path.exists(chunk_audio):
                    # 读取音频数据
                    with open(chunk_audio, 'rb') as f:
                        audio_chunks.append(f.read())
                    self._debug(f"第 {i+1} 块合成完成，大小: {len(audio_chunks[-1])} bytes")
                else:
                    self._debug(f"第 {i+1} 块合成失败")
                    return None
            finally:
                # 恢复原始文本
                self.text = original_text
        
        # 合并音频块
        if audio_chunks:
            combined_audio = b''.join(audio_chunks)
            temp_path = f"{self.output_path}.tmp"
            with open(temp_path, 'wb') as f:
                f.write(combined_audio)
            
            # 原子性替换
            if os.path.exists(self.output_path):
                os.remove(self.output_path)
            os.rename(temp_path, self.output_path)
            
            self._debug(f"合并完成，总大小: {len(combined_audio)} bytes")
            return self.output_path
        
        return None

    def _split_text_into_chunks(self, text, max_size):
        """智能分割文本为合适的块"""
        if len(text) <= max_size:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # 按句子分割（优先级：。！？；.!?;）
        sentences = []
        current_sentence = ""
        
        for char in text:
            current_sentence += char
            if char in '。！？；.!?;':
                sentences.append(current_sentence)
                current_sentence = ""
        
        # 处理最后一个句子（如果没有结束符）
        if current_sentence:
            sentences.append(current_sentence)
        
        for sentence in sentences:
            # 如果单个句子就超过最大长度，需要强制分割
            if len(sentence) > max_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # 强制按字符分割超长句子
                while len(sentence) > max_size:
                    chunks.append(sentence[:max_size])
                    sentence = sentence[max_size:]
                
                if sentence:
                    current_chunk = sentence
            
            # 检查是否能添加到当前块
            elif len(current_chunk) + len(sentence) <= max_size:
                current_chunk += sentence
            else:
                # 当前块已满，开始新块
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        # 添加最后一块
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks

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