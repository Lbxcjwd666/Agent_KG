"""
KG 查询 Agent — 封装批量/分层查询，输出结构化子图
"""

from core.base_agent import BaseAgent
from typing import Dict, List


class KGQueryAgent(BaseAgent):
    """KG 查询 Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("kg_query", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        entities = payload.get("entities", [])
        layer = payload.get("layer", "L1")
        question = payload.get("question", "")

        if not entities and not question:
            return {"subgraph": {}, "relation_count": 0, "entity_count": 0}

        # 如果没有传入实体，用问题文本做个简单提取
        if not entities:
            entities = self._extract_basic_entities(question)

        all_results = {}
        total_relations = 0

        for ent in entities[:5]:  # 最多5个实体
            entity_text = ent.get("text", ent.get("original_text", ""))
            entity_type = ent.get("label", ent.get("type", ""))

            if not entity_text:
                continue

            try:
                if layer == "ALL":
                    kg_result = self.kg.query_relations(entity_text, entity_type)
                else:
                    kg_result = self.kg.query_relations_layered(
                        entity_text, entity_type, layer)

                if kg_result:
                    all_results[entity_text] = {
                        "type": entity_type,
                        "relations": kg_result,
                        "relation_count": sum(len(v) for v in kg_result.values())
                    }
                    total_relations += all_results[entity_text]["relation_count"]
            except Exception as e:
                self.logger.warning(f"查询 '{entity_text}' 失败: {e}")

        # 格式化 KG 上下文
        kg_context = self._format_context(all_results)

        return {
            "subgraph": all_results,
            "entity_count": len(all_results),
            "relation_count": total_relations,
            "kg_context": kg_context,
            "layer": layer
        }

    def _extract_basic_entities(self, question: str) -> List[Dict]:
        """备用：从问题简单提取实体"""
        if not self.kg:
            return []
        # 用 LLM 快速提取
        entities_data = self.qwen_api.extract_entities(question)
        return entities_data if entities_data else []

    def _format_context(self, subgraph: Dict) -> str:
        """将子图格式化为自然语言上下文"""
        parts = []
        for entity_text, data in subgraph.items():
            entity_type = data.get("type", "")
            parts.append(f"\n【{entity_text}（{entity_type}）】")
            for key, values in data.get("relations", {}).items():
                if not values:
                    continue
                names = [v["text"] for v in values[:5]]
                parts.append(f"  {key}: {', '.join(names)}")
        return "\n".join(parts) if parts else ""
