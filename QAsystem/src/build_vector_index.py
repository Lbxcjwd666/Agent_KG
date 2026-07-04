"""
离线脚本: 批量编码知识图谱实体并创建 Neo4j 向量索引

使用方式:
    cd QAsystem/src
    python build_vector_index.py

特性:
    - 多线程并发编码, 速度提升数倍
    - 边编码边写入, 中断后重启自动跳过已编码实体
    - 支持换模型继续 (维度必须一致)
    - 逐条重试容错
"""

import sys
import re
import time
import threading
import logging
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from neo4j import GraphDatabase
from qwen_api import QwenAPI
from config import NEO4J_CONFIG, ENTITY_TYPES, VECTOR_INDEX_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("build_vector_index")

_progress_lock = threading.Lock()
_progress = {"encoded": 0, "failed": 0}


def is_valid_text(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) == 0:
        return False
    if len(text) > 512:
        return False
    if re.match(r'^[\d\.\,\-\+\s]+$', text):
        return False
    if len(text.strip()) == 1 and text.strip() in '，。、；：！？':
        return False
    return True


def load_unencoded_entities(driver) -> List[Dict]:
    entities = []
    with driver.session() as session:
        for cn_name, neo4j_label in ENTITY_TYPES.items():
            query = (
                f"MATCH (n:{neo4j_label}) "
                f"WHERE n.text IS NOT NULL AND n.embedding IS NULL "
                f"RETURN id(n) AS node_id, n.text AS text"
            )
            result = session.run(query)
            count = 0
            for record in result:
                text = record["text"]
                if is_valid_text(text):
                    entities.append({
                        "node_id": record["node_id"],
                        "text": str(text).strip(),
                        "label": neo4j_label
                    })
                    count += 1
            logger.info(f"待编码 {cn_name}({neo4j_label}): {count} 个")

    logger.info(f"共 {len(entities)} 个待编码实体")
    return entities


def count_encoded(driver) -> int:
    total = 0
    with driver.session() as session:
        for cn_name, neo4j_label in ENTITY_TYPES.items():
            result = session.run(
                f"MATCH (n:{neo4j_label}) WHERE n.embedding IS NOT NULL RETURN count(n) AS cnt"
            )
            cnt = result.single()["cnt"]
            total += cnt
    return total


def count_total(driver) -> int:
    total = 0
    with driver.session() as session:
        for cn_name, neo4j_label in ENTITY_TYPES.items():
            result = session.run(
                f"MATCH (n:{neo4j_label}) WHERE n.text IS NOT NULL RETURN count(n) AS cnt"
            )
            cnt = result.single()["cnt"]
            total += cnt
    return total


def _encode_single_batch(qwen_api: QwenAPI, batch: List[Dict], batch_num: int) -> Dict:
    """编码单个批次, 返回 {success, batch, embeddings, error}"""
    batch_texts = [e["text"] for e in batch]
    model = VECTOR_INDEX_CONFIG["embedding_model"]
    dimensions = VECTOR_INDEX_CONFIG["embedding_dimension"]
    provider = VECTOR_INDEX_CONFIG.get("embedding_provider", "api")

    max_attempts = 1 if provider == "local" else 3
    for attempt in range(max_attempts):
        try:
            embeddings = qwen_api.get_embeddings(
                batch_texts, model=model, dimensions=dimensions
            )
            if len(embeddings) == len(batch_texts):
                return {"success": True, "batch": batch, "embeddings": embeddings}
            else:
                logger.warning(f"批次 {batch_num} 返回数量不匹配: 请求{len(batch_texts)}, 返回{len(embeddings)}")
        except Exception as e:
            logger.warning(f"批次 {batch_num} 编码失败 (尝试 {attempt + 1}/{max_attempts}): {e}")
            if attempt < max_attempts - 1:
                time.sleep(3)

    return {"success": False, "batch": batch, "embeddings": None, "error": "all_attempts_failed"}


def _encode_single_entity(qwen_api: QwenAPI, entity: Dict) -> Dict:
    """逐条编码单个实体"""
    model = VECTOR_INDEX_CONFIG["embedding_model"]
    dimensions = VECTOR_INDEX_CONFIG["embedding_dimension"]

    try:
        embeddings = qwen_api.get_embeddings(
            [entity["text"]], model=model, dimensions=dimensions
        )
        if embeddings and len(embeddings) > 0:
            return {"success": True, "entity": entity, "embedding": embeddings[0]}
    except Exception as e:
        logger.debug(f"逐条编码失败 (text='{entity['text'][:20]}...'): {e}")

    return {"success": False, "entity": entity}


