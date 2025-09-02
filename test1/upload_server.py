# -*- coding: utf-8 -*-
"""
知识库上传服务器
用于接收手机端上传的学校知识信息
"""
import os
import json
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, redirect, url_for
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
            display: none;
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
        
        .upload-btn {
            width: 100%;
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
            padding: 12px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .upload-btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4);
        }
        
        .upload-btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }
        
        .upload-btn:active:not(:disabled) {
            transform: translateY(0);
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
                <div class="section-header">
                    <h3>📁 上传本地知识库</h3>
                    <p class="section-subtext">支持 .pdf .doc .docx .md .markdown .txt。将文件保存到本地知识库文件夹，仅用于存储，不参与对话。</p>
                </div>
                
                <div class="usage-display">
                    <div class="usage-text">
                        <span id="usage-info">正在加载存储信息...</span>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar">
                            <div id="progress-fill" class="progress-fill"></div>
                        </div>
                    </div>
                </div>
                
                <form id="fileUploadForm" enctype="multipart/form-data">
                    <div class="file-input-container">
                        <input type="file" id="files" name="files" multiple accept=".pdf,.doc,.docx,.md,.markdown,.txt" class="file-input">
                        <label for="files" class="file-input-label">
                            📎 选择文件 (可多选)
                        </label>
                        <div id="selected-files" class="selected-files"></div>
                    </div>
                    
                    <button type="submit" id="upload-btn" class="upload-btn" disabled>
                        📤 上传文件
                    </button>
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
    </script>
    
    <!-- 文件上传功能脚本 -->
    <script>
        // 加载存储使用情况
        function loadUsageInfo() {
            fetch('/kb/usage')
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        document.getElementById('usage-info').textContent = '加载存储信息失败';
                        return;
                    }
                    
                    const usageText = `已使用: ${data.used_human} / ${data.max_human} (${data.percent}%)`;
                    document.getElementById('usage-info').textContent = usageText;
                    document.getElementById('progress-fill').style.width = data.percent + '%';
                    
                    // 如果存储已满，禁用上传按钮
                    const uploadBtn = document.getElementById('upload-btn');
                    if (data.percent >= 100) {
                        uploadBtn.disabled = true;
                        uploadBtn.textContent = '📦 存储已满';
                    }
                })
                .catch(error => {
                    console.error('加载存储信息失败:', error);
                    document.getElementById('usage-info').textContent = '加载存储信息失败';
                });
        }
        
        // 格式化文件大小
        function formatFileSize(bytes) {
            const units = ['B', 'KB', 'MB', 'GB'];
            let size = bytes;
            let unitIndex = 0;
            
            while (size >= 1024 && unitIndex < units.length - 1) {
                size /= 1024;
                unitIndex++;
            }
            
            return `${size.toFixed(1)} ${units[unitIndex]}`;
        }
        
        // 处理文件选择
        document.getElementById('files').addEventListener('change', function(e) {
            const files = e.target.files;
            const selectedFilesDiv = document.getElementById('selected-files');
            const uploadBtn = document.getElementById('upload-btn');
            
            if (files.length > 0) {
                selectedFilesDiv.style.display = 'block';
                selectedFilesDiv.innerHTML = '';
                
                for (let file of files) {
                    const fileDiv = document.createElement('div');
                    fileDiv.className = 'selected-file';
                    fileDiv.innerHTML = `
                        <span class="file-name">${file.name}</span>
                        <span class="file-size">${formatFileSize(file.size)}</span>
                    `;
                    selectedFilesDiv.appendChild(fileDiv);
                }
                
                uploadBtn.disabled = false;
                uploadBtn.textContent = '📤 上传文件';
            } else {
                selectedFilesDiv.style.display = 'none';
                uploadBtn.disabled = true;
                uploadBtn.textContent = '📤 上传文件';
            }
        });
        
        // 处理文件上传
        document.getElementById('fileUploadForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const formData = new FormData();
            const files = document.getElementById('files').files;
            const statusDiv = document.getElementById('file-status');
            const uploadBtn = document.getElementById('upload-btn');
            
            if (files.length === 0) {
                statusDiv.className = 'status error';
                statusDiv.style.display = 'block';
                statusDiv.textContent = '⚠️ 请选择要上传的文件';
                return;
            }
            
            // 添加所有文件到FormData
            for (let file of files) {
                formData.append('files', file);
            }
            
            // 显示上传中状态
            statusDiv.className = 'status';
            statusDiv.style.display = 'block';
            statusDiv.textContent = '📤 正在上传文件...';
            uploadBtn.disabled = true;
            uploadBtn.textContent = '⏳ 上传中...';
            
            fetch('/kb/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    statusDiv.className = 'status success';
                    let message = data.message;
                    
                    // 显示详细结果
                    if (data.results && data.results.length > 0) {
                        message += '\\n\\n详细结果：';
                        data.results.forEach(result => {
                            if (result.success) {
                                message += `\\n✅ ${result.filename} (${result.size})`;
                            } else {
                                message += `\\n❌ ${result.filename}: ${result.message}`;
                            }
                        });
                    }
                    
                    statusDiv.textContent = message;
                    
                    // 清空表单
                    document.getElementById('fileUploadForm').reset();
                    document.getElementById('selected-files').style.display = 'none';
                    
                    // 更新存储使用情况
                    if (data.usage) {
                        const usageText = `已使用: ${data.usage.used_human} / ${data.usage.max_human} (${data.usage.percent}%)`;
                        document.getElementById('usage-info').textContent = usageText;
                        document.getElementById('progress-fill').style.width = data.usage.percent + '%';
                    } else {
                        loadUsageInfo();
                    }
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.textContent = '❌ ' + data.message;
                }
                
                uploadBtn.disabled = true;
                uploadBtn.textContent = '📤 上传文件';
            })
            .catch(error => {
                statusDiv.className = 'status error';
                statusDiv.textContent = '❌ 上传失败：' + error.message;
                uploadBtn.disabled = true;
                uploadBtn.textContent = '📤 上传文件';
            });
        });
        
        // 页面加载时获取存储使用情况
        document.addEventListener('DOMContentLoaded', function() {
            loadUsageInfo();
        });
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

