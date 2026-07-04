"""
养生Agent — 体质适配饮食建议 + 忌口 + 起居调摄
"""

from core.base_agent import BaseAgent
from typing import Dict

REGIMEN_SYSTEM = """你是一位资深中医养生专家。请根据辨证结果提供养生调护方案。

【推荐步骤】
1. 体质(CON)识别 → 饮食建议(food_to_eat→FOO)
2. 证候(SYN)→ 忌口(Food_to_avoid→FOO)
3. 季节时令适配
4. 情志调摄、运动导引

【输出格式】严格输出JSON:
{
    "dietary_advice": {
        "recommended": [
            {"food": "食物名", "reason": "理由", "evidence": "KG: CON→food_to_eat→食物"}
        ],
        "avoid": [
            {"food": "食物名", "reason": "理由", "evidence": "KG: SYN→Food_to_avoid→食物"}
        ],
        "principles": ["饮食原则1", "饮食原则2"]
    },
    "lifestyle": {
        "exercise": "运动建议",
        "sleep": "作息建议",
        "emotional": "情志调摄"
    },
    "seasonal_notes": "季节注意事项",
    "overall_confidence": 0.82
}"""


class RegimenAgent(BaseAgent):
    """养生Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("regimen", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        diagnosis_result = payload.get("diagnosis", {})
        kg_context = payload.get("kg_context", "")
        entities = payload.get("entities", [])
        subgraph = payload.get("subgraph", {})

        syndrome = diagnosis_result.get("syndrome", {})
        syndrome_name = ""
        if isinstance(syndrome.get("primary"), dict):
            syndrome_name = syndrome["primary"].get("name", "")

        constitution = self._find_entity_by_type(entities, "CON")

        regimen_kg = ""
        if subgraph:
            regimen_kg = self._format_subgraph(subgraph)
        elif kg_context:
            regimen_kg = kg_context
        elif self.kg:
            regimen_kg = self._query_regimen(syndrome_name, constitution, entities)

        prompt = self._build_prompt(syndrome_name, constitution, regimen_kg, kg_context)
        messages = [
            {"role": "system", "content": REGIMEN_SYSTEM},
            {"role": "user", "content": prompt}
        ]

        response = self._llm_call(messages, temperature=0.3, max_tokens=1200)
        result = self._parse_json_response(response)

        if not result:
            return self._fallback()

        return {
            "dietary_advice": result.get("dietary_advice", {}),
            "lifestyle": result.get("lifestyle", {}),
            "seasonal_notes": result.get("seasonal_notes", ""),
            "overall_confidence": result.get("overall_confidence", 0.8),
            "kg_context_used": bool(regimen_kg) or bool(kg_context)
        }

    def _find_entity_by_type(self, entities: list, target_type: str) -> str:
        for ent in entities:
            if ent.get("label", ent.get("type", "")) == target_type:
                return ent.get("text", "")
        return ""

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

    def _query_regimen(self, syndrome_name: str, constitution: str,
                       entities: list) -> str:
        parts = []
        try:
            # 查询饮食建议
            if constitution:
                results = self.kg.query_relations(constitution, "CON", "宜吃")
                if results:
                    ctx = self.kg.format_kg_context(results, constitution, "CON")
                    parts.append(ctx)

            # 查询忌口
            if syndrome_name:
                for rel in ["不宜吃", "Food_to_avoid"]:
                    try:
                        results = self.kg.query_relations(syndrome_name, "SYN", "不宜吃")
                        if results:
                            ctx = self.kg.format_kg_context(results, syndrome_name, "SYN")
                            parts.append(ctx)
                            break
                    except Exception:
                        continue

            # 查食物相关实体
            for ent in entities[:3]:
                text = ent.get("text", "")
                etype = ent.get("label", ent.get("type", ""))
                if etype in ("FOO", "CON") and text:
                    r = self.kg.query_relations_layered(text, etype, "L1")
                    if r:
                        ctx = self.kg.format_kg_context(r, text, etype)
                        parts.append(ctx)
        except Exception:
            pass
        return "\n".join(parts)

    def _build_prompt(self, syndrome: str, constitution: str,
                      regimen_kg: str, kg_ctx: str) -> str:
        parts = []
        if syndrome:
            parts.append(f"证候: {syndrome}")
        if constitution:
            parts.append(f"体质: {constitution}")
        kg_all = "\n".join(filter(None, [regimen_kg, kg_ctx]))
        if kg_all:
            parts.append(f"\n【KG参考】\n{kg_all}")
        return "\n".join(parts)

    def _fallback(self) -> Dict:
        return {
            "dietary_advice": {"principles": ["饮食有节", "均衡营养"]},
            "overall_confidence": 0.3
        }