# 数据合并与去重工具使用说明

## 功能说明

这个工具可以将多个文件夹中的 `entities_*.csv` 和 `relations_*.csv` 文件进行合并和去重处理。

## 文件格式要求

### entities 文件格式
```
Label	Entity Text	ID
MER	足太阳膀胱经	1
MER	足少阴肾经	2
```
- 使用制表符（Tab）分隔
- 必须包含三列：Label, Entity Text, ID

### relations 文件格式
```
id	from_id	to_id	type
1	3	4	from
2	3	5	from
```
- 使用制表符（Tab）分隔
- 必须包含四列：id, from_id, to_id, type
- from_id 和 to_id 对应同一文件夹中 entities 文件的 ID

## 使用方法

### 方法一：命令行运行

```bash
python merge_and_deduplicate.py <data文件夹路径>
```

例如：
```bash
python merge_and_deduplicate.py /path/to/data
```

### 方法二：默认路径运行

如果你的数据文件夹就叫 `data` 并且在脚本同一目录下：
```bash
python merge_and_deduplicate.py
```

## 输出结果

脚本会在指定的data文件夹中生成两个文件：

1. **merged_entities.csv** - 合并并去重后的实体文件
2. **merged_relations.csv** - 合并并去重后的关系文件，ID已更新

## 处理逻辑

### 实体去重规则
- 基于 `Label` 和 `Entity Text` 的组合进行去重
- 如果两个实体的Label和Entity Text完全相同，则视为重复
- 保留第一次出现的实体

### 关系处理
1. 读取所有文件夹的关系数据
2. 根据实体去重后的ID映射，更新关系中的 `from_id` 和 `to_id`
3. 基于 `from_id`, `to_id` 和 `type` 的组合进行去重
4. 如果关系中的实体在去重后被删除，该关系也会被跳过

### ID重新分配
- 实体ID从1开始连续分配
- 关系ID从1开始连续分配
- 所有关系的from_id和to_id都会正确指向新的实体ID

## 示例输出

```
开始数据合并和去重处理...

找到 9 个文件夹

=== 读取实体数据 ===
读取: data/074pjf/entities_pjf.csv
读取: data/103htsf/entities_htsf.csv
...

=== 读取关系数据 ===
读取: data/074pjf/relations_pjf.csv
读取: data/103htsf/relations_htsf.csv
...

成功读取 9 个实体文件
成功读取 9 个关系文件

=== 合并并去重实体 ===
合并前总实体数: 1500
去重后实体数: 1200
去除重复实体数: 300

=== 合并并去重关系 ===
合并前总关系数: 2000
去重后关系数: 1800
去除重复关系数: 200

实体文件已保存到: data/merged_entities.csv
关系文件已保存到: data/merged_relations.csv

=== 最终统计 ===
合并后实体总数: 1200
合并后关系总数: 1800

实体标签分布:
MER    800
ACU    400

关系类型分布:
from    1500
to      300

处理完成！
```

## 注意事项

1. 确保所有CSV文件使用制表符（Tab）作为分隔符
2. 文件编码建议使用UTF-8
3. 确保relations文件中的from_id和to_id在对应的entities文件中存在
4. 脚本会自动处理找不到对应实体的关系（跳过并提示警告）
5. 建议在处理前备份原始数据

## 依赖库

需要安装以下Python库：
```bash
pip install pandas
```

## 故障排除

### 问题1：找不到entities或relations文件
- 检查文件夹中是否包含 `entities_*.csv` 和 `relations_*.csv` 文件
- 确保文件名格式正确

### 问题2：编码错误
- 确保CSV文件使用UTF-8编码
- 如果使用其他编码，可以修改脚本中的 `encoding='utf-8'` 参数

### 问题3：分隔符错误
- 确保CSV文件使用制表符（Tab）分隔
- 如果使用逗号分隔，需要修改脚本中的 `sep='\t'` 为 `sep=','`

## 技术支持

如有问题，请检查：
1. Python版本（建议3.7+）
2. pandas库是否正确安装
3. 文件路径是否正确
4. CSV文件格式是否符合要求
