"""语音识别线程，对接火山引擎流式ASR"""
import os
import json
import gzip
import uuid
import asyncio
import wave
from io import BytesIO
from hashlib import sha256
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import websockets
import time


class AiIOPut(QThread):
    update_signal = Signal(str)  # 日志更新信号（终端输出）
    text_result = Signal(str)  # 语音转文字结果信号
    finished = Signal()  # 处理完成信号

    def __init__(self, api_key, base_url):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.input_audio_path = "recording.wav"
        self.mutex = QMutex()
        self._stop_requested = False

        # 火山引擎ASR配置
        self.appid = "6505759856"
        self.token = "eLnTRrJoZpztOD_hP4AO4m4mJaD0eQH2"
        self.secret = "ClwFYkQ-WwP7y04_sYw-0Fo9ZMWQtGHD"
        self.cluster = "volcengine_streaming_common"
        self.ws_url = "wss://openspeech.bytedance.com/api/v2/asr"

        # WebSocket超时设置
        self.ws_timeout = 30
        self.max_retries = 3

    def run(self):
        """主线程逻辑：检查文件 -> 读取音频 -> 调用ASR"""
        try:
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return

            # 1. 检查录音文件是否有效
            if not self.check_file_valid():
                self.finished.emit()
                return

            # 2. 读取音频文件（增加重试机制）
            audio_data = None
            for attempt in range(3):
                try:
                    with open(self.input_audio_path, "rb") as f:
                        audio_data = f.read()
                    break
                except Exception as e:
                    if attempt == 2:
                        raise e
                    time.sleep(0.1)

            # 3. 校验音频格式
            if not self.validate_audio_format(audio_data):
                self.finished.emit()
                return

            # 4. 调用流式ASR识别
            self.update_signal.emit("🔍 正在识别语音...")
            transcript = self.transcribe_audio(audio_data)

            # 处理识别结果
            if isinstance(transcript, list) and len(transcript) > 0:
                transcript = transcript[0].get("text", "")
            elif isinstance(transcript, dict) and "text" in transcript:
                transcript = transcript["text"]

            # 5. 处理识别结果
            if not transcript:
                self.update_signal.emit("❌ 未识别到有效语音内容")
            else:
                self.text_result.emit(transcript)

        except Exception as e:
            self.update_signal.emit(f"❌ 处理失败：{str(e)}")
        finally:
            self.finished.emit()

    def check_file_valid(self):
        """检查录音文件是否存在且非空"""
        max_wait = 2.0  # 最多等待2秒
        wait_interval = 0.1
        waited = 0

        # 等待文件生成
        while waited < max_wait:
            if os.path.exists(self.input_audio_path):
                break
            time.sleep(wait_interval)
            waited += wait_interval

        if not os.path.exists(self.input_audio_path):
            self.update_signal.emit(f"❌ 录音文件不存在：{self.input_audio_path}")
            return False

        # 等待文件写入完成
        time.sleep(0.1)

        if os.path.getsize(self.input_audio_path) < 1024:
            self.update_signal.emit(f"❌ 录音文件无效（大小不足1KB）")
            return False
        return True

    def validate_audio_format(self, audio_data):
        """校验音频格式是否符合火山引擎ASR要求"""
        try:
            with BytesIO(audio_data) as f:
                wf = wave.open(f, 'rb')
                nchannels = wf.getnchannels()
                framerate = wf.getframerate()
                sampwidth = wf.getsampwidth()
                wf.close()

            # 要求：单声道、16000Hz采样率、16位深
            if nchannels != 1:
                self.update_signal.emit(f"❌ 音频格式错误：需单声道，实际{nchannels}声道")
                return False
            if framerate != 16000:
                self.update_signal.emit(f"❌ 音频格式错误：需16000Hz，实际{framerate}Hz")
                return False
            if sampwidth != 2:
                self.update_signal.emit(f"❌ 音频格式错误：需16位深，实际{sampwidth * 8}位深")
                return False
            return True
        except Exception as e:
            self.update_signal.emit(f"❌ 音频格式解析失败：{str(e)}")
            return False

    def generate_header(self, version=0b0001, message_type=0b0001,
                        message_type_specific_flags=0b0000, serial_method=0b0001,
                        compression_type=0b0001, reserved_data=0x00, extension_header=bytes()):
        """生成协议头"""
        header = bytearray()
        header_size = int(len(extension_header) / 4) + 1
        header.append((version << 4) | header_size)
        header.append((message_type << 4) | message_type_specific_flags)
        header.append((serial_method << 4) | compression_type)
        header.append(reserved_data)
        header.extend(extension_header)
        return header

    def generate_full_default_header(self):
        return self.generate_header()

    def generate_audio_default_header(self):
        return self.generate_header(message_type=0b0010)

    def generate_last_audio_default_header(self):
        return self.generate_header(
            message_type=0b0010,
            message_type_specific_flags=0b0010
        )

    def parse_response(self, res):
        """解析服务器响应数据"""
        try:
            protocol_version = res[0] >> 4
            header_size = res[0] & 0x0f
            message_type = res[1] >> 4
            message_compression = res[2] & 0x0f
            serialization_method = res[2] >> 4
            payload = res[header_size * 4:]
            result = {}
            payload_msg = None
            payload_size = 0

            if message_type == 0b1001:  # 完整响应
                payload_size = int.from_bytes(payload[:4], "big", signed=True)
                payload_msg = payload[4:]
            elif message_type == 0b1011:  # 确认响应
                seq = int.from_bytes(payload[:4], "big", signed=True)
                result['seq'] = seq
                if len(payload) >= 8:
                    payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                    payload_msg = payload[8:]
            elif message_type == 0b1111:  # 错误响应
                code = int.from_bytes(payload[:4], "big", signed=False)
                result['code'] = code
                payload_msg = payload[8:] if len(payload) >= 8 else b""

            if payload_msg:
                if message_compression == 0b0001:  # GZIP解压
                    payload_msg = gzip.decompress(payload_msg)
                if serialization_method == 0b0001:  # JSON解析
                    try:
                        payload_msg = json.loads(payload_msg.decode("utf-8"))
                    except json.JSONDecodeError:
                        payload_msg = payload_msg.decode("utf-8")
                else:
                    payload_msg = payload_msg.decode("utf-8")
                result['payload_msg'] = payload_msg
            return result
        except Exception as e:
            self.update_signal.emit(f"❌ 响应解析失败：{str(e)}")
            return {"error": str(e)}

    def construct_request(self, reqid):
        """构建ASR请求参数"""
        return {
            'app': {
                'appid': self.appid,
                'cluster': self.cluster,
                'token': self.token,
            },
            'user': {'uid': 'streaming_asr_demo'},
            'request': {
                'reqid': reqid,
                'nbest': 1,
                'workflow': 'audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate',
                'show_language': False,
                'show_utterances': False,
                'result_type': 'full',
                "sequence": 1
            },
            'audio': {
                'format': 'wav',
                'rate': 16000,
                'language': 'zh-CN',
                'bits': 16,
                'channel': 1,
                'codec': 'raw'
            }
        }

    def slice_data(self, data: bytes, chunk_size: int):
        """将音频数据分片"""
        data_len = len(data)
        offset = 0
        while offset + chunk_size < data_len:
            yield data[offset: offset + chunk_size], False
            offset += chunk_size
        yield data[offset:], True

    def token_auth(self):
        """生成Token认证头"""
        return {'Authorization': f'Bearer; {self.token}'}

    async def segment_data_processor(self, wav_data: bytes, segment_size: int):
        """处理音频分片"""
        reqid = str(uuid.uuid4())

        try:
            # 检查是否停止
            with QMutexLocker(self.mutex):
                if self._stop_requested:
                    return None

            request_params = self.construct_request(reqid)
            payload_bytes = gzip.compress(json.dumps(request_params).encode())
            full_request = bytearray(self.generate_full_default_header())
            full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
            full_request.extend(payload_bytes)

            header = self.token_auth()

            # 使用超时设置建立连接
            async with websockets.connect(
                    self.ws_url,
                    additional_headers=header,
                    ping_interval=10,
                    ping_timeout=5,
                    close_timeout=10
            ) as ws:
                # 发送初始请求
                await ws.send(full_request)
                res = await asyncio.wait_for(ws.recv(), timeout=self.ws_timeout)
                init_result = self.parse_response(res)

                if 'payload_msg' in init_result:
                    if init_result['payload_msg'].get('code') != 1000:
                        self.update_signal.emit(
                            f"❌ 服务器初始化失败：{init_result['payload_msg'].get('message', '未知错误')}"
                        )
                        return None
                else:
                    self.update_signal.emit("❌ 未收到服务器初始化响应")
                    return None

                # 发送音频分片
                final_result = ""
                for seq, (chunk, is_last) in enumerate(self.slice_data(wav_data, segment_size), 1):
                    # 检查是否停止
                    with QMutexLocker(self.mutex):
                        if self._stop_requested:
                            return None

                    chunk_bytes = gzip.compress(chunk)
                    header = self.generate_last_audio_default_header() if is_last else self.generate_audio_default_header()
                    audio_request = bytearray(header)
                    audio_request.extend(len(chunk_bytes).to_bytes(4, 'big'))
                    audio_request.extend(chunk_bytes)

                    await ws.send(audio_request)
                    res = await asyncio.wait_for(ws.recv(), timeout=self.ws_timeout)
                    segment_result = self.parse_response(res)

                    if 'code' in segment_result and segment_result['code'] != 0:
                        self.update_signal.emit(
                            f"❌ 分片{seq}错误：{segment_result.get('payload_msg', '未知错误')}"
                        )
                        return None

                    if 'payload_msg' in segment_result and 'result' in segment_result['payload_msg']:
                        result_data = segment_result['payload_msg']['result']

                        if isinstance(result_data, list):
                            text_content = result_data[0].get('text', '') if result_data else ''
                            final_result = text_content
                        elif isinstance(result_data, str):
                            final_result = result_data
                        else:
                            final_result = str(result_data)

                        self.update_signal.emit(f"📝 已识别片段{seq}：{final_result[:30]}...")

                return final_result if final_result else None

        except asyncio.TimeoutError:
            self.update_signal.emit("❌ WebSocket连接超时")
        except websockets.exceptions.WebSocketError as e:
            self.update_signal.emit(f"❌ WebSocket错误：{str(e)}")
        except Exception as e:
            self.update_signal.emit(f"❌ 分片处理失败：{str(e)}")
        return None

    async def execute_streaming_asr(self, audio_data: bytes):
        """执行流式ASR识别"""
        nchannels, sampwidth, framerate, _, _ = self.read_wav_info(audio_data)
        size_per_sec = nchannels * sampwidth * framerate
        segment_size = int(size_per_sec * 15)  # 15秒分片
        return await self.segment_data_processor(audio_data, segment_size)

    def transcribe_audio(self, audio_data):
        """调用异步ASR识别"""
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(
                    asyncio.wait_for(
                        self.execute_streaming_asr(audio_data),
                        timeout=60  # 总超时60秒
                    )
                )
                return result
            finally:
                loop.close()

        except asyncio.TimeoutError:
            self.update_signal.emit("❌ 语音识别超时")
            return None
        except Exception as e:
            self.update_signal.emit(f"❌ 语音识别出错：{str(e)}")
            return None

    def read_wav_info(self, data: bytes):
        """读取WAV文件信息"""
        with BytesIO(data) as f:
            wf = wave.open(f, 'rb')
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            wave_bytes = wf.readframes(nframes)
            wf.close()
        return nchannels, sampwidth, framerate, nframes, len(wave_bytes)

    def stop(self):
        """停止线程"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True