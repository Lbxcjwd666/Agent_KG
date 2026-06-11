"""
千问API调用模块
"""

import requests
import json
import re
from typing import List, Dict, Optional, Generator
from config import QWEN_API_CONFIG, ENTITY_TYPES
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def validate_extracted_entities(entities: List[Dict]) -> List[Dict]:
    """
    校验抽取的实体结果

    规则：
    1. 实体类型标签必须在16种定义内
    2. 实体文本不能为空或过短
    """
    valid_labels = set(ENTITY_TYPES.values())
    validated = []
    for ent in entities:
        text = (ent.get("text") or "").strip()
        label = (ent.get("label") or "").strip()
        ent_type = (ent.get("type") or "").strip()

        if len(text) < 2:
            continue
        if label and label not in valid_labels:
            continue

        validated.append({
            "text": text,
            "type": ent_type,
            "label": label if label else ent_type
        })
    return validated


class QwenAPI:
    """千问API客户端"""

    # 支持的文本对话模型列表
    SUPPORTED_TEXT_MODELS = [
        "qwen-turbo",
        "qwen-plus",
        "qwen-max",
        "qwen2.5-7b-instruct",
        "qwen2.5-14b-instruct",
        "qwen2.5-32b-instruct",
        "qwen2.5-72b-instruct"
    ]

    # 不支持的模型（需要特殊处理）
    UNSUPPORTED_MODELS = [
        "qwen2.5-vl",  # 视觉语言模型，需要图像输入
        "qwen2.5-vl-embedding",  # 嵌入模型，不用于对话
        "qwen-vl",  # 视觉语言模型
        "qwen-vl-plus"  # 视觉语言模型
    ]

    def __init__(self):
        self.api_key = QWEN_API_CONFIG["api_key"]
        self.base_url = QWEN_API_CONFIG["base_url"]
        self.model = QWEN_API_CONFIG["model"]
        self.temperature = QWEN_API_CONFIG["temperature"]
        self.max_tokens = QWEN_API_CONFIG["max_tokens"]

        # 验证模型配置
        self._validate_model()
    
    def _validate_model(self):
        """验证模型配置是否合理"""
        if self.model in self.UNSUPPORTED_MODELS:
            print(f"[WARNING] 模型 {self.model} 不适合文本对话任务")
            print(f"[INFO] 建议使用以下模型之一: {', '.join(self.SUPPORTED_TEXT_MODELS)}")
            print(f"[INFO] 当前将尝试使用 {self.model}，如果失败请修改配置")
        elif self.model not in self.SUPPORTED_TEXT_MODELS:
            print(f"[INFO] 模型 {self.model} 不在已知支持列表中，将尝试使用")
    
    def chat(self, messages: List[Dict], temperature: Optional[float] = None, 
             max_tokens: Optional[int] = None) -> str:
        """
        调用千问API进行对话
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大token数
        
        Returns:
            API返回的文本内容
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=30, verify=False)
            response.raise_for_status()
            
            result = response.json()
            
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            else:
                raise Exception(f"API返回格式错误: {result}")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"API请求失败: {str(e)}")

    def chat_stream(self, messages: List[Dict], temperature: Optional[float] = None,
                    max_tokens: Optional[int] = None) -> Generator[str, None, None]:
        """
        流式调用千问API进行对话

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Yields:
            逐token返回的文本delta
        """
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "stream": True
        }

        try:
            response = requests.post(url, headers=headers, json=data,
                                     timeout=60, stream=True, verify=False)
            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                    choices = obj.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                except json.JSONDecodeError:
                    continue

        except requests.exceptions.RequestException as e:
            raise Exception(f"流式API请求失败: {str(e)}")

    def extract_entities(self, text: str) -> List[Dict]:
        """
        使用千问API抽取实体
        从config.py动态读取ENTITY_TYPES，保持与配置一致
        """
        entity_types_str = "、".join(
            [f"{name}({label})" for name, label in ENTITY_TYPES.items()]
        )

        entity_count = len(ENTITY_TYPES)

        prompt = f"""你是一位专业的中医文本分析专家。请从以下文本中识别中医相关的实体。

实体类型共{entity_count}种：{entity_types_str}

请严格按照以下JSON格式输出结果：
{{
    "entities": [
        {{
            "text": "实体文本",
            "type": "实体类型名称",
            "label": "实体类型标签"
        }}
    ]
}}

待分析文本：{text}

请开始识别："""

        messages = [
            {"role": "system", "content": "你是一位专业的中医文本分析专家，擅长识别中医相关的实体。"},
            {"role": "user", "content": prompt}
        ]

        response = self.chat(messages, temperature=0.1)

        # 解析JSON响应
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)
                raw_entities = data.get("entities", [])
                return validate_extracted_entities(raw_entities)
            else:
                return []
        except Exception as e:
            print(f"解析实体响应失败: {e}")
            return []
    
    def extract_relation(self, text: str, head_entity: str, head_type: str) -> str:
        """
        使用千问API抽取关系
        """
        from config import RELATION_TYPES
        relation_types_str = "、".join(RELATION_TYPES.keys())
        
        prompt = f"""你是一位专业的中医文本分析专家。请从以下文本中识别实体之间的关系。

关系类型：{relation_types_str}

头实体：{head_entity}（{head_type}）

请从文本中识别头实体与其他实体之间的关系，只输出关系名称，不要输出其他内容。

