# 基于知识图谱增强的中医问答系统

## 🎯 系统概述

本系统通过Neo4j知识图谱增强千问大模型的推理能力，提供准确的中医问答服务。系统严格按照提供的实体和关系设计表进行开发。

## 📋 功能特性

### 1. 知识图谱增强
- ✅ 基于Neo4j的知识图谱查询
- ✅ 严格按照16种实体类型和21种关系类型设计
- ✅ 支持多跳关系查询
- ✅ 自动格式化知识图谱上下文

### 2. 千问API集成
- ✅ 使用千问API进行实体抽取
- ✅ 使用千问API生成答案
- ✅ 支持知识图谱增强的上下文输入

### 3. 前后端分离
- ✅ React前端界面
- ✅ Flask后端API
- ✅ RESTful API设计

## 🏗️ 系统架构

```
smart-qa-system/
├── src/
│   ├── app.py                 # Flask后端主文件
│   ├── config.py              # 配置文件（实体、关系、API配置）
│   ├── kg_enhancer.py         # 知识图谱增强模块
│   ├── qwen_api.py            # 千问API调用模块
│   ├── QuestionAnswer.js      # 前端问答组件
│   └── QuestionAnswer.css     # 前端样式
└── README_知识图谱增强系统.md  # 本文档
```

## 🔧 配置说明

### 1. Neo4j配置
在 `config.py` 中配置Neo4j连接信息：

```python
NEO4J_CONFIG = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "123456"
}
```

### 2. 千问API配置
在 `config.py` 中配置千问API：

```python
QWEN_API_CONFIG = {
    "api_key": "your-qwen-api-key",  # 请替换为您的API密钥
    "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "model": "qwen-turbo",  # 可选: qwen-turbo, qwen-plus, qwen-max
    "temperature": 0.7,
    "max_tokens": 2000
}
```

### 3. 系统配置
```python
SYSTEM_CONFIG = {
    "max_entities": 5,  # 最多识别的实体数量
    "max_kg_results": 20,  # 知识图谱查询最多返回结果数
    "enable_kg_enhancement": True,  # 是否启用知识图谱增强
    "kg_confidence_threshold": 0.5  # 知识图谱结果置信度阈值
}
```

## 📊 实体和关系设计

### 实体类型（16种）
严格按照设计表实现：
- 疾病 (DIS)
- 症状 (SYM)
- 证候 (SYN)
- 体征 (SIG)
- 病因病机 (BEC)
- 方剂 (PRE)
- 中药材 (MED)
- 腧穴 (ACU)
- 经脉 (MER)
- 脏腑 (VIS)
- 脉象 (PUL)
- 身体部位 (BDP)
- 舌象 (TNG)
- 体质 (CON)
- 食物 (FOO)
- 文献 (LIT)

### 关系类型（21种）
严格按照设计表实现，包括：
- 治疗 (Treat)
- 组成 (comp)
- 出自 (from)
- 归属于 (belongto)
- 相关MER (related)
- 病脉表现 (abpulse)
- 脉诊 (pulse_diagnosis)
- 望诊 (visual_diagnosis)
- 互为表里 (inandex)
- 表现 (perf)
- 导致 (cause)
- 相关DIS (related)
- 别名 (oname)
- 反映 (reflect)
- 辅助诊断 (assist_diag)
- 指导用药 (guide_med)
- 指导方剂 (guide_pre)
- 治疗ACU (acupoints)
- 映射部位 (mapped_part)
- 宜吃 (food_to_eat)
- 不宜吃 (Food_to_avoid)

## 🚀 快速开始

### 1. 安装依赖

#### 后端依赖
```bash
pip install flask flask-cors neo4j requests
```

#### 前端依赖
```bash
cd smart-qa-system
npm install
```

### 2. 配置环境

1. 确保Neo4j数据库已启动
2. 在 `config.py` 中配置Neo4j连接信息
3. 在 `config.py` 中配置千问API密钥

