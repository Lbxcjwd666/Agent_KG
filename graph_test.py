import csv
import os
import base64
import re
from neo4j import GraphDatabase
from tqdm import tqdm
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===== 配置区域 =====
uri = "bolt://localhost:7687"
username = "neo4j"
password = "12345678"

# ========================================
# 🧪 测试模式开关
# ========================================
TEST_MODE = False  # 改为 False 进行全量导入
TEST_ENTITY_LIMIT = 1000
TEST_RELATION_LIMIT = 1000
# ========================================

# ========================================
# 📋 允许导入的实体标签
# ========================================
ALLOWED_ENTITY_LABELS = {
    'DIS', 'SYM', 'SYN', 'SIG', 'BEC', 'PRE',
    'MED', 'ACU', 'MER', 'VIS', 'PUL', 'BDP',
    'TNG', 'CON', 'FOO', 'LIT'
}
# ========================================

# ========================================
# 📋 允许导入的关系类型
# ========================================
ALLOWED_RELATION_TYPES = {
    'comp', 'treat', 'perf', 'from', 'cause',
    'oname', 'mapped_part', 'pulse_diagnosis',
    'belongto', 'related', 'reflect', 'abpulse',
    'assist_diag', 'Food_to_avoid', 'food_to_eat',
    'guide_med', 'guide_pre', 'acupoints', 'inandex', 'visual_diagnosis',
}
# ========================================

# 性能配置
BATCH_SIZE = 10000  # 增大批次大小
MAX_WORKERS = 4

driver = GraphDatabase.driver(uri, auth=(username, password),
                              max_connection_pool_size=20)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def sanitize_label(label):
    """清理标签名称"""
    if not label:
        return "Entity"
    label_str = str(label).strip()

    # 直接返回已知的标签
    known_labels = {
        'DIS', 'SYM', 'SYN', 'SIG', 'BEC', 'PRE', 'MED', 'ACU',
        'MER', 'VIS', 'PUL', 'BDP', 'TNG', 'CON', 'FOO', 'LIT'
    }
    if label_str in known_labels:
        return label_str

    # 其他标签需要清理
    if label_str.isdigit():
        return f"Entity_{label_str}"
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', label_str)
    if sanitized and sanitized[0].isdigit():
        sanitized = f"Entity_{sanitized}"
    if not sanitized:
        sanitized = "Entity"
    elif len(sanitized) > 50:
        sanitized = sanitized[:50]
    return sanitized


