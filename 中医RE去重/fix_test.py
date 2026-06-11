import pandas as pd
import numpy as np

# 关系映射表：(from_label, to_label) -> type
relation_mapping = {
    # 治疗关系 (Treat)
    ('MED', 'DIS'): 'treat',
    ('MED', 'SYN'): 'treat',
    ('MED', 'SIG'): 'treat',
    ('MED', 'SYM'): 'treat',
    ('PRE', 'DIS'): 'treat',
    ('PRE', 'SYN'): 'treat',
    ('PRE', 'SIG'): 'treat',
    ('PRE', 'SYM'): 'treat',
    ('ACU', 'DIS'): 'treat',
    ('ACU', 'SYN'): 'treat',
    ('ACU', 'SIG'): 'treat',
    ('ACU', 'SYM'): 'treat',

    # 组成关系 (comp)
    ('MED', 'PRE'): 'comp',

    # 出自关系 (from)
    ('MED', 'LIT'): 'from',
    ('PRE', 'LIT'): 'from',
    ('ACU', 'LIT'): 'from',
    ('DIS', 'LIT'): 'from',
    ('TNG', 'LIT'): 'from',

    # 归属于关系 (belongto)
    ('ACU', 'MER'): 'belongto',

    # 相关关系 (related)
    ('MER', 'DIS'): 'related',
    ('DIS', 'MER'): 'related',
    ('TNG', 'MER'): 'related',

    # 脉诊关系 (pulse_diagnosis)
    ('DIS', 'MER'): 'pulse_diagnosis',

    # 视诊关系 (visual_diagnosis)
    ('DIS', 'BDP'): 'visual_diagnosis',

    # 互为表里关系 (manifest)
    ('MER', 'VIS'): 'inandex',

    # 表现关系 (perf)
    ('DIS', 'SYM'): 'perf',
    ('DIS', 'SIG'): 'perf',
    ('DIS', 'SYN'): 'perf',
    ('TNG', 'SYM'): 'perf',
    ('TNG', 'SIG'): 'perf',

    # 原因关系 (cause)
    ('DIS', 'BEC'): 'cause',

    # 反映关系 (reflect)
    ('TNG', 'BEC'): 'reflect',

    # 辅助诊断关系 (assist_diag)
    ('TNG', 'DIS'): 'assist_diag',

    # 指导用药关系 (guide_med)
    ('TNG', 'MED'): 'guide_med',
    ('TNG', 'PRE'): 'guide_pre',

    # 穴位关系 (acupoint)
    ('TNG', 'ACU'): 'acupoints',

    # 映射到关系 (mapped_to)
    ('TNG', 'BDP'): 'mapped_part',

#     # 宜食关系 (food_to_eat)
#     ('TNG', 'FOO'): 'food_to_eat',
}


def fix_relation_type(from_label, to_label, old_type):
    """根据头尾实体标签确定正确的关系类型"""
    # 处理空值情况
    if pd.isna(from_label) or pd.isna(to_label):
        return old_type

    # 转换为字符串并去除空格
    from_label = str(from_label).strip()
    to_label = str(to_label).strip()

    # 当头尾实体标签一致时，关系为 "oname"
    if from_label == to_label:
        return 'oname'

    # 查找关系映射表，如果找不到则保留原值
    return relation_mapping.get((from_label, to_label), old_type)


def process_csv(input_file, output_file):
    """读取CSV文件，修正关系类型，并保存"""
    print("=" * 60)
    print("开始处理CSV文件...")
    print("=" * 60)

    # 读取CSV文件 - 先尝试utf-8，如果失败则尝试其他编码
    try:
        df = pd.read_csv(input_file, encoding='utf-8')
        print(f"✓ 使用UTF-8编码成功读取文件")
    except:
        try:
            df = pd.read_csv(input_file, encoding='gbk')
            print(f"✓ 使用GBK编码成功读取文件")
        except:
            df = pd.read_csv(input_file, encoding='latin1')
            print(f"✓ 使用Latin1编码成功读取文件")

    original_rows = len(df)
    print(f"原始数据行数: {original_rows}")

    # 检查关键列是否存在
    required_columns = ['from_label', 'to_label', 'type']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"❌ 错误：缺少必需的列: {missing_columns}")
        print(f"文件中的列: {df.columns.tolist()}")
        return

    # 检查空值情况
    print("\n" + "=" * 60)
    print("数据质量检查:")
    print("=" * 60)
    print(f"from_label 空值数量: {df['from_label'].isna().sum()}")
    print(f"to_label 空值数量: {df['to_label'].isna().sum()}")
    print(f"type 空值数量: {df['type'].isna().sum()}")

    # 显示原始type的分布
    print("\n原始type字段分布:")
    print(df['type'].value_counts().head(10))

    # 创建副本进行修改
    df_modified = df.copy()

    # 统计信息
    changed_count = 0
    oname_count = 0
    kept_count = 0

    # 遍历每一行，修正type字段
    for idx, row in df_modified.iterrows():
        from_label = row['from_label']
        to_label = row['to_label']
        old_type = row['type']

        # 获取正确的关系类型
        new_type = fix_relation_type(from_label, to_label, old_type)

        if new_type == 'oname' and old_type != 'oname':
            oname_count += 1

        if new_type != old_type:
            df_modified.at[idx, 'type'] = new_type
            changed_count += 1
        else:
            kept_count += 1

    # 验证数据行数是否一致
    modified_rows = len(df_modified)
    print("\n" + "=" * 60)
    print("数据修改统计:")
    print("=" * 60)
    print(f"修改前行数: {original_rows}")
    print(f"修改后行数: {modified_rows}")
    print(f"修改的记录数: {changed_count}")
    print(f"保持原值的记录数: {kept_count}")
    print(f"其中修改为oname的记录数: {oname_count}")

    if original_rows != modified_rows:
        print(f"⚠️  警告：数据行数发生变化！差异: {original_rows - modified_rows}")
    else:
        print("✓ 数据行数一致，没有数据丢失")

    # 显示修改后type的分布
    print("\n修改后type字段分布:")
    print(df_modified['type'].value_counts().head(10))

    # 检查是否有重复的关系
    print("\n" + "=" * 60)
    print("重复数据检查:")
    print("=" * 60)
    duplicate_count = df_modified.duplicated(subset=['from_id', 'to_id', 'type']).sum()
    print(f"重复的关系数量: {duplicate_count}")
    if duplicate_count > 0:
        print("⚠️  警告：存在重复关系，图谱导入时可能会自动去重")

    # 检查type字段的唯一值
    unique_types = df_modified['type'].unique()
    print(f"\n修改后type字段的唯一值数量: {len(unique_types)}")
    print("所有type值:")
    for t in sorted(unique_types):
        print(f"  - {t}")

    # 保存修正后的CSV文件 - 保持原始编码格式
    df_modified.to_csv(output_file, index=False, encoding='utf-8-sig')

    print("\n" + "=" * 60)
    print(f"✓ 结果已保存到: {output_file}")
    print("=" * 60)

    # 验证保存的文件
    print("\n验证保存的文件...")
    df_verify = pd.read_csv(output_file, encoding='utf-8-sig')
    verify_rows = len(df_verify)
    print(f"保存文件的行数: {verify_rows}")

    if verify_rows != original_rows:
        print(f"❌ 错误：保存后文件行数不一致！差异: {original_rows - verify_rows}")
    else:
        print("✓ 文件保存成功，行数一致")


if __name__ == '__main__':
    input_file = 'data/final_merged_relations.csv'
    output_file = 'final_merged_relations_fixed1.csv'
    process_csv(input_file, output_file)