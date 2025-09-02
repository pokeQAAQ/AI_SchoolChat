# -*- coding: utf-8 -*-
"""
持久录音管理器 - 解决每次录音初始化延迟的问题
通过预启动arecord进程，实现零延迟录音开始
"""
import os
import time
import signal
import shutil
import subprocess
import threading
from PySide6.QtCore import QObject, Signal, QMutex, QMutexLocker


class PersistentRecordManager(QObject):
    """持久录音管理器 - 预启动arecord进程，零延迟录音"""
    
    update_text = Signal(str)          # 录音状态更新信号
    recording_finished = Signal(str)   # 录音完成信号（返回文件信息）
    
    def __init__(self, device_index=None):
        super().__init__()
        self.device_index = device_index
        self.device = None  # arecord 的 -D 设备名，可选
        self.out_path = "recording.wav"
        self._proc = None  # arecord 子进程句柄
        self.mutex = QMutex()
        self._is_prepared = False
        self._is_recording = False
        self._prepare_thread = None
        
        # 录音参数（ASR 要求）
        self.rate = 16000
        self.channels = 1
        self.sample_fmt = "S16_LE"  # 16-bit
        
        # 自动预启动
        self.prepare_recording()
    
    def _has_arecord(self):
        return shutil.which("arecord") is not None
    
    def prepare_recording(self):
        """预启动录音进程，减少延迟"""
        if self._is_prepared or (self._prepare_thread and self._prepare_thread.is_alive()):
            return
            
        self._prepare_thread = threading.Thread(target=self._prepare_arecord, daemon=True)
        self._prepare_thread.start()
    
    def _prepare_arecord(self):
        """在后台预先启动arecord进程"""
        if not self._has_arecord():
            print("⚠️ 系统没有arecord命令")
            return
            
        try:
            # 先删旧文件
            try:
                if os.path.exists(self.out_path):
                    os.remove(self.out_path)
            except:
                pass
                
            cmd = [
                "arecord",
                "-q",                    # 静默
                "-t", "wav",             # 输出 wav
                "-f", self.sample_fmt,   # S16_LE
                "-r", str(self.rate),    # 16000 Hz
                "-c", str(self.channels) # 单声道
            ]
            
            if self.device:
                cmd += ["-D", self.device]
            cmd += [self.out_path]
            
            print("🚀 预启动 arecord 进程:", " ".join(cmd))
            with QMutexLocker(self.mutex):
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            
            # 等待进程启动完成
            time.sleep(0.1)
            if self._proc.poll() is None:
                self._is_prepared = True
                print("✅ arecord 进程已预启动，录音零延迟准备就绪")
            else:
                print("❌ arecord 进程预启动失败")
                
        except Exception as e:
            print(f"❌ 预启动失败: {e}")
    
    def start_recording(self):
        """开始实际录音（零延迟）"""
        with QMutexLocker(self.mutex):
            if self._is_recording:
                return
            self._is_recording = True
            
        if self._is_prepared and self._proc and self._proc.poll() is None:
            self.update_text.emit("🎙️ 开始录音...（arecord预启动，零延迟）")
            print("✅ 录音已开始（零延迟模式）")
        else:
            self.update_text.emit("⚠️ 录音进程未准备好，正在启动...")
            self.prepare_recording()
            time.sleep(0.2)  # 给进程一点启动时间
            with QMutexLocker(self.mutex):
                if self._proc and self._proc.poll() is None:
                    self.update_text.emit("🎙️ 开始录音...（请对着麦克风说话）")
    
    def stop_recording(self):
        """停止录音"""
        with QMutexLocker(self.mutex):
            if not self._is_recording:
                return
            self._is_recording = False
            
        # 停止arecord进程
        if self._proc and self._proc.poll() is None:
            try:
                # 优先发 SIGINT 让 arecord 写好 WAV 头
                self._proc.send_signal(signal.SIGINT)
                for _ in range(40):  # 最多等 2 秒
                    if self._proc.poll() is not None:
                        break
                    time.sleep(0.05)
            except Exception as e:
                print(f"停止录音时出错: {e}")
                
        # 兜底：如果还没退出就强制终止
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1)
            except:
                try:
                    self._proc.kill()
                except:
                    pass
                    
        # 清理状态
        self._is_prepared = False
        self._proc = None
        
        # 检查文件并发送结果
        if os.path.exists(self.out_path) and os.path.getsize(self.out_path) >= 1024:
            file_size = os.path.getsize(self.out_path)
            self.recording_finished.emit(f"✅ 录音已保存（文件：{self.out_path}，大小：{file_size}字节）")
        else:
            self.recording_finished.emit("❌ 录音无效：文件太小或不存在")
        
        # 为下次录音重新预启动
        threading.Timer(0.5, self.prepare_recording).start()
        
    def cleanup(self):
        """清理资源"""
        with QMutexLocker(self.mutex):
            self._is_recording = False
            self._is_prepared = False
            
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except:
                try:
                    self._proc.kill()
                except:
                    pass
        
        print("🧹 持久录音管理器资源已清理")