def _write_batch(driver, entities: List[Dict], embeddings: List[List[float]]) -> int:
    rows = [
        {"node_id": e["node_id"], "embedding": emb}
        for e, emb in zip(entities, embeddings)
    ]
    try:
        with driver.session() as session:
            result = session.run(
                "UNWIND $rows AS row "
                "MATCH (n) WHERE id(n) = row.node_id "
                "SET n.embedding = row.embedding "
                "RETURN count(n) AS written",
                rows=rows
            )
            written = result.single()["written"]
            return written
    except Exception as e:
        logger.warning(f"UNWIND批量写入失败, 回退逐条写入: {e}")
        written = 0
        with driver.session() as session:
            for entity, embedding in zip(entities, embeddings):
                try:
                    session.run(
                        "MATCH (n) WHERE id(n) = $node_id SET n.embedding = $embedding",
                        node_id=entity["node_id"],
                        embedding=embedding
                    )
                    written += 1
                except Exception as e2:
                    logger.warning(f"写入向量失败 (id={entity['node_id']}): {e2}")
        return written


def _write_single(driver, entity: Dict, embedding: List[float]) -> bool:
    with driver.session() as session:
        try:
            session.run(
                "MATCH (n) WHERE id(n) = $node_id SET n.embedding = $embedding",
                node_id=entity["node_id"],
                embedding=embedding
            )
            return True
        except Exception as e:
            logger.warning(f"写入向量失败 (id={entity['node_id']}, text='{entity['text'][:20]}'): {e}")
            return False


def encode_and_write(driver, qwen_api: QwenAPI, entities: List[Dict],
                     batch_size: int = 10, max_workers: int = 5):
    total = len(entities)
    provider = VECTOR_INDEX_CONFIG.get("embedding_provider", "api")

    _progress["encoded"] = 0
    _progress["failed"] = 0

    if provider == "local":
        return _encode_and_write_sequential(driver, qwen_api, entities, batch_size, total)
    else:
        return _encode_and_write_concurrent(driver, qwen_api, entities, batch_size, max_workers, total)


def _encode_and_write_sequential(driver, qwen_api: QwenAPI, entities: List[Dict],
                                 batch_size: int, total: int):
    total_batches = (total + batch_size - 1) // batch_size
    logger.info(f"本地模型顺序编码: {total_batches} 个批次, 每批 {batch_size} 条")

    for batch_num in range(1, total_batches + 1):
        start = (batch_num - 1) * batch_size
        batch = entities[start:start + batch_size]

        result = _encode_single_batch(qwen_api, batch, batch_num)

        if result["success"]:
            written = _write_batch(driver, result["batch"], result["embeddings"])
            write_failed = len(batch) - written
            _progress["encoded"] += written
            _progress["failed"] += write_failed
            logger.info(
                f"批次 {batch_num}/{total_batches}: 编码+写入 {written}/{len(batch)} 条"
                + (f", 写入失败 {write_failed} 条" if write_failed > 0 else "")
            )
        else:
            logger.info(f"批次 {batch_num}/{total_batches} 整批失败, 逐条编码...")
            for entity in batch:
                single_result = _encode_single_entity(qwen_api, entity)
                if single_result["success"]:
                    if _write_single(driver, single_result["entity"], single_result["embedding"]):
                        _progress["encoded"] += 1
                    else:
                        _progress["failed"] += 1
                else:
                    _progress["failed"] += 1

        done = _progress["encoded"] + _progress["failed"]
        if done % 500 < batch_size or done == total:
            logger.info(
                f"总进度: {done}/{total} "
                f"(成功 {_progress['encoded']}, 失败 {_progress['failed']})"
            )

    logger.info(f"编码完成: 成功写入 {_progress['encoded']}, 失败 {_progress['failed']} (下次运行将重新编码)")
    return _progress["encoded"]


