/**
 * 知识上传页面JavaScript
 * 处理表单提交、文件上传和校友信息的动态管理
 */

document.addEventListener('DOMContentLoaded', function() {
    // 知识表单提交处理
    setupKnowledgeForm();
    
    // 知名校友动态表单处理
    setupCelebrityForm();
    
    // 文件上传功能
    setupFileUpload();
});

/**
 * 设置知识表单提交处理
 */
function setupKnowledgeForm() {
    const formEl = document.getElementById('uploadForm');
    formEl.addEventListener('submit', function (e) {
        e.preventDefault();

        // 1) 先收集校友数据并写回隐藏字段
        const celebrityItems = document.querySelectorAll('.celebrity-item');
        const celebritiesData = [];
        celebrityItems.forEach(item => {
            const name = (item.querySelector('.celebrity-name')?.value || '').trim();
            const desc = (item.querySelector('.celebrity-description')?.value || '').trim();
            // 允许只填描述或只填姓名
            if (name || desc) {
                celebritiesData.push({ name, description: desc });
            }
        });
        const celebritiesJson = celebritiesData.length ? JSON.stringify(celebritiesData) : '';
        document.getElementById('celebrities').value = celebritiesJson;

        // 2) 再创建 FormData（确保拿到最新隐藏字段的值）
        const formData = new FormData(this);

        // 可选：打印将要发送的数据，确认 celebs 不为空
        console.log('sending celebs:', formData.get('celebrities'));

        // 3) 轻量校验
        const schoolInfo = (formData.get('school_info') || '').trim();
        const history = (formData.get('history') || '').trim();
        const celebrities = (formData.get('celebrities') || '').trim();
        const statusDiv = document.getElementById('status');

        if (!schoolInfo && !history && !celebrities) {
            statusDiv.className = 'status error';
            statusDiv.style.display = 'block';
            statusDiv.textContent = '⚠️ 请至少填写一项内容';
            return;
        }

        statusDiv.className = 'status';
        statusDiv.style.display = 'block';
        statusDiv.textContent = '📤 正在上传...';

        fetch('/upload', { method: 'POST', body: formData })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    statusDiv.className = 'status success';
                    statusDiv.textContent = '✅ ' + data.message;
                } else {
                    statusDiv.className = 'status error';
                    statusDiv.textContent = '❌ ' + data.message;
                }
            })
            .catch(err => {
                statusDiv.className = 'status error';
                statusDiv.textContent = '❌ 上传失败：' + err.message;
            });
    });
}

/**
 * 设置校友表单的动态添加/删除功能
 */
