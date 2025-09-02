# -*- coding: utf-8 -*-
"""
知识库上传服务器
用于接收手机端上传的学校知识信息和文件
"""
import os
import json
import re
import mimetypes
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template_string, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
from knowledge_manager import knowledge_manager
import socket
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)


# 配置知识库文件存储
KNOWLEDGE_BASE_DIR = os.environ.get('KNOWLEDGE_BASE_DIR', './data/knowledge_base')
KNOWLEDGE_BASE_MAX_BYTES = int(os.environ.get('KNOWLEDGE_BASE_MAX_BYTES', '1073741824'))  # 1GB
KNOWLEDGE_BASE_MAX_FILE_BYTES = int(os.environ.get('KNOWLEDGE_BASE_MAX_FILE_BYTES', '10485760'))  # 10MB

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.md', '.markdown', '.txt'}

# 设置Flask最大内容长度
app.config['MAX_CONTENT_LENGTH'] = KNOWLEDGE_BASE_MAX_FILE_BYTES

def ensure_knowledge_base_dir():
    """确保知识库目录存在"""
    if not os.path.exists(KNOWLEDGE_BASE_DIR):
        os.makedirs(KNOWLEDGE_BASE_DIR, exist_ok=True)

def get_folder_size(folder_path):
    """递归计算文件夹大小"""
    if not os.path.exists(folder_path):
        return 0
    
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(file_path)
            except (OSError, IOError):
                pass
    return total_size

def format_bytes(bytes_count):
    """将字节数转换为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"

def is_allowed_file(filename):
    """检查文件扩展名是否允许"""
    return any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS)

def get_unique_filename(directory, filename):
    """生成唯一的文件名（避免重复）"""
    if not os.path.exists(os.path.join(directory, filename)):
        return filename
    
    name, ext = os.path.splitext(filename)
    counter = 1
    while True:
        new_filename = f"{name}_{counter}{ext}"
        if not os.path.exists(os.path.join(directory, new_filename)):
            return new_filename
        counter += 1

# 启动时创建知识库目录
ensure_knowledge_base_dir()

# 配置管理
class Config:
    """配置管理类"""
    def __init__(self):
        # 知识库文件存储配置
        self.KNOWLEDGE_BASE_DIR = os.environ.get('KNOWLEDGE_BASE_DIR', './data/knowledge_base')
        self.KNOWLEDGE_BASE_MAX_BYTES = int(os.environ.get('KNOWLEDGE_BASE_MAX_BYTES', '1073741824'))  # 1GB default
        self.KNOWLEDGE_BASE_MAX_FILE_BYTES = int(os.environ.get('KNOWLEDGE_BASE_MAX_FILE_BYTES', '10485760'))  # 10MB default
        
        # 允许的文件扩展名
        self.ALLOWED_EXTENSIONS = {'.pdf', '.doc', '.docx', '.md', '.markdown', '.txt'}
        
        # 确保知识库目录存在
        self.ensure_knowledge_base_dir()
    
    def ensure_knowledge_base_dir(self):
        """确保知识库目录存在"""
        try:
            os.makedirs(self.KNOWLEDGE_BASE_DIR, exist_ok=True)
            print(f"✅ 知识库目录已准备: {self.KNOWLEDGE_BASE_DIR}")
        except Exception as e:
            print(f"❌ 创建知识库目录失败: {e}")

# 全局配置实例
config = Config()

# 设置Flask配置
app.config['MAX_CONTENT_LENGTH'] = config.KNOWLEDGE_BASE_MAX_FILE_BYTES

# 文件处理工具函数
def get_folder_size(folder_path):
    """递归计算文件夹大小"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if os.path.isfile(file_path):
                    total_size += os.path.getsize(file_path)
    except Exception as e:
        print(f"❌ 计算文件夹大小失败: {e}")
    return total_size

