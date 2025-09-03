"""
AI SchoolChat - 智能校园聊天助手

系统要求:
- alsa-utils 用于音频播放 (pacman -S alsa-utils)
- 已移除PyAudio依赖，使用arecord/aplay避免ALSA/JACK错误
"""
import sys
import wave
import os
import time
import hashlib
import psutil
from pathlib import Path
import qrcode
from PIL import Image, ImageDraw

from PySide6.QtCore import QThread, Signal, Qt, QTimer, QSize, QMutex, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QLabel, QMessageBox,
                               QProgressBar, QFrame, QSizePolicy,
                               QListWidget, QListWidgetItem, QAbstractItemView, QScrollBar,
                               QDialog, QTextEdit, QMenu)
from PySide6.QtGui import QPixmap, QIcon, QFont, QWheelEvent, QKeyEvent, QPainter, QBrush, QColor, QAction
from playsound import playsound

import io
import socket
import subprocess

# 配置标志
USE_PLAYBACK = True  # 启用/禁用音频播放
APLAY_DEVICE = None  # 播放设备，例如 "hw:0,0" 或 None 使用默认设备

# 导入自定义模块
from RecordThread import RecordThread
from PersistentRecordManager import PersistentRecordManager
from AiIOPut import AiIOPut
from AiReply import AiReply
from TTSModel import TTSModel
from AplayPlayThread import AplayPlayThread
from smooth_scroll_list import SmoothScrollList
from knowledge_manager import knowledge_manager


# 替换PyAudio设备检测函数为无操作函数，避免ALSA/JACK错误
def check_device():
    """无操作设备检查函数"""
    print("🔊 使用alsa-utils进行音频播放，跳过PyAudio设备检查")
    return True

def get_device_index_by_name(device_name):
    """无操作设备索引获取函数"""
    print(f"🔊 设备 '{device_name}' 将使用默认alsa设备")
    return None


# 配置常量
class Config:
    MAX_CHAT_HISTORY = 50  # 最大聊天记录数
    MAX_CONVERSATION_HISTORY = 20  # 最大对话上下文
    MEMORY_THRESHOLD_MB = 200  # 内存阈值(MB)
    AUDIO_CHUNK_SIZE = 512  # 音频块大小(针对香橙派优化)
    UI_UPDATE_INTERVAL = 100  # UI更新间隔(ms)
    SCROLL_SENSITIVITY = 10  # 滚动灵敏度


class SecurityManager:
    """安全管理器"""

    @staticmethod
    def validate_file_path(file_path: str, allowed_extensions: list = None) -> bool:
        """验证文件路径安全性"""
        try:
            path = Path(file_path).resolve()

            # 检查路径遍历
            if '..' in str(path):
                return False

            # 检查文件扩展名
            if allowed_extensions and path.suffix.lower() not in allowed_extensions:
                return False

            # 检查文件是否存在且可读
            return path.exists() and os.access(path, os.R_OK)

        except Exception:
            return False

    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        """清理文本输入"""
        if not isinstance(text, str):
            return ""

        # 限制长度
        text = text[:max_length]

        # 移除潜在危险字符
        dangerous_chars = ['<script', '</script', 'javascript:', 'data:']
        for char in dangerous_chars:
            text = text.replace(char, '')

        return text.strip()


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self):
        self.process = psutil.Process()

    def get_memory_usage_mb(self) -> float:
        """获取内存使用量(MB)"""
        return self.process.memory_info().rss / 1024 / 1024

    def get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        return self.process.cpu_percent()

    def is_memory_critical(self) -> bool:
        """检查内存是否超过阈值"""
        return self.get_memory_usage_mb() > Config.MEMORY_THRESHOLD_MB


class ChatBubble(QWidget):
    """聊天气泡组件"""

    def __init__(self, text, is_user=False, parent=None):
        super().__init__(parent)
        self.is_user = is_user

        # 禁止接收鼠标事件（防止被选中）
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setFocusPolicy(Qt.NoFocus)

        # 安全清理文本
        self.text = SecurityManager.sanitize_text(text)

        # 主布局
        main_layout = QVBoxLayout(self)

        if is_user:
            main_layout.setContentsMargins(15, 5, 15, 15)
        else:
            main_layout.setContentsMargins(15, 5, 60, 15)
        main_layout.setSpacing(5)

        # 发送者名称标签
        self.sender_label = QLabel("我" if is_user else "小助手")
        font = QFont("Microsoft YaHei", 14, QFont.Bold)
        self.sender_label.setFont(font)
        self.sender_label.setStyleSheet("color: #666;")
        self.sender_label.setAlignment(Qt.AlignLeft if is_user else Qt.AlignRight)

        # 消息内容标签
        self.message_label = QLabel(self.text)
        self.message_label.setFont(QFont("Microsoft YaHei", 16))
        self.message_label.setWordWrap(True)

        # 设置气泡样式
        bubble_style = """
            background-color: #95ec69;
            color: #333;
            padding: 15px;
            border-radius: 18px;
            border-top-left-radius: 6px;
        """
        if not is_user:
            bubble_style = """
                background-color: #70b9ff;
                color: #333;
                padding: 15px;
                border-radius: 18px;
                border-top-right-radius: 6px;
            """
        self.message_label.setStyleSheet(bubble_style)

        # 添加控件到布局
        main_layout.addWidget(self.sender_label)
        main_layout.addWidget(self.message_label)

        # 设置尺寸策略
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

    def sizeHint(self):
        """计算最佳大小"""
        fm = self.message_label.fontMetrics()
        text_width = self.width() - 60
        if text_width < 100:
            text_width = 300

        text_rect = fm.boundingRect(
            0, 0, text_width, 0,
            Qt.TextWordWrap,
            self.message_label.text()
        )

        height = self.sender_label.sizeHint().height() + text_rect.height() + 50
        return QSize(self.width(), int(height))



