#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
中医知识图谱实体关系抽取系统 - 千问版本 (支持断点续传)

配置说明：
1. 在main()函数的配置区域设置您的千问API密钥
2. 调整其他参数（模型、文件路径、处理数量等）
3. 运行程序

获取千问API密钥: https://bailian.console.aliyun.com/
"""

import json
import csv
import re
import os
import time
import random
from typing import List, Dict, Any, Tuple
from openai import OpenAI
from dataclasses import dataclass


@dataclass
class Entity:
    text: str
    label: str
    start: int
    end: int
    id: int = 0


@dataclass
class Relation:
    head: str
    tail: str
    relation_type: str
    head_start: int = 0
    tail_start: int = 0
    id: int = 0


class TCMEntityRelationExtractor:
    def __init__(self, api_key: str = None, model: str = "qwen-plus"):
        # 初始化千问API客户端
        if api_key:
            qwen_api_key = api_key
        else:
            qwen_api_key = os.getenv('QWEN_API_KEY')

        if not qwen_api_key:
            raise ValueError("请提供千问API密钥或设置QWEN_API_KEY环境变量")

        self.client = OpenAI(
            api_key=qwen_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        self.model = model

        # 配置参数
        self.api_delay = 0.5
        self.output_dir = "./"

        # 实体类别定义
        self.entity_types = {
            'DIS': '疾病', 'SYM': '症状', 'SYN': '证候', 'SIG': '体征',
            'BEC': '病因病机', 'PRE': '方剂', 'MED': '中药材', 'ACU': '腧穴',
            'MER': '经脉', 'VIS': '脏腑', 'PUL': '脉象', 'BDP': '身体部位',
            'TNG': '舌象', 'CON': '体质', 'FOO': '食物', 'LIT': '文献'
        }

        # 关系类别定义
        self.relation_types = {
            'treat': '治疗', 'comp': '组成', 'from': '出自', 'belongto': '归属于',
            'related': '相关经脉', 'abpulse': '病脉表现', 'pulse_diagnosis': '脉诊',
            'inandex': '互为表里', 'perf': '表现', 'cause': '导致', 'oname': '别名',
            'reflect': '反映', 'assist_diag': '辅助诊断', 'guide_med': '指导用药',
            'guide_pre': '指导用药', 'acupoints': '治疗穴位', 'mapped_part': '映射部位',
            'food_to_eat': '宜吃', 'Food_to_avoid': '不宜吃'
        }

        self.entities = {}
        self.relations = []
        self.entity_id_counter = 1
        self.relation_id_counter = 1

        # 统计信息
        self.failed_segments = []
        self.success_count = 0
        self.fail_count = 0

        # 分批保存配置
        self.batch_size = 50
        self.last_processed_segment = 0

    def read_pujifang_file(self, file_path: str) -> str:
        """读取普济方文件"""
        try:
            encodings = ['gb2312', 'gbk', 'gb18030', 'utf-8', 'big5']
            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    print(f"✓ 成功使用 {encoding} 编码读取文件")
                    return content
                except UnicodeDecodeError:
                    continue

            with open(file_path, 'r', encoding='gb2312', errors='ignore') as f:
                content = f.read()
            print("✓ 使用错误忽略方式读取文件")
            return content

        except Exception as e:
            print(f"✗ 读取文件失败: {e}")
            return ""

    def split_text_into_segments(self, text: str, max_length: int = 800) -> List[str]:
        """将文本分割成适合处理的段落"""
        segments = []
        chapter_pattern = r'<目录>.*?<篇名>.*?</篇名>'
        chapters = re.split(chapter_pattern, text)

        for i, chapter in enumerate(chapters):
            if not chapter.strip():
                continue

            chapter = re.sub(r'\s+', ' ', chapter).strip()

            if len(chapter) > max_length:
                sentences = re.split(r'[。！？；]', chapter)
                current_segment = ""

                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    if len(current_segment + sentence) > max_length:
                        if current_segment:
                            segments.append(current_segment.strip())
                        current_segment = sentence
                    else:
                        current_segment += sentence + "。"

                if current_segment:
                    segments.append(current_segment.strip())
            else:
                if len(chapter) > 50:
                    segments.append(chapter)

        return segments

    def create_extraction_prompt(self, text: str) -> str:
        """创建实体和关系抽取的提示词"""
        prompt = f"""你是一个专业的中医知识抽取专家。请从以下中医古籍文本中抽取实体和关系。