# 实体名称到图片文件的映射
ENTITY_IMAGE_MAPPING = {
    # 食物类
    "姜": "姜.png", "生姜": "姜.png", "山药": "山药.png", "淮山": "山药.png",
    "当归": "当归饮片.png", "枸杞": "枸杞.png", "枸杞子": "枸杞.png",
    "核桃": "核桃.png", "胡桃": "核桃.png", "桃子": "桃子.png", "桃": "桃子.png",
    "梨": "梨.png", "雪梨": "梨.png", "猕猴桃": "猕猴桃.png", "奇异果": "猕猴桃.png",
    "白菜": "白菜.png", "大白菜": "白菜.png", "笋": "笋.png", "竹笋": "笋.png",
    "菠萝": "菠萝.png", "萝卜": "萝卜.png", "苹果": "苹果.png", "西红柿": "西红柿.png",

    # 穴位类
    "百会": "百会.png", "白虫窝": "白虫窝.png", "大椎": "大椎，肺俞.png", "肺俞": "大椎，肺俞.png",
    "膈俞": "大椎，膈俞.png", "至阳": "大椎，至阳.png", "胆俞": "胆俞，脾俞，胃俞.png",
    "脾俞": "胆俞，脾俞，胃俞.png", "胃俞": "胆俞，脾俞，胃俞.png", "肾俞": "肺俞，脾俞，肾俞.png",
    "丰隆": "丰隆.png", "风池": "风池.png", "风门": "风门.png", "关元": "关元.png",
    "中极": "关元，中极.png", "合谷": "合谷.png", "颊车": "颊车.png", "间使": "间使.png",
    "巨阙": "巨阙.png", "列缺": "列缺.png", "内关": "内关.png", "阴郄": "内关，阴郄.png",
    "内庭": "内庭.png", "期门": "期门.png", "气冲": "气冲，中极.png", "曲池": "曲池.png",
    "然谷": "然谷.png", "三阴交": "三阴交.png", "膻中": "膻中.png", "膀胱俞": "肾俞，膀胱俞.png",
    "石门": "石门，关元.png", "四白": "四白，地仓.png", "地仓": "四白，地仓.png",
    "四神聪": "四神聪，百会.png", "太冲": "太冲.png", "天井": "天井.png", "天枢": "天枢.png",
    "通里": "通里，阴郄.png", "腕骨": "腕骨，上冲.png", "上冲": "腕骨，上冲.png",
    "委中": "委中.png", "心俞": "心俞，膈俞.png", "行间": "行间.png", "悬钟": "悬钟.png",
    "血海": "血海.png", "阳陵泉": "阳陵泉.png", "阴陵泉": "阴陵泉.png", "公孙": "阴陵泉，公孙.png",
    "印堂": "印堂.png", "攒竹": "攒竹.png", "照海": "照海.png", "支沟": "支沟.png",
    "中院": "中院.png", "足三里": "足三里，上巨虚，丰隆.png", "上巨虚": "足三里，上巨虚，丰隆.png",

    # 舌象类
    "暗红舌": "舌象 24 暗红舌、白腻苔微厚.png", "白腻苔": "舌象 24 暗红舌、白腻苔微厚.png",
    "紫舌": "舌象 25 紫舌，黄腻苔 —— 痰热肝郁.png", "黄腻苔": "舌象 25 紫舌，黄腻苔 —— 痰热肝郁.png",
    "暗淡舌": "舌象 26 暗淡舌，灰黄腻苔.png", "灰黄腻苔": "舌象 26 暗淡舌，灰黄腻苔.png",
    "红舌": "舌象 27 红舌，薄腻苔.png", "薄腻苔": "舌象 27 红舌，薄腻苔.png",
    "暗红齿痕舌": "舌象 28 暗红齿痕舌，薄苔.png", "薄苔": "舌象 28 暗红齿痕舌，薄苔.png",
    "暗红舌": "舌象 29 暗红舌，黑燥苔.png", "黑燥苔": "舌象 29 暗红舌，黑燥苔.png",
    "舌红": "舌象 30 舌红，苔黄.png", "苔黄": "舌象 30 舌红，苔黄.png",
    "黄疸": "舌象 31 黄腻苔 —— 黄疸.png", "灰黑黄腻苔": "舌象 32 灰黑黄腻苔.png",

    # 病症类
    "痤疮": "痤疮.png", "下肢筋脉曲张": "下肢筋脉曲张.png",

    # 同义词映射
    "足三里穴": "足三里，上巨虚，丰隆.png", "合谷穴": "合谷.png", "百会穴": "百会.png",
    "风池穴": "风池.png", "关元穴": "关元.png", "三阴交穴": "三阴交.png", "太冲穴": "太冲.png",
    "阳陵泉穴": "阳陵泉.png", "阴陵泉穴": "阴陵泉.png", "血海穴": "血海.png", "委中穴": "委中.png",
    "曲池穴": "曲池.png", "内关穴": "内关.png", "外关": "支沟.png", "支沟穴": "支沟.png",
    "照海穴": "照海.png", "列缺穴": "列缺.png", "后溪": "腕骨，上冲.png", "腕骨穴": "腕骨，上冲.png",
}


def image_to_base64(image_path):
    """将图片转换为Base64编码字符串"""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        return None


