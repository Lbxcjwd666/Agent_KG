"""
诊断推理 Agent — 5步辨证推理链
症状聚类 → 证候匹配 → 病因推导 → 鉴别诊断 → 治则确定
"""

from core.base_agent import BaseAgent
from typing import Dict, List


DIAGNOSIS_PROMPT = """你是一位资深中医辨证专家。请根据以下患者信息进行辨证论治。

【患者信息】
主诉: {question}

【知识图谱参考】
{kg_context}

【辨证要求】
按以下5步进行推理：

1. **症状聚类**: 识别主症、兼症、舌脉信息，归类到脏腑经络
2. **证候匹配**: 在知识图谱中查询症状集合关联的证候(SYN)，按匹配度排序
3. **病因推导**: 通过舌象→病因(TNG→reflect→BEC)、脉象→经脉(PUL→abpulse→MER)推导病因病机
4. **鉴别诊断**: 列出相似证候的区分要点
5. **治则确定**: 基于最终证候确定治疗原则

请输出JSON格式:
{{
    "syndrome": {{
        "primary": "主要证候名称",
        "alternative": ["备选证候"],
        "confidence": 0.85
    }},
    "etiology": {{
        "cause": "病因",
        "mechanism": "病机",
        "confidence": 0.80
    }},
    "differential": [
        {{"syndrome": "相似证候", "difference": "区分要点"}}
    ],
    "treatment_principle": "治则",
    "reasoning_chain": [
        {{
            "step": 1,
            "name": "症状聚类",
            "conclusion": "...",
            "evidence": ["KG三元组1", "KG三元组2"],
            "confidence": 0.90
        }}
    ],
    "overall_confidence": 0.85
}}"""


class DiagnosisReasoningAgent(BaseAgent):
    """诊断推理 Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("diagnosis_reasoning", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        question = payload.get("question", "")
        complexity = payload.get("complexity", "simple")
        kg_context = payload.get("kg_context", "")
        entities = payload.get("entities", [])

        # 如果没有 kg_context，尝试自行查询
        if not kg_context and self.kg and entities:
            kg_results = {}
            for ent in entities[:3]:
                text = ent.get("text", "")
                etype = ent.get("label", ent.get("type", ""))
                if text and etype:
                    r = self.kg.query_relations_layered(text, etype, "L1")
                    if r:
                        kg_results[text] = r
            kg_context = self._summarize_kg(kg_results)

        # 执行辨证推理
        prompt = DIAGNOSIS_PROMPT.format(
            question=question,
            kg_context=kg_context or "（未检索到知识图谱信息，请基于专业知识）"
        )

        messages = [{"role": "user", "content": prompt}]
        response = self._llm_call(messages, temperature=0.3, max_tokens=2000)
        result = self._parse_json_response(response)

        if not result:
            return self._fallback_result(question)

        return {
            "syndrome": result.get("syndrome", {}),
            "etiology": result.get("etiology", {}),
            "differential": result.get("differential", []),
            "treatment_principle": result.get("treatment_principle", ""),
            "reasoning_chain": result.get("reasoning_chain", []),
            "overall_confidence": result.get("overall_confidence", 0.7),
            "kg_context_used": bool(kg_context)
        }

    def _summarize_kg(self, kg_results: Dict) -> str:
        parts = []
        for entity, data in kg_results.items():
            if isinstance(data, dict):
                for key, values in data.items():
                    if values:
                        names = [v.get("text", "") for v in values[:3]]
                        parts.append(f"{entity} {key}: {', '.join(names)}")
        return "\n".join(parts[:20])

    def _fallback_result(self, question: str) -> Dict:
        return {
            "syndrome": {"primary": "待进一步辨证", "confidence": 0.3},
            "etiology": {"cause": "待分析", "mechanism": "待分析", "confidence": 0.3},
            "differential": [],
            "treatment_principle": "建议提供更多症状信息",
            "reasoning_chain": [],
            "overall_confidence": 0.3,
            "kg_context_used": False
        }