文本内容：
{text}

请按照以下14种实体类型进行识别：
- DIS: 疾病（如：太阳痉、阳明烦躁、少阳潮热等）
- SYM: 症状（如：汗多、热利、烦躁、潮热、腹痛等）
- SYN: 证候（如：太阳证、阳明证、少阳证等）
- SIG: 体征（如：便秘、便利、呕吐等）
- BEC: 病因病机（如：火入于肺、火入于肾、宿食等）
- PRE: 方剂（如：栀子豆豉汤、大承气汤、羌活汤等）
- MED: 中药材（如：栀子、豆豉、大黄、石膏、滑石等）
- ACU: 腧穴（如：足三里、合谷、百会等）
- MER: 经脉（如：足太阳膀胱经、足阳明胃经等）
- VIS: 脏腑（如：肺、肾、心、肝、脾等）
- PUL: 脉象（如：浮脉、沉脉、数脉等）
- BDP: 身体部位（如：头、胸、腹、四肢等）
- TNG: 舌象（如：舌红、苔白、苔黄等）
- CON: 体质（如：阳虚、阴虚、气虚等）
- FOO: 食物（如：大米、小米、羊肉等）
- LIT: 文献（如：素问、灵枢、伤寒论等）

请按照以下17种关系类型进行识别：
- treat: 治疗（中药材/方剂/腧穴 → 疾病/证候/体征/症状）
- comp: 组成（中药材 → 方剂）
- from: 出自（实体 → 文献）
- belongto: 归属于（腧穴 → 经脉）
- related: 相关经脉（疾病 → 经脉）
- abpulse: 病脉表现（脉象 → 经脉）
- pulse_diagnosis: 脉诊（疾病 → 经脉）
- inandex: 互为表里（经脉 → 脏腑）
- perf: 表现（疾病 → 症状/体征/证候）
- cause: 导致（病因病机 → 疾病）
- oname: 别名（实体1 → 实体2）
- reflect: 反映（舌象 → 病因病机）
- assist_diag: 辅助诊断（舌象 → 疾病）
- guide_med: 指导用药（舌象 → 中药材）
- guide_pre: 指导用药（舌象 → 方剂）
- acupoints: 治疗穴位（舌象 → 腧穴）
- mapped_part: 映射部位（舌象 → 身体部位）
- food_to_eat: 宜吃（舌象/疾病/症状 → 食物）
- Food_to_avoid: 不宜吃（舌象/疾病/症状 → 食物）

请返回JSON格式的结果，严格按照以下格式：
{{
    "entities": [
        {{"text": "实体文本", "label": "实体类型", "start": 开始位置, "end": 结束位置}},
        ...
    ],
    "relations": [
        {{"head": "头实体文本", "tail": "尾实体文本", "relation": "关系类型", "head_start": 头实体开始位置, "tail_start": 尾实体开始位置}},
        ...
    ]
}}