### 3. 启动后端
```bash
cd smart-qa-system/src
python app.py
```

后端将在 `http://localhost:5000` 启动

### 4. 启动前端
```bash
cd smart-qa-system
npm start
```

前端将在 `http://localhost:3000` 启动

## 📡 API接口

### 1. 问答接口
```
POST /api/chat
Content-Type: application/json

{
    "question": "人参有什么功效？"
}

Response:
{
    "answer": "人参具有大补元气、复脉固脱的功效...",
    "entities": [
        {"text": "人参", "type": "MED"}
    ],
    "kg_context": "实体：人参（MED）\n相关知识：...",
    "kg_results": {...}
}
```

### 2. 实体抽取接口
```
POST /api/entities
Content-Type: application/json

{
    "text": "人参味甘微苦，性温，归脾、肺、心经。"
}

Response:
{
    "entities": [
        {"text": "人参", "type": "中药材", "label": "MED"}
    ]
}
```

### 3. 知识图谱查询接口
```
POST /api/kg/query
Content-Type: application/json

{
    "entity_text": "人参",
    "entity_type": "MED",
    "relation_name": "治疗"  // 可选
}

Response:
{
    "results": {
        "治疗_DIS": [
            {"text": "体虚", "type": "DIS", "relation": "Treat"}
        ]
    }
}
```

### 4. 多跳查询接口
```
POST /api/kg/multi-hop
Content-Type: application/json

{
    "entity_text": "人参",
    "entity_type": "MED",
    "max_hops": 2
}
```

### 5. 健康检查接口
```
GET /api/health

Response:
{
    "status": "ok",
    "kg_enabled": true,
    "qwen_model": "qwen-turbo"
}
```

## 🔄 工作流程

1. **用户提问** → 前端发送问题到后端
2. **实体抽取** → 使用千问API从问题中抽取实体
3. **知识图谱查询** → 根据实体查询Neo4j知识图谱
4. **上下文增强** → 将知识图谱信息格式化为上下文
5. **答案生成** → 使用千问API生成答案（带知识图谱增强）
6. **返回结果** → 返回答案、实体和知识图谱信息

## 🎨 前端功能

- ✅ 实时问答界面
- ✅ 实体识别显示
- ✅ 知识图谱信息展示（可展开/折叠）
- ✅ 历史问答记录
- ✅ 打字机效果显示答案
- ✅ 响应式设计

## 🔍 知识图谱查询逻辑

系统严格按照实体和关系设计表进行查询：

1. **实体类型验证**：确保实体类型在16种类型中
2. **关系类型验证**：确保关系类型在21种类型中
3. **头尾实体约束**：严格按照关系设计表中的头实体和尾实体约束
4. **双向查询**：支持实体作为头实体或尾实体查询

## 📝 注意事项

1. **API密钥**：请确保千问API密钥配置正确
2. **Neo4j连接**：确保Neo4j数据库已启动并可连接
3. **数据格式**：确保Neo4j中的实体和关系标签与配置一致
4. **性能优化**：大量实体时建议调整 `max_entities` 配置

## 🐛 故障排除

### 1. API调用失败
- 检查API密钥是否正确
- 检查网络连接
- 查看后端日志

### 2. 知识图谱查询失败
- 检查Neo4j连接配置
- 确认数据库已启动
- 检查实体和关系标签是否匹配

### 3. 实体识别不准确
- 调整千问API的temperature参数
- 优化实体抽取提示词
- 检查实体类型配置

## 📞 技术支持

如有问题，请检查：
1. 配置文件是否正确
2. 依赖包是否安装完整
3. Neo4j和API服务是否正常
4. 查看后端日志获取详细错误信息

## 🔄 更新日志

### v1.0.0 (2024-01-01)
- ✅ 初始版本
- ✅ 知识图谱增强功能
- ✅ 千问API集成
- ✅ 前后端完整实现