def format_bytes(bytes_value):
    """格式化字节数为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} TB"

def sanitize_filename(filename):
    """清理文件名，防止路径遍历和非法字符"""
    if not filename:
        return "unnamed_file"
    
    # 获取安全的文件名
    safe_filename = secure_filename(filename)
    if not safe_filename:
        safe_filename = "unnamed_file"
    
    # 进一步清理特殊字符
    safe_filename = re.sub(r'[^\w\-_\.]', '_', safe_filename)
    
    return safe_filename

def get_unique_filename(directory, filename):
    """获取唯一文件名，如果存在则添加数字后缀"""
    base_path = Path(directory)
    file_path = base_path / filename
    
    if not file_path.exists():
        return filename
    
    # 分离文件名和扩展名
    stem = file_path.stem
    suffix = file_path.suffix
    
    counter = 1
    while True:
        new_filename = f"{stem}_{counter}{suffix}"
        new_path = base_path / new_filename
        if not new_path.exists():
            return new_filename
        counter += 1

def is_allowed_file(filename):
    """检查文件扩展名是否被允许"""
    if not filename:
        return False
    
    file_ext = Path(filename).suffix.lower()
    return file_ext in config.ALLOWED_EXTENSIONS


# 获取设备信息
def get_device_info():
    """获取设备基本信息"""
    try:
        hostname = socket.gethostname()
        # 获取当前IP地址
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return {
            'hostname': hostname,
            'ip': ip,
            'mac': '60:e9:cd:e8:cc:aa'  # 从之前获取的MAC地址
        }
    except:
        return {
            'hostname': 'orangepi-zero3',
            'ip': '192.168.4.1',
            'mac': '60:e9:cd:e8:cc:aa'
        }

# 上传表单页面
UPLOAD_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📚 校园智能小助手 - 知识上传</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 600px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(45deg, #4a90e2, #357abd);
            color: white;
            padding: 30px 20px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 24px;
            margin-bottom: 10px;
        }
        
        .header p {
            opacity: 0.9;
            font-size: 14px;
        }
        
        .device-info {
            background: rgba(255,255,255,0.1);
            padding: 15px;
            border-radius: 10px;
            margin-top: 15px;
            font-size: 12px;
            text-align: left;
        }
        
        .form-container {
            padding: 30px;
        }
        
        .form-group {
            margin-bottom: 25px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: bold;
            color: #333;
            font-size: 16px;
        }
        
        textarea {
            width: 100%;
            padding: 15px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            font-family: inherit;
            resize: vertical;
            transition: border-color 0.3s;
        }
        
        textarea:focus {
            outline: none;
            border-color: #4a90e2;
            box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
        }
        
        .submit-btn {
            width: 100%;
            background: linear-gradient(45deg, #4a90e2, #357abd);
            color: white;
            padding: 15px;
            border: none;
            border-radius: 8px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        
        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(74, 144, 226, 0.4);
        }
        
        .submit-btn:active {
            transform: translateY(0);
        }
        
        .tips {
            background: #f8f9fa;
            padding: 20px;
            border-left: 4px solid #4a90e2;
            margin-bottom: 20px;
            border-radius: 0 8px 8px 0;
        }
        
        .tips h3 {
            color: #4a90e2;
            margin-bottom: 10px;
        }
        
        .tips ul {
            padding-left: 20px;
            color: #666;
        }
        
        .tips li {
            margin-bottom: 5px;
        }
        
        .status {
            text-align: center;
            padding: 15px;
            margin-top: 20px;
            border-radius: 8px;
            display: none;
        }
        
        .status.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .status.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        

        /* 文件上传部分样式 */

        /* 文件上传区域样式 */

        .file-upload-section {
            margin-top: 40px;
            padding-top: 30px;
            border-top: 2px solid #e9ecef;
        }

        .section-header h3 {
            color: #4a90e2;
            margin-bottom: 8px;
            font-size: 18px;
        }
        
        .section-subtext {
            color: #666;
            font-size: 14px;
            margin-bottom: 20px;
            line-height: 1.4;
        }
        
        .usage-display {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .usage-text {
            margin-bottom: 10px;
            font-size: 14px;
            color: #495057;
            font-weight: 500;
        }
        
        .progress-bar-container {
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .progress-bar {
            width: 100%;
            height: 100%;
            position: relative;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(45deg, #28a745, #20c997);
            border-radius: 10px;
            transition: width 0.3s ease;
            width: 0%;
        }
        
        .file-input-container {
            margin-bottom: 20px;
        }
        
        .file-input {
            width: 100%;
            padding: 15px;
            border: 2px dashed #4a90e2;
            border-radius: 8px;
            background: #f8f9fa;
            cursor: pointer;
            transition: border-color 0.3s, background 0.3s;
            pointer-events: auto;
            z-index: 1;
        }
        
        .file-input-label {
            display: block;
            padding: 15px;
            background: #f8f9fa;
            border: 2px dashed #4a90e2;
            border-radius: 8px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
            color: #4a90e2;
            font-weight: 500;
        }
        
        .file-input-label:hover {
            background: #e9f4ff;
            border-color: #357abd;
        }
        
        .selected-files {
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 6px;
            display: none;
        }
        
        .selected-file {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 5px 0;
            border-bottom: 1px solid #dee2e6;
        }
        
        .selected-file:last-child {
            border-bottom: none;
        }
        
        .file-name {
            color: #495057;
            font-size: 14px;
        }
        
        .file-size {
            color: #6c757d;
            font-size: 12px;
        }
        
        .file-upload-section h2 {
            color: #4a90e2;
            font-size: 20px;
            margin-bottom: 10px;
        }
        
        .file-upload-section .subtext {
            color: #666;
            font-size: 14px;
            margin-bottom: 20px;
            line-height: 1.5;
        }
        
        .file-input-wrapper {
            position: relative;
            margin-bottom: 15px;
        }
        
        .file-input:hover {
            border-color: #4a90e2;
            background: #f0f7ff;
        }
        
        .usage-info {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            font-size: 14px;
        }
        
        .usage-bar {
            width: 100%;
            height: 8px;
            background: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin: 8px 0;
        }
        
        .usage-progress {
            height: 100%;
            background: linear-gradient(45deg, #4a90e2, #357abd);
            transition: width 0.3s ease;
        }
        
        .file-select-btn {
            background: linear-gradient(45deg, #4a90e2, #357abd);
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            margin-bottom: 15px;
        }
        
        .file-select-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(74, 144, 226, 0.4);
        }
        
        .file-select-btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
            opacity: 0.6;
        }
        
        .upload-btn {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            width: 100%;
        }
        
        .upload-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4);
        }
        
        .upload-btn:active:not(:disabled) {
            transform: translateY(0);
        }
        
        .upload-btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
            opacity: 0.6;
        }
        
        .file-input:disabled {
            background: #e9ecef;
            cursor: not-allowed;
            opacity: 0.6;
        }
        
        .capacity-message {
            margin-top: 10px;
            padding: 10px;
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 500;
        }
        
        .usage-warning {
            margin-top: 8px;
            padding: 8px;
            background: #fff3cd;
            color: #856404;
            border: 1px solid #ffeaa7;
            border-radius: 4px;
            font-size: 13px;
        }
        
        .file-list {
            margin-top: 10px;
            font-size: 14px;
            color: #666;
        }
        
        .file-list .file-item {
            padding: 5px 0;
            border-bottom: 1px solid #eee;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 校园智能小助手</h1>
            <p>上传学校知识，让AI更懂您的校园</p>
            <div class="device-info">
                <div>📡 设备: {{ device_info.hostname }}</div>
                <div>🌐 IP: {{ device_info.ip }}</div>
                <div>🔗 MAC: {{ device_info.mac }}</div>
            </div>
        </div>
        
        <div class="form-container">
            <div class="tips">
                <h3>📝 上传说明</h3>
                <ul>
                    <li>请填写您学校的相关信息，帮助AI更好地回答校园问题</li>
                    <li>可以只填写部分内容，不必全部填写</li>
                    <li>内容会保存在本地，不会上传到外网</li>
                    <li>支持中文内容，请尽量详细描述</li>
                </ul>
            </div>
            
            <form id="uploadForm" method="POST" action="/upload">
                <div class="form-group">
                    <label for="school_info">🏫 学校简介</label>
                    <textarea 
                        id="school_info" 
                        name="school_info" 
                        rows="6" 
                        placeholder="请介绍您的学校，例如：学校名称、建校时间、办学特色、专业设置、校园环境等...">{{ form_data.school_info or '' }}</textarea>
                </div>
                
                <div class="form-group">
                    <label for="history">📜 校史沿革</label>
                    <textarea 
                        id="history" 
                        name="history" 
                        rows="6" 
                        placeholder="请介绍学校的历史发展，例如：重要历史节点、发展历程、重大事件、历史变迁等...">{{ form_data.history or '' }}</textarea>
                </div>
                
                <div class="form-group">
                    <label for="celebrities">🌟 知名校友</label>
                    <textarea 
                        id="celebrities" 
                        name="celebrities" 
                        rows="6" 
                        placeholder="请介绍知名校友或教师，例如：姓名、专业、成就、贡献、现任职位等...">{{ form_data.celebrities or '' }}</textarea>
                </div>
                
                <button type="submit" class="submit-btn">🚀 上传知识</button>
            </form>
            
            <div id="status" class="status"></div>
            

            <!-- 文件上传部分 -->
            <div class="file-upload-section">
                <h2>📁 上传本地知识库</h2>
                <div class="subtext">
                    支持 .pdf .doc .docx .md .markdown .txt。将文件保存到本地知识库文件夹，仅用于存储，不参与对话。
                </div>
                
                <div class="usage-info">
                    <div id="usage-text">正在加载使用情况...</div>
                    <div class="usage-bar">
                        <div id="usage-progress" class="usage-progress" style="width: 0%"></div>
                    </div>
                    <div id="usage-warning" class="usage-warning" style="display: none;"></div>
                </div>
                
                <form id="fileUploadForm" enctype="multipart/form-data">
                    <div class="file-input-wrapper">
                        <button type="button" id="fileSelectBtn" class="file-select-btn">📂 选择文件</button>
                        <input type="file" id="fileInput" name="files" multiple 
                               accept=".pdf,.doc,.docx,.md,.markdown,.txt"
                               class="file-input">
                    </div>
                    
                    <div id="file-list" class="file-list"></div>
                    
                    <button type="submit" id="uploadBtn" class="upload-btn">📤 上传文件</button>
                    
                    <div id="capacity-message" class="capacity-message" style="display: none;"></div>
                </form>
                
                <div id="file-status" class="status"></div>
            </div>
        </div>
    </div>
    
    <script>
        document.getElementById('uploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const statusDiv = document.getElementById('status');
            
            // 检查是否有内容
            const schoolInfo = formData.get('school_info').trim();
            const history = formData.get('history').trim();
            const celebrities = formData.get('celebrities').trim();
            
            if (!schoolInfo && !history && !celebrities) {
                statusDiv.className = 'status error';
                statusDiv.style.display = 'block';
                statusDiv.textContent = '⚠️ 请至少填写一项内容';
                return;
            }
            
            // 显示上传中
            statusDiv.className = 'status';
            statusDiv.style.display = 'block';
            statusDiv.textContent = '📤 正在上传...';
            
            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    statusDiv.className = 'status success';
                    statusDiv.textContent = '✅ ' + data.message;
                    // 清空表单
                    document.getElementById('uploadForm').reset();
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.textContent = '❌ ' + data.message;
                }
            })
            .catch(error => {
                statusDiv.className = 'status error';
                statusDiv.textContent = '❌ 上传失败：' + error.message;
            });
        });
        
        // 文件上传功能
        let currentUsage = { used_bytes: 0, max_bytes: 1073741824, percent: 0 };
        
        // 加载使用情况
        function loadUsage() {
            fetch('/kb/usage')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        currentUsage = data;
                        updateUsageDisplay();
                        updateUploadControls();
                    } else {
                        handleUsageLoadError('无法获取使用情况');
                    }
                })
                .catch(error => {
                    console.error('加载使用情况失败:', error);
                    handleUsageLoadError('用量信息获取失败，仍可尝试上传。');
                });
        }
        
        function handleUsageLoadError(message) {
            document.getElementById('usage-text').textContent = '加载使用情况失败';
            const warningDiv = document.getElementById('usage-warning');
            warningDiv.textContent = message;
            warningDiv.style.display = 'block';
            
            // 启用控件，允许用户尝试上传
            const fileInput = document.getElementById('fileInput');
            const fileSelectBtn = document.getElementById('fileSelectBtn');
            const uploadBtn = document.getElementById('uploadBtn');
            fileInput.disabled = false;
            fileSelectBtn.disabled = false;
            uploadBtn.disabled = fileInput.files.length === 0;
            if (fileInput.files.length > 0) {
                uploadBtn.textContent = '📤 上传文件';
            } else {
                uploadBtn.textContent = '📤 请选择文件';
            }
        }
        
        function updateUsageDisplay() {
            // 限制进度条百分比在0-100之间
            const clampedPercent = Math.max(0, Math.min(100, currentUsage.percent));
            document.getElementById('usage-text').textContent = 
                `已使用: ${currentUsage.used_human} / ${currentUsage.max_human} (${clampedPercent}%)`;
            document.getElementById('usage-progress').style.width = clampedPercent + '%';
        }
        
        function updateUploadControls() {
            const uploadBtn = document.getElementById('uploadBtn');
            const fileInput = document.getElementById('fileInput');
            const fileSelectBtn = document.getElementById('fileSelectBtn');
            const capacityMsg = document.getElementById('capacity-message');
            const warningDiv = document.getElementById('usage-warning');
            
            // 隐藏警告信息（如果之前显示过）
            warningDiv.style.display = 'none';
            
            // 检查容量是否已满
            const isFull = currentUsage.used_bytes >= currentUsage.max_bytes || currentUsage.percent >= 100;
            
            if (isFull) {
                // 容量已满：禁用控件但保持可见，显示说明消息
                fileInput.disabled = true;
                fileSelectBtn.disabled = true;
                uploadBtn.disabled = true;
                uploadBtn.textContent = '🚫 存储空间已满';
                capacityMsg.textContent = '容量已满，无法上传。请删除部分文件后重试。';
                capacityMsg.style.display = 'block';
            } else {
                // 容量未满：启用控件
                fileInput.disabled = false;
                fileSelectBtn.disabled = false;
                capacityMsg.style.display = 'none';
                
                if (fileInput.files.length === 0) {
                    uploadBtn.disabled = true;
                    uploadBtn.textContent = '📤 请选择文件';
                } else {
                    uploadBtn.disabled = false;
                    uploadBtn.textContent = '📤 上传文件';
                }
            }
        }
        
        // 文件选择事件
        document.getElementById('fileInput').addEventListener('change', function(e) {
            const files = Array.from(e.target.files);
            const fileList = document.getElementById('file-list');
            
            if (files.length === 0) {
                fileList.innerHTML = '';
                updateUploadControls();
                return;
            }
            
            let html = '<strong>已选择的文件:</strong><br>';
            files.forEach(file => {
                const size = file.size < 1024 * 1024 ? 
                    (file.size / 1024).toFixed(1) + ' KB' : 
                    (file.size / (1024 * 1024)).toFixed(1) + ' MB';
                html += `<div class="file-item">📄 ${file.name} (${size})</div>`;
            });
            
            fileList.innerHTML = html;
            updateUploadControls();
        });
        
        // 文件选择按钮事件
        document.getElementById('fileSelectBtn').addEventListener('click', function(e) {
            e.preventDefault();
            const fileInput = document.getElementById('fileInput');
            if (!fileInput.disabled) {
                fileInput.click();
            }
        });
        
        // 文件上传表单提交
        document.getElementById('fileUploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const fileInput = document.getElementById('fileInput');
            const files = fileInput.files;
            
            if (files.length === 0) {
                showFileStatus('请选择要上传的文件', 'error');
                return;
            }
            
            if (currentUsage.percent >= 100) {
                showFileStatus('存储空间已满，无法上传', 'error');
                return;
            }
            
            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }
            
            // 显示上传进度
            showFileStatus('📤 正在上传文件...', '');
            const uploadBtn = document.getElementById('uploadBtn');
            const originalText = uploadBtn.textContent;
            uploadBtn.disabled = true;
            uploadBtn.textContent = '🔄 上传中...';
            
            fetch('/kb/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showFileStatus(`✅ ${data.message}`, 'success');
                    
                    // 更新使用情况
                    if (data.usage) {
                        currentUsage = data.usage;
                        updateUsageDisplay();
                    }
                    
                    // 清空文件选择
                    fileInput.value = '';
                    document.getElementById('file-list').innerHTML = '';
                    
                    // 重新加载使用情况确保准确性
                    setTimeout(loadUsage, 1000);
                } else {
                    showFileStatus(`❌ ${data.message}`, 'error');
                }
            })
            .catch(error => {
                showFileStatus(`❌ 上传失败: ${error.message}`, 'error');
                console.error('文件上传错误:', error);
            })
            .finally(() => {
                updateUploadControls();
            });
        });
        
        function showFileStatus(message, type) {
            const statusDiv = document.getElementById('file-status');
            statusDiv.textContent = message;
            statusDiv.className = `status ${type}`;
            statusDiv.style.display = 'block';
            
            if (type === 'success') {
                setTimeout(() => {
                    statusDiv.style.display = 'none';
                }, 3000);
            }
        }
        
        // 页面加载时获取使用情况
        loadUsage();
    </script>

</body>
</html>
"""