注意：
1. 实体位置要准确，start和end是字符位置
2. 关系中的head_start和tail_start是头尾实体在文本中的开始位置
3. 只抽取明确存在的关系，不要推测
4. 实体文本要完整，不要截断
5. 请严格按照给出的14种实体和17种关系进行抽取，不要形成多余的标签，且根据实体的类型和上下文含义对应好关系类型
"""
        return prompt

    def call_qwen_api(self, text: str, segment_id: int, max_retries: int = 3) -> Dict[str, Any]:
        """调用千问API进行实体和关系抽取"""
        prompt = self.create_extraction_prompt(text)

        for retry in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是中医知识抽取专家，严格按JSON格式返回。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    max_tokens=4000
                )

                result_text = response.choices[0].message.content.strip()
                result_text = re.sub(r'```json\s*', '', result_text)
                result_text = re.sub(r'```\s*', '', result_text)
                result_text = result_text.strip()
                result_text = self.fix_json_errors(result_text)

                try:
                    result = json.loads(result_text)
                    if not isinstance(result, dict):
                        raise ValueError("返回结果不是字典类型")
                    if "entities" not in result:
                        result["entities"] = []
                    if "relations" not in result:
                        result["relations"] = []
                    return result

                except json.JSONDecodeError as je:
                    if retry < max_retries - 1:
                        print(f"⚠️  段落 {segment_id} JSON解析失败 (尝试 {retry + 1}/{max_retries})，{2 ** retry}秒后重试...")
                        time.sleep(2 ** retry)
                        continue
                    else:
                        print(f"✗ 段落 {segment_id} JSON解析失败: {je}")
                        return self.extract_partial_data(result_text, segment_id)

            except Exception as e:
                if retry < max_retries - 1:
                    print(f"⚠️  段落 {segment_id} API调用失败 (尝试 {retry + 1}/{max_retries}): {e}")
                    time.sleep(2 ** retry)
                    continue
                else:
                    print(f"✗ 段落 {segment_id} API调用失败: {e}")
                    return {"entities": [], "relations": []}

        return {"entities": [], "relations": []}

    def fix_json_errors(self, json_str: str) -> str:
        """修复常见的JSON错误"""
        json_str = json_str.replace('"', '"').replace('"', '"')
        json_str = json_str.replace(''', "'").replace(''', "'")

        if not json_str.endswith('}'):
            open_braces = json_str.count('{')
            close_braces = json_str.count('}')
            open_brackets = json_str.count('[')
            close_brackets = json_str.count(']')

            if open_brackets > close_brackets:
                json_str += ']' * (open_brackets - close_brackets)
            if open_braces > close_braces:
                json_str += '}' * (open_braces - close_braces)

        return json_str

    def save_checkpoint(self, segment_id: int, batch_num: int):
        """保存检查点"""
        checkpoint_dir = os.path.join(self.output_dir, 'checkpoints')
        os.makedirs(checkpoint_dir, exist_ok=True)

        checkpoint_data = {
            'last_segment': segment_id,
            'batch_num': batch_num,
            'entity_id_counter': self.entity_id_counter,
            'relation_id_counter': self.relation_id_counter,
            'entities': self.entities,
            'relations': self.relations,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'failed_segments': self.failed_segments
        }

        checkpoint_file = os.path.join(checkpoint_dir, 'checkpoint.json')
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

        print(f"📌 检查点已保存: 段落 {segment_id}, 批次 {batch_num}")

    def load_checkpoint(self):
        """加载检查点"""
        checkpoint_dir = os.path.join(self.output_dir, 'checkpoints')
        checkpoint_file = os.path.join(checkpoint_dir, 'checkpoint.json')

        if not os.path.exists(checkpoint_file):
            return None

        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            self.last_processed_segment = checkpoint_data['last_segment']
            self.entity_id_counter = checkpoint_data['entity_id_counter']
            self.relation_id_counter = checkpoint_data['relation_id_counter']
            self.entities = checkpoint_data['entities']
            self.relations = checkpoint_data['relations']
            self.success_count = checkpoint_data['success_count']
            self.fail_count = checkpoint_data['fail_count']
            self.failed_segments = checkpoint_data['failed_segments']

            print(f"✓ 已加载检查点: 从段落 {self.last_processed_segment + 1} 继续")
            print(f"  已处理段落: {self.last_processed_segment}")
            print(f"  当前实体数: {len(self.entities)}")
            print(f"  当前关系数: {len(self.relations)}")

            return checkpoint_data
        except Exception as e:
            print(f"⚠️  加载检查点失败: {e}")
            return None

    def save_batch_csv(self, batch_num: int):
        """保存分批CSV文件"""
        batch_dir = os.path.join(self.output_dir, 'batches')
        os.makedirs(batch_dir, exist_ok=True)

        # 保存实体批次
        entities_batch_file = os.path.join(batch_dir, f'entities_batch_{batch_num}.csv')
        with open(entities_batch_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Label', 'Entity Text', 'ID'])
            for entity in sorted(self.entities.values(), key=lambda x: x['id']):
                writer.writerow([entity['label'], entity['text'], entity['id']])

        # 保存关系批次
        relations_batch_file = os.path.join(batch_dir, f'relations_batch_{batch_num}.csv')
        with open(relations_batch_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'from_id', 'to_id', 'type'])
            for relation in self.relations:
                writer.writerow([relation['id'], relation['from_id'], relation['to_id'], relation['type']])

        print(f"💾 批次 {batch_num} 已保存")

    def merge_all_batches(self):
        """合并所有批次的CSV文件"""
        batch_dir = os.path.join(self.output_dir, 'batches')

        if not os.path.exists(batch_dir):
            print("⚠️  没有找到批次文件，跳过合并")
            return

        print(f"\n{'=' * 60}")
        print("开始合并批次文件...")
        print(f"{'=' * 60}")

        # 合并实体文件
        entity_files = sorted([f for f in os.listdir(batch_dir) if f.startswith('entities_batch_')])
        if entity_files:
            all_entities = {}
            for ef in entity_files:
                with open(os.path.join(batch_dir, ef), 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        entity_key = f"{row['Entity Text']}_{row['Label']}"
                        if entity_key not in all_entities:
                            all_entities[entity_key] = {
                                'label': row['Label'],
                                'text': row['Entity Text'],
                                'id': int(row['ID'])
                            }

            merged_entities_file = os.path.join(self.output_dir, 'entities_xcj.csv')   #修改entities_+抽取文本的首字母缩写
            with open(merged_entities_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Label', 'Entity Text', 'ID'])
                for entity in sorted(all_entities.values(), key=lambda x: x['id']):
                    writer.writerow([entity['label'], entity['text'], entity['id']])

            print(f"✓ 已合并 {len(entity_files)} 个实体批次 → {merged_entities_file}")
            print(f"  总实体数: {len(all_entities)}")

        # 合并关系文件
        relation_files = sorted([f for f in os.listdir(batch_dir) if f.startswith('relations_batch_')])
        if relation_files:
            all_relations = []
            seen_relations = set()

            for rf in relation_files:
                with open(os.path.join(batch_dir, rf), 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        rel_key = (int(row['id']), int(row['from_id']), int(row['to_id']), row['type'])
                        if rel_key not in seen_relations:
                            seen_relations.add(rel_key)
                            all_relations.append({
                                'id': int(row['id']),
                                'from_id': int(row['from_id']),
                                'to_id': int(row['to_id']),
                                'type': row['type']
                            })

            merged_relations_file = os.path.join(self.output_dir, 'relations_xcj.csv')  #修改relations_+抽取文本的首字母缩写
            with open(merged_relations_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['id', 'from_id', 'to_id', 'type'])
                for relation in sorted(all_relations, key=lambda x: x['id']):
                    writer.writerow([relation['id'], relation['from_id'], relation['to_id'], relation['type']])

            print(f"✓ 已合并 {len(relation_files)} 个关系批次 → {merged_relations_file}")
            print(f"  总关系数: {len(all_relations)}")

        print(f"{'=' * 60}\n")

    def extract_partial_data(self, text: str, segment_id: int) -> Dict[str, Any]:
        """从损坏的JSON中提取部分有效数据"""
        print(f"   尝试提取部分数据...")
        entities = []
        relations = []

        entity_pattern = r'\{"text":\s*"([^"]+)",\s*"label":\s*"([^"]+)",\s*"start":\s*(\d+),\s*"end":\s*(\d+)\}'
        entity_matches = re.findall(entity_pattern, text)

        for match in entity_matches:
            entities.append({
                "text": match[0],
                "label": match[1],
                "start": int(match[2]),
                "end": int(match[3])
            })

        relation_pattern = r'\{"head":\s*"([^"]+)",\s*"tail":\s*"([^"]+)",\s*"relation":\s*"([^"]+)"'
        relation_matches = re.findall(relation_pattern, text)

        for match in relation_matches:
            relations.append({
                "head": match[0],
                "tail": match[1],
                "relation": match[2],
                "head_start": 0,
                "tail_start": 0
            })

        if entities or relations:
            print(f"   ✓ 提取到: {len(entities)} 个实体, {len(relations)} 个关系")

        return {"entities": entities, "relations": relations}

    def process_segment(self, text: str, segment_id: int) -> Dict[str, Any]:
        """处理单个文本段落"""
        result = self.call_qwen_api(text, segment_id)

        has_entities = len(result.get('entities', [])) > 0
        has_relations = len(result.get('relations', [])) > 0

        if has_entities or has_relations:
            self.success_count += 1
            status = "✓"
        else:
            self.fail_count += 1
            self.failed_segments.append(segment_id)
            status = "✗"

        # 显示每个段落的处理情况
        print(f"{status} 段落 {segment_id}: {len(result.get('entities', []))} 实体, {len(result.get('relations', []))} 关系")

        # 处理实体
        entities = []
        entity_map = {}

        for entity in result.get('entities', []):
            entity_id = self.entity_id_counter
            self.entity_id_counter += 1

            entity_data = {
                "id": entity_id,
                "label": entity['label'],
                "start_offset": entity['start'],
                "end_offset": entity['end']
            }
            entities.append(entity_data)

            entity_key = f"{entity['text']}_{entity['label']}"
            if entity_key not in self.entities:
                self.entities[entity_key] = {
                    "id": entity_id,
                    "text": entity['text'],
                    "label": entity['label']
                }

            entity_map[(entity['start'], entity['text'])] = entity_id

        # 处理关系
        relations = []
        for relation in result.get('relations', []):
            head_id = None
            tail_id = None

            head_key = (relation.get('head_start', 0), relation['head'])
            tail_key = (relation.get('tail_start', 0), relation['tail'])

            if head_key in entity_map:
                head_id = entity_map[head_key]
            else:
                for key, ent in self.entities.items():
                    if ent['text'] == relation['head']:
                        head_id = ent['id']
                        break

            if tail_key in entity_map:
                tail_id = entity_map[tail_key]
            else:
                for key, ent in self.entities.items():
                    if ent['text'] == relation['tail']:
                        tail_id = ent['id']
                        break

            if head_id and tail_id:
                relation_id = self.relation_id_counter
                self.relation_id_counter += 1

                relation_data = {
                    "id": relation_id,
                    "from_id": head_id,
                    "to_id": tail_id,
                    "type": relation['relation']
                }
                relations.append(relation_data)
                self.relations.append(relation_data)

        return {
            "id": segment_id,
            "text": text,
            "entities": entities,
            "relations": relations
        }

    def extract_from_pujifang(self, file_path: str, max_segments: int = None, segment_length: int = 800):
        """从普济方文件中抽取实体和关系"""
        print("=" * 60)
        print("开始处理普济方文件...")
        print("=" * 60)

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"✓ 输出目录: {os.path.abspath(self.output_dir)}")

        # 检查并加载检查点
        checkpoint = self.load_checkpoint()
        start_from = self.last_processed_segment if checkpoint else 0

        content = self.read_pujifang_file(file_path)

        if not content:
            print("✗ 文件读取失败")
            return

        print(f"✓ 文件总长度: {len(content)} 字符")
        print("\n开始分割文本...")
        segments = self.split_text_into_segments(content, max_length=segment_length)
        print(f"✓ 共分割出 {len(segments)} 个段落")

        # 确定处理的段落数
        if max_segments is None:
            process_count = len(segments)
        else:
            process_count = min(max_segments, len(segments))

        if start_from > 0:
            print(f"✓ 从段落 {start_from + 1} 继续处理")
            print(f"✓ 剩余 {process_count - start_from} 个段落\n")
        else:
            print(f"✓ 将处理 {process_count} 个段落\n")

        # 处理每个段落
        results = []
        batch_num = (start_from // self.batch_size) + 1
        actual_processed = 0
        last_batch_save = start_from

        for i in range(start_from, process_count):
            segment = segments[i]

            if len(segment.strip()) < 50:
                print(f"⊘ 跳过段落 {i+1} (太短: {len(segment.strip())}字符)")
                continue

            result = self.process_segment(segment, i + 1)
            results.append(result)
            actual_processed += 1

            # 每10个显示汇总
            if actual_processed % 10 == 0:
                progress = (i + 1) / process_count * 100
                fail_rate = (self.fail_count / actual_processed * 100) if actual_processed > 0 else 0
                print(f"📊 进度: {progress:.1f}% ({i+1}/{process_count}) | 已处理: {actual_processed} | 成功: {self.success_count} | 失败: {self.fail_count} ({fail_rate:.1f}%)")

            # 分批保存
            if (i + 1 - last_batch_save) >= self.batch_size:
                print(f"\n{'='*60}")
                print(f"批次 {batch_num} 完成")
                print(f"{'='*60}")
                print(f"总位置: {i + 1}/{process_count} | 本批次: {i + 1 - last_batch_save} 个段落")

                self.save_checkpoint(i + 1, batch_num)
                self.save_batch_csv(batch_num)

                progress = (i + 1) / process_count * 100
                print(f"📊 整体进度: {progress:.1f}%")
                print(f"   成功: {self.success_count} | 失败: {self.fail_count}")
                print(f"   实体累计: {len(self.entities)} | 关系累计: {len(self.relations)}\n")

                batch_num += 1
                last_batch_save = i + 1

            # 添加延迟
            if i < process_count - 1:
                time.sleep(self.api_delay)

        # 处理剩余段落
        if last_batch_save < process_count:
            print(f"\n{'='*60}")
            print(f"保存最后批次 {batch_num}")
            print(f"{'='*60}")
            self.save_checkpoint(process_count, batch_num)
            self.save_batch_csv(batch_num)

        # 保存JSONL
        print("\n" + "=" * 60)
        print("保存JSONL文件...")
        print("=" * 60)

        output_jsonl = os.path.join(self.output_dir, "merged_data_xcj.jsonl")  #修改merged_data_+抽取文本的首字母缩写
        self.save_to_jsonl(results, output_jsonl)

        # 合并批次文件
        self.merge_all_batches()

        # 打印统计
        print(f"\n实际处理: {actual_processed} 个段落")
        self.print_statistics(actual_processed)

    def save_to_jsonl(self, results: List[Dict], filename: str):
        """保存结果到JSONL文件"""
        with open(filename, 'w', encoding='utf-8') as f:
            for result in results:
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
        print(f"✓ 已保存到 {filename}")

    def print_statistics(self, total_segments: int):
        """打印统计信息"""
        from collections import Counter

        print(f"\n{'='*60}")
        print("📊 最终统计")
        print(f"{'='*60}")

        success_rate = (self.success_count / total_segments * 100) if total_segments > 0 else 0
        fail_rate = (self.fail_count / total_segments * 100) if total_segments > 0 else 0

        print(f"\n【处理统计】")
        print(f"  总段落数: {total_segments}")
        print(f"  成功段落: {self.success_count} ({success_rate:.1f}%)")
        print(f"  失败段落: {self.fail_count} ({fail_rate:.1f}%)")

        # 实体统计
        entity_labels = [e['label'] for e in self.entities.values()]
        entity_counts = Counter(entity_labels)

        print(f"\n【实体统计】 总计: {len(self.entities)} 个")
        for label, count in sorted(entity_counts.items(), key=lambda x: -x[1]):
            print(f"  {self.entity_types.get(label, label):8s} ({label}): {count:4d} 个")

        # 关系统计
        relation_types = [r['type'] for r in self.relations]
        relation_counts = Counter(relation_types)

        print(f"\n【关系统计】 总计: {len(self.relations)} 条")
        for rel_type, count in sorted(relation_counts.items(), key=lambda x: -x[1]):
            print(f"  {self.relation_types.get(rel_type, rel_type):12s} ({rel_type}): {count:4d} 条")

        print(f"\n{'='*60}\n")


def main():
    """主函数"""
    # 千问API配置
    QWEN_API_KEY = "sk-f92049ca30eb4469a10814d0e867a4a1"  # 请替换为自己的API Key
    QWEN_MODEL = "qwen-plus"

    # 文件路径配置
    INPUT_FILE = "中医古籍700本/535-西池集.txt"
    OUTPUT_DIR = "data/535xcj"  # 修改为 data/文本号＋缩写

    # 处理参数配置
    MAX_SEGMENTS = None  # 测试用，设为None处理全部
    SEGMENT_LENGTH = 300
    API_DELAY = 0.5
    BATCH_SIZE = 50  # 每50个段落保存一次

    # 创建抽取器
    print(f"使用模型: {QWEN_MODEL}")
    extractor = TCMEntityRelationExtractor(api_key=QWEN_API_KEY, model=QWEN_MODEL)

    # 设置参数
    extractor.api_delay = API_DELAY
    extractor.output_dir = OUTPUT_DIR
    extractor.batch_size = BATCH_SIZE

    # 开始抽取
    extractor.extract_from_pujifang(
        file_path=INPUT_FILE,
        max_segments=MAX_SEGMENTS,
        segment_length=SEGMENT_LENGTH
    )


if __name__ == "__main__":
    main()