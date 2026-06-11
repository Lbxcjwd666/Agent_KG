"""
辨证Agent — 5步推理链 + 多轮追问
症状聚类 → 证候匹配 → 病因推导 → 鉴别诊断 → 治则确定
"""

from core.base_agent import BaseAgent
from typing import Dict

DIAGNOSIS_SYSTEM = """你是一位资深中医辨证专家。请根据患者信息进行系统辨证。

【辨证步骤】
1. 症状聚类：识别主症、兼症、舌象(TNG)、脉象(PUL)，归类到脏腑经络
2. 证候匹配：在知识图谱中查询症状→证候(SYN)关联，计算匹配度排序
3. 病因推导：舌象→病因病机(TNG→reflect→BEC)，脉象→经脉(PUL→abpulse→MER)
4. 鉴别诊断：列出2-3个相似证候及其区分要点
5. 治则确定：基于最终证候确定治疗原则

【输出格式】严格输出JSON:
{
    "chief_complaint": "主诉概括",
    "symptom_clusters": [
        {"group": "热象症状", "symptoms": ["面红", "目赤", "口干"], "meridian": "肝经"}
    ],
    "syndrome": {
        "primary": {"name": "证候名", "label": "SYN", "confidence": 0.91},
        "alternatives": [{"name": "备选证候", "confidence": 0.72}]
    },
    "etiology": {
        "cause": "病因",
        "mechanism": "病机演变",
        "pathway": ["A→B→C"],
        "evidence": ["舌红苔黄→reflect→肝火上炎"]
    },
    "differential": [
        {"syndrome": "相似证候", "key_difference": "区分要点"}
    ],
    "treatment_principle": "治则概括",
    "missing_info": ["缺失的四诊信息，如舌象、脉象等"],
    "follow_up_questions": ["追问1", "追问2"],
    "reasoning_chain": [
        {"step": 1, "name": "症状聚类", "conclusion": "...", "evidence": [...], "confidence": 0.9}
    ],
    "overall_confidence": 0.85
}

【重要】
- 如果四诊信息不足（缺舌象/脉象等），在missing_info中列出，在follow_up_questions中生成追问
- 每一步推理必须在evidence中引用具体的KG查询路径
- confidence基于证据强度和症状覆盖度综合评估"""


class DiagnosisAgent(BaseAgent):
    """辨证Agent — 5步推理链"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("diagnosis", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        question = payload.get("question", "")
        kg_context = payload.get("kg_context", "")
        entities = payload.get("entities", [])
        conversation_history = payload.get("conversation_history", [])
        collected_info = payload.get("collected_info", {})

        # 构建增强的患者信息
        patient_info = self._build_patient_context(question, entities, collected_info)

        # KG上下文（自行查询或使用传入的）
        if not kg_context and self.kg and entities:
            kg_context = self._query_kg_for_diagnosis(entities)

        # LLM辨证推理
        prompt = self._build_prompt(patient_info, kg_context, conversation_history)
        messages = [
            {"role": "system", "content": DIAGNOSIS_SYSTEM},
            {"role": "user", "content": prompt}
        ]

        response = self._llm_call(messages, temperature=0.3, max_tokens=2000)
        result = self._parse_json_response(response)

        if not result:
            return self._fallback(question, kg_context)

        # 判断是否需要追问
        missing = result.get("missing_info", [])
        need_followup = len(missing) > 0 and len(conversation_history) < 6

        return {
            "chief_complaint": result.get("chief_complaint", question),
            "symptom_clusters": result.get("symptom_clusters", []),
            "syndrome": result.get("syndrome", {}),
            "etiology": result.get("etiology", {}),
            "differential": result.get("differential", []),
            "treatment_principle": result.get("treatment_principle", ""),
            "reasoning_chain": result.get("reasoning_chain", []),
            "overall_confidence": result.get("overall_confidence", 0.7),
            "missing_info": missing,
            "follow_up_questions": result.get("follow_up_questions", []),
            "need_followup": need_followup,
            "kg_context_used": bool(kg_context)
        }

    def _build_patient_context(self, question: str, entities: list,
                               collected: Dict) -> str:
        parts = [f"患者描述: {question}"]
        if entities:
            entity_str = ", ".join([f"{e.get('text','')}({e.get('label','')})"
                                    for e in entities[:10]])
            parts.append(f"已识别实体: {entity_str}")
        if collected:
            parts.append(f"已采集信息: {collected}")
        return "\n".join(parts)

    def _query_kg_for_diagnosis(self, entities: list) -> str:
        """自行查询KG获取辨证所需信息"""
        parts = []
        for ent in entities[:5]:
            text = ent.get("text", ent.get("original_text", ""))
            etype = ent.get("label", ent.get("type", ""))
            if not text or not etype:
                continue
            try:
                results = self.kg.query_relations_layered(text, etype, "L1")
                if results:
                    ctx = self.kg.format_kg_context(results, text, etype)
                    parts.append(ctx)
            except Exception:
                continue
        return "\n".join(parts)

    def _build_prompt(self, patient_info: str, kg_context: str,
                      history: list) -> str:
        prompt = f"【患者信息】\n{patient_info}"
        if kg_context:
            prompt += f"\n\n【知识图谱参考】\n{kg_context}"
        if history:
            recent = history[-6:]
            hist_str = "\n".join([f"{m['role']}: {m['content'][:200]}"
                                  for m in recent])
            prompt += f"\n\n【对话历史】\n{hist_str}"
        prompt += "\n\n请进行系统辨证分析，输出JSON。"
        return prompt

    def _fallback(self, question: str, kg: str) -> Dict:
        return {
            "chief_complaint": question,
            "syndrome": {"primary": {"name": "待完善", "confidence": 0.3}},
            "treatment_principle": "请补充舌脉信息后再辨证",
            "missing_info": ["舌象", "脉象"],
            "follow_up_questions": ["请问舌象如何？舌色、舌苔厚薄？", "请问脉象怎样？浮沉迟数？"],
            "need_followup": True,
            "overall_confidence": 0.3,
            "kg_context_used": bool(kg)
        }
