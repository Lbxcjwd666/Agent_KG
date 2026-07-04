"""
实体链接模块 (Entity Linking)
将 LLM 提取的文本实体指称(Mention)链接到知识图谱中的标准实体节点

流程: Mention → 精确匹配 → 别名匹配 → 向量检索 → 模糊匹配 → 链接决策
"""

from typing import Dict, List, Optional, Tuple
from config import ENTITY_TYPES, VECTOR_INDEX_CONFIG
import logging


class EntityLinker:
    """实体链接器"""

    SIMILARITY_THRESHOLD = 0.6
    EXACT_MATCH_SCORE = 1.0
    ALIAS_MATCH_SCORE = 0.95
    VECTOR_MATCH_SCORE = 0.85
    EDIT_DISTANCE_WEIGHT = 0.4
    SUBSTRING_WEIGHT = 0.3
    ALIAS_WEIGHT = 0.3

    def __init__(self, kg_enhancer=None, embedding_api=None):
        self.kg = kg_enhancer
        self._embedding_api = embedding_api
        self.logger = logging.getLogger("entity_linker")
        self._entity_cache = {}
        self._vector_index_available = None

    def link_entities(self, mentions: List[Dict]) -> List[Dict]:
        """
        对一批 Mention 执行实体链接

        Args:
            mentions: LLM 提取的实体列表, 每项含 text, label/type

        Returns:
            链接后的实体列表, 增加 linked_text, matched_via, confidence, candidates
        """
        if not mentions:
            return []

        self._ensure_cache()

        linked = []
        for mention in mentions:
            result = self._link_single(mention)
            linked.append(result)

        return self._deduplicate(linked)

    def _link_single(self, mention: Dict) -> Dict:
        """链接单个 Mention"""
        text = mention.get("text", "").strip()
        label = mention.get("label", mention.get("type", ""))

        if not text:
            return {**mention, "linked_text": text, "matched_via": "empty", "confidence": 0.0, "candidates": []}

        # Step 1: 精确匹配
        exact = self._exact_match(text, label)
        if exact:
            return {
                **mention,
                "linked_text": exact["text"],
                "linked_label": exact["label"],
                "matched_via": "exact",
                "confidence": self.EXACT_MATCH_SCORE,
                "candidates": [{"text": exact["text"], "label": exact["label"], "score": 1.0, "method": "exact"}]
            }

        # Step 2: 别名匹配 (oname 关系, 同类型过滤)
        alias_result = self._alias_match(text, label)
        if alias_result:
            return {
                **mention,
                "linked_text": alias_result["canonical"],
                "linked_label": alias_result["label"],
                "matched_via": "alias",
                "confidence": self.ALIAS_MATCH_SCORE,
                "candidates": [{
                    "text": alias_result["canonical"],
                    "label": alias_result["label"],
                    "score": self.ALIAS_MATCH_SCORE,
                    "method": "alias"
                }]
            }

        # Step 3: 向量稠密检索
        vector_candidates = self._vector_search(text, label)
        if vector_candidates:
            best = vector_candidates[0]
            threshold = VECTOR_INDEX_CONFIG.get("vector_match_threshold", 0.75)
            if best["score"] >= threshold:
                return {
                    **mention,
                    "linked_text": best["text"],
                    "linked_label": best["label"],
                    "matched_via": "vector",
                    "confidence": round(best["score"], 3),
                    "candidates": vector_candidates[:5]
                }

        # Step 4: 候选生成 + 模糊匹配 (兜底)
        candidates = self._generate_candidates(text, label)
        if candidates:
            ranked = self._rank_candidates(text, candidates)
            best = ranked[0]

            if best["score"] >= self.SIMILARITY_THRESHOLD:
                return {
                    **mention,
                    "linked_text": best["text"],
                    "linked_label": best["label"],
                    "matched_via": "fuzzy",
                    "confidence": round(best["score"], 3),
                    "candidates": ranked[:5]
                }

        # Step 5: 无法链接, 保留原文
        return {
            **mention,
            "linked_text": text,
            "linked_label": label,
            "matched_via": "llm_only",
            "confidence": 0.5,
            "candidates": candidates[:3] if candidates else []
        }

    def _exact_match(self, text: str, label: str) -> Optional[Dict]:
        """精确匹配: 检查 KG 中是否存在完全相同的 text"""
        if not self.kg:
            cache_key = (text, label)
            if cache_key in self._entity_cache:
                return {"text": text, "label": label}
            return None

        try:
            results = self.kg.query_entities_by_type(text, label)
            if results:
                return {"text": text, "label": label}
        except Exception:
            pass

        cache_key = (text, label)
        if cache_key in self._entity_cache:
            return {"text": text, "label": label}

        return None

    def _alias_match(self, text: str, label: str) -> Optional[Dict]:
        """别名匹配: 通过 oname 关系查找标准名 (仅信任同类型别名)"""
        if not self.kg:
            return None

        neo4j_label = ENTITY_TYPES.get(label, label)

        try:
            with self.kg.driver.session() as session:
                query = f"""
                MATCH (n:{neo4j_label} {{text: $text}})-[r:oname]->(m:{neo4j_label})
                WHERE m.text <> $text
                RETURN m.text as canonical, labels(m)[0] as label
                LIMIT 1
                """
                result = session.run(query, text=text)
                for record in result:
                    return {
                        "canonical": record["canonical"],
                        "label": record["label"]
                    }

                query_rev = f"""
                MATCH (n:{neo4j_label})-[r:oname]->(m:{neo4j_label} {{text: $text}})
                WHERE n.text <> $text
                RETURN n.text as canonical, labels(n)[0] as label
                LIMIT 1
                """
                result_rev = session.run(query_rev, text=text)
                for record in result_rev:
                    return {
                        "canonical": record["canonical"],
                        "label": record["label"]
                    }
        except Exception as e:
            self.logger.warning(f"别名匹配失败: {e}")

        return None

    def _generate_candidates(self, text: str, label: str) -> List[Dict]:
        """
        候选生成: 从 KG 中找出可能的匹配候选

        策略:
        1. 同类型实体中子串包含
        2. 同类型实体中编辑距离较近的
        3. 跨类型子串包含 (低优先级)
        """
        candidates = []
        neo4j_label = ENTITY_TYPES.get(label, label)

        # 从缓存中获取同类型实体
        same_type_entities = self._entity_cache.get(neo4j_label, [])

        # 同类型候选
        for entity_text in same_type_entities:
            if entity_text == text:
                continue
            score = self._compute_similarity(text, entity_text)
            if score > 0.3:
                candidates.append({
                    "text": entity_text,
                    "label": neo4j_label,
                    "similarity": score
                })

        # 跨类型候选 (仅子串匹配)
        for type_label, entities in self._entity_cache.items():
            if type_label == neo4j_label:
                continue
            for entity_text in entities:
                if text in entity_text or entity_text in text:
                    score = self._compute_similarity(text, entity_text)
                    if score > 0.4:
                        candidates.append({
                            "text": entity_text,
                            "label": type_label,
                            "similarity": score * 0.8
                        })

        # 如果缓存不足, 尝试从 KG 实时搜索
        if len(candidates) < 3 and self.kg:
            kg_candidates = self._kg_fuzzy_search(text, label)
            candidates.extend(kg_candidates)

        # 去重
        seen = set()
        unique = []
        for c in candidates:
            key = (c["text"], c["label"])
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique

    def _rank_candidates(self, mention_text: str, candidates: List[Dict]) -> List[Dict]:
        """
        候选排序: 综合多种特征计算最终得分

        得分 = 编辑距离分 * 0.4 + 子串匹配分 * 0.3 + 别名关系分 * 0.3
        """
        scored = []
        for cand in candidates:
            cand_text = cand["text"]

            # 编辑距离得分
            edit_score = self._edit_distance_score(mention_text, cand_text)

            # 子串匹配得分
            substr_score = self._substring_score(mention_text, cand_text)

            # 别名关系得分 (如果 KG 中有 oname 关系)
            alias_score = 0.0
            if self.kg:
                try:
                    results = self.kg.query_relations(cand_text, cand["label"], "别名")
                    for key, values in results.items():
                        for v in values:
                            if v.get("text") == mention_text:
                                alias_score = 1.0
                                break
                        if alias_score > 0:
                            break
                except Exception:
                    pass

            final_score = (
                edit_score * self.EDIT_DISTANCE_WEIGHT +
                substr_score * self.SUBSTRING_WEIGHT +
                alias_score * self.ALIAS_WEIGHT
            )

            # 同类型加分
            cand_label = ENTITY_TYPES.get(cand["label"], cand["label"])
            mention_label = ENTITY_TYPES.get(mention_text, "")
            if cand_label == mention_label or cand["label"] == mention_label:
                final_score += 0.1

            scored.append({
                "text": cand_text,
                "label": cand["label"],
                "score": round(min(final_score, 1.0), 3),
                "method": "fuzzy",
                "detail": {
                    "edit_score": round(edit_score, 3),
                    "substr_score": round(substr_score, 3),
                    "alias_score": round(alias_score, 3)
                }
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    @staticmethod
    def _edit_distance_score(s1: str, s2: str) -> float:
        """基于编辑距离的相似度得分 (0~1)"""
        if not s1 or not s2:
            return 0.0

        len1, len2 = len(s1), len(s2)
        max_len = max(len1, len2)
        if max_len == 0:
            return 1.0

        # 优化: 只计算短字符串的编辑距离
        if max_len > 20:
            # 长字符串用子串匹配代替
            return EntityLinker._substring_score(s1, s2)

        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

        distance = dp[len1][len2]
        return 1.0 - distance / max_len

    @staticmethod
    def _substring_score(s1: str, s2: str) -> float:
        """基于子串包含的相似度得分 (0~1)"""
        if not s1 or not s2:
            return 0.0

        # 完全包含
        if s1 in s2:
            return len(s1) / len(s2)
        if s2 in s1:
            return len(s2) / len(s1)

        # 最长公共子串
        max_common = 0
        len1, len2 = len(s1), len(s2)

        # 优化: 短字符串直接计算
        if len1 > 50 or len2 > 50:
            # 简单滑动窗口
            for i in range(len1 - 1):
                for j in range(i + 2, min(i + 10, len1 + 1)):
                    if s1[i:j] in s2:
                        max_common = max(max_common, j - i)
        else:
            # 完整 LCS 计算
            for i in range(len1):
                for j in range(len2):
                    k = 0
                    while i + k < len1 and j + k < len2 and s1[i + k] == s2[j + k]:
                        k += 1
                    max_common = max(max_common, k)

        min_len = min(len1, len2)
        return max_common / min_len if min_len > 0 else 0.0

    @staticmethod
    def _compute_similarity(s1: str, s2: str) -> float:
        """综合相似度 (编辑距离 + 子串匹配的加权平均)"""
        edit = EntityLinker._edit_distance_score(s1, s2)
        substr = EntityLinker._substring_score(s1, s2)
        return 0.5 * edit + 0.5 * substr

    def _kg_fuzzy_search(self, text: str, label: str) -> List[Dict]:
        """从 KG 中模糊搜索候选实体"""
        if not self.kg:
            return []

        candidates = []
        neo4j_label = ENTITY_TYPES.get(label, label)

        try:
            with self.kg.driver.session() as session:
                # CONTAINS 模糊搜索
                query = f"""
                MATCH (n:{neo4j_label})
                WHERE n.text CONTAINS $keyword OR $keyword CONTAINS n.text
                RETURN n.text as text, labels(n)[0] as label
                LIMIT 20
                """
                result = session.run(query, keyword=text)
                for record in result:
                    entity_text = record["text"]
                    entity_label = record["label"]
                    if entity_text != text:
                        score = self._compute_similarity(text, entity_text)
                        if score > 0.3:
                            candidates.append({
                                "text": entity_text,
                                "label": entity_label,
                                "similarity": score
                            })

                # 如果同类型候选不足, 搜索所有类型
                if len(candidates) < 3:
                    query2 = """
                    MATCH (n)
                    WHERE n.text CONTAINS $keyword OR $keyword CONTAINS n.text
                    RETURN n.text as text, labels(n)[0] as label
                    LIMIT 20
                    """
                    result2 = session.run(query2, keyword=text)
                    for record in result2:
                        entity_text = record["text"]
                        entity_label = record["label"]
                        if entity_text != text:
                            key = (entity_text, entity_label)
                            if key not in {(c["text"], c["label"]) for c in candidates}:
                                score = self._compute_similarity(text, entity_text)
                                if score > 0.4:
                                    candidates.append({
                                        "text": entity_text,
                                        "label": entity_label,
                                        "similarity": score * 0.8
                                    })
        except Exception as e:
            self.logger.warning(f"KG模糊搜索失败: {e}")

        return candidates

    def _vector_search(self, text: str, label: str) -> List[Dict]:
        """
        向量稠密检索: 使用 Qwen Embedding 编码查询文本，
        在 Neo4j 向量索引中搜索语义最相近的实体

        Args:
            text: 查询文本 (Mention)
            label: 实体类型

        Returns:
            候选实体列表, 按相似度降序排列
        """
        if not self._embedding_api:
            return []

        if self._vector_index_available is None:
            self._vector_index_available = self._check_vector_index()

        if not self._vector_index_available:
            return []

        try:
            query_embedding = self._embedding_api.get_embeddings(
                [text],
                model=VECTOR_INDEX_CONFIG["embedding_model"],
                dimensions=VECTOR_INDEX_CONFIG["embedding_dimension"]
            )
            if not query_embedding:
                return []

            query_vec = query_embedding[0]
            neo4j_label = ENTITY_TYPES.get(label, label)
            top_k = VECTOR_INDEX_CONFIG.get("top_k", 10)
            index_name = VECTOR_INDEX_CONFIG["index_name"]

            with self.kg.driver.session() as session:
                try:
                    query = (
                        "CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector) "
                        "YIELD node, score "
                        "WHERE $label IS NULL OR $label IN labels(node) "
                        "RETURN node.text AS text, labels(node)[0] AS label, score "
                        "ORDER BY score DESC LIMIT $top_k"
                    )
                    result = session.run(
                        query,
                        index_name=index_name,
                        top_k=top_k,
                        query_vector=query_vec,
                        label=neo4j_label
                    )
                except Exception:
                    label_index_name = f"{index_name}_{neo4j_label.lower()}"
                    query = (
                        "CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector) "
                        "YIELD node, score "
                        "RETURN node.text AS text, labels(node)[0] AS label, score "
                        "ORDER BY score DESC LIMIT $top_k"
                    )
                    result = session.run(
                        query,
                        index_name=label_index_name,
                        top_k=top_k,
                        query_vector=query_vec
                    )

                candidates = []
                for record in result:
                    candidates.append({
                        "text": record["text"],
                        "label": record["label"],
                        "score": round(record["score"], 4),
                        "method": "vector"
                    })

                return candidates

        except Exception as e:
            self.logger.warning(f"向量检索失败: {e}")
            return []

    def _check_vector_index(self) -> bool:
        if not self.kg:
            return False

        try:
            with self.kg.driver.session() as session:
                result = session.run("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name")
                index_names = [record["name"] for record in result]
                base_name = VECTOR_INDEX_CONFIG["index_name"]
                if base_name in index_names:
                    return True
                for name in index_names:
                    if name.startswith(base_name + "_"):
                        return True
                return False
        except Exception as e:
            self.logger.warning(f"检查向量索引失败: {e}")
            return False

    def _ensure_cache(self):
        """确保实体缓存已加载"""
        if self._entity_cache:
            return

        if not self.kg:
            return

        try:
            with self.kg.driver.session() as session:
                for cn_name, neo4j_label in ENTITY_TYPES.items():
                    query = f"MATCH (n:{neo4j_label}) RETURN n.text as text LIMIT 500"
                    result = session.run(query)
                    self._entity_cache[neo4j_label] = [
                        record["text"] for record in result if record["text"]
                    ]

            total = sum(len(v) for v in self._entity_cache.values())
            self.logger.info(f"实体缓存已加载: {total} 个实体, {len(self._entity_cache)} 种类型")
        except Exception as e:
            self.logger.warning(f"实体缓存加载失败: {e}")

    def refresh_cache(self):
        """强制刷新实体缓存"""
        self._entity_cache = {}
        self._ensure_cache()

    @staticmethod
    def _deduplicate(entities: List[Dict]) -> List[Dict]:
        """去重: 同一 linked_text + linked_label 只保留得分最高的"""
        seen = {}
        for e in entities:
            key = (e.get("linked_text", e.get("text", "")), e.get("linked_label", e.get("label", "")))
            if key not in seen or e.get("confidence", 0) > seen[key].get("confidence", 0):
                seen[key] = e

        result = list(seen.values())

        # 如果多个 mention 链接到同一实体, 保留置信度最高的, 合并 original_text
        final = {}
        for e in result:
            key = e.get("linked_text", "")
            if key in final:
                existing = final[key]
                orig = existing.get("original_text", existing.get("text", ""))
                new_orig = e.get("original_text", e.get("text", ""))
                if orig != new_orig:
                    merged = f"{orig}/{new_orig}" if orig else new_orig
                    existing["original_text"] = merged
                if e.get("confidence", 0) > existing.get("confidence", 0):
                    existing["confidence"] = e["confidence"]
                    existing["matched_via"] = e.get("matched_via", "")
            else:
                final[key] = dict(e)
                if "original_text" not in final[key]:
                    final[key]["original_text"] = e.get("text", "")

        return list(final.values())