def get_image_base64(entity_text):
    """根据实体文本查找对应的图片"""
    if not entity_text:
        return None

    for entity_name, image_file in ENTITY_IMAGE_MAPPING.items():
        if entity_name in entity_text:
            image_path = os.path.join(SCRIPT_DIR, "图片", image_file)
            if os.path.exists(image_path):
                return image_to_base64(image_path)
    return None


def create_indexes(labels):
    """创建索引以加速查询 - 关键优化点"""
    print("\n🔧 创建索引...")

    with driver.session() as session:
        # 检查现有索引
        existing = session.run("SHOW INDEXES").data()
        existing_indexes = {idx['labelsOrTypes'][0] + '_' + idx['properties'][0]
                            for idx in existing
                            if idx.get('labelsOrTypes') and idx.get('properties')}

        created = 0
        for label in labels:
            sanitized = sanitize_label(label)
            index_name = f"{sanitized}_id"

            if index_name not in existing_indexes:
                try:
                    # 创建索引
                    query = f"CREATE INDEX {index_name}_idx IF NOT EXISTS FOR (n:{sanitized}) ON (n.id)"
                    session.run(query)
                    created += 1
                    print(f"   ✓ {sanitized}.id")
                except Exception as e:
                    print(f"   ⚠️  {sanitized}: {e}")

        if created > 0:
            print(f"\n⏳ 等待索引创建完成...")
            time.sleep(2)  # 等待索引生效

            # 等待索引变为ONLINE状态
            max_wait = 30
            for i in range(max_wait):
                indexes = session.run("SHOW INDEXES").data()
                pending = [idx for idx in indexes if idx.get('state') != 'ONLINE']
                if not pending:
                    break
                time.sleep(1)
                if i % 5 == 0:
                    print(f"   等待中... ({len(pending)} 个索引待完成)")

            print(f"✅ 索引创建完成: {created} 个新索引")
        else:
            print(f"✅ 索引已存在，无需创建")


def import_entities():
    """导入实体 - 包含完整的图片处理和标签过滤"""
    entities_file = os.path.join(SCRIPT_DIR, "final_merged_entities.csv")

    if not os.path.exists(entities_file):
        print(f"❌ 实体文件不存在: {entities_file}")
        return 0, 0, set()

    print("📁 读取实体文件...")

    entities_by_label = {}
    entities_with_images = 0
    all_labels = set()
    total_read = 0
    skipped_labels = set()

    with open(entities_file, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, None)

        for row in reader:
            if TEST_MODE and total_read >= TEST_ENTITY_LIMIT:
                break

            if len(row) >= 3:
                id_str = str(row[0]).strip()
                label = str(row[1]).strip()
                text = str(row[2]).strip()

                # 🔍 跳过不允许的实体标签
                if label not in ALLOWED_ENTITY_LABELS:
                    skipped_labels.add(label)
                    continue

                if id_str and id_str.isdigit():
                    id_int = int(id_str)
                    all_labels.add(label)

                    if label not in entities_by_label:
                        entities_by_label[label] = []

                    # 🖼️ 获取图片的Base64编码
                    image_base64 = get_image_base64(text)
                    if image_base64:
                        entities_with_images += 1

                    entities_by_label[label].append({
                        'id': id_int,
                        'text': text,
                        'image_base64': image_base64,
                        'has_image': image_base64 is not None
                    })
                    total_read += 1

    total_entities = sum(len(entities) for entities in entities_by_label.values())
    print(f"   读取 {total_entities:,} 个实体，{len(all_labels)} 种标签")
    print(
        f"   🖼️  有图片: {entities_with_images:,} 个 ({entities_with_images / total_entities * 100:.1f}%)" if total_entities > 0 else "")

    if skipped_labels:
        print(f"   ⏭️  跳过标签: {', '.join(sorted(skipped_labels))}")

    # 先创建索引
    create_indexes(all_labels)

    # 批量导入
    print(f"\n🚀 开始批量导入实体...")
    success_count = 0

    for label, entities in entities_by_label.items():
        sanitized_label = sanitize_label(label)
        count = len(entities)

        print(f"\n📦 {label} ({sanitized_label}): {count:,} 个")

        for i in tqdm(range(0, count, BATCH_SIZE), desc=f"   导入", unit="批"):
            batch = entities[i:i + BATCH_SIZE]
            try:
                with driver.session() as session:
                    query = f"""
                    UNWIND $batch AS entity
                    CREATE (n:{sanitized_label})
                    SET n.id = entity.id,
                        n.text = entity.text,
                        n.has_image = entity.has_image,
                        n.image_base64 = CASE WHEN entity.image_base64 IS NOT NULL 
                                              THEN entity.image_base64 
                                              ELSE null END
                    """

                    result = session.run(query, batch=batch)
                    summary = result.consume()
                    success_count += summary.counters.nodes_created
            except Exception as e:
                print(f"   ⚠️  批次失败: {e}")
                # 逐条处理
                for entity in batch:
                    try:
                        with driver.session() as session:
                            if entity['image_base64']:
                                query = f"CREATE (n:{sanitized_label} {{id: $id, text: $text, image_base64: $img, has_image: true}})"
                                session.run(query, id=entity['id'], text=entity['text'], img=entity['image_base64'])
                            else:
                                query = f"CREATE (n:{sanitized_label} {{id: $id, text: $text, has_image: false}})"
                                session.run(query, id=entity['id'], text=entity['text'])
                        success_count += 1
                    except:
                        continue

    print(f"\n✅ 实体导入完成: {success_count:,}/{total_entities:,}")
    print(f"   🖼️  含图片: {entities_with_images:,}")
    return success_count, entities_with_images, all_labels


