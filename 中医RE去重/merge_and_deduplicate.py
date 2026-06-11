#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据合并与去重脚本 v2.0
用于合并多个文件夹中的entities和relations CSV文件，并进行去重处理
增强版：自动检测列名、处理各种格式问题
"""

import os
import pandas as pd
from pathlib import Path
from typing import Dict, Tuple, Set


class DataMerger:
    def __init__(self, data_folder: str):
        self.data_folder = Path(data_folder)
        self.all_entities = []
        self.all_relations = []
        self.entity_mapping = {}  # 旧ID到新ID的映射 {(folder_name, old_id): new_id}

    def scan_folders(self):
        """扫描data文件夹下的所有子文件夹"""
        folders = []
        for item in self.data_folder.iterdir():
            if item.is_dir():
                folders.append(item)
        print(f"找到 {len(folders)} 个文件夹")
        return folders

    def normalize_column_names(self, df: pd.DataFrame, file_type: str) -> pd.DataFrame:
        """标准化列名，处理空格、大小写等问题"""
        # 去除列名前后的空格
        df.columns = df.columns.str.strip()

        if file_type == 'entities':
            # 创建列名映射
            column_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                if 'label' in col_lower:
                    column_mapping[col] = 'Label'
                elif 'entity' in col_lower and 'text' in col_lower:
                    column_mapping[col] = 'Entity Text'
                elif col_lower == 'id' or col_lower == 'ID':
                    column_mapping[col] = 'ID'

            # 如果找不到匹配的列，尝试按位置匹配
            if len(column_mapping) < 3:
                cols = df.columns.tolist()
                if len(cols) >= 3:
                    print(f"  警告：使用列位置匹配。原始列名: {cols}")
                    df.columns = ['Label', 'Entity Text', 'ID'] + cols[3:]
                else:
                    print(f"  错误：列数不足。实际列: {cols}")
                    return None
            else:
                df = df.rename(columns=column_mapping)

        elif file_type == 'relations':
            # 创建列名映射
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

            # 如果找不到匹配的列，尝试按位置匹配
            if len(column_mapping) < 4:
                cols = df.columns.tolist()
                if len(cols) >= 4:
                    print(f"  警告：使用列位置匹配。原始列名: {cols}")
                    df.columns = ['id', 'from_id', 'to_id', 'type'] + cols[4:]
                else:
                    print(f"  错误：列数不足。实际列: {cols}")
                    return None
            else:
                df = df.rename(columns=column_mapping)

        return df

    def read_entities_from_folder(self, folder: Path):
        """从指定文件夹读取entities文件"""
        # 查找entities_*.csv文件
        entity_files = list(folder.glob("entities_*.csv"))

        if not entity_files:
            print(f"警告: {folder.name} 文件夹中没有找到entities文件")
            return None

        entity_file = entity_files[0]
        print(f"读取: {entity_file}")

        try:
            # 尝试不同的分隔符
            separators = ['\t', ',', '|', ';']
            df = None

            for sep in separators:
                try:
                    df = pd.read_csv(entity_file, sep=sep, encoding='utf-8')
                    if len(df.columns) >= 3:  # 至少需要3列
                        print(f"  使用分隔符: {repr(sep)}")
                        break
                except:
                    continue

            if df is None or len(df.columns) < 3:
                print(f"  错误：无法正确解析文件")
                return None

            # 打印原始列名以便调试
            print(f"  原始列名: {df.columns.tolist()}")

            # 标准化列名
            df = self.normalize_column_names(df, 'entities')

            if df is None:
                return None

            # 验证必需的列是否存在
            required_cols = ['Label', 'Entity Text', 'ID']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"  错误：缺少必需的列: {missing_cols}")
                print(f"  当前列名: {df.columns.tolist()}")
                return None

            df['source_folder'] = folder.name  # 记录来源文件夹
            print(f"  成功读取 {len(df)} 条实体记录")
            return df

        except Exception as e:
            print(f"读取 {entity_file} 时出错: {e}")
            import traceback
            traceback.print_exc()
            return None

    def read_relations_from_folder(self, folder: Path):
        """从指定文件夹读取relations文件"""
        # 查找relations_*.csv文件
        relation_files = list(folder.glob("relations_*.csv"))

        if not relation_files:
            print(f"警告: {folder.name} 文件夹中没有找到relations文件")
            return None

        relation_file = relation_files[0]
        print(f"读取: {relation_file}")

        try:
            # 尝试不同的分隔符
            separators = ['\t', ',', '|', ';']
            df = None

            for sep in separators:
                try:
                    df = pd.read_csv(relation_file, sep=sep, encoding='utf-8')
                    if len(df.columns) >= 4:  # 至少需要4列
                        print(f"  使用分隔符: {repr(sep)}")
                        break
                except:
                    continue

            if df is None or len(df.columns) < 4:
                print(f"  错误：无法正确解析文件")
                return None

            # 打印原始列名以便调试
            print(f"  原始列名: {df.columns.tolist()}")

            # 标准化列名
            df = self.normalize_column_names(df, 'relations')

            if df is None:
                return None

            # 验证必需的列是否存在
            required_cols = ['id', 'from_id', 'to_id', 'type']
            missing_cols = [col for col in required_cols if col not in df.columns]
            if missing_cols:
                print(f"  错误：缺少必需的列: {missing_cols}")
                print(f"  当前列名: {df.columns.tolist()}")
                return None

            df['source_folder'] = folder.name  # 记录来源文件夹
            print(f"  成功读取 {len(df)} 条关系记录")
            return df

        except Exception as e:
            print(f"读取 {relation_file} 时出错: {e}")
            import traceback
            traceback.print_exc()
            return None

    def load_all_data(self):
        """加载所有文件夹的数据"""
        folders = self.scan_folders()

        print("\n=== 读取实体数据 ===")
        for folder in folders:
            entities_df = self.read_entities_from_folder(folder)
            if entities_df is not None:
                self.all_entities.append(entities_df)

        print("\n=== 读取关系数据 ===")
        for folder in folders:
            relations_df = self.read_relations_from_folder(folder)
            if relations_df is not None:
                self.all_relations.append(relations_df)

        print(f"\n成功读取 {len(self.all_entities)} 个实体文件")
        print(f"成功读取 {len(self.all_relations)} 个关系文件")

    def merge_and_deduplicate_entities(self) -> pd.DataFrame:
        """合并并去重实体"""
        print("\n=== 合并并去重实体 ===")

        # 合并所有实体数据
        merged_entities = pd.concat(self.all_entities, ignore_index=True)
        print(f"合并前总实体数: {len(merged_entities)}")

        # 确保ID列是整数类型
        merged_entities['ID'] = pd.to_numeric(merged_entities['ID'], errors='coerce').astype('Int64')

        # 去重：基于Label和Entity Text的组合
        # 保留第一次出现的实体
        merged_entities['entity_key'] = merged_entities['Label'].astype(str) + '|||' + merged_entities[
            'Entity Text'].astype(str)

        # 在去重前，先建立旧ID到实体key的映射
        for idx, row in merged_entities.iterrows():
            old_key = (row['source_folder'], row['ID'])
            entity_key = row['entity_key']
            if old_key not in self.entity_mapping:
                self.entity_mapping[old_key] = entity_key

        # 去重
        deduplicated_entities = merged_entities.drop_duplicates(subset=['entity_key'], keep='first')
        print(f"去重后实体数: {len(deduplicated_entities)}")
        print(f"去除重复实体数: {len(merged_entities) - len(deduplicated_entities)}")

        # 重新分配ID
        deduplicated_entities = deduplicated_entities.reset_index(drop=True)
        deduplicated_entities['new_ID'] = range(1, len(deduplicated_entities) + 1)

        # 创建entity_key到新ID的映射
        entity_key_to_new_id = dict(zip(deduplicated_entities['entity_key'], deduplicated_entities['new_ID']))

        # 更新entity_mapping: 旧ID -> 新ID
        for old_key, entity_key in self.entity_mapping.items():
            self.entity_mapping[old_key] = entity_key_to_new_id[entity_key]

        # 准备最终的实体DataFrame
        final_entities = deduplicated_entities[['Label', 'Entity Text', 'new_ID']].copy()
        final_entities.columns = ['Label', 'Entity Text', 'ID']

        return final_entities

    def merge_and_deduplicate_relations(self, merged_entities: pd.DataFrame) -> pd.DataFrame:
        """合并并去重关系，更新ID映射"""
        print("\n=== 合并并去重关系 ===")

        # 合并所有关系数据
        merged_relations = pd.concat(self.all_relations, ignore_index=True)
        print(f"合并前总关系数: {len(merged_relations)}")

        # 确保ID列是整数类型
        merged_relations['from_id'] = pd.to_numeric(merged_relations['from_id'], errors='coerce').astype('Int64')
        merged_relations['to_id'] = pd.to_numeric(merged_relations['to_id'], errors='coerce').astype('Int64')

        # 更新from_id和to_id为新的ID
        updated_relations = []
        skipped_count = 0

        for idx, row in merged_relations.iterrows():
            source_folder = row['source_folder']
            old_from_id = row['from_id']
            old_to_id = row['to_id']

            # 跳过无效的ID
            if pd.isna(old_from_id) or pd.isna(old_to_id):
                skipped_count += 1
                continue

            # 查找新的ID
            from_key = (source_folder, old_from_id)
            to_key = (source_folder, old_to_id)

            if from_key in self.entity_mapping and to_key in self.entity_mapping:
                new_from_id = self.entity_mapping[from_key]
                new_to_id = self.entity_mapping[to_key]

                updated_relations.append({
                    'from_id': new_from_id,
                    'to_id': new_to_id,
                    'type': row['type']
                })
            else:
                skipped_count += 1
                if skipped_count <= 10:  # 只打印前10个跳过的关系
                    print(f"警告: 跳过关系 (from_id={old_from_id}, to_id={old_to_id})，找不到对应的实体")

        if skipped_count > 0:
            print(f"总共跳过 {skipped_count} 个无效关系")

        # 创建新的关系DataFrame
        relations_df = pd.DataFrame(updated_relations)

        # 去重：基于from_id, to_id和type的组合
        if len(relations_df) > 0:
            relations_df['relation_key'] = (
                    relations_df['from_id'].astype(str) + '|||' +
                    relations_df['to_id'].astype(str) + '|||' +
                    relations_df['type'].astype(str)
            )

            deduplicated_relations = relations_df.drop_duplicates(subset=['relation_key'], keep='first')
            print(f"去重后关系数: {len(deduplicated_relations)}")
            print(f"去除重复关系数: {len(relations_df) - len(deduplicated_relations)}")

            # 重新分配关系ID
            deduplicated_relations = deduplicated_relations.reset_index(drop=True)
            deduplicated_relations['id'] = range(1, len(deduplicated_relations) + 1)

            # 准备最终的关系DataFrame
            final_relations = deduplicated_relations[['id', 'from_id', 'to_id', 'type']].copy()
        else:
            print("警告: 没有有效的关系数据")
            final_relations = pd.DataFrame(columns=['id', 'from_id', 'to_id', 'type'])

        return final_relations

    def save_results(self, entities_df: pd.DataFrame, relations_df: pd.DataFrame, output_folder: str = None):
        """保存合并后的结果"""
        if output_folder is None:
            output_folder = self.data_folder
        else:
            output_folder = Path(output_folder)
            output_folder.mkdir(parents=True, exist_ok=True)

        # 保存实体文件
        entities_output = output_folder / "merged_entities.csv"
        entities_df.to_csv(entities_output, sep='\t', index=False, encoding='utf-8')
        print(f"\n实体文件已保存到: {entities_output}")

        # 保存关系文件
        relations_output = output_folder / "merged_relations.csv"
        relations_df.to_csv(relations_output, sep='\t', index=False, encoding='utf-8')
        print(f"关系文件已保存到: {relations_output}")

        # 打印统计信息
        print("\n=== 最终统计 ===")
        print(f"合并后实体总数: {len(entities_df)}")
        print(f"合并后关系总数: {len(relations_df)}")

        # 显示实体标签分布
        if len(entities_df) > 0:
            print("\n实体标签分布:")
            label_counts = entities_df['Label'].value_counts()
            for label, count in label_counts.head(10).items():
                print(f"  {label}: {count}")
            if len(label_counts) > 10:
                print(f"  ... 还有 {len(label_counts) - 10} 个标签")

        # 显示关系类型分布
        if len(relations_df) > 0:
            print("\n关系类型分布:")
            type_counts = relations_df['type'].value_counts()
            for rel_type, count in type_counts.head(10).items():
                print(f"  {rel_type}: {count}")
            if len(type_counts) > 10:
                print(f"  ... 还有 {len(type_counts) - 10} 个类型")

    def run(self, output_folder: str = None):
        """执行完整的合并和去重流程"""
        print("开始数据合并和去重处理...\n")

        # 1. 加载所有数据
        self.load_all_data()

        if not self.all_entities:
            print("错误: 没有找到任何实体数据")
            return

        # 2. 合并并去重实体
        merged_entities = self.merge_and_deduplicate_entities()

        # 3. 合并并去重关系
        merged_relations = self.merge_and_deduplicate_relations(merged_entities)

        # 4. 保存结果
        self.save_results(merged_entities, merged_relations, output_folder)

        print("\n处理完成！")


def main():
    """主函数"""
    import sys

    # 设置data文件夹路径
    if len(sys.argv) > 1:
        data_folder = sys.argv[1]
    else:
        # 默认路径（根据图片中的结构）
        data_folder = "data"

    # 检查文件夹是否存在
    if not os.path.exists(data_folder):
        print(f"错误: 找不到文件夹 '{data_folder}'")
        print(f"请确保文件夹路径正确，或者在命令行中指定路径:")
        print(f"python merge_and_deduplicate_v2.py <data_folder_path>")
        return

    # 创建处理器并运行
    merger = DataMerger(data_folder)

    # 输出到data文件夹（如果需要输出到其他位置，可以修改这里）
    merger.run(output_folder=data_folder)


if __name__ == "__main__":
    main()