@app.route('/status')
def status():
    """获取知识库状态"""
    try:
        stats = knowledge_manager.get_knowledge_stats()
        device_info = get_device_info()
        return jsonify({
            'success': True,
            'device_info': device_info,
            'knowledge_stats': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/kb/usage')
def get_knowledge_base_usage():
    """获取知识库文件存储使用情况"""
    try:
        ensure_knowledge_base_dir()
        used_bytes = get_folder_size(KNOWLEDGE_BASE_DIR)
        max_bytes = KNOWLEDGE_BASE_MAX_BYTES
        percent = (used_bytes / max_bytes * 100) if max_bytes > 0 else 0
        
        return jsonify({
            'used_bytes': used_bytes,
            'max_bytes': max_bytes,
            'used_human': format_bytes(used_bytes),
            'max_human': format_bytes(max_bytes),
            'percent': round(percent, 1)
        })
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/kb/upload', methods=['POST'])
def upload_knowledge_files():
    """处理知识库文件上传"""
    try:
        ensure_knowledge_base_dir()
        
        if 'files' not in request.files:
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            }), 400
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            }), 400
        
        # 检查当前存储使用情况
        current_size = get_folder_size(KNOWLEDGE_BASE_DIR)
        
        # 计算所有文件的总大小
        total_upload_size = 0
        file_info = []
        
        for file in files:
            if file.filename:
                # 模拟读取文件大小（不完全加载到内存）
                file.seek(0, 2)  # 移动到文件末尾
                file_size = file.tell()
                file.seek(0)  # 重置到开头
                
                file_info.append({
                    'file': file,
                    'filename': file.filename,
                    'size': file_size
                })
                total_upload_size += file_size
        
        # 检查总容量限制
        if current_size + total_upload_size > KNOWLEDGE_BASE_MAX_BYTES:
            return jsonify({
                'success': False,
                'message': f'存储容量不足。当前已使用 {format_bytes(current_size)}，尝试上传 {format_bytes(total_upload_size)}，总容量限制 {format_bytes(KNOWLEDGE_BASE_MAX_BYTES)}'
            }), 413
        
        # 处理每个文件
        results = []
        saved_files = []
        
        for info in file_info:
            file = info['file']
            original_filename = info['filename']
            file_size = info['size']
            
            try:
                # 检查文件大小限制
                if file_size > KNOWLEDGE_BASE_MAX_FILE_BYTES:
                    results.append({
                        'filename': original_filename,
                        'success': False,
                        'message': f'文件过大，限制为 {format_bytes(KNOWLEDGE_BASE_MAX_FILE_BYTES)}'
                    })
                    continue
                
                # 检查文件类型
                if not is_allowed_file(original_filename):
                    results.append({
                        'filename': original_filename,
                        'success': False,
                        'message': f'不支持的文件类型，仅支持: {", ".join(ALLOWED_EXTENSIONS)}'
                    })
                    continue
                
                # 安全化文件名
                safe_filename = secure_filename(original_filename)
                if not safe_filename:
                    safe_filename = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                
                # 生成唯一文件名
                unique_filename = get_unique_filename(KNOWLEDGE_BASE_DIR, safe_filename)
                file_path = os.path.join(KNOWLEDGE_BASE_DIR, unique_filename)
                
                # 流式保存文件（8KB块，适合低内存设备）
                with open(file_path, 'wb') as f:
                    while True:
                        chunk = file.read(8192)  # 8KB 块
                        if not chunk:
                            break
                        f.write(chunk)
                
                saved_files.append(unique_filename)
                results.append({
                    'filename': original_filename,
                    'saved_as': unique_filename,
                    'success': True,
                    'size': format_bytes(file_size)
                })
                
            except Exception as e:
                results.append({
                    'filename': original_filename,
                    'success': False,
                    'message': f'保存失败: {str(e)}'
                })
        
        # 获取更新后的使用情况
        new_size = get_folder_size(KNOWLEDGE_BASE_DIR)
        percent = (new_size / KNOWLEDGE_BASE_MAX_BYTES * 100) if KNOWLEDGE_BASE_MAX_BYTES > 0 else 0
        
        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)
        
        return jsonify({
            'success': True,
            'message': f'成功上传 {success_count}/{total_count} 个文件',
            'results': results,
            'usage': {
                'used_bytes': new_size,
                'max_bytes': KNOWLEDGE_BASE_MAX_BYTES,
                'used_human': format_bytes(new_size),
                'max_human': format_bytes(KNOWLEDGE_BASE_MAX_BYTES),
                'percent': round(percent, 1)
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'上传失败: {str(e)}'
        }), 500

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