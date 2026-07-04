"""
Agent 基类 — 所有智能体的抽象基类
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from config import AGENT_CONFIG
import json
import re
import time
import logging


class BaseAgent(ABC):
    """智能体基类"""

    def __init__(self, name: str, qwen_api, kg_enhancer=None):
        self.name = name
        self.agent_config = AGENT_CONFIG.get(name, {})
        self.model = self.agent_config.get("model", "qwen3.7-plus")
        self.timeout = self.agent_config.get("timeout", 15)
        self.qwen_api = qwen_api
        self.kg = kg_enhancer
        self.logger = logging.getLogger(f"agent.{name}")

    @abstractmethod
    def run(self, payload: Dict) -> Dict:
        """
        执行 Agent 核心逻辑

        Args:
            payload: 输入数据字典

        Returns:
            输出数据字典，必须包含 status 字段 (ok/error)
        """
        pass

    def _llm_call(self, messages: list, temperature: float = 0.3,
                  max_tokens: int = 1500) -> str:
        """通用 LLM 调用"""
        try:
            return self.qwen_api.chat(messages, temperature=temperature,
                                      max_tokens=max_tokens)
        except Exception as e:
            self.logger.error(f"LLM调用失败: {e}")
            raise

    def _parse_json_response(self, response: str) -> Dict:
        """从 LLM 响应中提取 JSON"""
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        return {}

    def execute(self, payload: Dict, bus=None) -> Dict:
        """
        带超时和追踪的执行包装

        Args:
            payload: 输入数据
            bus: AgentBus 实例（可选，用于发布事件）

        Returns:
            执行结果
        """
        start_time = time.time()
        self.logger.info(f"[{self.name}] 开始执行")

        if bus:
            bus.publish("agent_start", {
                "agent": self.name,
                "timestamp": start_time
            })

        try:
            result = self.run(payload)
            duration_ms = int((time.time() - start_time) * 1000)
            result["_meta"] = {
                "agent": self.name,
                "status": "ok",
                "duration_ms": duration_ms
            }
            self.logger.info(f"[{self.name}] 完成, 耗时 {duration_ms}ms")

            if bus:
                bus.publish("agent_done", {
                    "agent": self.name,
                    "duration_ms": duration_ms,
                    "summary": self._summarize_result(result)
                })

            return result

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            self.logger.error(f"[{self.name}] 失败: {e}, 耗时 {duration_ms}ms")

            if bus:
                bus.publish("agent_error", {
                    "agent": self.name,
                    "error": str(e),
                    "duration_ms": duration_ms
                })

            return {
                "_meta": {
                    "agent": self.name,
                    "status": "error",
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            }

    def _summarize_result(self, result: Dict) -> str:
        """生成结果摘要（子类可覆盖）"""
        keys = [k for k in result.keys() if not k.startswith("_")]
        return f"输出字段: {', '.join(keys[:5])}"