def import_relationships_optimized():
    """优化的关系导入 - 使用索引加速"""
    relations_file = os.path.join(SCRIPT_DIR, "final_merged_relations_fixed1.csv")

    if not os.path.exists(relations_file):
        print(f"❌ 关系文件不存在: {relations_file}")
        return 0

    print("\n📁 读取关系文件...")

    # 按 (rel_type, from_label, to_label) 分组
    relationships_grouped = {}
    total_read = 0
    skipped_types = set()

    with open(relations_file, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, None)

        # 确定列索引
        try:
            from_id_idx = header.index('from_id')
            to_id_idx = header.index('to_id')
            type_idx = header.index('type')
            from_label_idx = header.index('from_label')
            to_label_idx = header.index('to_label')
            has_labels = True
            print(f"   ✅ CSV格式: {', '.join(header)}")
        except ValueError as e:
            print(f"   ❌ CSV格式错误: {e}")
            return 0

        for row in reader:
            if TEST_MODE and total_read >= TEST_RELATION_LIMIT:
                break

            if len(row) > max(from_id_idx, to_id_idx, type_idx, from_label_idx, to_label_idx):
                from_id_str = str(row[from_id_idx]).strip()
                to_id_str = str(row[to_id_idx]).strip()
                rel_type = str(row[type_idx]).strip()
                from_label = str(row[from_label_idx]).strip()
                to_label = str(row[to_label_idx]).strip()

                # 跳过不允许的关系类型
                if rel_type not in ALLOWED_RELATION_TYPES:
                    skipped_types.add(rel_type)
                    continue

                if from_id_str.isdigit() and to_id_str.isdigit() and from_label and to_label:
                    from_id = int(from_id_str)
                    to_id = int(to_id_str)

                    from_label_clean = sanitize_label(from_label)
                    to_label_clean = sanitize_label(to_label)

                    # 按关系类型和标签对分组
                    group_key = (rel_type, from_label_clean, to_label_clean)
                    if group_key not in relationships_grouped:
                        relationships_grouped[group_key] = []

                    relationships_grouped[group_key].append({
                        'from_id': from_id,
                        'to_id': to_id
                    })
                    total_read += 1

    total_count = sum(len(rels) for rels in relationships_grouped.values())

    print(f"   读取 {total_count:,} 个关系")
    print(f"   关系分组: {len(relationships_grouped)} 个")

    if skipped_types:
        print(f"   ⏭️  跳过类型: {', '.join(sorted(skipped_types))}")

    if total_count == 0:
        print("   ❌ 没有关系可导入")
        return 0

    print(f"\n🚀 开始批量导入关系...")
    print(f"   批次大小: {BATCH_SIZE:,}")
    print("=" * 80)

    start_time = time.time()
    success_count = 0
    failed_count = 0

    # 按关系数量排序
    sorted_groups = sorted(relationships_grouped.items(),
                           key=lambda x: len(x[1]), reverse=True)

    for idx, ((rel_type, from_label, to_label), rels) in enumerate(sorted_groups, 1):
        print(f"\n[{idx}/{len(sorted_groups)}] {rel_type}: {from_label}→{to_label} ({len(rels):,}条)")

        group_start = time.time()
        group_success = 0
        group_failed = 0

        # 使用优化的查询
        for i in tqdm(range(0, len(rels), BATCH_SIZE), desc="   处理", unit="批", ncols=70):
            batch = rels[i:i + BATCH_SIZE]

            try:
                with driver.session() as session:
                    # 🔑 关键优化：使用标签+ID，利用索引加速
                    query = f"""
                    UNWIND $batch AS row
                    MATCH (a:{from_label} {{id: row.from_id}})
                    MATCH (b:{to_label} {{id: row.to_id}})
                    CREATE (a)-[:{rel_type}]->(b)
                    """

                    result = session.run(query, batch=batch)
                    summary = result.consume()
                    batch_success = summary.counters.relationships_created
                    batch_failed = len(batch) - batch_success

                    group_success += batch_success
                    group_failed += batch_failed

            except Exception as e:
                # 批次失败时逐条重试
                for rel in batch:
                    try:
                        with driver.session() as session:
                            query = f"""
                            MATCH (a:{from_label} {{id: $from_id}})
                            MATCH (b:{to_label} {{id: $to_id}})
                            CREATE (a)-[:{rel_type}]->(b)
                            """
                            result = session.run(query, from_id=rel['from_id'], to_id=rel['to_id'])
                            summary = result.consume()
                            if summary.counters.relationships_created > 0:
                                group_success += 1
                            else:
                                group_failed += 1
                    except:
                        group_failed += 1

        group_elapsed = time.time() - group_start
        speed = group_success / group_elapsed if group_elapsed > 0 else 0

        success_count += group_success
        failed_count += group_failed

        print(f"   ✅ 成功: {group_success:,}/{len(rels):,} | "
              f"耗时: {group_elapsed:.1f}s | "
              f"速度: {speed:.0f}条/s")

        if group_failed > 0:
            print(f"   ⚠️  失败: {group_failed:,} (节点可能不存在)")

    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print(f"🎉 关系导入完成!")
    print(f"   ✅ 成功: {success_count:,}/{total_count:,} ({success_count / total_count * 100:.1f}%)")
    if failed_count > 0:
        print(f"   ⚠️  失败: {failed_count:,}")
    print(f"   ⏱️  总耗时: {elapsed:.1f}秒")
    print(f"   ⚡ 平均速度: {success_count / elapsed if elapsed > 0 else 0:,.0f} 关系/秒")

    return success_count


