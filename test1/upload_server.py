# -*- coding: utf-8 -*-
"""
知识库上传服务器
用于接收手机端上传的学校知识信息和文件
"""
import os
import json
import re
import mimetypes
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, request, render_template, jsonify, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename
from knowledge_manager import knowledge_manager
import socket
from werkzeug.utils import secure_filename
import shutil

app = Flask(__name__)

# 配置静态文件路径
app.static_folder = 'static'
app.template_folder = 'templates'


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


def get_latest_knowledge():
    """获取最新的知识库内容"""
    try:
        # 获取设备信息作为标识
        device_info = get_device_info()
        device_id = f"{device_info['hostname']}_{device_info['mac']}"
        
        # 打印数据库路径以确保正确
        db_path = knowledge_manager.db_path
        print(f"数据库路径: {db_path}")
        
        # 检查数据库文件是否存在
        if not os.path.exists(db_path):
            print(f"数据库文件不存在: {db_path}")
            knowledge_manager.init_database()  # 初始化数据库
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        knowledge_data = {
            'school_info': '',
            'history': '',
            'celebrities': ''
        }
        
        # 获取每个类别的最新内容
        for category in knowledge_data.keys():
            try:
                print(f"查询类别: {category}, 设备ID: {device_id}")
                cursor.execute('''
                    SELECT content FROM knowledge 
                    WHERE category = ? AND device_id = ?
                    ORDER BY updated_at DESC LIMIT 1
                ''', (category, device_id))
                
                result = cursor.fetchone()
                if result:
                    content = result[0]
                    # 处理校友数据，尝试将文本转为JSON数组
                    if category == 'celebrities' and content:
                        # 对于校友数据，我们需要将其转换为JSON格式供前端使用
                        try:
                            # 先尝试直接解析JSON（如果已经是JSON格式）
                            json.loads(content)
                            # 如果能解析，说明是有效的JSON，直接使用
                            knowledge_data[category] = content
                            print(f"成功加载JSON校友数据")
                        except json.JSONDecodeError:
                            # 不是JSON，尝试将文本转换为结构化数据
                            lines = content.split("\n\n")
                            celebrities_array = []
                            
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                    
                                if ':' in line:
                                    name, desc = line.split(':', 1)
                                    celebrities_array.append({
                                        "name": name.strip(),
                                        "description": desc.strip()
                                    })
                                else:
                                    celebrities_array.append({
                                        "name": "",
                                        "description": line
                                    })
                            
                            # 将结构化数据转为JSON字符串
                            if celebrities_array:
                                knowledge_data[category] = json.dumps(celebrities_array, ensure_ascii=False)
                                print(f"将文本转换为JSON校友数据，共 {len(celebrities_array)} 条")
                            else:
                                knowledge_data[category] = "[]"
                                print(f"校友数据为空，设置为空数组")
                    else:
                        # 非校友数据，直接使用
                        knowledge_data[category] = content
                    
                    print(f"找到已有内容: {category} -> {content[:30]}...")
                else:
                    print(f"未找到内容: {category}")
                    # 对于校友数据，如果没有内容，设置为空数组
                    if category == 'celebrities':
                        knowledge_data[category] = "[]"
            except Exception as category_error:
                print(f"查询类别 {category} 失败: {category_error}")
                # 对于校友数据，如果出现错误，设置为空数组
                if category == 'celebrities':
                    knowledge_data[category] = "[]"
        
        conn.close()
        return knowledge_data
        
    except Exception as e:
        print(f"获取知识库内容失败: {e}")
        # 返回默认值，确保校友数据是空数组
        return {
            'school_info': '',
            'history': '',
            'celebrities': '[]'
        }

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
        # 固定使用这个MAC地址作为设备标识
        mac = '60:e9:cd:e8:cc:aa'  # 固定值，确保数据库查询一致性
        return {
            'hostname': hostname,
            'ip': ip,
            'mac': mac
        }
    except:
        # 默认返回值也使用固定MAC
        return {
            'hostname': 'orangepi-zero3',
            'ip': '192.168.4.1',
            'mac': '60:e9:cd:e8:cc:aa'  # 保持一致
        }

# 创建目录
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# 成功页面渲染
@app.route('/success')
def success_page():
    """显示上传成功页面"""
    message = request.args.get('message', '知识已成功上传！')
    return render_template('success.html', message=message)

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
    # 获取设备信息
    device_info = get_device_info()
    
    # 获取已保存的知识库内容
    try:
        form_data = get_latest_knowledge()
        print(f"首页加载数据: {form_data}")
        
        # 打印具体内容信息以确认
        for key, value in form_data.items():
            if value:
                print(f"{key}: {value[:50]}...")
    except Exception as e:
        print(f"加载表单数据失败: {e}")
        form_data = {
            'school_info': '',
            'history': '',
            'celebrities': ''
        }
    
    return render_template('upload.html', 
                        device_info=device_info, 
                        form_data=form_data)

