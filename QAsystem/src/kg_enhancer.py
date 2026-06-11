"""
知识图谱增强模块
通过Neo4j知识图谱增强大模型推理能力
"""

from neo4j import GraphDatabase
from typing import List, Dict, Tuple, Optional
import json
from config import ENTITY_TYPES, RELATION_TYPES, NEO4J_CONFIG, SYSTEM_CONFIG


class KnowledgeGraphEnhancer:
    """知识图谱增强器"""
    
    def __init__(self):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(
            NEO4J_CONFIG["uri"],
            auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"])
        )
        self.entity_types = ENTITY_TYPES
        self.relation_types = RELATION_TYPES
    
    def close(self):
        """关闭数据库连接"""
        if self.driver:
            self.driver.close()
    
    def query_entities_by_type(self, entity_text: str, entity_type: str) -> List[Dict]:
        """根据实体类型查询实体"""
        label = self.entity_types.get(entity_type, entity_type)
        
        query = f"""
        MATCH (n:{label} {{text: $entity_text}})
        RETURN n.text as text, labels(n)[0] as type
        LIMIT 1
        """
        
        with self.driver.session() as session:
            result = session.run(query, entity_text=entity_text)
            return [record.data() for record in result]
    
    def query_relations(self, entity_text: str, entity_type: str, relation_name: str = None) -> Dict:
        """
        查询实体的关系
        严格按照关系设计表进行查询
        """
        label = self.entity_types.get(entity_type, entity_type)
        results = {}
        
        with self.driver.session() as session:
            # 如果没有指定关系，查询所有可能的关系
            if relation_name is None:
                # 遍历所有关系类型
                for rel_name, rel_config in self.relation_types.items():
                    rel_label = rel_config["label"]
                    head_entities = rel_config["head_entities"]
                    tail_entities = rel_config["tail_entities"]
                    
                    # 检查当前实体类型是否可以作为头实体
                    if label in head_entities or "实体" in head_entities:
                        # 查询所有可能的尾实体
                        for tail_type in tail_entities:
                            if tail_type == "实体":
                                # 查询所有实体类型
                                for et_type, et_label in self.entity_types.items():
                                    query = f"""
                                    MATCH (n:{label} {{text: $entity_text}})-[r:{rel_label}]->(m:{et_label})
                                    RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                    LIMIT $limit
                                    """
                                    result = session.run(query, entity_text=entity_text, 
                                                        limit=SYSTEM_CONFIG["max_kg_results"])
                                    data = [record.data() for record in result]
                                    if data:
                                        key = f"{rel_name}_{et_label}"
                                        results[key] = data
                            else:
                                tail_label = self.entity_types.get(tail_type, tail_type)
                                query = f"""
                                MATCH (n:{label} {{text: $entity_text}})-[r:{rel_label}]->(m:{tail_label})
                                RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                LIMIT $limit
                                """
                                result = session.run(query, entity_text=entity_text,
                                                    limit=SYSTEM_CONFIG["max_kg_results"])
                                data = [record.data() for record in result]
                                if data:
                                    key = f"{rel_name}_{tail_label}"
                                    results[key] = data
                    
                    # 检查当前实体类型是否可以作为尾实体
                    if label in tail_entities or "实体" in tail_entities:
                        # 查询所有可能的头实体
                        for head_type in head_entities:
                            if head_type == "实体":
                                # 查询所有实体类型
                                for et_type, et_label in self.entity_types.items():
                                    query = f"""
                                    MATCH (m:{et_label})-[r:{rel_label}]->(n:{label} {{text: $entity_text}})
                                    RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                    LIMIT $limit
                                    """
                                    result = session.run(query, entity_text=entity_text,
                                                        limit=SYSTEM_CONFIG["max_kg_results"])
                                    data = [record.data() for record in result]
                                    if data:
                                        key = f"{rel_name}_from_{et_label}"
                                        results[key] = data
                            else:
                                head_label = self.entity_types.get(head_type, head_type)
                                query = f"""
                                MATCH (m:{head_label})-[r:{rel_label}]->(n:{label} {{text: $entity_text}})
                                RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                LIMIT $limit
                                """
                                result = session.run(query, entity_text=entity_text,
                                                    limit=SYSTEM_CONFIG["max_kg_results"])
                                data = [record.data() for record in result]
                                if data:
                                    key = f"{rel_name}_from_{head_label}"
                                    results[key] = data
            else:
                # 查询指定关系
                if relation_name in self.relation_types:
                    rel_config = self.relation_types[relation_name]
                    rel_label = rel_config["label"]
                    head_entities = rel_config["head_entities"]
                    tail_entities = rel_config["tail_entities"]
                    
                    # 作为头实体查询
                    if label in head_entities or "实体" in head_entities:
                        for tail_type in tail_entities:
                            if tail_type == "实体":
                                for et_type, et_label in self.entity_types.items():
                                    query = f"""
                                    MATCH (n:{label} {{text: $entity_text}})-[r:{rel_label}]->(m:{et_label})
                                    RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                    LIMIT $limit
                                    """
                                    result = session.run(query, entity_text=entity_text,
                                                        limit=SYSTEM_CONFIG["max_kg_results"])
                                    data = [record.data() for record in result]
                                    if data:
                                        results[f"{relation_name}_{et_label}"] = data
                            else:
                                tail_label = self.entity_types.get(tail_type, tail_type)
                                query = f"""
                                MATCH (n:{label} {{text: $entity_text}})-[r:{rel_label}]->(m:{tail_label})
                                RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                LIMIT $limit
                                """
                                result = session.run(query, entity_text=entity_text,
                                                    limit=SYSTEM_CONFIG["max_kg_results"])
                                data = [record.data() for record in result]
                                if data:
                                    results[f"{relation_name}_{tail_label}"] = data
                    
                    # 作为尾实体查询
                    if label in tail_entities or "实体" in tail_entities:
                        for head_type in head_entities:
                            if head_type == "实体":
                                for et_type, et_label in self.entity_types.items():
                                    query = f"""
                                    MATCH (m:{et_label})-[r:{rel_label}]->(n:{label} {{text: $entity_text}})
                                    RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                    LIMIT $limit
                                    """
                                    result = session.run(query, entity_text=entity_text,
                                                        limit=SYSTEM_CONFIG["max_kg_results"])
                                    data = [record.data() for record in result]
                                    if data:
                                        results[f"{relation_name}_from_{et_label}"] = data
                            else:
                                head_label = self.entity_types.get(head_type, head_type)
                                query = f"""
                                MATCH (m:{head_label})-[r:{rel_label}]->(n:{label} {{text: $entity_text}})
                                RETURN m.text as text, labels(m)[0] as type, type(r) as relation
                                LIMIT $limit
                                """
                                result = session.run(query, entity_text=entity_text,
                                                    limit=SYSTEM_CONFIG["max_kg_results"])
                                data = [record.data() for record in result]
                                if data:
                                    results[f"{relation_name}_from_{head_label}"] = data
        
        return results

    # L1 核心关系：直接影响临床决策
    L1_CORE_RELATIONS = {"治疗", "组成", "表现", "导致", "归属于"}

    # L2 扩展关系：辅助信息
    L2_EXTENDED_RELATIONS = {
        "出自", "相关MER", "病脉表现", "脉诊", "望诊", "互为表里",
        "相关DIS", "别名", "反映", "辅助诊断", "指导用药", "指导方剂",
        "治疗ACU", "映射部位", "宜吃", "不宜吃"
    }

    def query_relations_batch(self, queries: List[Tuple[str, str, str]]) -> Dict:
        """
        批量查询关系，使用 UNION ALL 合并为单次 Cypher 查询

        Args:
            queries: [(entity_text, entity_type, relation_name), ...]

        Returns:
            Dict: keyed by "{relation_name}_{entity_type}", values are query results
        """
        if not queries:
            return {}

        results = {}
        union_parts = []
        params = {}

        for idx, (entity_text, entity_type, relation_name) in enumerate(queries):
            label = self.entity_types.get(entity_type, entity_type)
            if not label or label not in self.entity_types.values():
                continue

            if relation_name not in self.relation_types:
                continue

            rel_config = self.relation_types[relation_name]
            rel_label = rel_config["label"]
            head_entities = rel_config["head_entities"]
            tail_entities = rel_config["tail_entities"]

            # 作为头实体查询
            if label in head_entities:
                for tail_type in tail_entities:
                    if tail_type == "实体":
                        for et_label in set(self.entity_types.values()):
                            p_name = f"text_{idx}"
                            part = (
                                f"MATCH (n:{label} {{text: ${p_name}}})"
                                f"-[r:{rel_label}]->(m:{et_label})"
                                f"RETURN '{relation_name}' AS rel_name,"
                                f" m.text AS text, labels(m)[0] AS type,"
                                f" type(r) AS relation, 'out' AS direction"
                                f" LIMIT $limit"
                            )
                            union_parts.append(part)
                            params[p_name] = entity_text
                    else:
                        tail_label = self.entity_types.get(tail_type, tail_type)
                        p_name = f"text_{idx}"
                        part = (
                            f"MATCH (n:{label} {{text: ${p_name}}})"
                            f"-[r:{rel_label}]->(m:{tail_label})"
                            f"RETURN '{relation_name}' AS rel_name,"
                            f" m.text AS text, labels(m)[0] AS type,"
                            f" type(r) AS relation, 'out' AS direction"
                            f" LIMIT $limit"
                        )
                        union_parts.append(part)
                        params[p_name] = entity_text

            # 作为尾实体查询
            if label in tail_entities:
                for head_type in head_entities:
                    if head_type == "实体":
                        for et_label in set(self.entity_types.values()):
                            p_name = f"text_{idx}"
                            part = (
                                f"MATCH (m:{et_label})"
                                f"-[r:{rel_label}]->(n:{label} {{text: ${p_name}}})"
                                f"RETURN '{relation_name}' AS rel_name,"
                                f" m.text AS text, labels(m)[0] AS type,"
                                f" type(r) AS relation, 'in' AS direction"
                                f" LIMIT $limit"
                            )
                            union_parts.append(part)
                            params[p_name] = entity_text
                    else:
                        head_label = self.entity_types.get(head_type, head_type)
                        p_name = f"text_{idx}"
                        part = (
                            f"MATCH (m:{head_label})"
                            f"-[r:{rel_label}]->(n:{label} {{text: ${p_name}}})"
                            f"RETURN '{relation_name}' AS rel_name,"
                            f" m.text AS text, labels(m)[0] AS type,"
                            f" type(r) AS relation, 'in' AS direction"
                            f" LIMIT $limit"
                        )
                        union_parts.append(part)
                        params[p_name] = entity_text

        if not union_parts:
            return results

        params["limit"] = SYSTEM_CONFIG["max_kg_results"]

        combined_query = " CALL { " + " UNION ALL ".join(union_parts) + " } RETURN rel_name, text, type, relation, direction LIMIT 200"

        try:
            with self.driver.session() as session:
                result = session.run(combined_query, params)
                for record in result:
                    rel_name = record["rel_name"]
                    rtype = record["type"]
                    direction = record["direction"]
                    suffix = f"_from_{rtype}" if direction == "in" else f"_{rtype}"
                    key = f"{rel_name}{suffix}"
                    if key not in results:
                        results[key] = []
                    results[key].append({
                        "text": record["text"],
                        "type": rtype,
                        "relation": record["relation"]
                    })
        except Exception as e:
            print(f"批量查询失败，回退到常规查询: {e}")
            # 回退到逐个查询
            for entity_text, entity_type, relation_name in queries:
                partial = self.query_relations(entity_text, entity_type, relation_name)
                for k, v in partial.items():
                    if k not in results:
                        results[k] = []
                    results[k].extend(v)

        return results

    def query_relations_layered(self, entity_text: str, entity_type: str,
                                layer: str = "L1") -> Dict:
        """
        分层查询：L1只查核心关系，L2查扩展关系

        Args:
            entity_text: 实体文本
            entity_type: 实体类型
            layer: "L1" (核心), "L2" (扩展), "ALL" (全部)

        Returns:
            查询结果字典
        """
        if layer == "L1":
            target_relations = list(self.L1_CORE_RELATIONS)
        elif layer == "L2":
            target_relations = list(self.L2_EXTENDED_RELATIONS)
        else:
            target_relations = None  # 查全部，回退到原方法

        if target_relations is None:
            return self.query_relations(entity_text, entity_type)

        queries = [(entity_text, entity_type, r) for r in target_relations]
        return self.query_relations_batch(queries)

    def query_multi_hop(self, entity_text: str, entity_type: str, max_hops: int = 2) -> Dict:
        """
        多跳查询 - 查询实体的多跳关系
        """
        label = self.entity_types.get(entity_type, entity_type)
        results = {}
        
        with self.driver.session() as session:
            # 查询2跳关系
            query = f"""
            MATCH path = (n:{label} {{text: $entity_text}})-[*1..{max_hops}]-(m)
            WHERE n <> m
            RETURN DISTINCT m.text as text, labels(m)[0] as type, 
                   length(path) as hops, 
                   [r in relationships(path) | type(r)] as relations
            LIMIT $limit
            """
            result = session.run(query, entity_text=entity_text,
                               limit=SYSTEM_CONFIG["max_kg_results"])
            data = [record.data() for record in result]
            if data:
                results["multi_hop"] = data
        
        return results
    
    def format_kg_context(self, kg_results: Dict, entity_text: str, entity_type: str) -> str:
        """
        格式化知识图谱查询结果为上下文
        用于增强大模型的推理
        """
        context_parts = []
        
        # 获取实体类型的中文名称
        entity_type_cn = None
        for cn_name, label in self.entity_types.items():
            if label == entity_type or cn_name == entity_type:
                entity_type_cn = cn_name
                break
        
        entity_display = entity_type_cn if entity_type_cn else entity_type
        
        # 实体信息
        context_parts.append(f"实体：{entity_text}（{entity_display}）")
        
        # 关系信息
        if kg_results:
            context_parts.append("\n相关知识：")
            
            for key, values in kg_results.items():
                if not values:
                    continue
                
                # 解析关系类型和实体类型
                parts = key.split("_")
                if len(parts) >= 2:
                    relation_name = parts[0]
                    direction = "指向" if "from" not in key else "来自"
                    related_type = parts[-1]
                    
                    # 获取实体类型的中文名称
                    related_type_cn = None
                    for cn_name, label in self.entity_types.items():
                        if label == related_type or cn_name == related_type:
                            related_type_cn = cn_name
                            break
                    
                    related_type_display = related_type_cn if related_type_cn else related_type
                    
                    related_entities = [v["text"] for v in values[:5]]  # 最多5个
                    if related_entities:
                        context_parts.append(
                            f"  - {relation_name}关系（{direction}{related_type_display}）：{', '.join(related_entities)}"
                        )
        
        return "\n".join(context_parts)
    
    def enhance_question(self, question: str, entities: List[Tuple[str, str]]) -> str:
        """
        使用知识图谱增强问题
        """
        if not SYSTEM_CONFIG["enable_kg_enhancement"]:
            return question
        
        enhanced_parts = [question]
        kg_contexts = []
        
        # 为每个实体查询知识图谱
        for entity_text, entity_type in entities[:SYSTEM_CONFIG["max_entities"]]:
            kg_results = self.query_relations(entity_text, entity_type)
            if kg_results:
                context = self.format_kg_context(kg_results, entity_text, entity_type)
                kg_contexts.append(context)
        
        # 组合增强后的上下文
        if kg_contexts:
            enhanced_parts.append("\n\n【知识图谱增强信息】")
            enhanced_parts.extend(kg_contexts)
        
        return "\n".join(enhanced_parts)
