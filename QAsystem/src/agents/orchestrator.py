"""
协调者 Agent — 意图分类 + 复杂度评估 + DAG 执行计划生成
"""

from core.base_agent import BaseAgent
from typing import Dict


INTENT_TEMPLATE = """你是一位中医临床决策协调专家。请分析用户问题，输出JSON格式。

用户问题: {question}

请输出:
{{
    "intent": "diagnosis" | "prescription" | "acupuncture" | "simple_qa" | "knowledge_learning",
    "complexity": "simple" | "medium" | "complex",
    "reason": "简述分类理由"
}}

分类标准:
- diagnosis: 包含症状、舌脉、体征，寻求证候判断
- prescription: 已明确证候/病名，寻求方剂或药物治疗
- acupuncture: 涉及腧穴、经脉、针灸治疗
- simple_qa: 简单的知识问答（"人参有什么功效"、"什么是经络"）
- knowledge_learning: 涉及引入新知识、纠正或补充"""


class OrchestratorAgent(BaseAgent):
    """协调者 Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("orchestrator", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        question = payload.get("question", "")
        conversation_history = payload.get("conversation_history", [])

        # 1. 意图分类
        classification = self._classify_intent(question)
        intent = classification.get("intent", "simple_qa")
        complexity = classification.get("complexity", "simple")

        # 2. 生成执行计划 DAG
        plan = self._build_plan(intent, complexity, question, conversation_history)

        return {
            "intent": intent,
            "complexity": complexity,
            "reason": classification.get("reason", ""),
            "plan": plan,
            "plan_summary": " → ".join([t["task_id"] for t in plan])
        }

    def _classify_intent(self, question: str) -> Dict:
        prompt = INTENT_TEMPLATE.format(question=question)
        messages = [{"role": "user", "content": prompt}]
        try:
            response = self._llm_call(messages, temperature=0.2, max_tokens=300)
            return self._parse_json_response(response)
        except Exception:
            return {"intent": "simple_qa", "complexity": "simple"}

    def _build_plan(self, intent: str, complexity: str,
                    question: str, history: list) -> list:
        """根据意图和复杂度生成 DAG 执行计划"""

        plans = {
            "simple_qa": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "L1"}, "depends_on": ["entity_recognition"]},
                {"task_id": "generate_answer", "agent": "explanation",
                 "params": {"question": question, "layer": "simple"},
                 "depends_on": ["kg_query"]},
            ],

            "diagnosis": {
                "simple": [
                    {"task_id": "entity_recognition", "agent": "entity_recognition",
                     "params": {"question": question}, "depends_on": []},
                    {"task_id": "kg_query", "agent": "kg_query",
                     "params": {"layer": "L2"}, "depends_on": ["entity_recognition"]},
                    {"task_id": "diagnosis_reasoning", "agent": "diagnosis_reasoning",
                     "params": {"question": question, "complexity": "simple"},
                     "depends_on": ["kg_query"]},
                    {"task_id": "verification", "agent": "verification",
                     "params": {}, "depends_on": ["diagnosis_reasoning"]},
                    {"task_id": "explanation", "agent": "explanation",
                     "params": {"question": question, "layer": "full"},
                     "depends_on": ["diagnosis_reasoning", "verification"]},
                ],
                "medium": [
                    {"task_id": "entity_recognition", "agent": "entity_recognition",
                     "params": {"question": question}, "depends_on": []},
                    {"task_id": "kg_query", "agent": "kg_query",
                     "params": {"layer": "ALL"}, "depends_on": ["entity_recognition"]},
                    {"task_id": "diagnosis_reasoning", "agent": "diagnosis_reasoning",
                     "params": {"question": question, "complexity": "medium"},
                     "depends_on": ["kg_query"]},
                    {"task_id": "prescription", "agent": "prescription",
                     "params": {}, "depends_on": ["diagnosis_reasoning"]},
                    {"task_id": "verification", "agent": "verification",
                     "params": {}, "depends_on": ["diagnosis_reasoning", "prescription"]},
                    {"task_id": "explanation", "agent": "explanation",
                     "params": {"question": question, "layer": "full"},
                     "depends_on": ["diagnosis_reasoning", "prescription", "verification"]},
                ],
                "complex": [
                    {"task_id": "entity_recognition", "agent": "entity_recognition",
                     "params": {"question": question}, "depends_on": []},
                    {"task_id": "kg_query", "agent": "kg_query",
                     "params": {"layer": "ALL"}, "depends_on": ["entity_recognition"]},
                    {"task_id": "diagnosis_reasoning", "agent": "diagnosis_reasoning",
                     "params": {"question": question, "complexity": "complex"},
                     "depends_on": ["kg_query"]},
                    {"task_id": "prescription", "agent": "prescription",
                     "params": {"include_acupuncture": True},
                     "depends_on": ["diagnosis_reasoning"]},
                    {"task_id": "verification", "agent": "verification",
                     "params": {"strict": True},
                     "depends_on": ["diagnosis_reasoning", "prescription"]},
                    {"task_id": "explanation", "agent": "explanation",
                     "params": {"question": question, "layer": "full"},
                     "depends_on": ["diagnosis_reasoning", "prescription", "verification"]},
                    {"task_id": "continuous_learning", "agent": "continuous_learning",
                     "params": {}, "depends_on": ["explanation"]},
                ],
            },

            "prescription": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "L2"}, "depends_on": ["entity_recognition"]},
                {"task_id": "prescription", "agent": "prescription",
                 "params": {"question": question},
                 "depends_on": ["kg_query"]},
                {"task_id": "verification", "agent": "verification",
                 "params": {}, "depends_on": ["prescription"]},
                {"task_id": "explanation", "agent": "explanation",
                 "params": {"question": question, "layer": "full"},
                 "depends_on": ["prescription", "verification"]},
            ],

            "acupuncture": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "ALL"}, "depends_on": ["entity_recognition"]},
                {"task_id": "prescription", "agent": "prescription",
                 "params": {"question": question, "mode": "acupuncture"},
                 "depends_on": ["kg_query"]},
                {"task_id": "explanation", "agent": "explanation",
                 "params": {"question": question, "layer": "full"},
                 "depends_on": ["prescription"]},
            ],

            "knowledge_learning": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "L2"}, "depends_on": ["entity_recognition"]},
                {"task_id": "generate_answer", "agent": "explanation",
                 "params": {"question": question, "layer": "simple"},
                 "depends_on": ["kg_query"]},
                {"task_id": "continuous_learning", "agent": "continuous_learning",
                 "params": {"source": "user_query"},
                 "depends_on": ["generate_answer"]},
            ],
        }

        if intent in plans:
            if intent == "diagnosis" and complexity in plans["diagnosis"]:
                return plans["diagnosis"][complexity]
            return plans[intent]

        return plans["simple_qa"]
