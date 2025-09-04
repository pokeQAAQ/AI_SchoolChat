# main_window.py (修改后)
import sys
import os
import time
from PySide6.QtCore import Qt, QTimer, QMutex, QSize
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                              QProgressBar, QFrame, QLabel, QPushButton,
                              QMessageBox, QAbstractItemView, QSizePolicy,
                              QListWidgetItem)  # 添加这一行！
from PySide6.QtGui import QFont, QCursor
from audio_utils import suppress_stderr_fd

# 导入自定义组件和线程

from audio_threads import AudioPlayThread
from test1 import ChatBubble, RecordButton


# 导入外部业务线程
from RecordThread import RecordThread
from AiIOPut import AiIOPut
from AiReply import AiReply
from TTSModel import TTSModel
class ChatWindow(QWidget):
    """聊天主窗口"""
    def __init__(self, api_key, base_url):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url

        # 初始化变量
        self.recorder = None
        self.ai_handle = None
        self.current_play_thread = None
        self.conversation_history = [
            {"role": "system", "content": "你是校园小朋友的好帮手，回答要简单亲切"}
        ]

        # 设备初始化
        self.target_device_name = "MIC"
        self.target_device_index = self.get_device_index_by_name(self.target_device_name)

        # 界面设置
        self.init_ui()
        self.check_device()
        self._original_cursor = self.cursor()
        self.setCursor(Qt.BlankCursor)

        # 长按录音计时器
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.start_recording)

        # 全屏显示
        self.set_fullscreen()

        # 线程管理
        self.active_threads = []
        self.thread_mutex = QMutex()

    def init_ui(self):
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题栏
        title_container = self._create_title_bar()
        main_layout.addWidget(title_container, 1)

        # 聊天记录区域
        self.chat_list = self._create_chat_list()
        main_layout.addWidget(self.chat_list, 7)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar, 0)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #e0e0e0; height: 2px;")
        main_layout.addWidget(line)

        # 底部录音区域
        bottom_container = self._create_bottom_area()
        main_layout.addWidget(bottom_container, 2)

        # 绑定事件
        self.record_btn.pressed_signal.connect(self.prepare_recording)
        self.record_btn.released_signal.connect(self.stop_recording)
        self.new_chat_btn.clicked.connect(self.confirm_new_btn)
        self.chat_list.itemDelegate().sizeHintChanged.connect(self.adjust_bubble_sizes)

    def _create_title_bar(self):
        """创建标题栏"""
        title_container = QWidget()
        title_container.setStyleSheet("background-color: #4a90e2;")
        title_container.setFixedHeight(70)
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(15, 0, 15, 0)

        # 新对话按钮
        self.new_chat_btn = QPushButton("新对话")
        self.new_chat_btn.setStyleSheet("""
            QPushButton{
                background-color: #3a70d9;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2a60c9; }
            QPushButton:pressed { background-color: #1a50b9; }
        """)
        self.new_chat_btn.setFixedSize(100, 40)
        title_layout.addWidget(self.new_chat_btn)

        # 左侧拉伸空间
        left_spacer = QWidget()
        left_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_layout.addWidget(left_spacer)

        # 标题
        title_label = QLabel("校园智能小助手")
        title_label.setStyleSheet("color: white; font-size: 24px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title_label)

        # 右侧拉伸空间
        right_spacer = QWidget()
        right_spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        title_layout.addWidget(right_spacer)

        # 右侧占位
        spacer = QWidget()
        spacer.setFixedSize(100, 40)
        title_layout.addWidget(spacer)

        return title_container

    def _create_chat_list(self):
        """创建聊天记录列表"""
        chat_list = QListWidget()
        chat_list.setSelectionMode(QAbstractItemView.NoSelection)
        chat_list.setFocusPolicy(Qt.NoFocus)
        chat_list.setStyleSheet("""
            QListWidget {
                background-color: #f0f2f5;
                border: none;
                padding: 10px;
            }
            QListWidget::item { border: none; background: transparent; }
            QListWidget::item:selected { background: transparent; }
        """)
        chat_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        return chat_list

    def _create_bottom_area(self):
        """创建底部录音区域"""
        bottom_container = QWidget()
        bottom_container.setStyleSheet("background-color: white;")
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(20, 15, 20, 25)
        bottom_layout.setSpacing(10)

        # 提示文字
        self.record_hint = QLabel("长按按钮说话，松开发送")
        self.record_hint.setStyleSheet("font-size: 18px; color: #555;")
        self.record_hint.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(self.record_hint)

        # 录音按钮（居中）
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_container.setStyleSheet("background-color: transparent;")

        button_image_path = "Icon/button.png"
        self.record_btn = RecordButton(button_image_path)
        self.record_btn.setFixedSize(100, 100)
        self.record_btn.setStyleSheet("""
            QPushButton {
                border: 3px solid #e0e0e0;
                border-radius: 50px;
                background-color: white;
            }
            QPushButton:pressed { background-color: #f0f0f0; }
        """)
        btn_layout.addWidget(self.record_btn)
        bottom_layout.addWidget(btn_container)

        # 使用说明
        guide_label = QLabel("小提示：说话时保持距离麦克风10-30厘米效果最佳")
        guide_label.setStyleSheet("color: #999; font-size: 14px;")
        guide_label.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(guide_label)

        return bottom_container

    # 以下为原逻辑中的其他方法（保持不变）
    def set_fullscreen(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.showFullScreen()

    def confirm_new_btn(self):
        confirm_box = QMessageBox(self)
        confirm_box.setIcon(QMessageBox.Question)
        confirm_box.setWindowTitle("开启新对话")
        confirm_box.setText("确定要开启新对话吗？")
        confirm_box.setInformativeText("当前对话记录将被清空。")
        confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_box.setDefaultButton(QMessageBox.No)
        confirm_box.setStyleSheet("""
            QMessageBox { background-color: white; font-size: 16px; }
            QLabel { color: #333; }
            QPushButton { min-width: 80px; min-height: 30px; font-size: 14px; padding: 5px 10px; }
        """)

        if confirm_box.exec() == QMessageBox.Yes:
            self.start_new_chat()

    def start_new_chat(self):
        self.chat_list.clear()
        self.conversation_history = [
            {"role": "system", "content": "你是校园小朋友的好帮手，回答要简单亲切"}
        ]
        self.stop_recording()

        self.thread_mutex.lock()
        for thread in self.active_threads:
            if thread and thread.isRunning():
                if hasattr(thread, "stop"):
                    thread.stop()
                elif hasattr(thread, "terminate"):
                    thread.terminate()
                thread.wait(500)
        self.active_threads.clear()
        self.thread_mutex.unlock()
        print("已经开启新对话")

    def adjust_bubble_sizes(self):
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            widget = self.chat_list.itemWidget(item)
            if isinstance(widget, ChatBubble):
                item.setSizeHint(widget.sizeHint())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_bubble_sizes()

    def check_device(self):
        if self.target_device_index is None:
            self.add_system_message(f"❌ 未找到麦克风设备（{self.target_device_name}）")
            QMessageBox.warning(self, "设备错误", "请检查麦克风连接")
            return

        try:
            # 懒加载 PyAudio 并抑制 stderr 消息
            with suppress_stderr_fd():
                import pyaudio
                audio = pyaudio.PyAudio()
            device_info = audio.get_device_info_by_index(self.target_device_index)
            print(f"✅ 已连接设备：{device_info['name']}")
            audio.terminate()
        except Exception as e:
            self.add_system_message(f"❌ 设备错误：{str(e)}")
            QMessageBox.warning(self, "设备错误", f"无法访问麦克风：{str(e)}")

    def add_system_message(self, text):
        item = QListWidgetItem(self.chat_list)
        label = QLabel(f'<div style="text-align: center; color: #999; font-size: 16px; padding: 10px;">{text}</div>')
        label.setContentsMargins(10, 10, 10, 10)
        label.setWordWrap(True)
        item.setSizeHint(QSize(self.width(), 60))
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, label)
        self.scroll_to_bottom()

    def add_user_message(self, text):
        item = QListWidgetItem(self.chat_list)
        bubble = ChatBubble(text, is_user=True)
        item.setSizeHint(bubble.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, bubble)
        self.scroll_to_bottom()
        QTimer.singleShot(50, self.adjust_bubble_sizes)

    def add_ai_message(self, text):
        item = QListWidgetItem(self.chat_list)
        bubble = ChatBubble(text, is_user=False)
        item.setSizeHint(bubble.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, bubble)
        self.scroll_to_bottom()
        QTimer.singleShot(50, self.adjust_bubble_sizes)

    def scroll_to_bottom(self):
        self.chat_list.scrollToBottom()

    def prepare_recording(self):
        self.progress_bar.setVisible(True)
        self.record_hint.setText("正在录音...松开发送")
        self.hold_timer.start(300)
        self.record_btn.setStyleSheet("""
            QPushButton {
                border: 3px solid #ff4444;
                border-radius: 50px;
                background-color: #ffeeee;
            }
            QPushButton:pressed { background-color: #ffdddd; }
        """)
        print("准备开始录音...")

    def start_recording(self):
        if not self.recorder or not self.recorder.isRunning():
            self.recorder = RecordThread(self.target_device_index)
            self.thread_mutex.lock()
            self.active_threads.append(self.recorder)
            self.thread_mutex.unlock()
            self.recorder.update_text.connect(self.print_to_terminal)
            self.recorder.recording_finished.connect(self.on_recording_finished)
            self.recorder.start()

    def stop_recording(self):
        self.hold_timer.stop()
        self.record_btn.setStyleSheet("""
            QPushButton {
                border: 3px solid #e0e0e0;
                border-radius: 50px;
                background-color: white;
            }
            QPushButton:pressed { background-color: #f0f0f0; }
        """)
        self.record_hint.setText("长按按钮说话，松开发送")

        if self.recorder and self.recorder.isRunning():
            self.recorder.stop()
            self.recorder.wait()
            self.progress_bar.setVisible(False)
            print("录音已停止")

    def on_recording_finished(self, message):
        print(message)
        print("🔄 正在识别语音...")
        self.progress_bar.setVisible(True)
        self.start_ai_processing()

    def start_ai_processing(self):
        if not self.api_key or not self.base_url:
            self.add_system_message("❌ API配置错误，请检查API密钥和URL")
            return

        self.ai_handle = AiIOPut(self.api_key, self.base_url)
        self.thread_mutex.lock()
        self.active_threads.append(self.ai_handle)
        self.thread_mutex.unlock()
        self.ai_handle.update_signal.connect(self.print_to_terminal)
        self.ai_handle.text_result.connect(self.on_transcribe_finished)
        self.ai_handle.finished.connect(lambda: self.progress_bar.setVisible(False))
        self.ai_handle.start()

    def on_transcribe_finished(self, user_text):
        """语音转文字完成"""
        # 确保处理字符串结果（修复点）
        if not user_text or (isinstance(user_text, list) and len(user_text) == 0):
            self.add_system_message("❌ 未识别到语音，请重试")
            print("❌ 未识别到语音")
            return

        # 处理不同格式的识别结果
        if isinstance(user_text, list):
            # 提取第一个候选文本
            user_text = user_text[0].get("text", "") if user_text else ""
        elif isinstance(user_text, dict) and "text" in user_text:
            user_text = user_text["text"]

        # 确保是字符串
        if not isinstance(user_text, str):
            try:
                user_text = str(user_text)
            except:
                self.add_system_message("❌ 识别结果格式错误")
                return

        self.add_user_message(user_text)
        self.conversation_history.append({"role": "user", "content": user_text})
        print("🤖 正在思考...")

        self.ai_reply_thread = AiReply(self.api_key, self.base_url, self.conversation_history)
        self.thread_mutex.lock()
        self.active_threads.append(self.ai_reply_thread)
        self.thread_mutex.unlock()
        self.ai_reply_thread.result.connect(self.on_ai_reply_finished)
        self.ai_reply_thread.start()

    def on_ai_reply_finished(self, ai_text):
        if not ai_text:
            self.add_system_message("❌ AI回复为空，请重试")
            print("❌ AI回复为空")
            return

        # 新增：TTS接口字符限制处理（假设最大支持300字符，需根据实际文档调整）
        MAX_TTS_LENGTH = 300  # 替换为TTS接口实际限制的字符数
        if isinstance(ai_text, str):
            if len(ai_text) > MAX_TTS_LENGTH:
                ai_text = ai_text[:MAX_TTS_LENGTH] + "..."  # 截断并添加省略号
                print(f"⚠️ TTS文本过长，已截断至{MAX_TTS_LENGTH}字符")

        if "LLM失败" in ai_text or "LLM错误" in ai_text:
            self.add_system_message(f"❌ AI错误：{ai_text}")
            print(f"❌ AI错误：{ai_text}")
            return

        if isinstance(ai_text, dict) and "content" in ai_text:
            if isinstance(ai_text["content"], list):
                ai_text = next(
                    (item["text"] for item in ai_text["content"] if item.get("type") == "text"),
                    str(ai_text)
                )

        self.add_ai_message(ai_text)
        self.conversation_history.append({"role": "assistant", "content": ai_text})
        print("🔊 正在生成语音...")

        self.tts_thread = TTSModel(self.api_key, self.base_url, ai_text)
        self.thread_mutex.lock()
        self.active_threads.append(self.tts_thread)
        self.thread_mutex.unlock()
        self.tts_thread.finished.connect(self.on_tts_finished)
        self.tts_thread.start()

    def on_audio_play_finished(self):
        if self.current_play_thread == self.sender():
            self.thread_mutex.lock()
            if self.current_play_thread in self.active_threads:
                self.active_threads.remove(self.current_play_thread)
            self.thread_mutex.unlock()
        self.current_play_thread = None
        print("播放完成")

    def on_tts_finished(self, audio_path):
        if not audio_path:
            self.add_system_message("❌ 语音生成失败，路径为空")
            print("❌ 语音生成失败，路径为空")
            return

        if "TTS失败" in audio_path:
            self.add_system_message(f"❌ 语音生成失败：{audio_path}")
            print(f"❌ 语音生成失败：{audio_path}")
            return

        if self.current_play_thread and self.current_play_thread.isRunning():
            print("停止播放当前音频")
            self.current_play_thread.stop()
            self.current_play_thread.wait(300)

        self.thread_mutex.lock()
        if self.current_play_thread in self.active_threads:
            self.active_threads.remove(self.current_play_thread)
        self.thread_mutex.unlock()
        self.current_play_thread = None

        print("▶️ 正在播放回答...")
        self.play_thread = AudioPlayThread(audio_path)
        self.thread_mutex.lock()
        self.active_threads.append(self.play_thread)
        self.thread_mutex.unlock()
        self.play_thread.finished_signal.connect(self.on_audio_play_finished)
        self.current_play_thread = self.play_thread
        self.play_thread.start()

    def get_device_index_by_name(self, target_name):
        # 懒加载 PyAudio 并抑制 stderr 消息
        with suppress_stderr_fd():
            import pyaudio
            audio = pyaudio.PyAudio()
        try:
            for i in range(audio.get_device_count()):
                device_info = audio.get_device_info_by_index(i)
                if target_name.lower() in device_info["name"].lower() and device_info["maxInputChannels"] > 0:
                    return i
        except Exception as e:
            print(f"获取设备列表失败: {str(e)}")
        finally:
            audio.terminate()
        return None

    def print_to_terminal(self, text):
        print(text)

    def closeEvent(self, event):
        self.hold_timer.stop()
        self.setCursor(self._original_cursor)

        self.thread_mutex.lock()
        for thread in self.active_threads:
            if thread and thread.isRunning():
                if hasattr(thread, 'stop'):
                    thread.stop()
                elif hasattr(thread, 'terminate'):
                    thread.terminate()
                thread.wait(500)
        self.active_threads.clear()
        self.thread_mutex.unlock()

        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.showNormal()
        elif event.key() == Qt.Key_F11:
            self.showFullScreen()
        super().keyPressEvent(event)