def verify_results():
    """验证结果"""
    print("\n" + "=" * 80)
    print("🔍 验证导入结果")
    print("=" * 80)

    with driver.session() as session:
        # 节点统计
        node_count = session.run("MATCH (n) RETURN count(n) as count").single()["count"]
        print(f"\n📊 节点总数: {node_count:,}")

        # 有图片的节点
        with_img = session.run("MATCH (n {has_image: true}) RETURN count(n) as count").single()["count"]
        if node_count > 0:
            print(f"   🖼️  含图片: {with_img:,} ({with_img / node_count * 100:.1f}%)")

        # 关系统计
        rel_count = session.run("MATCH ()-[r]->() RETURN count(r) as count").single()["count"]
        print(f"\n🔗 关系总数: {rel_count:,}")

        # 索引状态
        indexes = session.run("SHOW INDEXES").data()
        online = [idx for idx in indexes if idx.get('state') == 'ONLINE']
        print(f"\n📇 索引状态: {len(online)}/{len(indexes)} 在线")

        # 关系类型分布
        print(f"\n📊 关系类型分布 (Top 10):")
        rel_types = session.run("""
            MATCH ()-[r]->() 
            RETURN type(r) as rel_type, count(r) as count 
            ORDER BY count DESC LIMIT 10
        """).data()

        for rel in rel_types:
            print(f"   ✓ {rel['rel_type']}: {rel['count']:,}")

        # 标签分布
        print(f"\n📊 节点标签分布 (Top 10):")
        label_dist = session.run("""
            MATCH (n)
            RETURN labels(n)[0] as label, count(n) as count
            ORDER BY count DESC LIMIT 10
        """).data()

        for item in label_dist:
            print(f"   ✓ {item['label']}: {item['count']:,}")

        # 有图片的实体样本
        if with_img > 0:
            print(f"\n🖼️  有图片的实体样本:")
            samples = session.run("""
                MATCH (n {has_image: true})
                RETURN labels(n)[0] as label, n.text as text, size(n.image_base64) as img_size
                LIMIT 5
            """).data()

            for s in samples:
                img_kb = s['img_size'] / 1024
                print(f"   • {s['label']}: {s['text']} ({img_kb:.1f} KB)")