function setupCelebrityForm() {
    const addCelebrityBtn = document.getElementById('add-celebrity-btn');
    const celebritiesContainer = document.getElementById('celebrities-container');
    const celebritiesInput = document.getElementById('celebrities');
    
    // 添加校友条目
    function addCelebrityItem(name = '', description = '') {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'celebrity-item';
        
        // 添加动画效果
        itemDiv.style.opacity = '0';
        itemDiv.style.transform = 'translateY(20px)';
        
        itemDiv.innerHTML = `
            <div class="celebrity-header">
                <div class="celebrity-name-container">
                    <input type="text" class="celebrity-name" placeholder="请输入校友姓名" value="${name}">
                </div>
                <button type="button" class="celebrity-remove" title="删除此条目">×</button>
            </div>
            <textarea class="celebrity-description" rows="3" placeholder="请输入专业、成就、贡献、现任职位等信息...">${description}</textarea>
        `;
        
        // 添加删除按钮事件
        const removeBtn = itemDiv.querySelector('.celebrity-remove');
        removeBtn.addEventListener('click', function() {
            // 添加渐变效果
            itemDiv.style.opacity = '0';
            itemDiv.style.transform = 'translateY(20px)';
            itemDiv.style.maxHeight = '0';
            
            // 等待动画完成后删除
            setTimeout(() => {
                celebritiesContainer.removeChild(itemDiv);
            }, 300);
        });
        
        celebritiesContainer.appendChild(itemDiv);
        
        // 触发重排布并显示动画
        setTimeout(() => {
            itemDiv.style.opacity = '1';
            itemDiv.style.transform = 'translateY(0)';
        }, 10);
        
        // 聚焦新添加的名称输入框
        setTimeout(() => {
            const nameInput = itemDiv.querySelector('.celebrity-name');
            nameInput.focus();
        }, 350);
    }
    
    // 添加按钮事件
    addCelebrityBtn.addEventListener('click', function() {
        // 添加点击效果
        this.classList.add('adding');
        this.style.transform = 'scale(0.95)';
        
        // 恢复按钮状态
        setTimeout(() => {
            this.style.transform = 'scale(1)';
            this.classList.remove('adding');
        }, 150);
        
        // 添加新条目
        addCelebrityItem();
    });
    
    // 加载已有数据
    if (celebritiesInput.value.trim()) {
        try {
            const celebritiesData = JSON.parse(celebritiesInput.value);
            if (Array.isArray(celebritiesData)) {
                celebritiesData.forEach(celeb => {
                    addCelebrityItem(celeb.name || '', celeb.description || '');
                });
            } else if (typeof celebritiesInput.value === 'string') {
                // 兼容原有的纯文本格式
                addCelebrityItem('', celebritiesInput.value);
            }
        } catch (e) {
            // 如果不是JSON，将其作为一个条目添加
            if (celebritiesInput.value.trim()) {
                addCelebrityItem('', celebritiesInput.value);
            }
        }
    }
    
    // 如果没有条目，默认添加一个空条目
    if (celebritiesContainer.children.length === 0) {
        addCelebrityItem();
    }
}

/**
 * 设置文件上传功能
 */
function setupFileUpload() {
    let currentUsage = { used_bytes: 0, max_bytes: 1073741824, percent: 0 };
    
    // 加载使用情况
    loadUsage();
    
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
    
    // 加载存储使用情况
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
    
    // 处理加载使用情况错误
    function handleUsageLoadError(message) {
        document.getElementById('usage-text').textContent = '加载使用情况失败';
        const warningDiv = document.getElementById('usage-warning');
        warningDiv.textContent = message;
        warningDiv.style.display = 'block';
        
        // 启用控件，允许用户尝试上传
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        fileInput.disabled = false;
        uploadBtn.disabled = fileInput.files.length === 0;
        if (fileInput.files.length > 0) {
            uploadBtn.textContent = '📤 上传文件';
        } else {
            uploadBtn.textContent = '📤 请选择文件';
        }
    }
    
    // 更新使用情况显示
    function updateUsageDisplay() {
        // 限制进度条百分比在0-100之间
        const clampedPercent = Math.max(0, Math.min(100, currentUsage.percent));
        document.getElementById('usage-text').textContent = `已使用: ${currentUsage.used_human} / ${currentUsage.max_human} (${clampedPercent}%)`;
        document.getElementById('usage-progress').style.width = clampedPercent + '%';
    }
    
    // 更新上传控件状态
    function updateUploadControls() {
        const uploadBtn = document.getElementById('uploadBtn');
        const fileInput = document.getElementById('fileInput');
        const capacityMsg = document.getElementById('capacity-message');
        const warningDiv = document.getElementById('usage-warning');
        
        // 隐藏警告信息（如果之前显示过）
        warningDiv.style.display = 'none';
        
        // 检查容量是否已满
        const isFull = currentUsage.used_bytes >= currentUsage.max_bytes || currentUsage.percent >= 100;
        
        if (isFull) {
            // 容量已满：禁用控件但保持可见，显示说明消息
            fileInput.disabled = true;
            uploadBtn.disabled = true;
            uploadBtn.textContent = '🚫 存储空间已满';
            capacityMsg.textContent = '容量已满，无法上传。请删除部分文件后重试。';
            capacityMsg.style.display = 'block';
        } else {
            // 容量未满：启用控件
            fileInput.disabled = false;
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
    
    // 显示文件状态消息
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
}