"""
KG 查询 Agent — 封装批量/分层查询，输出结构化子图
支持多症状交集推理：多个症状指向共同疾病时优先展开交集疾病
无交集时返回候选疾病及其症状，等待用户交互确认
支持 DIS→SYN→治疗 链路追查
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
        confirmed_diseases = payload.get("confirmed_diseases", [])

        if not entities and not question:
            return {"subgraph": {}, "relation_count": 0, "entity_count": 0}

        if not entities:
            entities = self._extract_basic_entities(question)

        all_results = {}
        total_relations = 0

        # 如果有用户确认的疾病，直接展开
        if confirmed_diseases and self.kg:
            for dis_name in confirmed_diseases[:5]:
                try:
                    if layer == "ALL":
                        dis_result = self.kg.query_relations(dis_name, "疾病")
                    else:
                        dis_result = self.kg.query_relations_layered(dis_name, "疾病", layer)
                    if dis_result:
                        all_results[f"{dis_name}(用户确认)"] = {
                            "type": "疾病",
                            "relations": dis_result,
                            "relation_count": sum(len(v) for v in dis_result.values()),
                            "confirmed": True
                        }
                        total_relations += all_results[f"{dis_name}(用户确认)"]["relation_count"]
                        self._expand_disease_syndromes(dis_name, dis_result, layer, all_results)
                        total_relations = sum(v.get("relation_count", 0) for v in all_results.values())
                except Exception as e:
                    self.logger.warning(f"查询确认疾病 '{dis_name}' 失败: {e}")

            # 同时查询原始实体的关系
            for ent in entities[:5]:
                entity_text = ent.get("text", ent.get("original_text", ""))
                entity_type = ent.get("label", ent.get("type", ""))
                if not entity_text:
                    continue
                try:
                    if layer == "ALL":
                        kg_result = self.kg.query_relations(entity_text, entity_type)
                    else:
                        kg_result = self.kg.query_relations_layered(entity_text, entity_type, layer)
                    if kg_result:
                        all_results[entity_text] = {
                            "type": entity_type,
                            "relations": kg_result,
                            "relation_count": sum(len(v) for v in kg_result.values())
                        }
                        total_relations += all_results[entity_text]["relation_count"]
                except Exception as e:
                    self.logger.warning(f"查询 '{entity_text}' 失败: {e}")

            kg_context = self._format_context(all_results)
            return {
                "subgraph": all_results,
                "entity_count": len(all_results),
                "relation_count": total_relations,
                "kg_context": kg_context,
                "layer": layer
            }

        # 分离 SYM 实体和非 SYM 实体
        sym_entities = []
        other_entities = []
        for ent in entities[:5]:
            entity_text = ent.get("text", ent.get("original_text", ""))
            entity_type = ent.get("label", ent.get("type", ""))
            if not entity_text:
                continue
            label = self.kg.entity_types.get(entity_type, entity_type) if self.kg else entity_type
            if label == "SYM":
                sym_entities.append(ent)
            else:
                other_entities.append(ent)

        # 非 SYM 实体：直接查询
        for ent in other_entities:
            entity_text = ent.get("text", ent.get("original_text", ""))
            entity_type = ent.get("label", ent.get("type", ""))
            try:
                if layer == "ALL":
                    kg_result = self.kg.query_relations(entity_text, entity_type)
                else:
                    kg_result = self.kg.query_relations_layered(entity_text, entity_type, layer)
                if kg_result:
                    all_results[entity_text] = {
                        "type": entity_type,
                        "relations": kg_result,
                        "relation_count": sum(len(v) for v in kg_result.values())
                    }
                    total_relations += all_results[entity_text]["relation_count"]
            except Exception as e:
                self.logger.warning(f"查询 '{entity_text}' 失败: {e}")

        # SYM 实体：多症状交集推理
        if sym_entities and self.kg:
            sym_texts = [e.get("text", e.get("original_text", "")) for e in sym_entities]

            # 先查每个症状自身的关系
            for ent in sym_entities:
                entity_text = ent.get("text", ent.get("original_text", ""))
                entity_type = ent.get("label", ent.get("type", ""))
                try:
                    if layer == "ALL":
                        kg_result = self.kg.query_relations(entity_text, entity_type)
                    else:
                        kg_result = self.kg.query_relations_layered(entity_text, entity_type, layer)
                    if kg_result:
                        all_results[entity_text] = {
                            "type": entity_type,
                            "relations": kg_result,
                            "relation_count": sum(len(v) for v in kg_result.values())
                        }
                        total_relations += all_results[entity_text]["relation_count"]
                except Exception as e:
                    self.logger.warning(f"查询 '{entity_text}' 失败: {e}")

            # 多症状→疾病交集
            disease_info = self.kg.find_diseases_by_symptoms(sym_texts)
            shared_diseases = disease_info["shared"]
            ranked_diseases = disease_info["ranked"]

            # 有交集：展开交集疾病
            if shared_diseases:
                for dis_name in shared_diseases[:5]:
                    try:
                        if layer == "ALL":
                            dis_result = self.kg.query_relations(dis_name, "疾病")
                        else:
                            dis_result = self.kg.query_relations_layered(dis_name, "疾病", layer)
                        if dis_result:
                            all_results[f"{dis_name}(由症状推断)"] = {
                                "type": "疾病",
                                "relations": dis_result,
                                "relation_count": sum(len(v) for v in dis_result.values()),
                                "inferred_from": sym_texts,
                                "shared_by": len(shared_diseases)
                            }
                            total_relations += all_results[f"{dis_name}(由症状推断)"]["relation_count"]
                            self._expand_disease_syndromes(dis_name, dis_result, layer, all_results)
                            total_relations = sum(v.get("relation_count", 0) for v in all_results.values())
                    except Exception as e:
                        self.logger.warning(f"查询疾病 '{dis_name}' 失败: {e}")
            else:
                # 无交集：将候选疾病标记到 subgraph 中，由 DiagnosisAgent 负责问诊确认
                for dis_name, hit_count in ranked_diseases[:5]:
                    dis_symptoms = self.kg.get_disease_symptoms(dis_name)
                    all_results[f"{dis_name}(候选)"] = {
                        "type": "疾病",
                        "candidate": True,
                        "hit_count": hit_count,
                        "symptoms": dis_symptoms,
                        "symptom_count": len(dis_symptoms)
                    }
                    total_relations += len(dis_symptoms)

        kg_context = self._format_context(all_results)

        return {
            "subgraph": all_results,
            "entity_count": len(all_results),
            "relation_count": total_relations,
            "kg_context": kg_context,
            "layer": layer
        }

    def _expand_disease_syndromes(self, dis_name: str, dis_result: Dict,
                                   layer: str, all_results: Dict):
        """
        DIS→SYN→治疗 链路追查
        从疾病查询结果中提取关联的证候，再查询证候的治疗关系
        """
        if not self.kg:
            return

        syn_names = []
        for key, values in dis_result.items():
            if "SYN" in key:
                for v in values:
                    text = v.get("text", v.get("m.text", ""))
                    if text:
                        syn_names.append(text)

        for syn_name in syn_names[:5]:
            try:
                if layer == "ALL":
                    syn_result = self.kg.query_relations(syn_name, "证候")
                else:
                    syn_result = self.kg.query_relations_layered(syn_name, "证候", layer)
                if syn_result:
                    all_results[f"{syn_name}(证候,源自{dis_name})"] = {
                        "type": "证候",
                        "relations": syn_result,
                        "relation_count": sum(len(v) for v in syn_result.values()),
                        "source_disease": dis_name
                    }
            except Exception as e:
                self.logger.warning(f"查询证候 '{syn_name}' 失败: {e}")

    def _extract_basic_entities(self, question: str) -> List[Dict]:
        if not self.kg:
            return []
        entities_data = self.qwen_api.extract_entities(question)
        return entities_data if entities_data else []

    def _format_context(self, subgraph: Dict) -> str:
        parts = []
        for entity_text, data in subgraph.items():
            entity_type = data.get("type", "")
            shared_by = data.get("shared_by")
            confirmed = data.get("confirmed")
            source_disease = data.get("source_disease")
            is_candidate = data.get("candidate", False)
            if confirmed:
                parts.append(f"\n【{entity_text}（{entity_type}，用户确认）】")
            elif source_disease:
                parts.append(f"\n【{entity_text}（{entity_type}，源自{source_disease}）】")
            elif shared_by:
                parts.append(f"\n【{entity_text}（{entity_type}，{shared_by}个症状共同指向）】")
            elif is_candidate:
                parts.append(f"\n【{entity_text}（{entity_type}，候选疾病，{data.get('symptom_count', 0)}个症状匹配）】")
            else:
                parts.append(f"\n【{entity_text}（{entity_type}）】")
            for key, values in data.get("relations", {}).items():
                if not values:
                    continue
                names = [v["text"] for v in values[:5]]
                parts.append(f"  {key}: {', '.join(names)}")
        return "\n".join(parts) if parts else ""

    # ══════════════════════════════════════════════════════════
    # 运行时按需查询接口 — 供辨证Agent通过调度Agent调用
    # ══════════════════════════════════════════════════════════

    def query_supplement(self, entity_text: str, entity_type: str,
                         relation_filter: List[str] = None,
                         layer: str = "ALL") -> Dict:
        """
        按需查询单个实体的指定关系，返回增量subgraph

        Args:
            entity_text: 实体名称
            entity_type: 实体类型（中文，如"疾病"、"证候"）
            relation_filter: 只查询这些关系（如["治疗", "表现"]），None则查全部
            layer: 查询层级

        Returns:
            {"subgraph": {...}, "kg_context": "..."}
        """
        if not self.kg:
            return {"subgraph": {}, "kg_context": ""}

        all_results = {}

        if relation_filter:
            for rel_name in relation_filter:
                try:
                    results = self.kg.query_relations(entity_text, entity_type, rel_name)
                    if results:
                        all_results[entity_text] = {
                            "type": entity_type,
                            "relations": results,
                            "relation_count": sum(len(v) for v in results.values()),
                            "supplement": True
                        }
                except Exception as e:
                    self.logger.warning(f"补充查询 '{entity_text}' 关系 '{rel_name}' 失败: {e}")
        else:
            try:
                if layer == "ALL":
                    results = self.kg.query_relations(entity_text, entity_type)
                else:
                    results = self.kg.query_relations_layered(entity_text, entity_type, layer)
                if results:
                    all_results[entity_text] = {
                        "type": entity_type,
                        "relations": results,
                        "relation_count": sum(len(v) for v in results.values()),
                        "supplement": True
                    }
            except Exception as e:
                self.logger.warning(f"补充查询 '{entity_text}' 失败: {e}")

            if layer == "ALL" and entity_type == "疾病":
                self._expand_disease_syndromes(entity_text, 
                    all_results.get(entity_text, {}).get("relations", {}),
                    layer, all_results)

        kg_context = self._format_context(all_results)
        return {
            "subgraph": all_results,
            "kg_context": kg_context
        }

    def query_disease_symptoms(self, disease_name: str) -> Dict:
        """
        查询疾病的症状列表（供辨证Agent生成问诊词）

        Args:
            disease_name: 疾病名称

        Returns:
            {"disease": "...", "symptoms": [...], "syndromes": [...]}
        """
        if not self.kg:
            return {"disease": disease_name, "symptoms": [], "syndromes": []}

        symptoms = []
        syndromes = []

        try:
            results = self.kg.query_relations(disease_name, "疾病")
            if results:
                for key, values in results.items():
                    if "SYM" in key or "症状" in key:
                        for v in values:
                            text = v.get("text", "")
                            if text and text not in symptoms:
                                symptoms.append(text)
                    if "SYN" in key or "证候" in key:
                        for v in values:
                            text = v.get("text", "")
                            if text and text not in syndromes:
                                syndromes.append(text)
        except Exception as e:
            self.logger.warning(f"查询疾病 '{disease_name}' 症状失败: {e}")

        return {
            "disease": disease_name,
            "symptoms": symptoms,
            "syndromes": syndromes
        }