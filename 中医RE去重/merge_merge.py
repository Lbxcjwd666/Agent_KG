#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并已处理的merged文件 - 三步法
用于合并多个merged_entities.csv和merged_relations.csv文件
"""

import os
import pandas as pd
from pathlib import Path
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')


class MergedFilesMerger:
    def __init__(self, data_folder: str):
        self.data_folder = Path(data_folder)
        self.temp_id_counter = 1  # 临时ID计数器

        # 第一步的数据
        self.merged_entities_temp = None
        self.merged_relations_temp = None

        # 第二步的映射
        self.temp_id_to_final_id = {}

        # 最终结果
        self.final_entities = None
        self.final_relations = None

    def find_files(self):
        """查找所有merged_entities和merged_relations文件"""
        entity_files = sorted(self.data_folder.glob("merged_entities*.csv"))
        relation_files = sorted(self.data_folder.glob("merged_relations*.csv"))

        print(f"找到 {len(entity_files)} 个实体文件:")
        for f in entity_files:
            print(f"  - {f.name}")

        print(f"找到 {len(relation_files)} 个关系文件:")
        for f in relation_files:
            print(f"  - {f.name}")

        return entity_files, relation_files

    def read_csv_auto_detect(self, file_path: Path):
        """自动检测分隔符并读取CSV"""
        try:
            # 尝试不同的分隔符
            separators = [',', '\t', '|', ';']

            for sep in separators:
                try:
                    df = pd.read_csv(file_path, sep=sep, encoding='utf-8-sig')
                    # 检查是否成功读取了多列
                    if len(df.columns) > 1:
                        return df
                except:
                    continue

            # 如果都失败，尝试默认读取
            return pd.read_csv(file_path, encoding='utf-8-sig')

        except Exception as e:
            print(f"读取 {file_path} 时出错: {e}")
            return None

    def safe_int_convert(self, value, default=0):
        """
        安全地将值转换为整数
        如果值是NaN或无法转换，返回默认值
        """
        if pd.isna(value):
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def step1_merge_without_dedup(self, entity_files, relation_files):
        """
        第一步：合并但不去重，建立完整的关系信息
        """
        print("\n" + "=" * 80)
        print("第一步：合并实体和关系（不去重），建立完整关系信息")
        print("=" * 80)

        all_entities = []
        all_relations = []

        # (文件名, 原始ID) -> 临时ID 的映射
        old_id_to_temp_id = {}

        # --- 处理实体文件 ---
        print("\n--- 处理实体文件 ---")
        for entity_file in entity_files:
            print(f"\n读取: {entity_file.name}")

            entities_df = self.read_csv_auto_detect(entity_file)
            if entities_df is None:
                print(f"  ⚠️ 读取失败，跳过")
                continue

            print(f"  原始列: {list(entities_df.columns)}")
            print(f"  原始实体数: {len(entities_df)}")

            # 检查必需的列
            required_cols = ['ID', 'Label', 'Entity Text']
            missing_cols = [col for col in required_cols if col not in entities_df.columns]

            if missing_cols:
                print(f"  ⚠️ 缺少必需的列: {missing_cols}，跳过")
                continue

            # 为每个实体分配新的临时ID
            for idx, row in entities_df.iterrows():
                try:
                    old_id = int(row['ID'])
                except:
                    print(f"  ⚠️ 无效的ID: {row['ID']}，跳过")
                    continue

                temp_id = self.temp_id_counter
                self.temp_id_counter += 1

                # 建立映射：(文件名, 原始ID) -> 临时ID
                old_id_to_temp_id[(entity_file.name, old_id)] = temp_id

                # 保存实体信息
                all_entities.append({
                    'temp_id': temp_id,
                    'Label': str(row['Label']) if pd.notna(row['Label']) else '',
                    'Entity Text': str(row['Entity Text']) if pd.notna(row['Entity Text']) else '',
                    'source_file': entity_file.name,
                    'original_id': old_id
                })

            print(f"  ✓ 成功处理 {len(entities_df)} 个实体")

        if not all_entities:
            print("\n❌ 错误：没有成功读取任何实体")
            return False

        print(f"\n合并后临时实体总数: {len(all_entities)}")
        self.merged_entities_temp = pd.DataFrame(all_entities)

        # --- 处理关系文件 ---
        print("\n--- 处理关系文件 ---")
        relation_success = 0
        relation_failed = 0

        for relation_file in relation_files:
            # 确定对应的实体文件名
            # 例如：merged_relations1.csv 对应 merged_entities1.csv
            base_name = relation_file.name.replace('relations', 'entities')

            print(f"\n读取: {relation_file.name}")
            print(f"  对应实体文件: {base_name}")

            relations_df = self.read_csv_auto_detect(relation_file)
            if relations_df is None:
                print(f"  ⚠️ 读取失败，跳过")
                continue

            print(f"  原始列: {list(relations_df.columns)}")
            print(f"  原始关系数: {len(relations_df)}")

            # 检查必需的列
            required_cols = ['from_id', 'to_id', 'type']
            missing_cols = [col for col in required_cols if col not in relations_df.columns]

            if missing_cols:
                print(f"  ⚠️ 缺少必需的列: {missing_cols}，跳过")
                continue

            for idx, row in relations_df.iterrows():
                try:
                    old_from_id = int(row['from_id'])
                    old_to_id = int(row['to_id'])
                except:
                    relation_failed += 1
                    continue

                from_key = (base_name, old_from_id)
                to_key = (base_name, old_to_id)

                # 检查是否能找到对应的实体
                if from_key not in old_id_to_temp_id:
                    if relation_failed < 5:  # 只打印前5个错误
                        print(f"  ⚠️ 找不到from实体: {from_key}")
                    relation_failed += 1
                    continue

                if to_key not in old_id_to_temp_id:
                    if relation_failed < 5:
                        print(f"  ⚠️ 找不到to实体: {to_key}")
                    relation_failed += 1
                    continue

                temp_from_id = old_id_to_temp_id[from_key]
                temp_to_id = old_id_to_temp_id[to_key]

                # 获取实体信息
                from_entity = self.merged_entities_temp[
                    self.merged_entities_temp['temp_id'] == temp_from_id
                    ].iloc[0]

                to_entity = self.merged_entities_temp[
                    self.merged_entities_temp['temp_id'] == temp_to_id
                    ].iloc[0]

                # 🔧 修复：使用安全的整数转换方法处理 from_modified 和 to_modified
                from_modified = self.safe_int_convert(row.get('from_modified'), default=0)
                to_modified = self.safe_int_convert(row.get('to_modified'), default=0)

                # 保存关系及完整信息
                all_relations.append({
                    'temp_from_id': temp_from_id,
                    'temp_to_id': temp_to_id,
                    'type': str(row['type']),
                    'from_label': from_entity['Label'],
                    'from_entity': from_entity['Entity Text'],
                    'from_modified': from_modified,
                    'to_label': to_entity['Label'],
                    'to_entity': to_entity['Entity Text'],
                    'to_modified': to_modified
                })
                relation_success += 1

        print(f"\n关系处理结果:")
        print(f"  成功: {relation_success}")
        print(f"  失败: {relation_failed}")
        if relation_success + relation_failed > 0:
            print(f"  成功率: {relation_success / (relation_success + relation_failed) * 100:.2f}%")

        if not all_relations:
            print("\n⚠️ 警告：没有成功处理任何关系")
            self.merged_relations_temp = pd.DataFrame(columns=[
                'temp_from_id', 'temp_to_id', 'type',
                'from_label', 'from_entity', 'from_modified',
                'to_label', 'to_entity', 'to_modified'
            ])
        else:
            self.merged_relations_temp = pd.DataFrame(all_relations)

        print(f"\n第一步完成！")
        print(f"  临时实体数: {len(self.merged_entities_temp)}")
        print(f"  临时关系数: {len(self.merged_relations_temp)}")

        return True

    def step2_deduplicate_entities_and_update_relations(self):
        """
        第二步：实体去重，建立完整映射，更新关系ID
        """
        print("\n" + "=" * 80)
        print("第二步：实体去重，建立完整映射，更新关系ID")
        print("=" * 80)

        print(f"\n去重前实体数: {len(self.merged_entities_temp)}")

        # 创建实体的唯一key（基于Label和Entity Text）
        self.merged_entities_temp['entity_key'] = (
                self.merged_entities_temp['Label'].astype(str) + '|||' +
                self.merged_entities_temp['Entity Text'].astype(str)
        )

        # 记录每个实体key首次出现的临时ID
        entity_key_to_first_temp_id = {}

        for idx, row in self.merged_entities_temp.iterrows():
            entity_key = row['entity_key']
            temp_id = row['temp_id']

            if entity_key not in entity_key_to_first_temp_id:
                entity_key_to_first_temp_id[entity_key] = temp_id

        # 去重实体
        deduplicated_entities = self.merged_entities_temp.drop_duplicates(
            subset=['entity_key'], keep='first'
        )

        # 重新分配最终ID
        deduplicated_entities = deduplicated_entities.reset_index(drop=True)
        deduplicated_entities['final_id'] = range(1, len(deduplicated_entities) + 1)

        # 建立临时ID到最终ID的映射
        for idx, row in deduplicated_entities.iterrows():
            temp_id = row['temp_id']
            final_id = row['final_id']
            self.temp_id_to_final_id[temp_id] = final_id

        # 为相同entity_key的所有临时ID建立到同一个最终ID的映射
        for idx, row in self.merged_entities_temp.iterrows():
            temp_id = row['temp_id']
            entity_key = row['entity_key']

            if temp_id not in self.temp_id_to_final_id:
                # 找到这个entity_key对应的首次出现的临时ID
                first_temp_id = entity_key_to_first_temp_id[entity_key]
                # 使用首次出现的临时ID对应的最终ID
                self.temp_id_to_final_id[temp_id] = self.temp_id_to_final_id[first_temp_id]

        # 准备输出的最终实体表
        self.final_entities = deduplicated_entities[['final_id', 'Label', 'Entity Text']].copy()
        self.final_entities.columns = ['ID', 'Label', 'Entity Text']

        print(f"去重后实体数: {len(self.final_entities)}")
        print(f"去除重复: {len(self.merged_entities_temp) - len(self.final_entities)}")

        # --- 更新关系中的ID ---
        print("\n--- 更新关系ID ---")
        print(f"待更新关系数: {len(self.merged_relations_temp)}")

        if len(self.merged_relations_temp) == 0:
            print(f"没有关系需要更新")
            return

        updated_relations = []
        update_success = 0
        update_failed = 0

        for idx, row in self.merged_relations_temp.iterrows():
            temp_from_id = row['temp_from_id']
            temp_to_id = row['temp_to_id']

            # 通过临时ID找到最终ID
            if temp_from_id not in self.temp_id_to_final_id:
                if update_failed < 5:
                    print(f"  ⚠️ 找不到from的映射: temp_id={temp_from_id}")
                update_failed += 1
                continue

            if temp_to_id not in self.temp_id_to_final_id:
                if update_failed < 5:
                    print(f"  ⚠️ 找不到to的映射: temp_id={temp_to_id}")
                update_failed += 1
                continue

            final_from_id = self.temp_id_to_final_id[temp_from_id]
            final_to_id = self.temp_id_to_final_id[temp_to_id]

            updated_relations.append({
                'from_id': final_from_id,
                'to_id': final_to_id,
                'type': row['type'],
                'from_label': row['from_label'],
                'from_entity': row['from_entity'],
                'from_modified': row['from_modified'],
                'to_label': row['to_label'],
                'to_entity': row['to_entity'],
                'to_modified': row['to_modified']
            })
            update_success += 1

        print(f"\n关系ID更新结果:")
        print(f"  成功: {update_success}")
        print(f"  失败: {update_failed}")
        if update_success + update_failed > 0:
            print(f"  成功率: {update_success / (update_success + update_failed) * 100:.2f}%")

        self.merged_relations_temp = pd.DataFrame(updated_relations)

        print(f"\n第二步完成！")
        print(f"  最终实体数: {len(self.final_entities)}")
        print(f"  更新后关系数: {len(self.merged_relations_temp)}")

    def step3_deduplicate_relations(self):
        """
        第三步：关系去重
        """
        print("\n" + "=" * 80)
        print("第三步：关系去重")
        print("=" * 80)

        if len(self.merged_relations_temp) == 0:
            print(f"\n没有关系需要去重")
            self.final_relations = pd.DataFrame(columns=[
                'id', 'from_id', 'to_id', 'type',
                'from_label', 'from_entity', 'from_modified',
                'to_label', 'to_entity', 'to_modified'
            ])
            print(f"\n第三步完成！")
            return

        print(f"\n去重前关系数: {len(self.merged_relations_temp)}")

        # 创建关系的唯一key（包含所有重要信息）
        self.merged_relations_temp['relation_key'] = (
                self.merged_relations_temp['from_id'].astype(str) + '|||' +
                self.merged_relations_temp['to_id'].astype(str) + '|||' +
                self.merged_relations_temp['type'].astype(str) + '|||' +
                self.merged_relations_temp['from_label'].astype(str) + '|||' +
                self.merged_relations_temp['from_entity'].astype(str) + '|||' +
                self.merged_relations_temp['to_label'].astype(str) + '|||' +
                self.merged_relations_temp['to_entity'].astype(str)
        )

        # 去重
        deduplicated_relations = self.merged_relations_temp.drop_duplicates(
            subset=['relation_key'], keep='first'
        )

        # 重新分配ID
        deduplicated_relations = deduplicated_relations.reset_index(drop=True)
        deduplicated_relations['id'] = range(1, len(deduplicated_relations) + 1)

        # 选择最终输出的列
        self.final_relations = deduplicated_relations[[
            'id', 'from_id', 'to_id', 'type',
            'from_label', 'from_entity', 'from_modified',
            'to_label', 'to_entity', 'to_modified'
        ]].copy()

        print(f"去重后关系数: {len(self.final_relations)}")
        print(f"去除重复: {len(self.merged_relations_temp) - len(self.final_relations)}")

        print(f"\n第三步完成！")

    def save_results(self):
        """保存结果"""
        import time

        output_folder = self.data_folder

        # 保存实体文件
        entities_output = output_folder / "final_merged_entities.csv"

        if entities_output.exists():
            try:
                entities_output.unlink()
            except:
                pass

        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.final_entities.to_csv(
                    entities_output, sep=',', index=False, encoding='utf-8-sig'
                )
                print(f"\n✓ 实体文件已保存: {entities_output}")
                print(f"  列数: {len(self.final_entities.columns)}")
                print(f"  行数: {len(self.final_entities)}")
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    print(f"  文件被占用，2秒后重试...")
                    time.sleep(2)
                else:
                    print(f"  ❌ 无法保存，请关闭Excel")
                    raise

        # 保存关系文件
        relations_output = output_folder / "final_merged_relations.csv"

        if relations_output.exists():
            try:
                relations_output.unlink()
            except:
                pass

        for attempt in range(max_retries):
            try:
                self.final_relations.to_csv(
                    relations_output, sep=',', index=False, encoding='utf-8-sig'
                )
                print(f"✓ 关系文件已保存: {relations_output}")
                print(f"  列数: {len(self.final_relations.columns)}")
                print(f"  行数: {len(self.final_relations)}")
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    print(f"  文件被占用，2秒后重试...")
                    time.sleep(2)
                else:
                    print(f"  ❌ 无法保存，请关闭Excel")
                    raise

        # 打印最终统计
        print("\n" + "=" * 80)
        print("最终统计")
        print("=" * 80)
        print(f"实体总数: {len(self.final_entities)}")
        print(f"关系总数: {len(self.final_relations)}")

        if len(self.final_entities) > 0:
            print(f"\n实体示例（前3行）:")
            print(self.final_entities.head(3).to_string(index=False))

        if len(self.final_relations) > 0:
            print(f"\n关系示例（前3行）:")
            print(self.final_relations.head(3).to_string(index=False))

    def run(self):
        """执行完整的三步处理"""
        print("=" * 80)
        print("合并已处理的merged文件 - 三步法")
        print("=" * 80)
        print("\n处理流程:")
        print("  第一步: 合并实体和关系（不去重），建立完整关系信息")
        print("  第二步: 实体去重，建立完整映射，更新关系ID")
        print("  第三步: 关系去重")

        # 查找文件
        entity_files, relation_files = self.find_files()

        if not entity_files:
            print("\n❌ 错误：没有找到任何merged_entities文件")
            return

        if not relation_files:
            print("\n⚠️ 警告：没有找到任何merged_relations文件")

        # 第一步
        success = self.step1_merge_without_dedup(entity_files, relation_files)
        if not success:
            return

        # 第二步
        self.step2_deduplicate_entities_and_update_relations()

        # 第三步
        self.step3_deduplicate_relations()

        # 保存结果
        self.save_results()

        print("\n" + "=" * 80)
        print("处理完成！")
        print("=" * 80)
        print("\n输出文件:")
        print(f"  - final_merged_entities.csv")
        print(f"  - final_merged_relations.csv")


def main():
    """主函数"""
    import sys

    data_folder = sys.argv[1] if len(sys.argv) > 1 else "data"

    if not os.path.exists(data_folder):
        print(f"错误: 找不到文件夹 '{data_folder}'")
        print(f"用法: python merge_merged_files.py <data_folder_path>")
        return

    merger = MergedFilesMerger(data_folder)
    merger.run()


if __name__ == "__main__":
    main()