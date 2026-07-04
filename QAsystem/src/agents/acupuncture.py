"""
针灸Agent — 证候→腧穴匹配 + 经脉分析 + 针刺手法
"""

from core.base_agent import BaseAgent
from typing import Dict

ACUPUNCTURE_SYSTEM = """你是一位资深中医针灸专家。请根据辨证结果推荐针灸处方。

【推荐步骤】
1. 证候→腧穴匹配：TNG→acupoints→ACU，SYN/DIS→treat→ACU
2. 经脉分析：ACU→belongto→MER，分析经脉关联
3. 配穴方案：主穴+配穴，远近配穴、上下配穴
4. 针刺手法：提插补泻、捻转补泻，留针时间

【输出格式】严格输出JSON:
{
    "primary_points": [
        {"name": "腧穴名", "meridian": "所属经脉", "location": "定位", "method": "刺法", "evidence": "KG: 证候→acupoints→腧穴"}
    ],
    "secondary_points": [
        {"name": "配穴", "reason": "配穴理由"}
    ],
    "meridian_analysis": "经脉分析说明",
    "needle_technique": {
        "reinforce_reduce": "补泻手法",
        "retention": "留针时间(分钟)",
        "moxibustion": "是否加灸"
    },
    "contraindicated_points": ["禁针穴位"],
    "overall_confidence": 0.85
}"""


class AcupunctureAgent(BaseAgent):
    """针灸Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("acupuncture", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        diagnosis_result = payload.get("diagnosis", {})
        kg_context = payload.get("kg_context", "")
        entities = payload.get("entities", [])
        question = payload.get("question", "")
        subgraph = payload.get("subgraph", {})

        syndrome = diagnosis_result.get("syndrome", {})
        syndrome_name = ""
        if isinstance(syndrome.get("primary"), dict):
            syndrome_name = syndrome["primary"].get("name", "")

        acu_kg = ""
        if subgraph:
            acu_kg = self._format_subgraph(subgraph)
        elif kg_context:
            acu_kg = kg_context
        elif self.kg:
            acu_kg = self._query_acupuncture(syndrome_name, entities)

        prompt = self._build_prompt(question, syndrome_name, acu_kg, kg_context)
        messages = [
            {"role": "system", "content": ACUPUNCTURE_SYSTEM},
            {"role": "user", "content": prompt}
        ]

        response = self._llm_call(messages, temperature=0.3, max_tokens=1500)
        result = self._parse_json_response(response)

        if not result:
            return self._fallback()

        return {
            "primary_points": result.get("primary_points", []),
            "secondary_points": result.get("secondary_points", []),
            "meridian_analysis": result.get("meridian_analysis", ""),
            "needle_technique": result.get("needle_technique", {}),
            "contraindicated_points": result.get("contraindicated_points", []),
            "overall_confidence": result.get("overall_confidence", 0.8),
            "kg_context_used": bool(acu_kg) or bool(kg_context)
        }

    def _format_subgraph(self, subgraph: Dict) -> str:
        """格式化专属子图为自然语言"""
        parts = []
        for entity_text, data in subgraph.items():
            if not isinstance(data, dict):
                continue
            entity_type = data.get("type", "")
            parts.append(f"【{entity_text}（{entity_type}）】")
            for key, values in data.get("relations", {}).items():
                if not values:
                    continue
                names = [v.get("text", "") for v in values[:5]]
                parts.append(f"  {key}: {', '.join(names)}")
        return "\n".join(parts)

    def _query_acupuncture(self, syndrome_name: str, entities: list) -> str:
        parts = []
        try:
            if syndrome_name:
                # 查询证候关联的腧穴
                for rel in ["治疗ACU", "治疗"]:
                    results = self.kg.query_relations(syndrome_name, "SYN", rel)
                    if results:
                        ctx = self.kg.format_kg_context(results, syndrome_name, "SYN")
                        parts.append(ctx)
                        break

            # 查TNG相关
            for ent in entities[:3]:
                text = ent.get("text", "")
                etype = ent.get("label", ent.get("type", ""))
                if etype == "TNG" and text:
                    results = self.kg.query_relations(text, "TNG", "治疗ACU")
                    if results:
                        ctx = self.kg.format_kg_context(results, text, "TNG")
                        parts.append(ctx)
        except Exception:
            pass
        return "\n".join(parts)

    def _build_prompt(self, question: str, syndrome: str,
                      acu_kg: str, kg_ctx: str) -> str:
        parts = []
        if question:
            parts.append(f"患者问题: {question}")
        if syndrome:
            parts.append(f"证候: {syndrome}")
        kg_all = "\n".join(filter(None, [acu_kg, kg_ctx]))
        if kg_all:
            parts.append(f"\n【KG参考】\n{kg_all}")
        return "\n".join(parts)

    def _fallback(self) -> Dict:
        return {
            "primary_points": [],
            "secondary_points": [],
            "meridian_analysis": "需更多证候信息",
            "overall_confidence": 0.3
        }