"""
配置文件 - 严格按照实体和关系设计表
"""

# 实体类型配置（16种）
ENTITY_TYPES = {
    "疾病": "DIS",
    "症状": "SYM",
    "证候": "SYN",
    "体征": "SIG",
    "病因病机": "BEC",
    "方剂": "PRE",
    "中药材": "MED",
    "腧穴": "ACU",
    "经脉": "MER",
    "脏腑": "VIS",
    "脉象": "PUL",
    "身体部位": "BDP",
    "舌象": "TNG",
    "体质": "CON",
    "食物": "FOO",
    "文献": "LIT"
}

# 关系类型配置（严格按照设计表）
RELATION_TYPES = {
    "治疗": {
        "label": "treat",
        "head_entities": ["MED", "PRE", "ACU"],
        "tail_entities": ["DIS", "SYN", "SIG", "SYM"]
    },
    "组成": {
        "label": "comp",
        "head_entities": ["MED"],
        "tail_entities": ["PRE"]
    },
    "出自": {
        "label": "from",
        "head_entities": ["MED", "PRE", "ACU", "DIS", "TNG"],
        "tail_entities": ["LIT"]
    },
    "归属于": {
        "label": "belongto",
        "head_entities": ["ACU"],
        "tail_entities": ["MER"]
    },
    "相关MER": {
        "label": "related",
        "head_entities": ["DIS", "TNG"],
        "tail_entities": ["MER"]
    },
    "病脉表现": {
        "label": "abpulse",
        "head_entities": ["PUL"],
        "tail_entities": ["MER"]
    },
    "脉诊": {
        "label": "pulse_diagnosis",
        "head_entities": ["DIS"],
        "tail_entities": ["MER"]
    },
    "望诊": {
        "label": "visual_diagnosis",
        "head_entities": ["DIS"],
        "tail_entities": ["BDP"]
    },
    "互为表里": {
        "label": "inandex",
        "head_entities": ["MER"],
        "tail_entities": ["VIS"]
    },
    "表现": {
        "label": "perf",
        "head_entities": ["DIS", "TNG"],
        "tail_entities": ["SYM", "SIG", "SYN"]
    },
    "导致": {
        "label": "cause",
        "head_entities": ["BEC"],
        "tail_entities": ["DIS"]
    },
    "相关DIS": {
        "label": "related",
        "head_entities": ["DIS"],
        "tail_entities": ["DIS"]
    },
    "别名": {
        "label": "oname",
        "head_entities": ["实体"],
        "tail_entities": ["实体"]
    },
    "反映": {
        "label": "reflect",
        "head_entities": ["TNG"],
        "tail_entities": ["BEC"]
    },
    "辅助诊断": {
        "label": "assist_diag",
        "head_entities": ["TNG"],
        "tail_entities": ["DIS"]
    },
    "指导用药": {
        "label": "guide_med",
        "head_entities": ["TNG"],
        "tail_entities": ["MED"]
    },
    "指导方剂": {
        "label": "guide_pre",
        "head_entities": ["TNG"],
        "tail_entities": ["PRE"]
    },
    "治疗ACU": {
        "label": "acupoints",
        "head_entities": ["TNG"],
        "tail_entities": ["ACU"]
    },
    "映射部位": {
        "label": "mapped_part",
        "head_entities": ["TNG"],
        "tail_entities": ["BDP"]
    },
    "宜吃": {
        "label": "food_to_eat",
        "head_entities": ["TNG"],
        "tail_entities": ["FOO"]
    },
    "不宜吃": {
        "label": "Food_to_avoid",
        "head_entities": ["TNG"],
        "tail_entities": ["FOO"]
    }
}

# Neo4j配置
NEO4J_CONFIG = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "12345678"
}

# 千问API配置
QWEN_API_CONFIG = {
    "api_key": "sk-ws-H.RYYYMPP.o4kb.MEUCIGgnVzZ4Eq1bRwmb7qydmHbeDwRNfcwtljsj7ENrWXOdAiEAxOrrMDPVT3-XOOdLK374a0ugTXVlwDilyOVB9Lxv4yw",  # 请替换为您的API密钥
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    # 模型选项说明：
    # - qwen-turbo: 快速响应，适合一般对话
    # - qwen-plus: 平衡性能和效果
    # - qwen-max: 最强性能，适合复杂任务
    # - qwen2.5-7b-instruct: 7B参数模型，支持微调
    # - qwen2.5-14b-instruct: 14B参数模型，支持微调
    # - qwen2.5-32b-instruct: 32B参数模型，支持微调
    # - qwen2.5-72b-instruct: 72B参数模型，支持微调
    # 注意：qwen2.5-vl是视觉语言模型，主要用于图像理解，不适合纯文本问答
    "model": "qwen3.7-plus",
    "temperature": 0.7,
    "max_tokens": 2000
}

# 系统配置
SYSTEM_CONFIG = {
    "max_entities": 5,  # 最多识别的实体数量
    "max_kg_results": 20,  # 知识图谱查询最多返回结果数
    "enable_kg_enhancement": True,  # 是否启用知识图谱增强
    "kg_confidence_threshold": 0.5  # 知识图谱结果置信度阈值
}

# 多Agent配置 — 5 Agent 诊疗管线 + 辅助Agent
AGENT_CONFIG = {
    # 核心诊疗Agent
    "diagnosis": {"model": "qwen3.7-plus", "timeout": 120},
    "formula": {"model": "qwen3.7-plus", "timeout": 90},
    "acupuncture": {"model": "qwen3.7-plus", "timeout": 90},
    "regimen": {"model": "qwen3.7-plus", "timeout": 60},
    "review": {"model": "qwen3.7-plus", "timeout": 60},
    # 辅助Agent
    "orchestrator": {"model": "qwen3.7-plus", "timeout": 20},
    "entity_recognition": {"model": "qwen3.7-plus", "timeout": 15},
    "kg_query": {"timeout": 10},
}

# 向量索引配置
VECTOR_INDEX_CONFIG = {
    "embedding_model": "bge-large-zh-v1.5",
    "embedding_provider": "local",
    "embedding_dimension": 1024,
    "index_name": "entity_vector_index",
    "similarity_function": "cosine",
    "top_k": 10,
    "batch_size": 64,
    "vector_match_threshold": 0.75,
    "concurrent_workers": 1,
}

# 持续学习配置
LEARNING_CONFIG = {
    "auto_approve_threshold": 0.9,       # >= 此阈值自动写入KG
    "review_threshold": 0.7,             # >= 此阈值进入审核队列
    "max_candidates_per_session": 10,    # 每次对话最多产生候选数
    "review_db_path": "review_queue.db", # 审核队列SQLite路径
}