"""
方剂Agent — 治则→方剂匹配 + 组成分析 + 加减化裁 + 禁忌检查
"""

from core.base_agent import BaseAgent
from typing import Dict, List

FORMULA_SYSTEM = """你是一位资深中医方剂学专家。请根据辨证结果推荐方剂。

【推荐步骤】
1. 治则→方剂匹配：在KG中查询证候(SYN)←treat—方剂(PRE)
2. 方剂组成分析：PRE→comp→各MED，分析君臣佐使配伍
3. 加减化裁：根据兼症、体质(CON)推荐加减药物
4. 禁忌检查：查询不宜吃(Food_to_avoid)关系、药物配伍禁忌
5. 剂量建议：给出参考剂量范围

【输出格式】严格输出JSON:
{
    "primary_formula": {
        "name": "方剂名",
        "confidence": 0.93,
        "evidence": "KG: 证候←treat—方剂名",
        "composition": [
            {"herb": "药名", "role": "君/臣/佐/使", "dosage_range": "3-9g", "evidence": "KG: 方剂→comp→药物"}
        ],
        "modifications": [
            {"condition": "兼症", "add": ["药1"], "remove": ["药2"], "reason": "理由"}
        ]
    },
    "alternatives": [{"name": "备选方", "scenario": "适用场景"}],
    "contraindications": [
        {"herb": "药名", "risk": "禁忌说明", "severity": "high/medium/low"}
    ],
    "preparation": "煎服法建议",
    "overall_confidence": 0.88
}

【重要】每个药物组成必须引用KG证据(PRE→comp→MED)，无KG证据的标注为"模型推断"。"""


class FormulaAgent(BaseAgent):
    """方剂Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("formula", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        diagnosis_result = payload.get("diagnosis", {})
        kg_context = payload.get("kg_context", "")
        entities = payload.get("entities", [])
        question = payload.get("question", "")

        syndrome = diagnosis_result.get("syndrome", {})
        syndrome_name = ""
        if isinstance(syndrome.get("primary"), dict):
            syndrome_name = syndrome["primary"].get("name", "")
        elif isinstance(syndrome.get("primary"), str):
            syndrome_name = syndrome["primary"]

        treatment = diagnosis_result.get("treatment_principle", "")

        # KG查询方剂
        formula_kg = ""
        if self.kg and syndrome_name:
            formula_kg = self._query_formulas(syndrome_name, entities)

        # LLM方剂推荐
        prompt = self._build_prompt(syndrome_name, treatment, formula_kg,
                                    kg_context, question)
        messages = [
            {"role": "system", "content": FORMULA_SYSTEM},
            {"role": "user", "content": prompt}
        ]

        response = self._llm_call(messages, temperature=0.3, max_tokens=1800)
        result = self._parse_json_response(response)

        if not result:
            return self._fallback(syndrome_name, treatment)

        # 结构化禁忌检查
        contraindications = result.get("contraindications", [])
        if self.kg:
            contraindications = self._check_contraindications(
                result.get("primary_formula", {}).get("composition", []),
                contraindications)

        return {
            "primary_formula": result.get("primary_formula", {}),
            "alternatives": result.get("alternatives", []),
            "modifications": result.get("primary_formula", {}).get("modifications", []),
            "contraindications": contraindications,
            "preparation": result.get("preparation", ""),
            "overall_confidence": result.get("overall_confidence", 0.8),
            "kg_context_used": bool(formula_kg)
        }

    def _query_formulas(self, syndrome_name: str, entities: list) -> str:
        """查询KG获取方剂信息"""
        parts = []
        try:
            # 查询证候的treat关系 → 方剂
            results = self.kg.query_relations(syndrome_name, "SYN", "治疗")
            if results:
                ctx = self.kg.format_kg_context(results, syndrome_name, "SYN")
                parts.append(ctx)

            # 对于每个证候相关的实体，也查一下
            for ent in entities[:3]:
                text = ent.get("text", "")
                etype = ent.get("label", ent.get("type", ""))
                if text and etype and text != syndrome_name:
                    r = self.kg.query_relations_layered(text, etype, "L1")
                    if r:
                        ctx = self.kg.format_kg_context(r, text, etype)
                        parts.append(ctx)
        except Exception:
            pass
        return "\n".join(parts)

    def _build_prompt(self, syndrome: str, treatment: str,
                      formula_kg: str, kg_ctx: str, question: str) -> str:
        parts = []
        if question:
            parts.append(f"患者问题: {question}")
        if syndrome:
            parts.append(f"辨证结果: {syndrome}")
        if treatment:
            parts.append(f"治则: {treatment}")
        kg_all = "\n".join(filter(None, [formula_kg, kg_ctx]))
        if kg_all:
            parts.append(f"\n【KG参考】\n{kg_all}")
        return "\n".join(parts)

    def _check_contraindications(self, composition: List[Dict],
                                 existing_warnings: List[Dict]) -> List[Dict]:
        """KG辅助禁忌检查"""
        warnings = list(existing_warnings)
        for herb in composition:
            herb_name = herb.get("herb", "")
            if not herb_name:
                continue
            try:
                results = self.kg.query_relations(herb_name, "MED", "不宜吃")
                if results:
                    for key, values in results.items():
                        for v in values:
                            warnings.append({
                                "herb": herb_name,
                                "risk": f"不宜: {v.get('text', '')}",
                                "severity": "medium",
                                "evidence": f"KG: {key}"
                            })
            except Exception:
                continue
        return warnings

    def _fallback(self, syndrome: str, treatment: str) -> Dict:
        return {
            "primary_formula": {"name": "待辨证明确后推荐", "confidence": 0.2},
            "alternatives": [],
            "contraindications": [],
            "overall_confidence": 0.2
        }