class QRCodeGenerator:
    """二维码生成器（使用qrcode库）"""
    
    @staticmethod
    def create_qr_pixmap(data, size=200):
        """创建QPixmap的二维码图像"""
        try:
            # 创建qrcode对象
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            # 生成PIL图像
            pil_image = qr.make_image(fill_color="black", back_color="white")
            
            # 转换为QPixmap
            # 先保存为临时文件
            temp_path = "/tmp/qr_temp.png"
            pil_image.save(temp_path)
            
            # 加载QPixmap
            pixmap = QPixmap(temp_path)
            
            # 缩放到指定尺寸
            if pixmap.width() != size or pixmap.height() != size:
                pixmap = pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            
            # 清理临时文件
            try:
                os.remove(temp_path)
            except:
                pass
            
            return pixmap
            
        except Exception as e:
            print(f"⚠️ 生成二维码失败: {e}")
            # 如果失败，返回空白图像
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor(255, 255, 255))
            return pixmap


class KnowledgeQRDialog(QDialog):
    """知识库二维码显示对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📚 知识库上传")
        self.setFixedSize(450, 600)
        self.setModal(True)
        
        self.init_ui()
        self.generate_device_info()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("扫码上传知识")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
            margin: 10px 0;
        """)
        layout.addWidget(title)
        
        # 说明文字
        instruction = QLabel(" 手机连接设备热点，然后扫码访问下面的网址：")
        instruction.setWordWrap(True)
        instruction.setAlignment(Qt.AlignCenter)
        instruction.setStyleSheet("font-size: 16px; color: #34495e; margin: 10px;")
        layout.addWidget(instruction)
        
        # 二维码显示区域
        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setStyleSheet("""
            border: 2px solid #bdc3c7;
            border-radius: 10px;
            padding: 20px;
            background-color: white;
        """)
        layout.addWidget(self.qr_label)
        
        # 设备信息显示
        self.device_info = QTextEdit()
        self.device_info.setMaximumHeight(120)
        self.device_info.setReadOnly(True)
        self.device_info.setStyleSheet("""
            border: 1px solid #bdc3c7;
            border-radius: 5px;
            padding: 10px;
            background-color: #f8f9fa;
            font-family: monospace;
            font-size: 12px;
        """)
        layout.addWidget(self.device_info)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)
        close_btn.clicked.connect(self.accept)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def generate_device_info(self):
        """生成设备信息和二维码"""
        try:
            # 获取设备信息
            device_info = self.get_device_info()
            
            # 生成访问网址
            access_url = f"http://{device_info['ip']}:8080"
            
            # 生成二维码
            qr_pixmap = QRCodeGenerator.create_qr_pixmap(access_url, 180)
            self.qr_label.setPixmap(qr_pixmap)
            
            # 显示设备信息
            info_text = f"""设备信息：
设备名： {device_info['hostname']}
MAC地址： {device_info['mac']}
IP地址： {device_info['ip']}
访问网址： {access_url}

操作步骤：
1. 手机连接设备WiFi热点
2. 扫码或输入上面网址
3. 上传学校信息、校史、名人介绍等"""
            
            self.device_info.setPlainText(info_text)
            
        except Exception as e:
            print(f"⚠️ 生成设备信息失败: {e}")
            self.device_info.setPlainText("获取设备信息失败，请检查网络连接")
    
    def get_device_info(self):
        """获取设备信息"""
        info = {
            'hostname': 'orangepi-zero3',
            'mac': '00:00:00:00:00:00',
            'ip': '192.168.4.1'  # 默认热点IP
        }
        
        try:
            # 获取主机名
            with open('/etc/hostname', 'r') as f:
                info['hostname'] = f.read().strip()
        except:
            pass
        
        try:
            # 获取MAC地址（优先获取wlan0）
            result = subprocess.run(['cat', '/sys/class/net/wlan0/address'], 
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                info['mac'] = result.stdout.strip().upper()
        except:
            try:
                # 备用方法：使用ifconfig
                result = subprocess.run(['ifconfig', 'wlan0'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    import re
                    mac_match = re.search(r'ether\s+([a-fA-F0-9:]{17})', result.stdout)
                    if mac_match:
                        info['mac'] = mac_match.group(1).upper()
            except:
                pass
        
        try:
            # 获取当前 IP地址（如果不是热点模式）
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                current_ip = s.getsockname()[0]
                if current_ip != '127.0.0.1':
                    info['ip'] = current_ip
        except:
            pass
        
        return info


class RecordButton(QPushButton):
    """录音按钮"""
    pressed_signal = Signal()
    released_signal = Signal()

    def __init__(self, image_path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.is_recording = False

        self.setMinimumSize(80, 80)

        # 验证图片路径安全性
        if SecurityManager.validate_file_path(image_path, ['.png', '.jpg', '.jpeg']):
            self.set_icon(image_path)
        else:
            self.setText("按住说话")
            print(f"⚠️ 无效的按钮图片路径: {image_path}")

        # 按钮样式
        self.setStyleSheet("""
            QPushButton {
                border: none;
                border-radius: 40px;
                background-color: transparent;
            }
            QPushButton:pressed {
                padding: 2px;
            }
        """)

    def set_icon(self, image_path):
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self.setIcon(QIcon(pixmap))
                self.setIconSize(QSize(70, 70))
            else:
                self.setText("按住说话")
        except Exception as e:
            print(f"设置按钮图标失败: {e}")
            self.setText("按住说话")

    def resizeEvent(self, event):
        radius = self.width() // 2
        self.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: {radius}px;
                background-color: transparent;
            }}
            QPushButton:pressed {{
                padding: 2px;
            }}
        """)
        if hasattr(self, 'image_path') and SecurityManager.validate_file_path(self.image_path):
            self.set_icon(self.image_path)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_recording = True
            self.pressed_signal.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_recording:
            self.is_recording = False
            self.released_signal.emit()
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_recording and not self.rect().contains(event.position().toPoint()):
            self.is_recording = False
            self.released_signal.emit()
        super().mouseMoveEvent(event)



class ChatWindow(QWidget):
    """聊天界面"""

    def __init__(self, llm_api_key, llm_base_url):
        super().__init__(parent=None)

        # 安全检查API配置
        self.llm_api_key = SecurityManager.sanitize_text(llm_api_key, 200) if llm_api_key else ""
        self.llm_base_url = SecurityManager.sanitize_text(llm_base_url, 200) if llm_base_url else ""

        # 性能监控
        self.performance_monitor = PerformanceMonitor()
        self.last_memory_check = time.time()

        # 初始化变量
        self.recorder = None
        self.persistent_recorder = None  # 持久录音管理器
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

        # 长按录音计时器
        self.hold_timer = QTimer(self)
        self.hold_timer.setSingleShot(True)
        self.hold_timer.timeout.connect(self.start_recording)

        # 性能监控计时器
        self.memory_timer = QTimer(self)
        self.memory_timer.timeout.connect(self.check_memory_usage)
        self.memory_timer.start(5000)  # 每5秒检查一次

        # 初始化持久录音管理器
        self._init_persistent_recorder()

        # 全屏显示设置
        self.set_fullscreen()

        # 线程管理
        self.active_threads = []
        self.thread_mutex = QMutex()
        
        # 初始化知识库状态显示
        self.update_knowledge_status()

    def _init_persistent_recorder(self):
        """初始化持久录音管理器"""
        try:
            self.persistent_recorder = PersistentRecordManager(self.target_device_index)
            self.persistent_recorder.update_text.connect(self.print_to_terminal)
            self.persistent_recorder.recording_finished.connect(self.on_recording_finished)
            print("🚀 持久录音管理器已初始化")
        except Exception as e:
            print(f"❌ 持久录音管理器初始化失败: {e}")
            self.persistent_recorder = None

    def init_ui(self):
        # 主布局（垂直）
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 标题栏容器
        title_container = QWidget()
        title_container.setStyleSheet("background-color: #4a90e2;")
        title_container.setFixedHeight(70)
        title_layout = QHBoxLayout(title_container)
        title_layout.setContentsMargins(15, 0, 15, 0)

        # 左侧新对话按钮
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
            QPushButton:hover {
                background-color: #2a60c9;
            }
            QPushButton:pressed {
                background-color: #1a50b9;
            }""")
        self.new_chat_btn.setFixedSize(100, 40)
        title_layout.addWidget(self.new_chat_btn)
        
        # 添加左侧拉伸空间
        title_layout.addStretch()
        
        # 标题
        title_label = QLabel("校园智能小助手")
        title_label.setStyleSheet("""
            color: white;
            font-size: 24px;
            font-weight: bold;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        title_layout.addWidget(title_label)
        
        # 添加右侧拉伸空间
        title_layout.addStretch()
        
        # 右侧知识库管理按钮
        self.knowledge_btn = QPushButton("📚 上传知识")
        self.knowledge_btn.setStyleSheet("""
            QPushButton{
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }""")
        self.knowledge_btn.setFixedSize(120, 40)
        title_layout.addWidget(self.knowledge_btn)

        main_layout.addWidget(title_container, 1)

        # 聊天记录区域
        self.chat_list = SmoothScrollList()
        # 禁止选中气泡
        self.chat_list.setSelectionMode(QAbstractItemView.NoSelection)
        # 允许获取焦点以支持键盘滚动
        self.chat_list.setFocusPolicy(Qt.StrongFocus)
        # 样式表：隐藏滚动条
        self.chat_list.setStyleSheet("""
               QListWidget {
                   background-color: #f0f2f5;
                   border: none;
                   padding: 10px;
               }
               QListWidget::item {
                   border: none;
                   background: transparent;
                   padding: 0px;
               }
               QListWidget::item:selected {
                   background: transparent;
                   outline: none;
               }
               QListWidget::item:hover {
                   background: transparent;
               }
               /* 完全隐藏滚动条 */
               QScrollBar:vertical {
                   width: 0px;
                   background: transparent;
               }
               QScrollBar:horizontal {
                   height: 0px;
                   background: transparent;
               }
           """)
        # 禁止焦点（防止键盘干扰）
        self.chat_list.setFocusPolicy(Qt.NoFocus)

        # 设置列表属性
        self.chat_list.setSpacing(5)  # 气泡间距
        self.chat_list.setUniformItemSizes(False)  # 允许不同大小的项目

        main_layout.addWidget(self.chat_list, 7)

        # 隐藏垂直滚动条
        self.chat_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 启用鼠标跟踪以支持滚动
        self.chat_list.setMouseTracking(True)

        main_layout.addWidget(self.chat_list, 7)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar, 0)

        # 添加分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #e0e0e0; height: 2px;")
        main_layout.addWidget(line)

        # 底部录音区域
        bottom_container = QWidget()
        bottom_container.setObjectName("bottom_container")  # 添加对象名称
        bottom_container.setStyleSheet("background-color: white;")
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(20, 15, 20, 25)
        bottom_layout.setSpacing(10)

        # 提示文字
        self.record_hint = QLabel("长按按钮说话，松开发送 | 滚轮/方向键查看历史")
        self.record_hint.setStyleSheet("font-size: 18px; color: #555;")
        self.record_hint.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(self.record_hint)

        # 录音按钮（居中）
        btn_container = QWidget()
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_container.setStyleSheet("background-color: transparent;")

        button_image_path = "/home/orangepi/program/LTChat_updater/app/test1/Icon/button.png"
        self.record_btn = RecordButton(button_image_path)
        self.record_btn.setFixedSize(100, 100)
        self.record_btn.setStyleSheet("""
            QPushButton {
                border: 3px solid #e0e0e0;
                border-radius: 50px;
                background-color: white;
            }
            QPushButton:pressed {
                background-color: #f0f0f0;
            }
        """)
        btn_layout.addWidget(self.record_btn)

        bottom_layout.addWidget(btn_container)

        # 使用说明
        guide_label = QLabel("小提示：说话时保持距离麦克风10-30厘米效果最佳")
        guide_label.setStyleSheet("color: #999; font-size: 14px;")
        guide_label.setAlignment(Qt.AlignCenter)
        bottom_layout.addWidget(guide_label)

        main_layout.addWidget(bottom_container, 2)

        # 创建模型选择按钮
        self.model_selection_btn = ModelSelectionButton(self)
        
        # 绑定事件
        self.record_btn.pressed_signal.connect(self.prepare_recording)
        self.record_btn.released_signal.connect(self.stop_recording)
        self.new_chat_btn.clicked.connect(self.confirm_new_btn)
        self.knowledge_btn.clicked.connect(self.show_knowledge_qr)
        self.chat_list.itemDelegate().sizeHintChanged.connect(self.adjust_bubble_sizes)

    def resizeEvent(self, event):
        """窗口大小变化时调整气泡尺寸和按钮位置"""
        super().resizeEvent(event)
        # 延迟调整以避免频繁重绘
        QTimer.singleShot(Config.UI_UPDATE_INTERVAL, self.adjust_bubble_sizes)
        
        # 调整模型选择按钮位置
        if hasattr(self, 'model_selection_btn') and self.model_selection_btn:
            # 将按钮定位在窗口的右下角，更靠近边缘
            x = self.width() - self.model_selection_btn.width() - 10  # 减少右边距
            y = self.height() - self.model_selection_btn.height() - 10  # 减少下边距
            # 确保坐标不为负数
            x = max(0, x)
            y = max(0, y)
            self.model_selection_btn.move(x, y)
            self.model_selection_btn.raise_()  # 确保按钮在最前面
            self.model_selection_btn.show()  # 确保按钮可见

    def wheelEvent(self, event):
        """处理鼠标滚轮事件"""
        if event.angleDelta().y() != 0:
            # 计算滚动量
            scroll_amount = event.angleDelta().y() * Config.SCROLL_SENSITIVITY
            current_value = self.chat_list.verticalScrollBar().value()
            new_value = current_value - scroll_amount

            # 应用滚动
            self.chat_list.verticalScrollBar().setValue(new_value)
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        """处理键盘事件"""
        key = event.key()

        # 滚动快捷键
        if key == Qt.Key_Up or key == Qt.Key_PageUp:
            current_value = self.chat_list.verticalScrollBar().value()
            scroll_amount = 80 if key == Qt.Key_Up else 250
            self.chat_list.verticalScrollBar().setValue(current_value - scroll_amount)
            event.accept()
            return

        elif key == Qt.Key_Down or key == Qt.Key_PageDown:
            current_value = self.chat_list.verticalScrollBar().value()
            scroll_amount = 80 if key == Qt.Key_Down else 250
            self.chat_list.verticalScrollBar().setValue(current_value + scroll_amount)
            event.accept()
            return

        elif key == Qt.Key_Home:
            self.chat_list.verticalScrollBar().setValue(0)
            event.accept()
            return

        elif key == Qt.Key_End:
            self.chat_list.verticalScrollBar().setValue(
                self.chat_list.verticalScrollBar().maximum()
            )
            event.accept()
            return

        # 应用控制快捷键
        elif key == Qt.Key_Escape:
            self.showNormal()
            # 恢复鼠标显示
            self.setCursor(self._original_cursor)
            event.accept()
            return

        elif key == Qt.Key_F11:
            self.set_fullscreen()
            event.accept()
            return

        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_N:
            self.confirm_new_btn()
            event.accept()
            return

        elif event.modifiers() & Qt.ControlModifier and key == Qt.Key_Q:
            self.close()
            event.accept()
            return

        super().keyPressEvent(event)

    def set_fullscreen(self):
        """设置全屏显示"""
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.showFullScreen()
        # 延迟隐藏鼠标，确保界面完全加载
        QTimer.singleShot(1000, lambda: self.setCursor(Qt.BlankCursor))

    def check_memory_usage(self):
        """检查内存使用情况"""
        try:
            if self.performance_monitor.is_memory_critical():
                print(f"⚠️ 内存使用过高: {self.performance_monitor.get_memory_usage_mb():.1f}MB")
                self.cleanup_old_messages()

            # 每分钟打印一次状态
            current_time = time.time()
            if current_time - self.last_memory_check > 60:
                memory_mb = self.performance_monitor.get_memory_usage_mb()
                cpu_percent = self.performance_monitor.get_cpu_usage()
                print(f"📊 系统状态 - 内存: {memory_mb:.1f}MB, CPU: {cpu_percent:.1f}%")
                self.last_memory_check = current_time

        except Exception as e:
            print(f"性能监控错误: {e}")

    def cleanup_old_messages(self):
        """清理旧消息以释放内存"""
        try:
            chat_count = self.chat_list.count()
            if chat_count > Config.MAX_CHAT_HISTORY:
                # 删除最旧的消息
                items_to_remove = chat_count - Config.MAX_CHAT_HISTORY
                for i in range(items_to_remove):
                    item = self.chat_list.takeItem(0)
                    if item:
                        widget = self.chat_list.itemWidget(item)
                        if widget:
                            widget.deleteLater()
                        del item

                print(f"🧹 已清理 {items_to_remove} 条旧消息")

            # 限制对话历史长度
            if len(self.conversation_history) > Config.MAX_CONVERSATION_HISTORY:
                # 保留系统消息和最近的对话
                system_msg = self.conversation_history[0]
                recent_history = self.conversation_history[-(Config.MAX_CONVERSATION_HISTORY - 1):]
                self.conversation_history = [system_msg] + recent_history
                print(f"🧹 已清理对话历史，保留 {len(self.conversation_history)} 条")

        except Exception as e:
            print(f"清理消息错误: {e}")

    def confirm_new_btn(self):
        # 开启新对话
        confirm_box = QMessageBox(self)
        confirm_box.setIcon(QMessageBox.Question)
        confirm_box.setWindowTitle("开启新对话")
        confirm_box.setText("确定要开启新对话吗？")
        confirm_box.setInformativeText("当前对话记录将被清空。")
        confirm_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm_box.setDefaultButton(QMessageBox.No)
        confirm_box.setStyleSheet("""
            QMessageBox {
                background-color: white;
                font-size: 16px;
            }
            QLabel {
                color: #333;
            }
            QPushButton {
                min-width: 80px;
                min-height: 30px;
                font-size: 14px;
                padding: 5px 10px;
            }
        """)

        reply = confirm_box.exec()
        if reply == QMessageBox.Yes:
            self.start_new_chat()

    def start_new_chat(self):
        """开始新对话"""
        # 先停止当前录音
        self.stop_recording()

        # 安全停止当前音频
        self.stop_current_audio()

        print("🔄 清理所有线程资源...")
        self.thread_mutex.lock()
        try:
            # 优先停止音频相关线程
            audio_threads = [t for t in self.active_threads if isinstance(t, (AplayPlayThread, RecordThread))]
            for thread in audio_threads:
                if hasattr(thread, "stop"):
                    thread.stop()
                if thread in self.active_threads:
                    self.active_threads.remove(thread)

            # 停止其他线程
            for thread in self.active_threads[:]:
                if thread and thread.isRunning():
                    if hasattr(thread, "stop"):
                        thread.stop()
                    elif hasattr(thread, "terminate"):
                        thread.terminate()
                    thread.wait(200)
                if thread in self.active_threads:
                    self.active_threads.remove(thread)

            self.active_threads.clear()
        finally:
            self.thread_mutex.unlock()

            # 重置界面和状态
        self.chat_list.clear()
        self.conversation_history = [
            {"role": "system", "content": "你是校园小朋友的好帮手，回答要简单亲切"}
        ]

        # 强制垃圾回收
        import gc
        gc.collect()

        print("✅ 已开启新对话")

    def show_knowledge_qr(self):
        """显示知识库二维码对话框"""
        try:
            # 显示知识库状态
            stats = knowledge_manager.get_knowledge_stats()
            status_msg = f"📊 当前知识库状态：共 {stats.get('total', 0)} 条记录"
            if stats.get('total', 0) > 0:
                categories = []
                for cat, count in stats.items():
                    if cat != 'total' and count > 0:
                        cat_name = {'school_info': '学校信息', 'history': '校史', 'celebrities': '名人'}.get(cat, cat)
                        categories.append(f"{cat_name}({count}条)")
                if categories:
                    status_msg += f"\n包含：{', '.join(categories)}"
            
            self.add_system_message(status_msg)
            
            # 显示二维码对话框
            dialog = KnowledgeQRDialog(self)
            dialog.exec()
            
        except Exception as e:
            print(f"❌ 显示知识库二维码失败: {e}")
            QMessageBox.warning(self, "错误", "显示知识库信息失败，请稍后重试")

    def update_knowledge_status(self):
        """更新知识库状态显示"""
        try:
            stats = knowledge_manager.get_knowledge_stats()
            total = stats.get('total', 0)
            
            if total > 0:
                # 更新按钮文字显示当前状态
                self.knowledge_btn.setText(f"📚 知识库({total})")
                self.knowledge_btn.setToolTip(f"当前知识库包含 {total} 条记录，点击查看上传信息")
            else:
                self.knowledge_btn.setText("📚 上传知识")
                self.knowledge_btn.setToolTip("点击查看如何上传学校信息、校史、名人介绍等知识")
                
        except Exception as e:
            print(f"❌ 更新知识库状态失败: {e}")

    def adjust_bubble_sizes(self):
        """调整气泡大小以确保文本可见"""
        for i in range(self.chat_list.count()):
            item = self.chat_list.item(i)
            widget = self.chat_list.itemWidget(item)
            if isinstance(widget, ChatBubble):
                item.setSizeHint(widget.sizeHint())

    def check_device(self):
        time.sleep(2)
        if self.target_device_index is None:
            self.add_system_message(f"❌ 未找到麦克风设备（{self.target_device_name}）")
            QMessageBox.warning(self, "设备错误", "请检查麦克风连接")
            return
        try:
            audio = pyaudio.PyAudio()
            device_info = audio.get_device_info_by_index(self.target_device_index)
            print(f"✅ 已连接设备：{device_info['name']}")
            audio.terminate()
        except Exception as e:
            error_msg = SecurityManager.sanitize_text(str(e))
            self.add_system_message(f"❌ 设备错误：{error_msg}")
            QMessageBox.warning(self, "设备错误", f"无法访问麦克风：{error_msg}")

    def add_system_message(self, text):
        """添加系统消息"""
        safe_text = SecurityManager.sanitize_text(text)
        item = QListWidgetItem(self.chat_list)
        label = QLabel(
            f'<div style="text-align: center; color: #999; font-size: 16px; padding: 10px;">{safe_text}</div>')
        label.setContentsMargins(10, 10, 10, 10)
        label.setWordWrap(True)
        item.setSizeHint(QSize(self.width(), 60))
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, label)
        self.scroll_to_bottom()

    def add_user_message(self, text):
        """添加用户消息（左侧气泡）"""
        # 当用户发送新消息时，停止当前正在播放的音频
        self.stop_current_audio()

        safe_text = SecurityManager.sanitize_text(text)
        item = QListWidgetItem(self.chat_list)
        bubble = ChatBubble(safe_text, is_user=True)
        item.setSizeHint(bubble.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, bubble)
        self.scroll_to_bottom()
        QTimer.singleShot(50, self.adjust_bubble_sizes)

    def add_ai_message(self, text):
        """添加AI消息（右侧气泡）"""
        safe_text = SecurityManager.sanitize_text(text)
        item = QListWidgetItem(self.chat_list)
        bubble = ChatBubble(safe_text, is_user=False)
        item.setSizeHint(bubble.sizeHint())
        self.chat_list.addItem(item)
        self.chat_list.setItemWidget(item, bubble)
        self.scroll_to_bottom()
        QTimer.singleShot(50, self.adjust_bubble_sizes)

    def scroll_to_bottom(self):
        """滚动到最新消息"""
        QTimer.singleShot(100, lambda: self.chat_list.scrollToBottom())

    def prepare_recording(self):
        """准备录音"""
        # 准备录音时停止当前音频
        self.stop_current_audio()

        self.progress_bar.setVisible(True)
        self.record_hint.setText("正在录音...松开发送")
        self.hold_timer.start(300)
        self.record_btn.setStyleSheet("""
                        QPushButton {
                            border: 3px solid #ff4444;
                            border-radius: 50px;
                            background-color: #ffeeee;
                        }
                        QPushButton:pressed {
                            background-color: #ffdddd;
                        }
                    """)
        print("准备开始录音...")

    def start_recording(self):
        """开始录音 - 使用持久录音管理器，零延迟"""
        # 检查是否仍在按压
        if not self.record_btn.is_recording:
            return

        # 更新UI表示正在录音
        self.progress_bar.setVisible(True)
        self.record_hint.setText("正在录音...松开发送")
        self.record_btn.setStyleSheet("""
            QPushButton {
                border: 3px solid #ff4444;
                border-radius: 50px;
                background-color: #ffeeee;
            }
            QPushButton:pressed {
                background-color: #ffdddd;
            }
        """)

        # 使用持久录音管理器（零延迟）
        if self.persistent_recorder:
            self.persistent_recorder.start_recording()
            print("✅ 录音已开始（零延迟模式）")
        else:
            # 回退到原有方法
            if not self.recorder or not self.recorder.isRunning():
                try:
                    self.recorder = RecordThread(self.target_device_index)
                    self.thread_mutex.lock()
                    self.active_threads.append(self.recorder)
                    self.thread_mutex.unlock()
                    self.recorder.update_text.connect(self.print_to_terminal)
                    self.recorder.recording_finished.connect(self.on_recording_finished)
                    self.recorder.start()
                    print("✅ 录音已开始（回退模式）")
                except Exception as e:
                    error_msg = SecurityManager.sanitize_text(str(e))
                    self.add_system_message(f"❌ 录音启动失败：{error_msg}")
                    print(f"录音启动错误: {error_msg}")

    def stop_recording(self):
        """停止录音 - 支持持久录音管理器"""
        self.hold_timer.stop()
        self.record_btn.setStyleSheet("""
                        QPushButton {
                            border: 3px solid #e0e0e0;
                            border-radius: 50px;
                            background-color: white;
                        }
                        QPushButton:pressed {
                            background-color: #f0f0f0;
                        }
                    """)
        self.record_hint.setText("长按按钮说话，松开发送")

        # 停止持久录音管理器
        if self.persistent_recorder:
            self.persistent_recorder.stop_recording()
            print("🔴 持久录音管理器已停止")
        
        # 停止临时录音器（如果有）
        if self.recorder and self.recorder.isRunning():
            try:
                self.recorder.stop()
                self.recorder.wait()
                self.progress_bar.setVisible(False)
                print("录音已停止")
            except Exception as e:
                print(f"停止录音错误: {e}")

    def on_recording_finished(self, message):
        """录音完成后处理"""
        safe_message = SecurityManager.sanitize_text(message)
        print(safe_message)
        print("🔄 正在识别语音...")
        self.progress_bar.setVisible(True)
        self.start_ai_processing()

    def start_ai_processing(self):
        """语音转文字→AI回答→TTS"""
        # 新增：打印API配置（脱敏处理）
        print(f"API配置检查：URL={self.llm_base_url[:20]}..., Key={self.llm_api_key[:5]}...")

        if not self.llm_api_key or not self.llm_base_url:
            self.add_system_message("❌ API配置错误，请检查API密钥和URL")
            return

        try:
            self.ai_handle = AiIOPut(self.llm_api_key, self.llm_base_url)
            self.thread_mutex.lock()
            self.active_threads.append(self.ai_handle)
            self.thread_mutex.unlock()
            self.ai_handle.update_signal.connect(self.print_to_terminal)
            self.ai_handle.text_result.connect(self.on_transcribe_finished)
            self.ai_handle.finished.connect(lambda: self.progress_bar.setVisible(False))
            self.ai_handle.start()
        except Exception as e:
            error_msg = SecurityManager.sanitize_text(str(e))
            self.add_system_message(f"❌ AI处理启动失败：{error_msg}")
            print(f"AI处理错误: {error_msg}")

    def on_transcribe_finished(self, user_text):
        """语音转文字完成"""
        safe_user_text = SecurityManager.sanitize_text(user_text, 500) if user_text else ""

        if not safe_user_text:
            self.add_system_message("❌ 未识别到语音，请重试")
            print("❌ 未识别到语音")
            return

        self.add_user_message(safe_user_text)
        self.conversation_history.append({"role": "user", "content": safe_user_text})
        print("🤖 正在思考...")
        self.progress_bar.setVisible(True)

        try:
            self.ai_reply_thread = AiReply(self.conversation_history, self.llm_api_key, self.llm_base_url, safe_user_text)
            self.ai_reply_thread.error_signal.connect(self.on_ai_error)  # 连接错误信号
            self.thread_mutex.lock()
            self.active_threads.append(self.ai_reply_thread)
            self.thread_mutex.unlock()
            self.ai_reply_thread.result.connect(self.on_ai_reply_finished)
            self.ai_reply_thread.start()
        except Exception as e:
            error_msg = SecurityManager.sanitize_text(str(e))
            self.add_system_message(f"❌ AI回复启动失败：{error_msg}")
            print(f"AI回复错误: {error_msg}")
            self.progress_bar.setVisible(False)

    def on_ai_reply_finished(self, ai_text):
        """AI回答完成 - 现在只启动TTS，不立即显示气泡"""
        if not ai_text:
            self.add_system_message("❌ AI回复为空，请重试")
            print("❌ AI回复为空")
            self.progress_bar.setVisible(False)
            return

        if "LLM失败" in str(ai_text) or "LLM错误" in str(ai_text):
            safe_error = SecurityManager.sanitize_text(str(ai_text))
            self.add_system_message(f"❌ AI错误：{safe_error}")
            print(f"❌ AI错误：{safe_error}")
            self.progress_bar.setVisible(False)
            return

        # 提取AI回答文本
        if isinstance(ai_text, dict) and "content" in ai_text:
            if isinstance(ai_text["content"], list):
                ai_text = next(
                    (item["text"] for item in ai_text["content"] if item.get("type") == "text"),
                    str(ai_text)
                )

        safe_ai_text = SecurityManager.sanitize_text(str(ai_text))  # 移除长度限制，保持完整显示
        # 不在这里显示气泡，等待TTS完成
        self.conversation_history.append({"role": "assistant", "content": safe_ai_text})
        print("🔊 正在生成语音...")

        try:
            # 启动TTS线程，传入原始文本
            self.tts_thread = TTSModel(safe_ai_text)
            self.thread_mutex.lock()
            self.active_threads.append(self.tts_thread)
            self.thread_mutex.unlock()
            # 连接TTS完成信号到新的处理函数
            self.tts_thread.finished.connect(self.on_tts_and_audio_ready)
            self.tts_thread.start()
        except Exception as e:
            error_msg = SecurityManager.sanitize_text(str(e))
            self.add_system_message(f"❌ 语音生成启动失败：{error_msg}")
            print(f"TTS错误: {error_msg}")
            self.progress_bar.setVisible(False)

    def on_ai_error(self, error_msg):
        """处理AI回复线程的错误"""
        safe_error = SecurityManager.sanitize_text(error_msg)
        self.add_system_message(f"❌ AI思考失败：{safe_error}")
        print(f"🤖 思考错误：{safe_error}")
        self.progress_bar.setVisible(False)

    def on_tts_and_audio_ready(self, audio_path, ai_text):
        """TTS完成且音频下载好后，同时显示气泡和播放音频"""
        self.progress_bar.setVisible(False)

        if "错误" in audio_path:
            # 显示错误消息，但仍然显示AI回答的文本
            self.add_ai_message(ai_text)
            self.add_system_message(f"❌ 语音生成失败：{audio_path}")
            return

        try:
            # 1. 先显示AI回答气泡（完整文本，无截断）
            self.add_ai_message(ai_text)

            # 2. 检查是否启用播放
            if not USE_PLAYBACK:
                print("🔇 音频播放已禁用")
                return

            # 3. 验证音频文件安全性
            if not SecurityManager.validate_file_path(audio_path, ['.pcm', '.raw', '.wav']):
                raise FileNotFoundError(f"无效的音频文件: {audio_path}")

            # 4. 确保之前的播放已完全停止
            self.stop_current_audio()

            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                raise ValueError(f"音频文件为空或不存在: {audio_path}")

            # 5. 启动aplay播放线程
            self.play_thread = AplayPlayThread(audio_path, device=APLAY_DEVICE)
            self.thread_mutex.lock()
            self.active_threads.append(self.play_thread)
            self.thread_mutex.unlock()

            self.play_thread.finished_signal.connect(self.on_audio_play_finished)
            self.play_thread.stopped_signal.connect(self.on_audio_stopped)
            self.current_play_thread = self.play_thread
            self.play_thread.start()

        except Exception as e:
            error_msg = SecurityManager.sanitize_text(str(e))
            self.add_system_message(f"❌ 播放准备失败：{error_msg}")
            print(f"播放准备错误: {error_msg}")

        except Exception as e:
            error_msg = SecurityManager.sanitize_text(str(e))
            self.add_system_message(f"❌ 播放准备失败：{error_msg}")
            print(f"播放准备错误: {error_msg}")

    def stop_current_audio(self):
        """安全停止当前正在播放的音频"""
        if self.current_play_thread and self.current_play_thread.isRunning():
            print("🔴 正在安全停止音频播放...")

            self.current_play_thread.stop()

            wait_time = 0
            while self.current_play_thread.isRunning() and wait_time < 500:
                QThread.msleep(10)
                wait_time += 10

            self.thread_mutex.lock()
            if self.current_play_thread in self.active_threads:
                self.active_threads.remove(self.current_play_thread)
            self.thread_mutex.unlock()

            self.current_play_thread = None
            print("🔴 音频播放已停止")

    def on_audio_play_finished(self):
        """音频播放正常结束后处理"""
        if self.current_play_thread == self.sender():
            self.thread_mutex.lock()
            if self.current_play_thread in self.active_threads:
                self.active_threads.remove(self.current_play_thread)
            self.thread_mutex.unlock()
        self.current_play_thread = None
        print("播放完成")

    def on_audio_stopped(self):
        """音频被主动停止后处理"""
        if self.current_play_thread == self.sender():
            self.thread_mutex.lock()
            if self.current_play_thread in self.active_threads:
                self.active_threads.remove(self.current_play_thread)
            self.thread_mutex.unlock()
        self.current_play_thread = None
        print("音频已被安全打断")

    def get_device_index_by_name(self, target_name):
        """获取音频设备索引，模糊匹配"""
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
        safe_text = SecurityManager.sanitize_text(text, 200)
        print(safe_text)

    def closeEvent(self, event):
        """窗口关闭事件处理"""
        print("🔄 正在安全关闭应用...")

        # 清理持久录音管理器
        if self.persistent_recorder:
            self.persistent_recorder.cleanup()
            
        # 停止所有计时器
        self.hold_timer.stop()
        self.memory_timer.stop()

        # 恢复鼠标
        self.setCursor(self._original_cursor)

        # 停止当前音频
        self.stop_current_audio()

        # 停止所有活跃线程
        self.thread_mutex.lock()
        try:
            for thread in self.active_threads[:]:
                if thread and thread.isRunning():
                    if hasattr(thread, 'stop'):
                        thread.stop()
                    elif hasattr(thread, 'terminate'):
                        thread.terminate()
                    thread.wait(1000)  # 给更多时间让线程正确退出
                if thread in self.active_threads:
                    self.active_threads.remove(thread)
            self.active_threads.clear()
        finally:
            self.thread_mutex.unlock()

        # 强制垃圾回收
        import gc
        gc.collect()

        print("✅ 应用已安全关闭")
        event.accept()


class ModelSelectionButton(QPushButton):
    """模型选择按钮"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_model = "火山引擎"  # 默认模型
        self.model_icons = {}  # 存储模型图标
        self.init_ui()
        self.create_model_menu()
        self.update_button_display()  # 初始化按钮显示
        
    def init_ui(self):
        # 设置按钮样式
        self.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 15px;
                font-size: 14px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #3a70d9;
            }
            QPushButton:pressed {
                background-color: #2a60c9;
            }
        """)
        self.setFixedSize(120, 35)
        
        # 连接点击事件
        self.clicked.connect(self.show_model_menu)
        
    def create_model_menu(self):
        """创建模型选择菜单"""
        self.model_menu = QMenu(self)
        self.model_menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                padding: 8px 20px 8px 10px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #4a90e2;
                color: white;
            }
        """)
        
        # 添加模型选项
        models = [
            ("火山引擎", "/home/orangepi/program/LTChat_updater/app/test1/AI_Icon/火山引擎.png"),
            ("文心一言", "/home/orangepi/program/LTChat_updater/app/test1/AI_Icon/文心一言.png"),
            ("通义千问", "/home/orangepi/program/LTChat_updater/app/test1/AI_Icon/通义千问.png"),
            ("deepseek", "/home/orangepi/program/LTChat_updater/app/test1/AI_Icon/deepseek.png")
        ]
        
        self.model_actions = []
        for model_name, icon_path in models:
            action = QAction(model_name, self.model_menu)
            if os.path.exists(icon_path):
                icon = QIcon(icon_path)
                action.setIcon(icon)
                # 保存图标以便后续使用
                self.model_icons[model_name] = icon
            self.model_menu.addAction(action)
            self.model_actions.append((action, model_name))
            
        # 连接动作信号
        for action, model_name in self.model_actions:
            action.triggered.connect(lambda checked, name=model_name: self.select_model(name))
            
    def show_model_menu(self):
        """显示模型选择菜单"""
        # 在按钮下方显示菜单
        pos = self.mapToGlobal(self.rect().bottomLeft())
        self.model_menu.exec(pos)
        
    def select_model(self, model_name):
        """选择模型"""
        self.current_model = model_name
        self.update_button_display()
        # 这里可以添加处理模型选择的逻辑
        print(f"选择了模型: {model_name}")
        
    def update_button_display(self):
        """更新按钮显示"""
        # 设置按钮文本
        self.setText(self.current_model)
        
        # 如果有对应的图标，则设置图标
        if self.current_model in self.model_icons:
            icon = self.model_icons[self.current_model]
            self.setIcon(icon)
            self.setIconSize(QSize(20, 20))  # 设置图标大小