def main():
    try:
        print("=" * 80)
        print("🚀 知识图谱导入程序 (优化版)")
        print("=" * 80)

        if TEST_MODE:
            print(f"\n🧪 测试模式")
            print(f"   实体限制: {TEST_ENTITY_LIMIT:,}")
            print(f"   关系限制: {TEST_RELATION_LIMIT:,}")

        print(f"\n⚡ 性能优化:")
        print(f"   • 批次大小: {BATCH_SIZE:,}")
        print(f"   • 自动创建索引（加速查询）")
        print(f"   • 标签+ID双重匹配（确保准确）")

        print(f"\n📋 允许的实体标签: {len(ALLOWED_ENTITY_LABELS)} 种")
        print(f"   {', '.join(sorted(ALLOWED_ENTITY_LABELS))}")

        print(f"\n📋 允许的关系类型: {len(ALLOWED_RELATION_TYPES)} 种")

        # 1. 导入实体
        print("\n" + "=" * 80)
        print("1️⃣  导入实体")
        print("=" * 80)
        entities_count, images_count, labels = import_entities()

        if entities_count == 0:
            print("❌ 实体导入失败，程序终止")
            return

        # 2. 导入关系
        print("\n" + "=" * 80)
        print("2️⃣  导入关系")
        print("=" * 80)
        relations_count = import_relationships_optimized()

        # 3. 验证结果
        verify_results()

        # 总结
        print("\n" + "=" * 80)
        print("✅ 导入完成!")
        print("=" * 80)
        print(f"📊 统计:")
        print(f"   • 实体: {entities_count:,}")
        print(f"   • 关系: {relations_count:,}")
        print(f"   • 图片: {images_count:,}")

        if TEST_MODE:
            print(f"\n💡 下一步:")
            print(f"   1. 验证数据正确性")
            print(f"   2. 清空数据库: MATCH (n) DETACH DELETE n")
            print(f"   3. 设置 TEST_MODE = False")
            print(f"   4. 运行全量导入")
        else:
            print(f"\n✨ 全量导入完成！")
            print(f"\n💡 查询示例:")
            print(f"   MATCH (n:MED {{id: 195}}) RETURN n")
            print(f"   MATCH (a)-[r:treat]->(b) RETURN a, r, b LIMIT 10")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        driver.close()
        print("\n🔒 数据库连接已关闭")


if __name__ == "__main__":
    main()