@app.route('/upload', methods=['POST'])
def upload_knowledge():
    """处理知识上传"""
    try:
        # 获取表单数据
        school_info = request.form.get('school_info', '').strip()
        history = request.form.get('history', '').strip()
        celebrities_json = request.form.get('celebrities', '').strip()
        
        # 添加调试信息
        print(f"接收到的数据: school_info={school_info[:50]}..., history={history[:50]}..., celebrities_json={celebrities_json[:50]}...")
        
        # 处理校友数据：如果是JSON格式，将其转为格式化文本
        celebrities = ''
        if celebrities_json:
            try:
                celebrities_data = json.loads(celebrities_json)
                print(f"解析校友数据: {celebrities_data}")  # 调试信息
                formatted_items = []
                if isinstance(celebrities_data, list):
                    for celeb in celebrities_data:
                        if isinstance(celeb, dict):
                            name = (celeb.get('name') or '').strip()
                            desc = (celeb.get('description') or '').strip()
                            if name and desc:
                                formatted_items.append(f"{name}: {desc}")
                            elif name:
                                formatted_items.append(name)
                            elif desc:
                                formatted_items.append(desc)
                celebrities = "\n\n".join(formatted_items).strip()
                print(f"处理校友数据: {celebrities[:100]}...")  # 调试信息
            except json.JSONDecodeError:
                # 如果不是JSON格式，直接使用原文本
                celebrities = celebrities_json
                print("非JSON格式校友数据，使用原文本")
        else:
            print("未接收到校友数据")  # 调试信息
        
        # 检查是否有内容
        if not school_info and not history and not celebrities:
            return jsonify({
                'success': False,
                'message': '请至少填写一项内容'
            })
        
        # 获取设备信息作为标识
        device_info = get_device_info()
        device_id = f"{device_info['hostname']}_{device_info['mac']}"
        
        # 保存原始JSON到数据库，以便于维护结构化数据
        # 但同时存储格式化的文本版本以兼容原有的搜索功能
        success = knowledge_manager.add_knowledge(
            school_info=school_info,
            history=history,
            celebrities=celebrities,  # 使用格式化文本
            device_id=device_id
        )
        
        if success:
            # 统计信息
            stats = knowledge_manager.get_knowledge_stats()
            total = stats.get('total', 0)
            
            # 注意：不清空表单，而是让用户可以继续编辑
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
def upload_kb_files():
    """处理知识库文件上传"""
    try:
        # 检查是否有文件
        if 'files' not in request.files:
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            })
        
        files = request.files.getlist('files')
        if not files or files[0].filename == '':
            return jsonify({
                'success': False,
                'message': '没有选择文件'
            })
        
        # 检查存储空间
        current_size = get_folder_size(config.KNOWLEDGE_BASE_DIR)
        if current_size >= config.KNOWLEDGE_BASE_MAX_BYTES:
            return jsonify({
                'success': False,
                'message': '存储空间已满，无法上传新文件'
            })
        
        # 确保目标目录存在
        os.makedirs(config.KNOWLEDGE_BASE_DIR, exist_ok=True)
        
        # 保存文件
        success_count = 0
        fail_count = 0
        error_msgs = []
        
        for file in files:
            if file and file.filename:
                # 检查文件类型
                if not is_allowed_file(file.filename):
                    fail_count += 1
                    error_msgs.append(f"{file.filename}: 不支持的文件类型")
                    continue
                
                # 确保文件名安全
                filename = sanitize_filename(file.filename)
                unique_filename = get_unique_filename(config.KNOWLEDGE_BASE_DIR, filename)
                
                # 检查文件大小
                file_content = file.read()
                file.seek(0)  # 重置文件指针以便后续保存
                
                if len(file_content) > config.KNOWLEDGE_BASE_MAX_FILE_BYTES:
                    fail_count += 1
                    error_msgs.append(f"{filename}: 文件超过大小限制 ({format_bytes(len(file_content))})")
                    continue
                
                # 检查剩余空间
                if current_size + len(file_content) > config.KNOWLEDGE_BASE_MAX_BYTES:
                    return jsonify({
                        'success': False,
                        'message': '存储空间不足，无法上传所有文件'
                    })
                
                # 保存文件
                try:
                    file_path = os.path.join(config.KNOWLEDGE_BASE_DIR, unique_filename)
                    file.save(file_path)
                    current_size += len(file_content)  # 更新已用空间
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    error_msgs.append(f"{filename}: 保存失败 ({str(e)})")
        
        # 获取更新后的使用情况
        usage_info = {
            'used_bytes': get_folder_size(config.KNOWLEDGE_BASE_DIR),
            'max_bytes': config.KNOWLEDGE_BASE_MAX_BYTES,
            'used_human': format_bytes(get_folder_size(config.KNOWLEDGE_BASE_DIR)),
            'max_human': format_bytes(config.KNOWLEDGE_BASE_MAX_BYTES),
            'percent': min(100, (get_folder_size(config.KNOWLEDGE_BASE_DIR) / config.KNOWLEDGE_BASE_MAX_BYTES) * 100)
        }
        
        # 返回结果
        if success_count > 0:
            message = f"成功上传 {success_count} 个文件"
            if fail_count > 0:
                message += f"，{fail_count} 个文件失败"
                if error_msgs:
                    message += f"\n错误信息: {', '.join(error_msgs[:3])}"
                    if len(error_msgs) > 3:
                        message += f"...等 {len(error_msgs)} 个错误"
            
            return jsonify({
                'success': True,
                'message': message,
                'usage': usage_info
            })
        else:
            return jsonify({
                'success': False,
                'message': f"所有文件上传失败\n{', '.join(error_msgs[:5])}"
            })
            
    except Exception as e:
        print(f"文件上传错误: {e}")
        return jsonify({
            'success': False,
            'message': f'上传失败: {str(e)}'
        })

if __name__ == '__main__':
    # 获取实际的IP地址
    try:
        # 获取当前IP地址
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        actual_ip = s.getsockname()[0]
        s.close()
    except:
        actual_ip = "192.168.10.1"  # 默认值
    
    print("🚀 启动知识库上传服务器...")
    print("📱 请用手机连接热点：OrangePi-Knowledge")
    print(f"🔗 然后访问：http://{actual_ip}:8080")
    print("=" * 50)
    
    # 启动Flask服务器
    app.run(
        host='0.0.0.0',  # 监听所有接口
        port=8080,       # 使用8080端口
        debug=False,     # 生产模式
        threaded=True    # 支持多线程
    )