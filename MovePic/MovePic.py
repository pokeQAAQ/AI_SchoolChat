from PySide6 import QtWidgets, QtCore, QtGui
import sys
import os
import random
import signal
import psutil
import time


class HideCursorWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: black;")

    # 移除enterEvent中的光标隐藏，避免干扰全局事件


class MovePic(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.original_cursor = self.cursor()
        self.move_pic = QtCore.QRect()
        self.init_ui()
        self.start_random_movement()
        self.main_pid = self.find_main_program_pid()

        # 添加交互检测标志
        self.interaction_detected = False

    def find_main_program_pid(self):
        current_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.pid != current_pid and 'python' in proc.name().lower():
                    cmdline = proc.cmdline()
                    if any('test1.py' in arg or 'ProgramManager' in arg for arg in cmdline):
                        return proc.pid
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.background_container = HideCursorWidget()
        self.move_area = self.background_container

        background_layout = QtWidgets.QVBoxLayout(self.background_container)
        background_layout.setContentsMargins(0, 0, 0, 0)
        background_layout.setSpacing(0)

        self.MoveLabel = QtWidgets.QLabel()
        self.MoveLabel.setFixedSize(100, 100)
        self.MoveLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.MoveLabel.setStyleSheet("background: transparent; border: none;")
        self.set_label_image("/home/orangepi/program/LTChat_updater/app/MovePic//Icon/blackScreen.png")

        # 让图片标签可交互
        self.MoveLabel.setMouseTracking(True)
        self.MoveLabel.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)

        background_layout.setAlignment(QtCore.Qt.AlignCenter)
        background_layout.addWidget(self.MoveLabel)

        main_layout.addWidget(self.background_container)

        self.resize(600, 1024)
        self.full_screen()

        # 不立即隐藏光标，而是延迟隐藏
        QtCore.QTimer.singleShot(2000, self.hide_cursor)

        # 安装事件过滤器
        self.installEventFilter(self)
        self.background_container.installEventFilter(self)
        self.MoveLabel.installEventFilter(self)

    def eventFilter(self, obj, event):
        # 检测所有可能的交互事件
        event_types = [
            QtCore.QEvent.MouseButtonPress,
            QtCore.QEvent.MouseButtonRelease,
            QtCore.QEvent.MouseMove,
            QtCore.QEvent.Wheel,
            QtCore.QEvent.KeyPress,
            QtCore.QEvent.KeyRelease,
            QtCore.QEvent.TouchBegin,  # 添加触摸事件支持
            QtCore.QEvent.TouchUpdate,
            QtCore.QEvent.TouchEnd
        ]

        if event.type() in event_types:
            self.detect_interaction()
            return True
        return super().eventFilter(obj, event)

    def detect_interaction(self):
        """检测到交互时的处理"""
        if not self.interaction_detected:
            self.interaction_detected = True
            print("检测到用户交互，通知主程序切换")
            self.notify_main_program()

            # 短暂显示光标，让用户知道交互已被识别
            self.show_cursor()

            # 延迟重置交互标志
            QtCore.QTimer.singleShot(1000, self.reset_interaction_flag)

    def reset_interaction_flag(self):
        self.interaction_detected = False

    def notify_main_program(self):
        if self.main_pid:
            try:
                os.kill(self.main_pid, signal.SIGUSR1)
            except Exception as e:
                print(f"无法通知主程序: {e}")

    def start_random_movement(self):
        self.move_timer = QtCore.QTimer()
        self.move_timer.timeout.connect(self.move_to_random_position)
        self.move_timer.start(3000)

    def move_to_random_position(self):
        if self.move_area:
            self.move_pic = self.move_area.rect()
            max_x = self.move_pic.width() - self.MoveLabel.width()
            max_y = self.move_pic.height() - self.MoveLabel.height()

            if max_x > 0 and max_y > 0:
                random_x = random.randint(0, max_x)
                random_y = random.randint(0, max_y)
                self.MoveLabel.move(random_x, random_y)

    def hide_cursor(self):
        """修改光标隐藏方式，使用更柔和的方式"""
        try:
            self.setCursor(QtGui.QCursor(QtCore.Qt.BlankCursor))
            QtWidgets.QApplication.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BlankCursor))
        except:
            pass

    def show_cursor(self):
        """恢复光标显示"""
        try:
            self.setCursor(self.original_cursor)
            QtWidgets.QApplication.restoreOverrideCursor()
        except:
            pass

    def set_label_image(self, image_path):
        if os.path.exists(image_path):
            pixmap = QtGui.QPixmap(image_path)
            if not pixmap.isNull():
                self.MoveLabel.setPixmap(
                    pixmap.scaled(
                        self.MoveLabel.size(),
                        QtCore.Qt.KeepAspectRatio,
                        QtCore.Qt.SmoothTransformation
                    )
                )
                self.MoveLabel.setStyleSheet("background: transparent; border: none;")
                return

        self.MoveLabel.setText("图片未找到")
        self.MoveLabel.setStyleSheet("background-color: red; color: white; border: none;")
        self.MoveLabel.setPixmap(QtGui.QPixmap())

    def full_screen(self):
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowDoesNotAcceptFocus  # 不让窗口获取焦点，允许事件传递
        )
        self.showFullScreen()
        QtCore.QTimer.singleShot(100, self.move_to_random_position)

    def keyPressEvent(self, event):
        self.detect_interaction()  # 确保按键事件被捕获
        if event.key() == QtCore.Qt.Key_Escape:
            self.show_cursor()
            self.close()
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.show_cursor()
        if hasattr(self, 'move_timer'):
            self.move_timer.stop()
        event.accept()


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    # 启用触摸支持
    # app.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    # app.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    window = MovePic()
    window.show()
    sys.exit(app.exec())
