"""
实体识别 Agent — LLM抽取 + 实体链接(Entity Linking) + 别名展开 + 实体消歧
"""

from core.base_agent import BaseAgent
from entity_linker import EntityLinker
from typing import Dict, List
from config import ENTITY_TYPES


class EntityRecognitionAgent(BaseAgent):
    """实体识别 Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("entity_recognition", qwen_api, kg_enhancer)
        self.linker = EntityLinker(kg_enhancer, embedding_api=qwen_api)

    def run(self, payload: Dict) -> Dict:
        question = payload.get("question", "")

        # 1. LLM 初次抽取
        raw_entities = self.qwen_api.extract_entities(question)

        if not raw_entities:
            return {"entities": [], "entity_count": 0}

        # 2. 实体链接: 将 LLM 提取的 Mention 链接到 KG 标准实体
        linked_entities = self.linker.link_entities(raw_entities)

        # 3. 格式化输出
        formatted = []
        for e in linked_entities:
            formatted.append({
                "text": e.get("linked_text", e.get("text", "")),
                "type": e.get("linked_label", e.get("label", "")),
                "label": e.get("linked_label", e.get("label", "")),
                "original_text": e.get("original_text", e.get("text", "")),
                "matched_via": e.get("matched_via", "llm_only"),
                "confidence": e.get("confidence", 0.5),
                "candidates": e.get("candidates", [])
            })

        # 4. 统计
        exact_count = sum(1 for e in formatted if e["matched_via"] == "exact")
        alias_count = sum(1 for e in formatted if e["matched_via"] == "alias")
        fuzzy_count = sum(1 for e in formatted if e["matched_via"] == "fuzzy")
        unlinked_count = sum(1 for e in formatted if e["matched_via"] == "llm_only")

        return {
            "entities": formatted,
            "entity_count": len(formatted),
            "raw_count": len(raw_entities),
            "linking_stats": {
                "exact_match": exact_count,
                "alias_match": alias_count,
                "fuzzy_match": fuzzy_count,
                "unlinked": unlinked_count
            }
        }