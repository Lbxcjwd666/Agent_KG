"""
实体识别 Agent — LLM抽取 + 别名展开 + 实体消歧
"""

from core.base_agent import BaseAgent
from typing import Dict, List
from config import ENTITY_TYPES


class EntityRecognitionAgent(BaseAgent):
    """实体识别 Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("entity_recognition", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        question = payload.get("question", "")

        # 1. LLM 初次抽取
        raw_entities = self.qwen_api.extract_entities(question)

        if not raw_entities:
            return {"entities": [], "entity_count": 0}

        # 2. 别名展开 — 利用 KG oname 关系
        expanded = []
        for ent in raw_entities:
            entity_text = ent.get("text", "")
            entity_label = ent.get("label", ent.get("type", ""))

            # 查询别名（反向：是否有实体以此为别名）
            aliases = self._resolve_alias(entity_text, entity_label)
            if aliases:
                for alias in aliases:
                    expanded.append({
                        "text": alias["canonical"],
                        "type": alias["type"],
                        "label": alias["label"],
                        "original_text": entity_text,
                        "matched_via": "oname_alias",
                        "confidence": 0.85
                    })
            else:
                # 直接匹配KG
                kg_match = self._match_in_kg(entity_text, entity_label)
                expanded.append({
                    "text": entity_text,
                    "type": entity_label,
                    "label": entity_label,
                    "matched_via": "direct" if kg_match else "llm_only",
                    "confidence": 0.92 if kg_match else 0.65
                })

        # 3. 去重
        seen = set()
        unique = []
        for e in expanded:
            key = (e["text"], e["label"])
            if key not in seen:
                seen.add(key)
                unique.append(e)

        return {
            "entities": unique,
            "entity_count": len(unique),
            "raw_count": len(raw_entities)
        }

    def _resolve_alias(self, entity_text: str, entity_label: str) -> List[Dict]:
        """通过 oname 关系解析别名"""
        if not self.kg:
            return []

        label = ENTITY_TYPES.get(entity_label, entity_label)
        try:
            results = self.kg.query_relations(entity_text, entity_label, "别名")
            resolved = []
            for key, values in results.items():
                for v in values:
                    if v.get("text") != entity_text:
                        resolved.append({
                            "canonical": v["text"],
                            "type": v.get("type", label),
                            "label": v.get("type", label)
                        })
            return resolved
        except Exception:
            return []

    def _match_in_kg(self, entity_text: str, entity_label: str) -> bool:
        """检查实体是否在 KG 中存在"""
        if not self.kg:
            return False
        try:
            results = self.kg.query_entities_by_type(entity_text, entity_label)
            return len(results) > 0
        except Exception:
            return False
