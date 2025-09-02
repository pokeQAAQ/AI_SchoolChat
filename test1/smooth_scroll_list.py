# smooth_scroll_list.py
from PySide6.QtCore import (Qt, QTimer, QPointF, QPropertyAnimation,
                            QEasingCurve, Signal, QEvent, Property)
from PySide6.QtWidgets import QListWidget, QScroller, QAbstractItemView
from PySide6.QtGui import QTouchEvent
import time


class SmoothScrollList(QListWidget):
    """支持平滑触摸滚动的列表控件"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 触摸滑动相关变量
        self.touch_start_pos = None
        self.touch_start_time = None
        self.last_touch_pos = None
        self.last_touch_time = None
        self.velocity = 0
        self.is_touching = False

        # 动量滚动
        self.momentum_timer = QTimer(self)
        self.momentum_timer.timeout.connect(self._momentum_scroll)
        self.momentum_timer.setInterval(16)  # 约60fps

        # 滚动动画
        self.scroll_animation = QPropertyAnimation(self.verticalScrollBar(), b"value")
        self.scroll_animation.setEasingCurve(QEasingCurve.OutCubic)

        # 设置滚动属性
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # 禁止选中项目
        self.setSelectionMode(QAbstractItemView.NoSelection)

        # 启用触摸事件
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.SwipeGesture)
        self.grabGesture(Qt.PanGesture)

        # 尝试使用Qt的滚动器（更流畅）
        try:
            self.scroller = QScroller.scroller(self.viewport())
            # 配置滚动器属性
            properties = self.scroller.scrollerProperties()

            # 设置滚动速度和摩擦力
            properties.setScrollMetric(QScroller.DragVelocitySmoothingFactor, 0.6)
            properties.setScrollMetric(QScroller.DecelerationFactor, 0.4)
            properties.setScrollMetric(QScroller.MaximumVelocity, 1.5)
            properties.setScrollMetric(QScroller.MinimumVelocity, 0.05)
            properties.setScrollMetric(QScroller.FrameRate, QScroller.Fps60)

            # 设置过冲效果（弹性效果）
            properties.setScrollMetric(QScroller.OvershootDragResistanceFactor, 0.5)
            properties.setScrollMetric(QScroller.OvershootScrollDistanceFactor, 0.2)

            self.scroller.setScrollerProperties(properties)

            # 启用触摸手势
            self.scroller.grabGesture(self.viewport(), QScroller.TouchGesture)
            print("✅ 启用QScroller平滑滚动")
        except Exception as e:
            print(f"⚠️ QScroller初始化失败，使用备用方案: {e}")
            self.scroller = None

        # 滑动灵敏度和惯性参数
        self.SWIPE_SENSITIVITY = 1.2  # 滑动灵敏度
        self.FRICTION = 0.92  # 摩擦系数（用于惯性滚动）
        self.MIN_VELOCITY = 0.5  # 最小速度阈值

    def event(self, event):
        """处理各种事件"""
        if event.type() == QEvent.TouchBegin:
            self._handle_touch_begin(event)
            return True
        elif event.type() == QEvent.TouchUpdate:
            self._handle_touch_update(event)
            return True
        elif event.type() == QEvent.TouchEnd:
            self._handle_touch_end(event)
            return True
        elif event.type() == QEvent.TouchCancel:
            self._handle_touch_cancel(event)
            return True

        return super().event(event)

    def _handle_touch_begin(self, event):
        """处理触摸开始"""
        if event.touchPoints():
            touch_point = event.touchPoints()[0]

            # 停止当前动画和惯性滚动
            self.scroll_animation.stop()
            self.momentum_timer.stop()

            # 记录触摸开始位置和时间
            self.touch_start_pos = touch_point.position()
            self.touch_start_time = time.time()
            self.last_touch_pos = self.touch_start_pos
            self.last_touch_time = self.touch_start_time
            self.is_touching = True
            self.velocity = 0

            event.accept()

    def _handle_touch_update(self, event):
        """处理触摸移动"""
        if event.touchPoints() and self.is_touching:
            touch_point = event.touchPoints()[0]
            current_pos = touch_point.position()
            current_time = time.time()

            if self.last_touch_pos:
                # 计算移动距离
                delta_y = (current_pos.y() - self.last_touch_pos.y()) * self.SWIPE_SENSITIVITY

                # 计算速度（用于惯性滚动）
                time_delta = current_time - self.last_touch_time
                if time_delta > 0:
                    self.velocity = delta_y / time_delta

                # 立即滚动（注意方向：向下滑动查看历史，向上滑动查看最新）
                current_value = self.verticalScrollBar().value()
                new_value = current_value - int(delta_y)

                # 限制在有效范围内
                new_value = max(0, min(new_value, self.verticalScrollBar().maximum()))
                self.verticalScrollBar().setValue(new_value)

            self.last_touch_pos = current_pos
            self.last_touch_time = current_time
            event.accept()

    def _handle_touch_end(self, event):
        """处理触摸结束"""
        if self.is_touching:
            self.is_touching = False

            # 如果速度足够大，启动惯性滚动
            if abs(self.velocity) > self.MIN_VELOCITY * 100:
                self.momentum_timer.start()

            event.accept()

    def _handle_touch_cancel(self, event):
        """处理触摸取消"""
        self.is_touching = False
        self.momentum_timer.stop()
        event.accept()

    def _momentum_scroll(self):
        """惯性滚动"""
        if abs(self.velocity) < self.MIN_VELOCITY * 100:
            self.momentum_timer.stop()
            self.velocity = 0
            return

        # 应用速度
        current_value = self.verticalScrollBar().value()
        new_value = current_value - int(self.velocity * 0.016)  # 16ms间隔

        # 边界检测和弹性效果
        max_value = self.verticalScrollBar().maximum()
        if new_value < 0:
            new_value = 0
            self.velocity *= -0.5  # 反弹
        elif new_value > max_value:
            new_value = max_value
            self.velocity *= -0.5  # 反弹

        self.verticalScrollBar().setValue(new_value)

        # 应用摩擦力
        self.velocity *= self.FRICTION

    def mousePressEvent(self, event):
        """鼠标按下事件（用于非触摸屏环境测试）"""
        if event.button() == Qt.LeftButton:
            # 停止动画
            self.scroll_animation.stop()
            self.momentum_timer.stop()

            self.touch_start_pos = event.position()
            self.touch_start_time = time.time()
            self.last_touch_pos = self.touch_start_pos
            self.last_touch_time = self.touch_start_time
            self.is_touching = True
            self.velocity = 0
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """鼠标移动事件（用于非触摸屏环境测试）"""
        if self.is_touching and event.buttons() & Qt.LeftButton:
            current_pos = event.position()
            current_time = time.time()

            if self.last_touch_pos:
                delta_y = (current_pos.y() - self.last_touch_pos.y()) * self.SWIPE_SENSITIVITY

                time_delta = current_time - self.last_touch_time
                if time_delta > 0:
                    self.velocity = delta_y / time_delta

                current_value = self.verticalScrollBar().value()
                new_value = current_value - int(delta_y)
                new_value = max(0, min(new_value, self.verticalScrollBar().maximum()))
                self.verticalScrollBar().setValue(new_value)

            self.last_touch_pos = current_pos
            self.last_touch_time = current_time
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """鼠标释放事件（用于非触摸屏环境测试）"""
        if event.button() == Qt.LeftButton and self.is_touching:
            self.is_touching = False

            if abs(self.velocity) > self.MIN_VELOCITY * 100:
                self.momentum_timer.start()

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        """鼠标滚轮事件（保留原有功能）"""
        # 使用动画实现平滑滚动
        delta = event.angleDelta().y()
        current_value = self.verticalScrollBar().value()

        # 计算目标位置
        scroll_amount = delta * 0.5  # 调整滚动速度
        target_value = current_value - scroll_amount
        target_value = max(0, min(target_value, self.verticalScrollBar().maximum()))

        # 启动动画
        self.scroll_animation.stop()
        self.scroll_animation.setDuration(200)  # 动画时长
        self.scroll_animation.setStartValue(current_value)
        self.scroll_animation.setEndValue(int(target_value))
        self.scroll_animation.start()

        event.accept()