# 成功页面模板
SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>上传成功 - 校园智能小助手</title>
    <style>
        body { 
            font-family: 'Microsoft YaHei', sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
        }
        .success-container {
            background: white;
            padding: 40px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            max-width: 400px;
        }
        .success-icon { font-size: 60px; margin-bottom: 20px; }
        h1 { color: #28a745; margin-bottom: 15px; }
        p { color: #666; margin-bottom: 25px; line-height: 1.6; }
        .btn { 
            background: #4a90e2; 
            color: white; 
            padding: 12px 30px; 
            text-decoration: none; 
            border-radius: 8px; 
            display: inline-block;
            transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
    </style>
</head>
<body>
    <div class="success-container">
        <div class="success-icon">✅</div>
        <h1>上传成功！</h1>
        <p>{{ message }}</p>
        <a href="/" class="btn">继续上传</a>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """显示上传表单"""
    device_info = get_device_info()
    return render_template_string(UPLOAD_TEMPLATE, 
                                device_info=device_info, 
                                form_data={})

@app.route('/upload', methods=['POST'])
def upload_knowledge():
    """处理知识上传"""
    try:
        # 获取表单数据
        school_info = request.form.get('school_info', '').strip()
        history = request.form.get('history', '').strip()
        celebrities = request.form.get('celebrities', '').strip()
        
        # 检查是否有内容
        if not school_info and not history and not celebrities:
            return jsonify({
                'success': False,
                'message': '请至少填写一项内容'
            })
        
        # 获取设备信息作为标识
        device_info = get_device_info()
        device_id = f"{device_info['hostname']}_{device_info['mac']}"
        
        # 保存到知识库
        success = knowledge_manager.add_knowledge(
            school_info=school_info,
            history=history,
            celebrities=celebrities,
            device_id=device_id
        )
        
        if success:
            # 统计信息
            stats = knowledge_manager.get_knowledge_stats()
            total = stats.get('total', 0)
            
            return jsonify({
                'success': True,
                'message': f'知识上传成功！当前知识库共有 {total} 条记录'
            })
        else:
            return jsonify({
                'success': False,
                'message': '保存失败，请稍后重试'
            })
            
    except Exception as e:
        print(f"上传知识时出错: {e}")
        return jsonify({
            'success': False,
            'message': f'上传失败：{str(e)}'
        })

@app.route('/kb/usage')
def kb_usage():
    """获取知识库文件使用情况"""
    try:
        used_bytes = get_folder_size(config.KNOWLEDGE_BASE_DIR)
        max_bytes = config.KNOWLEDGE_BASE_MAX_BYTES
        used_human = format_bytes(used_bytes)
        max_human = format_bytes(max_bytes)
        percent = min(100, (used_bytes / max_bytes) * 100) if max_bytes > 0 else 0
        
        return jsonify({
            'success': True,
            'used_bytes': used_bytes,
            'max_bytes': max_bytes,
            'used_human': used_human,
            'max_human': max_human,
            'percent': round(percent, 1)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取使用情况失败: {str(e)}'
        })

@app.route('/kb/upload', methods=['POST'])
def kb_upload():
    """处理知识库文件上传"""
    try:
        if 'files' not in request.files:
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            })
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            })
        
        # 检查存储容量
        current_usage = get_folder_size(config.KNOWLEDGE_BASE_DIR)
        if current_usage >= config.KNOWLEDGE_BASE_MAX_BYTES:
            return jsonify({
                'success': False,
                'message': '存储空间已满，无法上传'
            })
        
        uploaded_files = []
        total_size = 0
        
        for file in files:
            if file.filename == '':
                continue
                
            if not is_allowed_file(file.filename):
                return jsonify({
                    'success': False,
                    'message': f'不支持的文件类型: {file.filename}'
                })
            
            # 检查文件大小
            file.seek(0, 2)  # 移动到文件末尾
            file_size = file.tell()
            file.seek(0)  # 重置到文件开头
            
            if file_size > config.KNOWLEDGE_BASE_MAX_FILE_BYTES:
                return jsonify({
                    'success': False,
                    'message': f'文件太大: {file.filename} ({format_bytes(file_size)})'
                })
            
            # 检查总容量
            if current_usage + total_size + file_size > config.KNOWLEDGE_BASE_MAX_BYTES:
                return jsonify({
                    'success': False,
                    'message': '上传文件将超出存储容量限制'
                })
            
            total_size += file_size
        
        # 保存文件
        for file in files:
            if file.filename == '':
                continue
                
            safe_filename = sanitize_filename(file.filename)
            unique_filename = get_unique_filename(config.KNOWLEDGE_BASE_DIR, safe_filename)
            file_path = os.path.join(config.KNOWLEDGE_BASE_DIR, unique_filename)
            
            file.save(file_path)
            uploaded_files.append(unique_filename)
        
        # 获取更新后的使用情况
        new_usage = get_folder_size(config.KNOWLEDGE_BASE_DIR)
        max_bytes = config.KNOWLEDGE_BASE_MAX_BYTES
        used_human = format_bytes(new_usage)
        max_human = format_bytes(max_bytes)
        percent = min(100, (new_usage / max_bytes) * 100) if max_bytes > 0 else 0
        
        return jsonify({
            'success': True,
            'message': f'成功上传 {len(uploaded_files)} 个文件',
            'files': uploaded_files,
            'usage': {
                'used_bytes': new_usage,
                'max_bytes': max_bytes,
                'used_human': used_human,
                'max_human': max_human,
                'percent': round(percent, 1)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'上传失败: {str(e)}'
        })

if __name__ == '__main__':
    print("🚀 启动知识库上传服务器...")
    print("📱 请用手机连接热点：OrangePi-Knowledge")
    print("🔗 然后访问：http://192.168.10.1:8080")
    print("=" * 50)
    
    # 启动Flask服务器
    app.run(
        host='0.0.0.0',  # 监听所有接口
        port=8080,       # 使用8080端口
        debug=False,     # 生产模式
        threaded=True    # 支持多线程
    )