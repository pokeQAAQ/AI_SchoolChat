import os
import subprocess
import sys
import time
import threading
import signal
import logging
import psutil

# 信号文件路径
SIGNAL_FILE = "/tmp/gpio_low_signal"

# 配置参数
TIMEOUT_SECONDS = 30
VENV_PYTHON = "/home/orangepi/test1/bin/python3"
TEST1_PATH = "/home/orangepi/program/LTChat_updater/app/test1/test1.py"
MOVEPIC_PATH = "/home/orangepi/program/LTChat_updater/app/MovePic/MovePic.py"
TEST1_WM_CLASS = "test1.py"
MOVEPIC_WM_CLASS = "MovePic.py"
GPIO_SCRIPT_PATH = os.path.join("/home/orangepi/program/LTChat_updater/gpio_monitor.sh")
TEST1_LOG = "/home/orangepi/test1.log"  # test1日志文件

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('AppManager')


class ApplicationManager:
    def __init__(self):
        os.environ['DISPLAY'] = ':0'
        os.environ['XAUTHORITY'] = '/home/orangepi/.Xauthority'

        self.is_running = True
        self.last_activity_time = time.time()
        self.current_program = "test1"
        self.movepic_process = None
        self.test1_process = None  # 记录当前test1进程
        self.test1_last_pid = None  # 记录上一次test1的PID（用于检测是否重启）
        self.test1_last_window_id = None  # 记录上一次窗口ID（用于检测窗口是否重建）
        self.switch_lock = threading.Lock()
        self.gpio_script_process = None
        self.screen_width, self.screen_height = self.get_screen_resolution()

        # 切换控制参数
        self.last_switch_time = 0
        self.SWITCH_COOLDOWN = 3
        self.start_time = time.time()
        self.STARTUP_PROTECTION = 5

        # 重启控制
        self.test1_restart_count = 0
        self.MAX_RESTART_COUNT = 5

        # 启动GPIO监控脚本
        self.start_gpio_script()

        logger.info("应用管理器启动")
        self.start_test1()
        self.start_monitors()

    def get_screen_resolution(self):
        """获取屏幕分辨率"""
        try:
            # 尝试多种方式获取分辨率
            methods = [
                "xwininfo -root | grep 'geometry' | awk '{print $2}'",
                "xrandr | grep '*' | head -n 1 | awk '{print $1}'",
                "xdpyinfo | grep 'dimensions:' | awk '{print $2}'"
            ]
            for cmd in methods:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True
                )
                output = result.stdout.strip()
                if 'x' in output:
                    width, height = output.split('x')
                    return int(width), int(height)
            logger.warning("无法获取屏幕分辨率，使用默认值 1024x600")
            return 1024, 600
        except Exception as e:
            logger.error(f"获取屏幕分辨率失败: {e}")
            return 1024, 600

    def start_gpio_script(self):
        """启动bash脚本监控GPIO"""
        try:
            if not os.path.exists(GPIO_SCRIPT_PATH):
                logger.error(f"GPIO脚本不存在: {GPIO_SCRIPT_PATH}")
                return
            self.gpio_script_process = subprocess.Popen(
                f"sudo {GPIO_SCRIPT_PATH}",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            logger.info("GPIO监控脚本已启动")
            threading.Thread(target=self.monitor_gpio_script_output, daemon=True).start()
        except Exception as e:
            logger.error(f"启动GPIO脚本失败: {e}")

    def monitor_gpio_script_output(self):
        """监控bash脚本的输出"""
        if not self.gpio_script_process:
            return
        while self.is_running:
            if self.gpio_script_process.poll() is not None:
                logger.error("GPIO监控脚本已退出，尝试重启...")
                self.start_gpio_script()
                time.sleep(1)
                continue
            line = self.gpio_script_process.stdout.readline()
            if line:
                logger.info(f"GPIO脚本: {line.strip()}")
            err_line = self.gpio_script_process.stderr.readline()
            if err_line:
                logger.error(f"GPIO脚本错误: {err_line.strip()}")
            time.sleep(0.1)

    def start_test1(self):
        """启动test1，记录PID用于跟踪是否崩溃"""
        logger.info("启动test1")
        try:
            self.test1_restart_count = 0
            self.kill_processes_by_name("test1.py")

            # 记录启动日志
            with open(TEST1_LOG, 'a') as f:
                f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动test1 =====")

            # 启动test1并记录PID
            self.test1_process = subprocess.Popen(
                [VENV_PYTHON, TEST1_PATH],
                stdout=open(TEST1_LOG, 'a'),
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            self.test1_last_pid = self.test1_process.pid  # 记录当前PID
            logger.info(f"test1进程已启动（PID: {self.test1_last_pid}）")

            # 等待窗口创建（20秒超时）
            if not self.wait_for_window(TEST1_WM_CLASS, timeout=20):
                if self.test1_process.poll() is None:
                    logger.warning(f"test1窗口未检测到，但进程（PID: {self.test1_last_pid}）仍在运行")
                    self.activate_window(TEST1_WM_CLASS)
                    self.force_fullscreen(TEST1_WM_CLASS, force=False)  # 非强制执行
                else:
                    logger.error(f"test1进程（PID: {self.test1_last_pid}）已退出，尝试重启")
                    self.restart_test1()
                    return

            # 记录窗口ID
            self.test1_last_window_id = self.find_window_id(TEST1_WM_CLASS)
            self.activate_window(TEST1_WM_CLASS)
            self.force_fullscreen(TEST1_WM_CLASS, force=False)
            self.current_program = "test1"
            self.last_activity_time = time.time()
            logger.info(f"test1启动成功（窗口ID: {self.test1_last_window_id}）")
        except Exception as e:
            logger.error(f"启动test1失败: {e}")
            self.restart_test1()

    def restart_test1(self):
        """重启test1，跟踪重启原因"""
        self.test1_restart_count += 1
        logger.warning(f"重启test1进程（连续第{self.test1_restart_count}次）")

        if self.test1_restart_count >= self.MAX_RESTART_COUNT:
            logger.critical(f"test1连续重启{self.MAX_RESTART_COUNT}次，可能存在严重问题，停止重启")
            return

        self.stop_test1(force_kill=True)
        time.sleep(2)
        self.start_test1()

    def stop_test1(self, force_kill=False):
        """停止test1进程"""
        if self.test1_process:
            pid = self.test1_process.pid
            try:
                logger.info(f"停止test1（PID: {pid}）")
                if force_kill:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                else:
                    self.test1_process.terminate()
                    self.test1_process.wait(timeout=2)
                    if self.test1_process.poll() is None:
                        self.test1_process.kill()
                self.test1_process = None
                self.kill_processes_by_name("test1.py")
            except Exception as e:
                logger.error(f"停止test1（PID: {pid}）失败: {e}")

    def start_movepic(self):
        logger.info("启动movepic")
        try:
            self.kill_processes_by_name("MovePic.py")
            self.movepic_process = subprocess.Popen(
                [VENV_PYTHON, MOVEPIC_PATH],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            self.wait_for_window(MOVEPIC_WM_CLASS, 5)
            self.activate_window(MOVEPIC_WM_CLASS)
            self.current_program = "movepic"
        except Exception as e:
            logger.error(f"启动movepic失败: {e}")

    def stop_movepic(self, force_kill=False):
        """停止movepic"""
        if self.movepic_process:
            try:
                logger.info("停止movepic")
                if force_kill:
                    os.killpg(os.getpgid(self.movepic_process.pid), signal.SIGKILL)
                else:
                    self.movepic_process.terminate()
                    self.movepic_process.wait(timeout=2)
                    if self.movepic_process.poll() is None:
                        self.movepic_process.kill()
                self.movepic_process = None
                self.kill_processes_by_name("MovePic.py")
                logger.info("movepic已完全停止")
            except Exception as e:
                logger.error(f"停止movepic失败: {e}")

    def switch_to_test1(self):
        with self.switch_lock:
            current_time = time.time()
            if current_time - self.last_switch_time < self.SWITCH_COOLDOWN:
                logger.info(f"切换冷却中（{self.SWITCH_COOLDOWN}秒），忽略切换到test1")
                return
            if self.current_program == "test1":
                return

            logger.info("切换到test1")
            self.stop_movepic(force_kill=True)
            time.sleep(0.5)

            if not self.is_test1_alive():
                logger.warning("test1进程不存在，重新启动")
                self.start_test1()
                self.last_switch_time = current_time
                return

            if not self.find_window_id(TEST1_WM_CLASS):
                logger.warning("test1窗口不存在，尝试重新激活")
                if not self.activate_window(TEST1_WM_CLASS):
                    logger.error("激活test1窗口失败，重启进程")
                    self.restart_test1()
                    self.last_switch_time = current_time
                    return

            self.activate_window(TEST1_WM_CLASS)
            self.force_fullscreen(TEST1_WM_CLASS, force=False)
            self.wake_up_window(TEST1_WM_CLASS)

            time.sleep(1)
            if not self.find_window_id(TEST1_WM_CLASS):
                logger.error("窗口激活后仍不可见，重启test1")
                self.restart_test1()
                self.last_switch_time = current_time
                return

            self.current_program = "test1"
            self.last_activity_time = time.time()
            self.last_switch_time = current_time
            logger.info("成功切换到test1")

    def is_test1_alive(self):
        """检查test1进程是否存活"""
        if not self.test1_process or self.test1_process.poll() is not None:
            return False
        try:
            os.kill(self.test1_process.pid, 0)
            return True
        except OSError:
            return False

    def switch_to_movepic(self):
        with self.switch_lock:
            current_time = time.time()
            if current_time - self.last_switch_time < self.SWITCH_COOLDOWN:
                logger.info(f"切换冷却中（{self.SWITCH_COOLDOWN}秒），忽略切换到movepic")
                return
            if self.current_program == "movepic":
                return

            logger.info("切换到movepic")
            self.start_movepic()
            self.last_switch_time = current_time

    def wait_for_window(self, wm_class, timeout=20):
        """等待窗口创建，同时监控进程是否存活"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            window_id = self.find_window_id(wm_class)
            if window_id:
                logger.info(f"{wm_class}窗口已创建（ID: {window_id}）")
                return True
            # 监控test1进程是否存活
            if wm_class == TEST1_WM_CLASS and self.test1_process:
                if self.test1_process.poll() is not None:
                    logger.error(f"{wm_class}进程已退出（退出码: {self.test1_process.returncode}）")
                    return False
            time.sleep(0.5)
        logger.warning(f"{wm_class}窗口未在{timeout}秒内创建")
        return False

    def find_window_id(self, wm_class):
        try:
            cmd = f"wmctrl -lx | grep -i '{wm_class}' | head -n 1 | awk '{{print $1}}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None
        except Exception as e:
            logger.error(f"查找窗口ID失败: {e}")
            return None

    def activate_window(self, wm_class):
        window_id = self.find_window_id(wm_class)
        if not window_id:
            logger.warning(f"未找到{wm_class}窗口")
            return False
        try:
            subprocess.run(f"wmctrl -i -a {window_id}", shell=True, check=True)
            subprocess.run(f"wmctrl -i -r {window_id} -b add,maximized_vert,maximized_horz", shell=True)
            subprocess.run(f"wmctrl -i -r {window_id} -b add,undecorated", shell=True)
            logger.info(f"已激活窗口: {wm_class}（ID: {window_id}）")
            return True
        except Exception as e:
            logger.error(f"激活窗口失败: {e}")
            return False

    def force_fullscreen(self, wm_class, force=False):
        """优化全屏逻辑：仅在窗口未全屏时执行，减少干扰"""
        window_id = self.find_window_id(wm_class)
        if not window_id:
            logger.warning(f"未找到{wm_class}窗口，无法强制全屏")
            return False

        try:
            # 检查窗口是否已全屏
            result = subprocess.run(
                f"wmctrl -i -lG | grep {window_id}",
                shell=True,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # 窗口信息格式：ID 桌面 X Y 宽度 高度 ...
                parts = result.stdout.strip().split()
                if len(parts) >= 6:
                    win_width, win_height = int(parts[4]), int(parts[5])
                    # 若窗口尺寸接近屏幕分辨率，视为已全屏
                    if abs(win_width - self.screen_width) < 10 and abs(win_height - self.screen_height) < 10:
                        logger.info(f"{wm_class}已全屏，无需操作（窗口尺寸: {win_width}x{win_height}）")
                        return True

            # 非强制模式下，仅在未全屏时执行
            if not force:
                logger.info(f"{wm_class}未全屏，执行全屏操作")
                subprocess.run(
                    f"wmctrl -i -r {window_id} -b add,fullscreen",
                    shell=True,
                    check=True
                )
                subprocess.run(
                    f"wmctrl -i -r {window_id} -e 0,0,0,{self.screen_width},{self.screen_height}",
                    shell=True,
                    check=True
                )
            else:
                # 强制模式（仅在必要时使用）
                subprocess.run(
                    f"xdotool windowactivate {window_id} key F11",
                    shell=True
                )
            logger.info(f"已设置{wm_class}全屏，分辨率: {self.screen_width}x{self.screen_height}")
            return True
        except Exception as e:
            logger.error(f"设置全屏失败: {e}")
            return False

    def wake_up_window(self, wm_class):
        window_id = self.find_window_id(wm_class)
        if not window_id:
            return False
        try:
            subprocess.run(
                f"xdotool windowactivate {window_id} mousemove --window {window_id} 100 100 click 1",
                shell=True,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info(f"已唤醒窗口: {wm_class}")
            return True
        except Exception as e:
            logger.warning(f"唤醒窗口失败: {e}")
            return False

    def is_process_running(self, match_string):
        try:
            for proc in psutil.process_iter(['cmdline']):
                if proc.info['cmdline'] and any(match_string in cmd for cmd in proc.info['cmdline']):
                    return True
            return False
        except Exception as e:
            logger.error(f"检查进程存活失败: {e}")
            return False

    def start_monitors(self):
        threading.Thread(target=self.monitor_user_input, daemon=True).start()
        threading.Thread(target=self.monitor_low_signal, daemon=True).start()
        threading.Thread(target=self.monitor_timeout, daemon=True).start()
        threading.Thread(target=self.monitor_test1_health, daemon=True).start()
        logger.info("监控线程启动完成")

    def monitor_user_input(self):
        try:
            import evdev
            from evdev import InputDevice, ecodes
            devices = [InputDevice(p) for p in evdev.list_devices()]
            target_devices = [d for d in devices if
                              ecodes.EV_KEY in d.capabilities() or ecodes.EV_REL in d.capabilities()]
            if not target_devices:
                logger.warning("无输入设备")
                return
            logger.info(f"监控{len(target_devices)}个输入设备")
            for dev in target_devices:
                threading.Thread(target=self.listen_device_input, args=(dev,), daemon=True).start()
        except ImportError:
            logger.warning("未安装evdev库，无法监控输入设备")
        except Exception as e:
            logger.error(f"输入监控异常: {e}")

    def listen_device_input(self, dev):
        try:
            import evdev
            logger.info(f"监听设备: {dev.name}")
            for event in dev.read_loop():
                if not self.is_running:
                    return
                if time.time() - self.start_time < self.STARTUP_PROTECTION:
                    continue
                if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    self.last_activity_time = time.time()
                    if self.current_program == 'movepic':
                        logger.info("用户按键输入，切换到test1")
                        self.switch_to_test1()
                elif event.type in [evdev.ecodes.EV_REL, evdev.ecodes.EV_ABS]:
                    if abs(event.value) > 5:
                        self.last_activity_time = time.time()
                        if self.current_program == 'movepic':
                            logger.info("用户移动输入，切换到test1")
                            self.switch_to_test1()
        except Exception as e:
            logger.error(f"设备监听异常: {e}")

    def monitor_low_signal(self):
        logger.info(f"开始监控低电平信号（信号文件: {SIGNAL_FILE}）")
        while self.is_running:
            try:
                if os.path.exists(SIGNAL_FILE):
                    logger.info(f"检测到信号文件{SIGNAL_FILE}，触发切换到test1")
                    subprocess.run(f"sudo rm -f {SIGNAL_FILE}", shell=True, check=True)
                    if self.current_program == 'movepic':
                        self.switch_to_test1()
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"低电平监控异常: {e}")
                time.sleep(1)

    def monitor_timeout(self):
        logger.info("开始监控超时")
        while self.is_running:
            try:
                if (self.current_program == 'test1' and
                        time.time() - self.start_time > self.STARTUP_PROTECTION and
                        time.time() - self.last_activity_time > TIMEOUT_SECONDS):
                    logger.info(f"{TIMEOUT_SECONDS}秒无活动，切换到movepic")
                    self.switch_to_movepic()
                time.sleep(1)
            except Exception as e:
                logger.error(f"超时监控异常: {e}")

    def monitor_test1_health(self):
        """增强健康监控：跟踪PID和窗口ID变化，判断是否崩溃/重建"""
        logger.info("启动test1健康监控")
        while self.is_running:
            try:
                if self.current_program == "test1":
                    # 1. 检查进程是否存活（核心）
                    if not self.is_test1_alive():
                        logger.warning(f"test1进程（原PID: {self.test1_last_pid}）已退出，重启")
                        self.restart_test1()
                        time.sleep(5)
                        continue

                    # 2. 检查PID是否变化（判断是否被重启）
                    current_pid = self.test1_process.pid
                    if current_pid != self.test1_last_pid:
                        logger.warning(
                            f"test1进程PID变化（原: {self.test1_last_pid} → 新: {current_pid}），可能自动重启过")
                        self.test1_last_pid = current_pid  # 更新PID记录

                    # 3. 检查窗口ID是否变化（判断窗口是否重建）
                    current_window_id = self.find_window_id(TEST1_WM_CLASS)
                    if current_window_id and current_window_id != self.test1_last_window_id:
                        logger.warning(
                            f"test1窗口ID变化（原: {self.test1_last_window_id} → 新: {current_window_id}），可能窗口重建")
                        self.test1_last_window_id = current_window_id  # 更新窗口ID记录
                        self.activate_window(TEST1_WM_CLASS)  # 激活新窗口

                    # 4. 按需执行全屏（仅在窗口未全屏时）
                    self.force_fullscreen(TEST1_WM_CLASS, force=False)

                time.sleep(5)  # 每5秒检查一次
            except Exception as e:
                logger.error(f"健康监控异常: {e}")
                time.sleep(10)

    def kill_processes_by_name(self, match_string):
        try:
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    if proc.info['cmdline'] and any(match_string in cmd for cmd in proc.info['cmdline']):
                        logger.info(f"终止进程{match_string}（PID: {proc.pid}）")
                        try:
                            proc.terminate()
                            proc.wait(2)
                        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                            proc.kill()
                except Exception as e:
                    continue
            logger.info(f"确保所有{match_string}进程已终止")
        except Exception as e:
            logger.error(f"终止进程失败: {e}")

    def run(self):
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("退出")
        finally:
            self.is_running = False
            self.terminate_all()

    def terminate_all(self):
        if self.gpio_script_process:
            try:
                self.gpio_script_process.terminate()
                self.gpio_script_process.wait(2)
                logger.info("GPIO监控脚本已停止")
            except Exception as e:
                logger.error(f"停止GPIO脚本失败: {e}")
        self.stop_movepic(force_kill=True)
        self.stop_test1(force_kill=True)
        logger.info("所有进程已终止")


def main():
    if os.geteuid() != 0:
        logger.warning("需要root权限运行，尝试获取...")
        os.execvp('sudo', ['sudo', 'python3', os.path.abspath(__file__)] + sys.argv[1:])
        return

    manager = ApplicationManager()

    def handle_exit(signum, frame):
        logger.info(f"接收到信号 {signum}，正在退出...")
        manager.is_running = False
        manager.terminate_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    try:
        manager.run()
    except Exception as e:
        logger.critical(f"未处理的异常: {e}")
        manager.terminate_all()
        sys.exit(1)


if __name__ == "__main__":
    main()