待分析文本：{text}

关系："""
        
        messages = [
            {"role": "system", "content": "你是一位专业的中医文本分析专家，擅长识别实体之间的关系。"},
            {"role": "user", "content": prompt}
        ]
        
        response = self.chat(messages, temperature=0.1, max_tokens=100)
        return response.strip()
    
    def generate_answer(self, question: str, kg_context: str = "", conversation_history: List[Dict] = None) -> str:
        """
        使用千问API生成答案
        
        Args:
            question: 用户问题
            kg_context: 知识图谱增强的上下文
            conversation_history: 对话历史，格式为 [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        
        Returns:
            生成的答案
        """
        system_prompt = """你是一位专业的中医专家，擅长回答中医相关的问题。
请基于提供的知识图谱信息，给出准确、专业、易懂的回答。
重要提示：
1. 如果知识图谱信息不足，可以结合你的专业知识进行补充说明。
2. 在回答过程中，如果使用了知识图谱的信息，请自然地提到"根据知识图谱的信息可得..."，但不要明确说明实体间没有直接关联或图谱信息不对。
3. 如果知识图谱信息不足，直接基于你的专业知识回答即可，不要提及知识图谱的不足。
4. 每次回答末尾必须添加免责提示："建议咨询执业医师"或"仅供参考"。
5. 请保持多轮对话的连贯性，理解上下文语境，根据之前的对话内容进行回答。"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # 添加对话历史（如果有）
        if conversation_history:
            messages.extend(conversation_history)
        
        # 构建当前问题
        user_prompt = question
        if kg_context:
            user_prompt = f"{question}\n\n【知识图谱信息】\n{kg_context}"
        
        messages.append({"role": "user", "content": user_prompt})
        
        response = self.chat(messages, temperature=0.7, max_tokens=2000)
        
        # 确保回答末尾有免责提示
        if "建议咨询执业医师" not in response and "仅供参考" not in response:
            import random
            disclaimer = random.choice(["建议咨询执业医师", "仅供参考"])
            response = response.rstrip() + f"\n\n{disclaimer}"

        return response

    def generate_answer_stream(self, question: str, kg_context: str = "",
                               conversation_history: List[Dict] = None) -> Generator[str, None, None]:
        """
        流式使用千问API生成答案

        Args:
            question: 用户问题
            kg_context: 知识图谱增强的上下文
            conversation_history: 对话历史

        Yields:
            逐token返回的答案文本
        """
        system_prompt = """你是一位专业的中医专家，擅长回答中医相关的问题。
请基于提供的知识图谱信息，给出准确、专业、易懂的回答。
重要提示：
1. 如果知识图谱信息不足，可以结合你的专业知识进行补充说明。
2. 在回答过程中，如果使用了知识图谱的信息，请自然地提到"根据知识图谱的信息可得..."，但不要明确说明实体间没有直接关联或图谱信息不对。
3. 如果知识图谱信息不足，直接基于你的专业知识回答即可，不要提及知识图谱的不足。
4. 每次回答末尾必须添加免责提示："建议咨询执业医师"或"仅供参考"。
5. 请保持多轮对话的连贯性，理解上下文语境，根据之前的对话内容进行回答。"""

        messages = [{"role": "system", "content": system_prompt}]

        if conversation_history:
            messages.extend(conversation_history)

        user_prompt = question
        if kg_context:
            user_prompt = f"{question}\n\n【知识图谱信息】\n{kg_context}"

        messages.append({"role": "user", "content": user_prompt})

        full_response = ""
        for token in self.chat_stream(messages, temperature=0.7, max_tokens=2000):
            full_response += token
            yield token

        if "建议咨询执业医师" not in full_response and "仅供参考" not in full_response:
            import random
            disclaimer = random.choice(["建议咨询执业医师", "仅供参考"])
            yield f"\n\n{disclaimer}"

    def generate_suggested_questions(self, question: str, answer: str) -> List[str]:
        """
        根据问题和答案生成建议问题
        
        Args:
            question: 用户问题
            answer: AI回答
        
        Returns:
            建议问题列表
        """
        prompt = f"""基于以下问题和回答，生成3-5个用户可能感兴趣的后续问题。
问题和回答应该保持在同一语境下，问题应该与中医相关。

用户问题：{question}

AI回答：{answer}

请生成3-5个相关的后续问题，每个问题一行，不要编号，不要其他说明文字。"""
        
        messages = [
            {"role": "system", "content": "你是一位专业的中医问答助手，擅长根据对话内容生成相关的后续问题建议。"},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self.chat(messages, temperature=0.8, max_tokens=300)
            # 解析响应，提取问题
            questions = []
            for line in response.strip().split('\n'):
                line = line.strip()
                # 移除编号（如"1. "、"1、"等）
                import re
                line = re.sub(r'^\d+[\.、]\s*', '', line)
                # 移除其他标记
                line = re.sub(r'^[-\*]\s*', '', line)
                if line and len(line) > 5 and '？' in line or '?' in line or len(line) > 10:
                    questions.append(line)
            
            # 如果解析失败，返回默认问题
            if not questions:
                questions = [
                    f"关于{question}，还有其他相关问题吗？",
                    "能否提供更多详细信息？",
                    "还有其他需要注意的事项吗？"
                ]
            
            return questions[:5]  # 最多返回5个问题
        except Exception as e:
            print(f"生成建议问题失败: {e}")
            return []