def _encode_and_write_concurrent(driver, qwen_api: QwenAPI, entities: List[Dict],
                                 batch_size: int, max_workers: int, total: int):
    batches = []
    for i in range(0, total, batch_size):
        batches.append((i // batch_size + 1, entities[i:i + batch_size]))

    total_batches = len(batches)
    logger.info(f"API并发编码: {max_workers} 个线程, {total_batches} 个批次, 每批 {batch_size} 条")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_batch = {}
        for batch_num, batch in batches:
            future = executor.submit(_encode_single_batch, qwen_api, batch, batch_num)
            future_to_batch[future] = (batch_num, batch)

        for future in as_completed(future_to_batch):
            batch_num, batch = future_to_batch[future]
            try:
                result = future.result()
            except Exception as e:
                logger.error(f"批次 {batch_num} 异常: {e}")
                result = {"success": False, "batch": batch, "embeddings": None}

            if result["success"]:
                written = _write_batch(driver, result["batch"], result["embeddings"])
                write_failed = len(batch) - written
                with _progress_lock:
                    _progress["encoded"] += written
                    _progress["failed"] += write_failed
                if write_failed > 0:
                    logger.warning(f"批次 {batch_num}: 编码成功 {len(batch)} 条, 写入失败 {write_failed} 条 (下次将重新编码)")
            else:
                logger.info(f"批次 {batch_num} 整批失败, 逐条编码...")
                for entity in batch:
                    single_result = _encode_single_entity(qwen_api, entity)
                    if single_result["success"]:
                        if _write_single(driver, single_result["entity"], single_result["embedding"]):
                            with _progress_lock:
                                _progress["encoded"] += 1
                        else:
                            with _progress_lock:
                                _progress["failed"] += 1
                    else:
                        with _progress_lock:
                            _progress["failed"] += 1
                    time.sleep(0.1)

            with _progress_lock:
                done = _progress["encoded"] + _progress["failed"]
                if done % 100 < batch_size or done == total:
                    logger.info(
                        f"进度: {done}/{total} "
                        f"(成功 {_progress['encoded']}, 失败 {_progress['failed']})"
                    )

    logger.info(f"编码完成: 成功写入 {_progress['encoded']}, 失败 {_progress['failed']} (下次运行将重新编码)")
    return _progress["encoded"]


def create_vector_index(driver) -> bool:
    index_name = VECTOR_INDEX_CONFIG["index_name"]
    dimension = VECTOR_INDEX_CONFIG["embedding_dimension"]
    similarity = VECTOR_INDEX_CONFIG["similarity_function"]

    with driver.session() as session:
        logger.info("为所有实体节点添加 Entity 通用标签...")
        for cn_name, neo4j_label in ENTITY_TYPES.items():
            try:
                added = 0
                while True:
                    result = session.run(
                        f"MATCH (n:{neo4j_label}) WHERE NOT 'Entity' IN labels(n) "
                        f"RETURN id(n) AS nid LIMIT 5000"
                    )
                    ids = [r["nid"] for r in result]
                    if not ids:
                        break
                    session.run(
                        "UNWIND $ids AS nid MATCH (n) WHERE id(n) = nid SET n:Entity",
                        ids=ids
                    )
                    added += len(ids)
                logger.info(f"  {neo4j_label}: 添加 Entity 标签 {added} 个")
            except Exception as e:
                logger.warning(f"为 {neo4j_label} 添加 Entity 标签失败: {e}")
        logger.info("Entity 通用标签添加完成")

        try:
            result = session.run("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name")
            existing = [record["name"] for record in result]
            if index_name in existing:
                logger.info(f"向量索引 '{index_name}' 已存在, 跳过创建")
                return True
        except Exception:
            pass

        try:
            create_query = (
                "CREATE VECTOR INDEX $index_name IF NOT EXISTS "
                "FOR (n:Entity) ON (n.embedding) "
                "OPTIONS { indexConfig: { "
                "`vector.dimensions`: $dimension, "
                "`vector.similarity_function`: $similarity "
                "} }"
            )
            session.run(
                create_query,
                index_name=index_name,
                dimension=dimension,
                similarity=similarity
            )
            logger.info(f"向量索引 '{index_name}' 创建成功 (维度={dimension}, 相似度={similarity})")
            return True
        except Exception as e:
            logger.warning(f"通用标签索引创建失败: {e}, 尝试按类型分别创建...")

            created_any = False
            for cn_name, neo4j_label in ENTITY_TYPES.items():
                label_index_name = f"{index_name}_{neo4j_label.lower()}"
                try:
                    session.run(
                        f"CREATE VECTOR INDEX {label_index_name} IF NOT EXISTS "
                        f"FOR (n:{neo4j_label}) ON (n.embedding) "
                        f"OPTIONS {{ indexConfig: {{ "
                        f"`vector.dimensions`: $dimension, "
                        f"`vector.similarity_function`: $similarity "
                        f"}} }}",
                        dimension=dimension,
                        similarity=similarity
                    )
                    logger.info(f"为 {neo4j_label} 创建向量索引: {label_index_name}")
                    created_any = True
                except Exception as e2:
                    logger.warning(f"为 {neo4j_label} 创建索引失败: {e2}")

            return created_any


def verify_index(driver, qwen_api: QwenAPI):
    test_text = "感冒"
    logger.info(f"验证向量索引, 测试查询: '{test_text}'")

    try:
        embedding = qwen_api.get_embeddings(
            [test_text],
            model=VECTOR_INDEX_CONFIG["embedding_model"],
            dimensions=VECTOR_INDEX_CONFIG["embedding_dimension"]
        )
        if not embedding:
            logger.error("测试文本编码失败")
            return

        query_vec = embedding[0]
        index_name = VECTOR_INDEX_CONFIG["index_name"]

        with driver.session() as session:
            try:
                query = (
                    "CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector) "
                    "YIELD node, score "
                    "RETURN node.text AS text, labels(node) AS labels, score "
                    "ORDER BY score DESC LIMIT 5"
                )
                result = session.run(
                    query,
                    index_name=index_name,
                    top_k=5,
                    query_vector=query_vec
                )

                found = []
                for record in result:
                    found.append({
                        "text": record["text"],
                        "labels": record["labels"],
                        "score": round(record["score"], 4)
                    })

                if found:
                    logger.info("向量索引验证成功! 搜索结果:")
                    for item in found:
                        logger.info(f"  - {item['text']} (labels={item['labels']}, score={item['score']})")
                else:
                    logger.warning("向量搜索返回空结果, 可能索引尚未就绪")
            except Exception as e:
                logger.error(f"通用索引搜索失败: {e}")
                logger.info("尝试按类型索引搜索...")
                for cn_name, neo4j_label in ENTITY_TYPES.items():
                    label_index_name = f"{index_name}_{neo4j_label.lower()}"
                    try:
                        result = session.run(
                            "CALL db.index.vector.queryNodes($index_name, $top_k, $query_vector) "
                            "YIELD node, score "
                            "RETURN node.text AS text, score ORDER BY score DESC LIMIT 3",
                            index_name=label_index_name,
                            top_k=3,
                            query_vector=query_vec
                        )
                        for record in result:
                            logger.info(f"  [{neo4j_label}] {record['text']} (score={round(record['score'], 4)})")
                        break
                    except Exception:
                        continue

    except Exception as e:
        logger.error(f"验证过程出错: {e}")


def test_entity_linking(driver, qwen_api: QwenAPI):
    from kg_enhancer import KnowledgeGraphEnhancer
    from entity_linker import EntityLinker

    test_cases = [
        {"text": "没劲", "label": "症状"},
        {"text": "风寒", "label": "疾病"},
        {"text": "六味地黄丸", "label": "方剂"},
        {"text": "足三里", "label": "腧穴"},
        {"text": "黄芪", "label": "中药材"},
        {"text": "肾阳虚", "label": "证候"},
        {"text": "脉浮紧", "label": "脉象"},
        {"text": "舌淡红", "label": "舌象"},
        {"text": "太阴脾经", "label": "经脉"},
        {"text": "气虚", "label": "病因病机"},
    ]

    try:
        kg = KnowledgeGraphEnhancer()
    except Exception as e:
        logger.error(f"KGEnhancer 初始化失败: {e}")
        return

    linker = EntityLinker(kg_enhancer=kg, embedding_api=qwen_api)

    logger.info(f"测试 {len(test_cases)} 个实体链接用例:")
    logger.info("-" * 80)

    stats = {"exact": 0, "alias": 0, "vector": 0, "fuzzy": 0, "llm_only": 0}
    for case in test_cases:
        result = linker._link_single(case)
        method = result.get("matched_via", "unknown")
        confidence = result.get("confidence", 0)
        linked = result.get("linked_text", case["text"])
        candidates = result.get("candidates", [])

        if method in stats:
            stats[method] += 1

        logger.info(
            f"  [{method:>8}] {case['text']:>6} -> {linked}  "
            f"(置信度={confidence}, 候选数={len(candidates)})"
        )
        if candidates and method in ("vector", "fuzzy"):
            for c in candidates[:3]:
                logger.info(f"           候选: {c['text']} (score={c.get('score', 'N/A')}, method={c.get('method', 'N/A')})")

    logger.info("-" * 80)
    logger.info(f"统计: 精确={stats['exact']}, 别名={stats['alias']}, "
                f"向量={stats['vector']}, 模糊={stats['fuzzy']}, 未链接={stats['llm_only']}")


def reset_embeddings(driver):
    cleared = 0
    batch_size = 5000
    for cn_name, neo4j_label in ENTITY_TYPES.items():
        label_cleared = 0
        while True:
            with driver.session() as session:
                result = session.run(
                    f"MATCH (n:{neo4j_label}) WHERE n.embedding IS NOT NULL "
                    f"RETURN id(n) AS nid LIMIT $batch",
                    batch=batch_size
                )
                nids = [r["nid"] for r in result]
            if not nids:
                break
            with driver.session() as session:
                session.run(
                    "UNWIND $nids AS nid "
                    "MATCH (n) WHERE id(n) = nid "
                    "REMOVE n.embedding",
                    nids=nids
                )
            label_cleared += len(nids)
        if label_cleared > 0:
            logger.info(f"清除 {cn_name}({neo4j_label}): {label_cleared} 条")
        cleared += label_cleared
    logger.info(f"共清除 {cleared} 条旧编码")
    return cleared


def main():
    import argparse
    parser = argparse.ArgumentParser(description="构建知识图谱向量索引")
    parser.add_argument("--reset", action="store_true", help="清除所有已有编码, 重新开始")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("开始构建知识图谱向量索引")
    logger.info(f"模型: {VECTOR_INDEX_CONFIG['embedding_model']}")
    logger.info(f"编码方式: {VECTOR_INDEX_CONFIG.get('embedding_provider', 'api')}")
    logger.info(f"维度: {VECTOR_INDEX_CONFIG['embedding_dimension']}")
    logger.info(f"批量大小: {VECTOR_INDEX_CONFIG['batch_size']}")
    logger.info(f"并发线程: {VECTOR_INDEX_CONFIG.get('concurrent_workers', 5)}")
    logger.info("=" * 60)

    driver = GraphDatabase.driver(
        NEO4J_CONFIG["uri"],
        auth=(NEO4J_CONFIG["user"], NEO4J_CONFIG["password"])
    )

    try:
        driver.verify_connectivity()
        logger.info("Neo4j 连接成功")
    except Exception as e:
        logger.error(f"Neo4j 连接失败: {e}")
        sys.exit(1)

    if args.reset:
        logger.info("\n--- 重置: 清除所有已有编码和向量索引 ---")
        reset_embeddings(driver)
        with driver.session() as session:
            try:
                result = session.run("SHOW INDEXES YIELD name, type WHERE type = 'VECTOR' RETURN name")
                for record in result:
                    idx_name = record["name"]
                    logger.info(f"  删除旧索引: {idx_name}")
                    session.run(f"DROP INDEX {idx_name} IF EXISTS")
            except Exception as e:
                logger.warning(f"删除旧索引失败: {e}")

    qwen_api = QwenAPI()

    already_encoded = count_encoded(driver)
    total_entities = count_total(driver)
    logger.info(f"\n--- 状态: 已编码 {already_encoded}/{total_entities} ---")

    logger.info("\n--- Step 1: 加载待编码实体 ---")
    entities = load_unencoded_entities(driver)
    if not entities:
        logger.info("所有实体已编码, 无需继续")
    else:
        logger.info(f"\n--- Step 2: 并发编码并写入 ({len(entities)} 个实体) ---")
        encoded = encode_and_write(
            driver, qwen_api, entities,
            batch_size=VECTOR_INDEX_CONFIG["batch_size"],
            max_workers=VECTOR_INDEX_CONFIG.get("concurrent_workers", 5)
        )
        if encoded == 0:
            logger.error("所有实体编码均失败, 请检查 API 配置和网络连接")
            driver.close()
            return

    logger.info("\n--- Step 3: 创建向量索引 ---")
    success = create_vector_index(driver)
    if not success:
        logger.error("向量索引创建失败")
        driver.close()
        return

    logger.info("\n--- Step 4: 验证索引 ---")
    time.sleep(5)
    verify_index(driver, qwen_api)

    logger.info("\n--- Step 5: 实体链接测试 ---")
    test_entity_linking(driver, qwen_api)

    driver.close()

    final_encoded = already_encoded + (encoded if 'encoded' in dir() else 0)
    logger.info("\n" + "=" * 60)
    logger.info(f"向量索引构建完成! 共编码 {final_encoded}/{total_entities} 个实体")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()