def validate_environment(has_default_api_key, has_default_base_url):
    """验证运行环境，判断是否有代码默认值"""
    errors = []

    # 检查必要的环境变量（如果没有代码默认值，则必须从环境变量获取）
    required_vars = []
    if not has_default_api_key:
        required_vars.append("AI_API_KEY")
    if not has_default_base_url:
        required_vars.append("AI_BASE_URL")

    for var in required_vars:
        if not os.environ.get(var):
            errors.append(f"缺少环境变量: {var}")

    # 其他检查（音频设备、内存）
    try:
        audio = pyaudio.PyAudio()
        device_count = audio.get_device_count()
        if device_count == 0:
            errors.append("未找到任何音频设备")
        audio.terminate()
    except Exception as e:
        errors.append(f"音频系统错误: {e}")

    try:
        memory_mb = psutil.virtual_memory().available / 1024 / 1024
        if memory_mb < 100:
            errors.append(f"可用内存不足: {memory_mb:.1f}MB")
    except Exception as e:
        errors.append(f"内存检查错误: {e}")

    return errors


if __name__ == '__main__':
    # 先定义默认API配置（如果环境变量未设置则使用这些值）
    # 使用提供的火山引擎API密钥
    DEFAULT_API_KEY = "da092e1c-5988-43d2-ae0b-e1c2dd70f41e"
    # 使用火山引擎API基础URL
    DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com"

    # 判断是否有默认值（用于环境检查逻辑）
    has_default_api = bool(DEFAULT_API_KEY)
    has_default_base = bool(DEFAULT_BASE_URL)

    # 环境配置
    os.environ['QT_QPA_PLATFORM'] = 'xcb'
    os.environ['QT_FONT_DPI'] = '96'
    os.environ['ALSA_PCM_PLUGIN'] = 'default'

    # 针对香橙派的优化设置
    os.environ['PA_ALSA_PLUGHW'] = '1'
    os.environ['PA_STREAM_LATENCY'] = '60,60'
    os.environ['QT_QUICK_FLICKABLE_WHEEL_DECELERATION'] = '5000'

    # 验证运行环境（传入默认值存在的标志）
    env_errors = validate_environment(has_default_api, has_default_base)
    if env_errors:
        print("❌ 环境检查失败:")
        for error in env_errors:
            print(f"  - {error}")
        sys.exit(1)

    # 从环境变量获取API配置（优先使用环境变量，不存在则用默认值）
    API_KEY = os.environ.get("AI_API_KEY", DEFAULT_API_KEY)
    BASE_URL = os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL)

    # 安全验证API配置
    API_KEY = SecurityManager.sanitize_text(API_KEY, 200)
    BASE_URL = SecurityManager.sanitize_text(BASE_URL, 200)

    print("✅ 环境检查通过，正在启动应用...")

    # 初始化应用
    app = QApplication(sys.argv)
    app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 启动窗口
    try:
        window = ChatWindow(API_KEY, BASE_URL)
        window.show()

        print("🚀 校园智能小助手已启动")
        print("💡 快捷键提示:")
        print("  - 滚轮/方向键: 查看聊天历史")
        print("  - Ctrl+N: 新对话")
        print("  - Ctrl+Q: 退出")
        print("  - Esc: 退出全屏")
        print("  - F11: 进入全屏")

        sys.exit(app.exec())

    except Exception as e:
        error_msg = SecurityManager.sanitize_text(str(e))
        print(f"❌ 应用启动失败: {error_msg}")
        sys.exit(1)
