import os
import sys
import json
import requests
import hashlib
import zipfile
import shutil
import subprocess
import time
from datetime import datetime
from tkinter import Tk, Label, messagebox, Toplevel
from tkinter.ttk import Progressbar

# 服务器基础地址
SERVER_BASE_URL = "http://www.marxmake.com/firmware/LTChat"
VERSION_INFO_URL = f"{SERVER_BASE_URL}/version_info.json"  # 版本信息接口
MAIN_APP_FILE = os.path.join(os.path.dirname(__file__), "app/MovePic/manager.py")  # 程序入口

# 路径配置
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(PROJECT_DIR, "app")
BACKUP_DIR = os.path.join(PROJECT_DIR, "backup")
TEMP_DIR = os.path.join(PROJECT_DIR, "temp")
LOG_FILE = os.path.join(PROJECT_DIR, "update_log.txt")
LOCAL_VERSION_FILE = os.path.join(PROJECT_DIR, "version.txt")


def log(message):
    """记录日志到文件和控制台"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    print(log_entry.strip())
    try:
        with open(LOG_FILE, 'a', encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"日志写入失败：{e}")


def get_local_version():
    """获取本地当前版本（统一转为大写）"""
    try:
        if os.path.exists(LOCAL_VERSION_FILE):
            with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
                return f.read().strip().upper()
        else:
            with open(LOCAL_VERSION_FILE, "w", encoding="utf-8") as f:
                f.write("V0.0.0")
            return "V0.0.0"
    except Exception as e:
        log(f"获取本地版本失败：{e}")
        return "V0.0.0"


def get_remote_version():
    """从服务器获取最新版本"""
    try:
        log(f"检查更新：{VERSION_INFO_URL}")
        response = requests.get(VERSION_INFO_URL, timeout=15)
        response.raise_for_status()
        return json.loads(response.text)
    except Exception as e:
        log(f"获取服务器版本失败：{e}")
        return None


def calculate_checksum(file_path):
    """计算文件的SHA256校验和"""
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        log(f"计算校验和失败：{e}")
        return None


def download_update(download_url, save_path, progress_bar, status_label):
    """下载更新包到临时目录，带进度条更新"""
    try:
        status_label.config(text="正在下载更新包...")
        root.update_idletasks()

        log(f"开始下载：{download_url}")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0

        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
                    if total_size > 0:
                        progress = int((downloaded_size / total_size) * 100)
                        progress_bar['value'] = progress
                        root.update_idletasks()

        status_label.config(text="下载完成")
        root.update_idletasks()
        log(f"下载完成：{save_path}")
        return True
    except Exception as e:
        log(f"下载失败：{e}")
        if os.path.exists(save_path):
            os.remove(save_path)
        return False


def backup_current_version(status_label):
    """备份当前版本（用于回滚）"""
    try:
        status_label.config(text="正在备份当前版本...")
        root.update_idletasks()
        log("开始备份当前版本...")

        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        os.makedirs(BACKUP_DIR, exist_ok=True)

        if os.path.exists(APP_DIR):
            shutil.copytree(APP_DIR, os.path.join(BACKUP_DIR, "app"))
            log("应用文件备份完成")

        if os.path.exists(LOCAL_VERSION_FILE):
            shutil.copy2(LOCAL_VERSION_FILE, os.path.join(BACKUP_DIR, "version.txt"))
            log("版本备份完成")

        status_label.config(text="备份完成")
        root.update_idletasks()
        return True
    except Exception as e:
        log(f"备份失败：{e}")
        if os.path.exists(BACKUP_DIR):
            shutil.rmtree(BACKUP_DIR)
        return False


def extract_update(zip_path, progress_bar, status_label):
    """解压更新到临时目录，带进度条更新"""
    try:
        status_label.config(text="正在解压更新包...")
        root.update_idletasks()
        log(f"解压更新包：{zip_path}")

        os.makedirs(TEMP_DIR, exist_ok=True)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            total_files = len(zip_ref.namelist())
            extracted_files = 0
            for file in zip_ref.namelist():
                zip_ref.extract(file, TEMP_DIR)
                extracted_files += 1
                progress = int((extracted_files / total_files) * 100)
                progress_bar['value'] = progress
                root.update_idletasks()

        status_label.config(text="解压完成")
        root.update_idletasks()
        log("解压完成")
        return True
    except Exception as e:
        log(f"解压失败：{e}")
        return False


def apply_update(status_label):
    """替换应用目录为新文件（兼容两种ZIP结构）"""
    try:
        status_label.config(text="正在应用更新...")
        root.update_idletasks()
        log("开始应用更新...")

        if os.path.exists(APP_DIR):
            shutil.rmtree(APP_DIR)

        # 处理ZIP包内是否有根目录的两种情况
        temp_items = os.listdir(TEMP_DIR)
        if len(temp_items) == 1 and os.path.isdir(os.path.join(TEMP_DIR, temp_items[0])):
            extract_dir = os.path.join(TEMP_DIR, temp_items[0])
        else:
            extract_dir = TEMP_DIR

        shutil.move(extract_dir, APP_DIR)

        status_label.config(text="更新应用完成")
        root.update_idletasks()
        log("更新应用完成")
        return True
    except Exception as e:
        log(f"应用更新失败：{e}")
        return False


def clean_up(temp_file=None):
    """清理临时文件"""
    try:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)
            log(f"删除临时文件：{temp_file}")
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
            log("清理临时目录")
    except Exception as e:
        log(f"清理失败：{e}")


def rollback():
    try:
        log("开始回滚...")
        if not os.path.exists(BACKUP_DIR):
            log("无备份可回滚")
            return False
        if os.path.exists(APP_DIR):
            shutil.rmtree(APP_DIR)
        shutil.copytree(os.path.join(BACKUP_DIR, "app"), APP_DIR)
        shutil.copy2(os.path.join(BACKUP_DIR, "version.txt"), LOCAL_VERSION_FILE)
        shutil.rmtree(BACKUP_DIR)
        log("回滚完成")
        return True
    except Exception as e:
        log(f"回滚失败：{e}")
        return False


def test_new_version(status_label):
    """测试新版本是否可以启动（使用sudo）"""
    try:
        status_label.config(text="正在测试新版本...")
        root.update_idletasks()
        log("测试新版本启动...")

        if not os.path.exists(MAIN_APP_FILE):
            log(f"主程序文件缺失：{MAIN_APP_FILE}")
            return False

        process = subprocess.Popen(
            ["sudo", sys.executable, MAIN_APP_FILE, "runserver", "--test"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # 等待10秒判断是否崩溃
        for _ in range(10):
            time.sleep(1)
            if process.poll() is not None:
                break

        return_code = process.poll()
        if return_code is None:
            process.terminate()
            status_label.config(text="新版本测试通过")
            log("新版本测试通过")
            return True
        else:
            log(f"新版本启动失败，返回码：{return_code}")
            log(f"错误信息：{process.stderr.read()}")
            return False
    except Exception as e:
        log(f"测试失败：{e}")
        return False


def update_version_file(new_version):
    """更新本地版本记录"""
    try:
        with open(LOCAL_VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(new_version)
        log(f"版本文件更新为：{new_version}")
        return True
    except Exception as e:
        log(f"版本文件更新失败：{e}")
        return False


def run_application():
    """启动实际应用程序（使用sudo）"""
    try:
        log("启动应用程序（管理员权限）...")
        os.execvp("sudo", ["sudo", sys.executable, MAIN_APP_FILE])
    except Exception as e:
        log(f"应用启动失败：{e}")
        log("尝试回滚...")
        if rollback():
            run_application()
        else:
            log("回滚失败，无法启动")


def show_temp_message(message, duration=2000):
    """显示临时消息，自动关闭"""
    top = Toplevel(root)
    top.overrideredirect(True)
    top.title("提示")

    # 居中显示
    window_width = 250
    window_height = 100
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    top.geometry(f"{window_width}x{window_height}+{x}+{y}")

    Label(top, text=message, padx=20, pady=20).pack()
    top.update_idletasks()

    # 定时关闭
    top.after(duration, top.destroy)
    return top


def main():
    global root
    # 创建主窗口
    root = Tk()
    root.overrideredirect(True)  # 隐藏标题栏按钮
    root.title('更新进度')

    # 窗口居中
    window_width = 300
    window_height = 150
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - window_width) // 2
    y = (screen_height - window_height) // 2
    root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    # 状态标签和进度条
    status_label = Label(root, text='正在检查更新...')
    status_label.pack(pady=10)
    progress_bar = Progressbar(root, length=200, mode='determinate')
    progress_bar.pack(pady=10)

    log("=======自动更新程序启动========")
    local_version = get_local_version()
    log(f"当前版本：{local_version}")

    remote_info = get_remote_version()
    if not remote_info:
        log("无法获取服务器版本，启动当前应用")
        show_temp_message("无法获取服务器版本，启动当前应用")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    # 处理版本信息
    remote_version = remote_info.get("system_version", "未知").upper()
    update_file = remote_info.get("update_file_name")
    remote_checksum = remote_info.get("checksum", "").lower()

    log(f"服务器最新版本：{remote_version}")
    if local_version == remote_version:
        log("已是最新版本，启动应用")
        # 显示临时消息后自动关闭并启动应用
        show_temp_message("已是最新版本，启动应用")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    if not update_file:
        log("服务器未提供更新包名称")
        show_temp_message("服务器未提供更新包名称")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    download_url = f"{SERVER_BASE_URL}/{update_file}"
    temp_zip = os.path.join(TEMP_DIR, os.path.basename(update_file))

    # 执行备份
    if not backup_current_version(status_label):
        log("备份失败，取消更新")
        show_temp_message("备份失败，取消更新")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    # 执行下载
    if not download_update(download_url, temp_zip, progress_bar, status_label):
        log("下载更新包失败，启动当前应用")
        clean_up(temp_zip)
        show_temp_message("下载更新包失败，启动当前应用")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    # 校验和检查
    if remote_checksum:
        local_checksum = calculate_checksum(temp_zip)
        if local_checksum and local_checksum.lower() != remote_checksum:
            log(f"校验和不匹配（本地：{local_checksum}，服务器：{remote_checksum}）")
            clean_up(temp_zip)
            show_temp_message("校验和不匹配，启动当前应用")
            root.after(2000, lambda: [root.destroy(), run_application()])
            root.mainloop()
            return

    # 执行解压
    if not extract_update(temp_zip, progress_bar, status_label):
        log("解压失败，尝试回滚")
        clean_up(temp_zip)
        rollback()
        show_temp_message("解压失败，已回滚")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    # 应用更新
    if not apply_update(status_label):
        log("应用更新失败，尝试回滚")
        clean_up(temp_zip)
        rollback()
        show_temp_message("应用更新失败，已回滚")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    clean_up(temp_zip)

    # 测试新版本
    if not test_new_version(status_label):
        log("新版本测试失败，开始回滚")
        rollback()
        show_temp_message("新版本测试失败，已回滚")
        root.after(2000, lambda: [root.destroy(), run_application()])
        root.mainloop()
        return

    # 更新完成
    update_version_file(remote_version)
    show_temp_message("软件更新成功，即将启动应用")
    root.after(2000, lambda: [root.destroy(), run_application()])
    root.mainloop()


if __name__ == "__main__":
    main()
