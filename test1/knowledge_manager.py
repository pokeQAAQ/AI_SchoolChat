# -*- coding: utf-8 -*-
"""
本地知识库管理器 - 优化版本
增强搜索功能和智能匹配
"""
import sqlite3
import json
import os
import time
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
import threading


class LocalKnowledgeManager:
    """本地知识库管理器 - 优化版本"""
    
    def __init__(self, db_path="/home/orangepi/program/LTChat_updater/app/test1/knowledge.db"):
        self.db_path = db_path
        self.lock = threading.Lock()  # 添加线程锁
        self.init_database()
        
        # 问题类型关键词映射
        self.question_type_keywords = {
            'school_info': ['学校', '简介', '介绍', '概况', '基本情况', '学院', '大学', '校园', '办学'],
            'history': ['历史', '校史', '沿革', '发展', '建校', '成立', '创办', '历程', '变迁'],
            'celebrities': ['校友', '名人', '知名', '杰出', '著名', '教授', '院士', '专家', '老师']
        }
    
    def init_database(self):
        """初始化SQLite数据库"""
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            # 使用锁保护数据库初始化
            with self.lock:
                conn = sqlite3.connect(self.db_path, timeout=20.0)
                cursor = conn.cursor()
                
                # 创建知识表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS knowledge (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        content TEXT NOT NULL,
                        keywords TEXT,
                        device_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        relevance_score REAL DEFAULT 1.0
                    )
                ''')
                
                # 创建索引优化搜索
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_keywords ON knowledge(keywords)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_category ON knowledge(category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_content ON knowledge(content)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_relevance ON knowledge(relevance_score)')
                
                conn.commit()
                conn.close()
            print("✅ 知识库数据库初始化成功")
            
        except Exception as e:
            print(f"❌ 知识库初始化失败: {e}")
    
    def _get_db_connection(self, timeout=20.0):
        """获取数据库连接，带重试机制"""
        max_retries = 5
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path, timeout=timeout)
                conn.execute('PRAGMA journal_mode=WAL')  # 启用WAL模式提高并发性能
                return conn
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    print(f"⚠️ 数据库被锁定，{retry_delay}秒后重试 ({attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                else:
                    raise e
        return None
    
    def add_knowledge(self, school_info="", history="", celebrities="", device_id=""):
        """添加知识到本地库"""
        try:
            # 使用锁保护写操作
            with self.lock:
                conn = self._get_db_connection()
                if not conn:
                    raise Exception("无法获取数据库连接")
                
                cursor = conn.cursor()
                
                knowledge_items = []
                if school_info.strip():
                    keywords = self._extract_keywords_enhanced(school_info)
                    knowledge_items.append(("school_info", school_info, keywords))
                    print(f"添加学校信息: {school_info[:50]}...")  # 调试信息
                if history.strip():
                    keywords = self._extract_keywords_enhanced(history)
                    knowledge_items.append(("history", history, keywords))
                    print(f"添加历史信息: {history[:50]}...")  # 调试信息
                if celebrities.strip():
                    keywords = self._extract_keywords_enhanced(celebrities)
                    knowledge_items.append(("celebrities", celebrities, keywords))
                    print(f"添加校友信息: {celebrities[:50]}...")  # 调试信息
                else:
                    print(f"校友信息为空或只有空格: '{celebrities}'")  # 调试信息
                
                print(f"总共要添加的知识项数: {len(knowledge_items)}")  # 调试信息
                
                for category, content, keywords in knowledge_items:
                    cursor.execute('''
                        SELECT id FROM knowledge 
                        WHERE category = ? AND device_id = ?
                    ''', (category, device_id))
                    
                    existing = cursor.fetchone()
                    
                    if existing:
                        cursor.execute('''
                            UPDATE knowledge 
                            SET content = ?, keywords = ?, updated_at = ?, relevance_score = ?
                            WHERE id = ?
                        ''', (content, keywords, datetime.now(), 1.0, existing[0]))
                        print(f"📝 更新知识: {category}")
                    else:
                        cursor.execute('''
                            INSERT INTO knowledge 
                            (category, content, keywords, device_id, created_at, updated_at, relevance_score) 
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (category, content, keywords, device_id, datetime.now(), datetime.now(), 1.0))
                        print(f"➕ 新增知识: {category}")
                
                conn.commit()
                conn.close()
                
                return len(knowledge_items) > 0
                
        except Exception as e:
            print(f"❌ 添加知识失败: {e}")
            return False
    
    def search_knowledge(self, query, max_results=5):
        """智能搜索本地知识库"""
        if not query.strip():
            return []
        
        # 多策略搜索
        results = []
        
        # 策略1: 问题类型识别搜索
        category_results = self._search_by_question_type(query)
        if category_results:
            results.extend(category_results)
        
        # 策略2: 关键词搜索
        keyword_results = self._search_by_keywords(query, max_results)
        results.extend(keyword_results)
        
        # 策略3: 模糊搜索
        fuzzy_results = self._search_fuzzy(query, max_results)
        results.extend(fuzzy_results)
        
        # 去重并排序
        unique_results = self._deduplicate_and_rank(results, query)
        
        return unique_results[:max_results]
    
    def _search_by_question_type(self, query):
        """根据问题类型搜索"""
        try:
            query_lower = query.lower()
            detected_types = []
            
            # 检测问题类型
            for category, keywords in self.question_type_keywords.items():
                for keyword in keywords:
                    if keyword in query_lower:
                        detected_types.append(category)
                        break
            
            if not detected_types:
                return []
            
            conn = self._get_db_connection()
            if not conn:
                return []
            
            cursor = conn.cursor()
            
            # 获取对应类型的所有知识
            results = []
            for category in detected_types:
                cursor.execute('''
                    SELECT category, content, keywords FROM knowledge 
                    WHERE category = ?
                    ORDER BY relevance_score DESC, updated_at DESC
                ''', (category,))
                
                category_results = cursor.fetchall()
                results.extend(category_results)
            
            conn.close()
            return results
            
        except Exception as e:
            print(f"❌ 类型搜索失败: {e}")
            return []
    
    def _search_by_keywords(self, query, max_results):
        """关键词搜索"""
        try:
            query_lower = query.lower()
            
            conn = self._get_db_connection()
            if not conn:
                return []
            
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT category, content, keywords FROM knowledge 
                WHERE LOWER(content) LIKE ? OR LOWER(keywords) LIKE ?
                ORDER BY relevance_score DESC, updated_at DESC
                LIMIT ?
            ''', (f'%{query_lower}%', f'%{query_lower}%', max_results))
            
            results = cursor.fetchall()
            conn.close()
            
            return results
            
        except Exception as e:
            print(f"❌ 关键词搜索失败: {e}")
            return []
    
    def _search_fuzzy(self, query, max_results):
        """模糊搜索"""
        try:
            # 提取查询中的关键词
            query_keywords = self._extract_keywords_enhanced(query).split()
            if not query_keywords:
                return []
            
            conn = self._get_db_connection()
            if not conn:
                return []
            
            cursor = conn.cursor()
            
            cursor.execute('SELECT category, content, keywords FROM knowledge')
            all_knowledge = cursor.fetchall()
            conn.close()
            
            scored_results = []
            for category, content, keywords in all_knowledge:
                score = self._calculate_similarity(query_keywords, keywords.split())
                if score > 0.3:  # 相似度阈值
                    scored_results.append((category, content, keywords, score))
            
            # 按相似度排序
            scored_results.sort(key=lambda x: x[3], reverse=True)
            
            return [(r[0], r[1], r[2]) for r in scored_results[:max_results]]
            
        except Exception as e:
            print(f"❌ 模糊搜索失败: {e}")
            return []
    
    def _calculate_similarity(self, keywords1, keywords2):
        """计算关键词相似度"""
        if not keywords1 or not keywords2:
            return 0.0
        
        set1 = set(keywords1)
        set2 = set(keywords2)
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def _deduplicate_and_rank(self, results, query):
        """去重并重新排序"""
        seen = set()
        unique_results = []
        
        for category, content, keywords in results:
            content_hash = hash(content[:100])  # 使用内容前100字符作为去重标识
            if content_hash not in seen:
                seen.add(content_hash)
                unique_results.append((category, content, keywords))
        
        return unique_results
    
    def get_all_knowledge_by_categories(self):
        """按分类获取所有知识"""
        try:
            conn = self._get_db_connection()
            if not conn:
                return {}
            
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT category, content, keywords FROM knowledge 
                ORDER BY category, relevance_score DESC, updated_at DESC
            ''')
            
            results = cursor.fetchall()
            conn.close()
            
            # 按分类组织
            categorized = {}
            for category, content, keywords in results:
                if category not in categorized:
                    categorized[category] = []
                categorized[category].append((content, keywords))
            
            return categorized
            
        except Exception as e:
            print(f"❌ 获取分类知识失败: {e}")
            return {}
    
    def get_knowledge_stats(self):
        """获取知识库统计信息"""
        try:
            conn = self._get_db_connection()
            if not conn:
                return {"total": 0}
            
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT category, COUNT(*) as count 
                FROM knowledge 
                GROUP BY category
            ''')
            
            stats = {}
            for category, count in cursor.fetchall():
                stats[category] = count
            
            cursor.execute('SELECT COUNT(*) FROM knowledge')
            total = cursor.fetchone()[0]
            stats['total'] = total
            
            conn.close()
            return stats
            
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {"total": 0}
    
    def clear_knowledge(self):
        """清空知识库"""
        try:
            # 使用锁保护写操作
            with self.lock:
                conn = self._get_db_connection()
                if not conn:
                    raise Exception("无法获取数据库连接")
                
                cursor = conn.cursor()
                cursor.execute('DELETE FROM knowledge')
                conn.commit()
                conn.close()
            print("🗑️ 知识库已清空")
            return True
        except Exception as e:
            print(f"❌ 清空知识库失败: {e}")
            return False
    
    def _extract_keywords_enhanced(self, text):
        """增强的关键词提取"""
        if not text:
            return ""
        
        # 移除标点符号
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # 分词
        words = []
        for delimiter in [' ', '，', '。', '、', '；', '：', '！', '？', '\n', '\t']:
            text = text.replace(delimiter, ' ')
        
        # 过滤有效词汇
        for word in text.split():
            word = word.strip()
            # 保留2个字符以上的词，过滤常见停用词
            if len(word) >= 2 and word not in ['的', '了', '在', '是', '有', '和', '与', '等', '为', '之']:
                words.append(word)
        
        # 返回前15个关键词
        return ' '.join(words[:15])


# 创建全局知识库实例
knowledge_manager = LocalKnowledgeManager()