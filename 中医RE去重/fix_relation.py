
import pandas as pd

# 关系映射表：(from_label, to_label) -> type
relation_mapping = {
    # 治疗关系 (Treat)
    ('MED', 'DIS'): 'Treat',
    ('MED', 'SYN'): 'Treat',
    ('MED', 'SIG'): 'Treat',
    ('MED', 'SYM'): 'Treat',
    ('PRE', 'DIS'): 'Treat',
    ('PRE', 'SYN'): 'Treat',
    ('PRE', 'SIG'): 'Treat',
    ('PRE', 'SYM'): 'Treat',
    ('ACU', 'DIS'): 'Treat',
    ('ACU', 'SYN'): 'Treat',
    ('ACU', 'SIG'): 'Treat',
    ('ACU', 'SYM'): 'Treat',

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
    ('MER', 'VIS'): 'manifest',

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
    ('TNG', 'PRE'): 'guide_med',

    # 穴位关系 (acupoint)
    ('TNG', 'ACU'): 'acupoint',

    # 映射到关系 (mapped_to)
    ('TNG', 'BDP'): 'mapped_to',
    #
    # # 宜食关系 (food_to_eat)
    # ('TNG', 'FOO'): 'food_to_eat',
}


def fix_relation_type(from_label, to_label, old_type):
    """根据头尾实体标签确定正确的关系类型"""
    # 当头尾实体标签一致时，关系为 "oname"
    if from_label == to_label:
        return 'oname'

    # 查找关系映射表，如果找不到则保留原值
    return relation_mapping.get((from_label, to_label), old_type)


def process_csv(input_file, output_file):
    """读取CSV文件，修正关系类型，并保存"""
    # 读取CSV文件
    df = pd.read_csv(input_file, encoding='utf-8')

    # 统计信息
    total_rows = len(df)
    changed_count = 0
    oname_count = 0
    kept_count = 0

    # 遍历每一行，修正type字段
    for idx, row in df.iterrows():
        from_label = row['from_label']
        to_label = row['to_label']
        old_type = row['type']

        # 获取正确的关系类型
        new_type = fix_relation_type(from_label, to_label, old_type)

        if new_type == 'oname':
            oname_count += 1

        if new_type != old_type:
            df.at[idx, 'type'] = new_type
            changed_count += 1
        else:
            kept_count += 1

    # 保存修正后的CSV文件
    df.to_csv(output_file, index=False, encoding='utf-8-sig')

    # 输出统计信息
    print(f"处理完成！")
    print(f"总记录数: {total_rows}")
    print(f"修改的记录数: {changed_count}")
    print(f"保持原值的记录数: {kept_count}")
    print(f"其中相同标签(oname)记录数: {oname_count}")
    print(f"结果已保存到: {output_file}")


if __name__ == '__main__':
    input_file = 'data/final_merged_relations.csv'
    output_file = 'final_merged_relations_fixed.csv'
    process_csv(input_file, output_file)
