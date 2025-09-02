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

app = Flask(__name__)

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