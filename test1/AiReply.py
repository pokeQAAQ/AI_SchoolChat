"""AI回复线程 - 优化版本，增强本地知识库集成"""
from PySide6.QtCore import QThread, Signal, QMutex, QMutexLocker
import requests
import json
import time
from knowledge_manager import knowledge_manager


class AiReply(QThread):
    result = Signal(str)
    error_signal = Signal(str)

    def __init__(self, conversation_history, api_key, base_url, user_query=""):
        super().__init__()
        self.messages = conversation_history.copy()
        self.user_query = user_query
        self.api_key = api_key
        self.base_url = "https://ark.cn-beijing.volces.com"
        self.model = "doubao-seed-1-6-250615"
        self.mutex = QMutex()
        self._stop_requested = False
        self.max_retries = 3
        self.retry_delay = 1.0

        # 优化系统提示
        if self.messages and self.messages[0]["role"] == "system":
            self.messages[0]["content"] = self._get_enhanced_system_prompt()

    def _get_enhanced_system_prompt(self):
        """获取增强的系统提示"""
        return """你是校园智能小助手，专门回答校园相关问题。

重要规则：
1. 🎯 优先级：本地知识库 > 你的通用知识
2. 📝 回答控制在200字以内，简洁明了
3. 🏫 当提供了本地知识时，必须基于本地知识回答
4. 💡 如果本地知识不够充分，可以适当补充通用知识
5. 🔍 如果没有相关本地知识，明确告知并使用通用知识
6. 😊 语言要亲切友好，适合校园环境

知识库使用指南：
- 看到"[学校信息]"标签时，这是官方学校介绍
- 看到"[校史沿革]"标签时，这是学校历史资料  
- 看到"[知名校友]"标签时，这是校友信息
- 这些信息来自本地知识库，请优先使用"""

    def run(self):
        """线程执行函数：智能搜索知识库，优化AI回答"""
        try:
            # 第一步：智能搜索本地知识库
            knowledge_context = self._search_and_format_knowledge()
            
            # 第二步：优化用户消息
            self._enhance_user_message(knowledge_context)
            
            # 第三步：调用AI API
            self.call_ai_api()
            
        except Exception as e:
            print(f"❌ AI回复整体流程出错: {e}")
            self.error_signal.emit(f"AI回复失败：{str(e)}")
    
    def _search_and_format_knowledge(self):
        """智能搜索并格式化知识库内容"""
        if not self.user_query.strip():
            return None
            
        try:
            # 多策略搜索
            results = knowledge_manager.search_knowledge(self.user_query, max_results=5)
            
            if results:
                knowledge_text = "📚 本地知识库相关信息：\n\n"
                
                for category, content, keywords in results:
                    category_name = {
                        'school_info': '🏫 学校信息',
                        'history': '📜 校史沿革',
                        'celebrities': '🌟 知名校友'
                    }.get(category, category)
                    
                    # 智能截取内容
                    content_preview = self._smart_content_preview(content, self.user_query)
                    knowledge_text += f"[{category_name}]\n{content_preview}\n\n"
                
                print(f"📚 找到 {len(results)} 条相关知识，正在结合AI回答...")
                return knowledge_text.strip()
            else:
                print(f"🔍 本地知识库无直接相关信息，使用AI通用知识回答")
                return None
                
        except Exception as e:
            print(f"⚠️ 搜索本地知识库失败: {e}")
            return None
    
    def _smart_content_preview(self, content, query):
        """智能内容预览 - 优先显示与查询相关的部分"""
        if len(content) <= 300:
            return content
        
        # 查找与查询最相关的段落
        query_words = set(query.lower().split())
        sentences = content.replace('。', '。\n').replace('！', '！\n').replace('？', '？\n').split('\n')
        
        scored_sentences = []
        for sentence in sentences:
            if len(sentence.strip()) < 10:
                continue
            sentence_words = set(sentence.lower().split())
            score = len(query_words.intersection(sentence_words))
            scored_sentences.append((sentence.strip(), score))
        
        # 排序并选择最相关的句子
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        result = ""
        current_length = 0
        for sentence, score in scored_sentences:
            if current_length + len(sentence) > 280:
                break
            result += sentence + " "
            current_length += len(sentence)
        
        return result.strip() + "..." if result else content[:280] + "..."
    
    def _enhance_user_message(self, knowledge_context):
        """优化用户消息，更好地集成知识库内容"""
        if self.messages and self.messages[-1]["role"] == "user":
            original_query = self.messages[-1]["content"]
            
            if knowledge_context:
                # 有本地知识时的消息格式
                enhanced_message = f"""{knowledge_context}

🎯 用户问题：{original_query}

请基于上述本地知识库信息回答用户问题。如果本地知识不够充分，可以适当补充相关的通用知识，但要明确标识哪些是补充信息。回答要简洁明了，控制在200字以内。"""
            else:
                # 无本地知识时的消息格式
                enhanced_message = f"""❗ 本地知识库中暂无直接相关信息

🎯 用户问题：{original_query}

请使用你的通用知识回答这个校园相关问题，并在回答开头提醒用户"这是基于通用知识的回答"。回答要简洁明了，控制在200字以内。"""
            
            self.messages[-1]["content"] = enhanced_message
    
    def call_ai_api(self):
        """调用AI API获取回复"""
        attempt = 0

        while attempt < self.max_retries:
            try:
                with QMutexLocker(self.mutex):
                    if self._stop_requested:
                        return

                url = f"{self.base_url}/api/v3/chat/completions"
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                data = {
                    "model": self.model,
                    "messages": self.format_messages(self.messages),
                    "stream": False,
                    "max_tokens": 400,  # 增加token限制以支持知识库内容
                    "temperature": 0.7,
                    "top_p": 0.9
                }

                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=45
                )
                response.raise_for_status()
                result = response.json()

                if "choices" in result and len(result["choices"]) > 0:
                    ai_content = result["choices"][0]["message"]["content"]
                    self.result.emit(ai_content)
                    return
                else:
                    raise ValueError("API返回数据格式错误")

            except requests.exceptions.Timeout:
                attempt += 1
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue
                self.error_signal.emit("请求超时，请稍后重试")
            except requests.exceptions.RequestException as e:
                attempt += 1
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue
                self.error_signal.emit(f"网络错误：{str(e)}")
            except Exception as e:
                self.error_signal.emit(f"AI调用失败：{str(e)}")
                return

    def format_messages(self, messages):
        """格式化消息"""
        formatted_messages = []
        for msg in messages:
            if msg["role"] == "user":
                formatted_messages.append({
                    "role": "user",
                    "content": [{"type": "text", "text": msg["content"]}]
                })
            else:
                formatted_messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        return formatted_messages

    def stop(self):
        """停止线程"""
        with QMutexLocker(self.mutex):
            self._stop_requested = True