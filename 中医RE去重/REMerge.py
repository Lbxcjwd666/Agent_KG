#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据合并与去重脚本 - 正确的三步法
核心思路：先合并建立关系，再去重建立完整映射，最后关系去重
"""

import os
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple
from collections import defaultdict
import warnings

warnings.filterwarnings('ignore')


class DataMergerCorrect:
    def __init__(self, data_folder: str):
        self.data_folder = Path(data_folder)
        self.temp_id_counter = 1  # 临时ID计数器

        # 第一步的临时数据
        self.merged_entities_temp = None  # 合并但未去重的实体
        self.merged_relations_temp = None  # 包含完整信息的关系

        # 第二步的映射
        self.entity_text_to_final_id = {}  # (label, entity_text) -> 最终ID
        self.temp_id_to_final_id = {}  # 临时ID -> 最终ID

        # 最终结果
        self.final_entities = None
        self.final_relations = None

    def scan_folders(self):
        """扫描data文件夹下的所有子文件夹"""
        folders = []
        for item in self.data_folder.iterdir():
            if item.is_dir():
                folders.append(item)
        print(f"找到 {len(folders)} 个文件夹")
        return folders

    def normalize_column_names(self, df: pd.DataFrame, file_type: str) -> pd.DataFrame:
        """标准化列名"""
        df.columns = df.columns.str.strip()

        if file_type == 'entities':
            column_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                if 'label' in col_lower:
                    column_mapping[col] = 'Label'
                elif 'entity' in col_lower and 'text' in col_lower:
                    column_mapping[col] = 'Entity Text'
                elif col_lower in ['id', 'ID']:
                    column_mapping[col] = 'ID'

            if len(column_mapping) >= 3:
                df = df.rename(columns=column_mapping)
            else:
                cols = df.columns.tolist()
                if len(cols) >= 3:
                    df.columns = ['Label', 'Entity Text', 'ID'] + cols[3:]

        elif file_type == 'relations':
            column_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                if col_lower == 'id':
                    column_mapping[col] = 'id'
                elif 'from' in col_lower and 'id' in col_lower:
                    column_mapping[col] = 'from_id'
                elif 'to' in col_lower and 'id' in col_lower:
                    column_mapping[col] = 'to_id'
                elif 'type' in col_lower:
                    column_mapping[col] = 'type'

            if len(column_mapping) >= 4:
                df = df.rename(columns=column_mapping)
            else:
                cols = df.columns.tolist()
                if len(cols) >= 4:
                    df.columns = ['id', 'from_id', 'to_id', 'type'] + cols[4:]

        return df

    def read_file(self, file_path: Path, file_type: str):
        """读取CSV文件"""
        try:
            separators = ['\t', ',', '|', ';']
            df = None

            for sep in separators:
                try:
                    df = pd.read_csv(file_path, sep=sep, encoding='utf-8')
                    if len(df.columns) >= (3 if file_type == 'entities' else 4):
                        break
                except:
                    continue

            if df is None:
                return None

            df = self.normalize_column_names(df, file_type)
            return df

        except Exception as e:
            print(f"读取 {file_path} 时出错: {e}")
            return None

    def step1_merge_without_dedup(self):
        """
        第一步：合并但不去重，建立完整的关系信息
        """
        print("\n" + "=" * 80)
        print("第一步：合并实体和关系（不去重），建立完整关系信息")
        print("=" * 80)

        folders = self.scan_folders()
        all_entities = []
        all_relations = []

        # 用于建立原始ID到临时ID的映射
        old_id_to_temp_id = {}  # (folder, old_id) -> temp_id

        # 读取并合并所有实体
        print("\n--- 处理实体 ---")
        for folder in folders:
            entity_file = list(folder.glob("entities_*.csv"))
            if not entity_file:
                continue

            entities_df = self.read_file(entity_file[0], 'entities')
            if entities_df is None:
                continue

            print(f"处理文件夹: {folder.name}")
            print(f"  原始实体数: {len(entities_df)}")

            # 为每个实体分配新的临时ID
            for idx, row in entities_df.iterrows():
                old_id = int(row['ID'])
                temp_id = self.temp_id_counter
                self.temp_id_counter += 1

                # 记录映射
                old_id_to_temp_id[(folder.name, old_id)] = temp_id

                # 保存实体信息
                all_entities.append({
                    'temp_id': temp_id,
                    'Label': str(row['Label']) if pd.notna(row['Label']) else '',
                    'Entity Text': str(row['Entity Text']) if pd.notna(row['Entity Text']) else '',
                    'original_folder': folder.name,
                    'original_id': old_id
                })

        print(f"\n合并后实体总数: {len(all_entities)}")
        self.merged_entities_temp = pd.DataFrame(all_entities)

        # 读取并处理所有关系
        print("\n--- 处理关系 ---")
        relation_success = 0
        relation_failed = 0

        for folder in folders:
            relation_file = list(folder.glob("relations_*.csv"))
            if not relation_file:
                continue

            relations_df = self.read_file(relation_file[0], 'relations')
            if relations_df is None:
                continue

            print(f"处理文件夹: {folder.name}")
            print(f"  原始关系数: {len(relations_df)}")

            for idx, row in relations_df.iterrows():
                old_from_id = int(row['from_id'])
                old_to_id = int(row['to_id'])

                from_key = (folder.name, old_from_id)
                to_key = (folder.name, old_to_id)

                # 检查是否能找到对应的实体
                if from_key not in old_id_to_temp_id:
                    print(f"  ⚠️ 找不到from实体: {from_key}")
                    relation_failed += 1
                    continue

                if to_key not in old_id_to_temp_id:
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

                # 保存关系及完整信息
                all_relations.append({
                    'temp_from_id': temp_from_id,
                    'temp_to_id': temp_to_id,
                    'type': str(row['type']),
                    'from_label': from_entity['Label'],
                    'from_entity': from_entity['Entity Text'],
                    'to_label': to_entity['Label'],
                    'to_entity': to_entity['Entity Text']
                })
                relation_success += 1

        print(f"\n关系处理结果:")
        print(f"  成功: {relation_success}")
        print(f"  失败: {relation_failed}")
        print(f"  成功率: {relation_success / (relation_success + relation_failed) * 100:.2f}%")

        self.merged_relations_temp = pd.DataFrame(all_relations)

        print(f"\n第一步完成！")
        print(f"  临时实体数: {len(self.merged_entities_temp)}")
        print(f"  临时关系数: {len(self.merged_relations_temp)}")

    def step2_deduplicate_entities_and_update_relations(self):
        """
        第二步：去重实体，建立完整映射，更新关系中的ID
        """
        print("\n" + "=" * 80)
        print("第二步：实体去重并更新关系ID")
        print("=" * 80)

        # 创建实体的唯一key
        def create_entity_key(row):
            label = str(row['Label']).strip()
            text = str(row['Entity Text']).strip()
            return f"{label}|||{text}"

        self.merged_entities_temp['entity_key'] = self.merged_entities_temp.apply(
            create_entity_key, axis=1
        )

        print(f"\n原始实体数: {len(self.merged_entities_temp)}")

        # 按entity_key分组，为每组分配一个最终ID
        final_id = 1
        entity_key_groups = self.merged_entities_temp.groupby('entity_key')

        print(f"唯一实体key数: {len(entity_key_groups)}")

        deduplicated_entities = []

        for entity_key, group in entity_key_groups:
            # 保留第一个作为代表
            first_row = group.iloc[0]

            deduplicated_entities.append({
                'ID': final_id,
                'Label': first_row['Label'],
                'Entity Text': first_row['Entity Text'],
                '是否修改': 1
            })

            # 为这组中的所有临时ID建立映射
            for temp_id in group['temp_id']:
                self.temp_id_to_final_id[temp_id] = final_id

            # 同时建立文本到最终ID的映射（用于第二步）
            self.entity_text_to_final_id[entity_key] = final_id

            final_id += 1

        self.final_entities = pd.DataFrame(deduplicated_entities)

        print(f"\n去重后实体数: {len(self.final_entities)}")
        print(f"去除重复: {len(self.merged_entities_temp) - len(self.final_entities)}")

        # 更新关系中的ID
        print(f"\n更新关系中的ID...")

        updated_relations = []
        update_success = 0
        update_failed = 0

        for idx, row in self.merged_relations_temp.iterrows():
            temp_from_id = row['temp_from_id']
            temp_to_id = row['temp_to_id']

            # 通过临时ID找到最终ID
            if temp_from_id not in self.temp_id_to_final_id:
                print(f"  ⚠️ 找不到from的映射: temp_id={temp_from_id}")
                update_failed += 1
                continue

            if temp_to_id not in self.temp_id_to_final_id:
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
                'from_modified': 0,
                'to_label': row['to_label'],
                'to_entity': row['to_entity'],
                'to_modified': 0
            })
            update_success += 1

        print(f"\n关系ID更新结果:")
        print(f"  成功: {update_success}")
        print(f"  失败: {update_failed}")
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

    def save_results(self, output_folder: str = None):
        """保存结果"""
        if output_folder is None:
            output_folder = self.data_folder
        else:
            output_folder = Path(output_folder)

        output_folder.mkdir(parents=True, exist_ok=True)

        import time

        # 保存实体文件
        entities_output = output_folder / "merged_entities.csv"

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
                break
            except PermissionError:
                if attempt < max_retries - 1:
                    print(f"  文件被占用，2秒后重试...")
                    time.sleep(2)
                else:
                    print(f"  ❌ 无法保存，请关闭Excel")
                    raise

        # 保存关系文件
        relations_output = output_folder / "merged_relations.csv"

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
        print("数据合并与去重 - 正确的三步法")
        print("=" * 80)
        print("\n处理流程:")
        print("  第一步: 合并实体和关系（不去重），建立完整关系信息")
        print("  第二步: 实体去重，建立完整映射，更新关系ID")
        print("  第三步: 关系去重")

        # 第一步
        self.step1_merge_without_dedup()

        # 第二步
        self.step2_deduplicate_entities_and_update_relations()

        # 第三步
        self.step3_deduplicate_relations()

        # 保存结果
        self.save_results()

        print("\n" + "=" * 80)
        print("处理完成！")
        print("=" * 80)


def main():
    """主函数"""
    import sys

    data_folder = sys.argv[1] if len(sys.argv) > 1 else "data1"

    if not os.path.exists(data_folder):
        print(f"错误: 找不到文件夹 '{data_folder}'")
        print(f"用法: python merge_correct.py <data_folder_path>")
        return

    merger = DataMergerCorrect(data_folder)
    merger.run()


if __name__ == "__main__":
    main()