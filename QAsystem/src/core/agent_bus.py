"""
Agent 消息总线 — Agent 间通信与事件发布/订阅
"""

from typing import Dict, Callable, List
from collections import defaultdict
import time
import logging


class AgentBus:
    """Agent 消息总线"""

    def __init__(self):
        self.agents: Dict[str, object] = {}            # name -> Agent 实例
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.execution_log: List[Dict] = []
        self.logger = logging.getLogger("agent_bus")

    def register(self, name: str, agent: object):
        """注册 Agent"""
        self.agents[name] = agent
        self.logger.info(f"注册 Agent: {name}")

    def unregister(self, name: str):
        """注销 Agent"""
        self.agents.pop(name, None)

    def request(self, target_agent: str, payload: Dict) -> Dict:
        """
        同步请求-响应：调用指定 Agent 并返回结果

        Args:
            target_agent: Agent 名称
            payload: 传递给 Agent 的输入

        Returns:
            Agent 执行结果
        """
        agent = self.agents.get(target_agent)
        if not agent:
            return {"_meta": {"status": "error", "error": f"Agent '{target_agent}' 未注册"}}

        result = agent.execute(payload, bus=self)
        self.execution_log.append({
            "agent": target_agent,
            "timestamp": time.time(),
            "status": result.get("_meta", {}).get("status", "unknown"),
            "duration_ms": result.get("_meta", {}).get("duration_ms", 0)
        })
        return result

    def publish(self, topic: str, event: Dict):
        """
        发布事件到主题，通知所有订阅者

        Args:
            topic: 事件主题（如 agent_start, agent_done, answer_token）
            event: 事件数据
        """
        event["topic"] = topic
        for callback in self.subscribers.get(topic, []):
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"订阅者回调失败 [{topic}]: {e}")

        # 也通知通配符订阅者
        for callback in self.subscribers.get("*", []):
            try:
                callback(event)
            except Exception as e:
                self.logger.error(f"通配符回调失败: {e}")

    def subscribe(self, topic: str, callback: Callable):
        """
        订阅事件主题

        Args:
            topic: 事件主题
            callback: 回调函数 callback(event: dict)
        """
        self.subscribers[topic].append(callback)

    def stream_events(self, target_agent: str, payload: Dict):
        """
        执行 Agent 并通过 publish 推送中间事件（用于 SSE）

        事件序列: agent_start → agent_progress(多次) → agent_done/agent_error
        """
        agent = self.agents.get(target_agent)
        if not agent:
            self.publish("agent_error", {
                "agent": target_agent,
                "error": f"Agent '{target_agent}' 未注册"
            })
            return

        result = agent.execute(payload, bus=self)
        return result

    def get_execution_summary(self) -> Dict:
        """获取执行摘要"""
        total = len(self.execution_log)
        success = sum(1 for e in self.execution_log if e["status"] == "ok")
        total_time = sum(e.get("duration_ms", 0) for e in self.execution_log)
        return {
            "total_agents": total,
            "success_count": success,
            "failed_count": total - success,
            "total_duration_ms": total_time,
            "log": self.execution_log
        }

    def __repr__(self):
        return f"AgentBus(agents={list(self.agents.keys())}, log_entries={len(self.execution_log)})"
