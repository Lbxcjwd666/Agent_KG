# 运行时调度架构修改计划

## 核心理念
调度Agent全程参与，辨证Agent管理问诊确认，KG查询Agent按需响应

## 修改状态：✅ 全部完成

---

## 已完成的修改清单

---

### 第1步：DAG执行引擎（task_plan.py）

**改动类型**：新增方法，保留原有接口

| 方法 | 类型 | 说明 |
|------|------|------|
| `execute_step(bus)` | 新增 | 逐步执行，返回当前步骤结果和状态 |
| `add_task_by_def(task_def)` | 新增 | 动态追加任务 |
| `skip_task(task_id)` | 新增 | 跳过指定任务 |
| `modify_task_params(task_id, new_params)` | 新增 | 修改任务参数 |
| `all_done()` | 新增 | 判断是否全部完成 |
| `get_state()` | 新增 | 返回执行状态快照 |
| `get_ready_agents()` | 新增 | 返回当前可执行的Agent列表 |
| `set_task_result(task_id, result)` | 新增 | 外部设置任务结果（用于注入已完成步骤） |

**execute_step 返回结构**：
```python
{
    "step_task_id": "...",
    "step_agent": "...",
    "step_status": "done" | "failed",
    "step_result": {...},
    "remaining": ["task_id1", "task_id2", ...],
    "all_done": False
}
```

---

### 第2步：KG查询Agent（kg_query.py）

**改动类型**：新增方法，保留原有run()

| 方法 | 类型 | 说明 |
|------|------|------|
| `query_supplement(entity_text, entity_type, relation_filter=None)` | 新增 | 按需查询单个实体的指定关系，返回增量subgraph |
| `query_disease_symptoms(disease_name)` | 新增 | 查询疾病的症状列表（供辨证Agent生成问诊词） |

**query_supplement 返回结构**：
```python
{
    "subgraph": {entity_text: {type, relations, relation_count}},
    "kg_context": "文本摘要"
}
```

**query_disease_symptoms 返回结构**：
```python
{
    "disease": "心积",
    "symptoms": ["潮热", "五心烦热", "口苦咽干", ...],
    "syndromes": ["心火旺盛证", ...]
}
```

---

### 第3步：辨证Agent（diagnosis.py）

**改动类型**：新增方法 + 修改run()

| 方法 | 类型 | 说明 |
|------|------|------|
| `generate_inquiry_questions(disease_name, disease_symptoms)` | 新增 | 将专业术语症状转为通俗问诊词 |
| `evaluate_user_response(disease_name, disease_symptoms, user_answers)` | 新增 | 根据用户回答判断是否有此疾病 |
| `run()` | 修改 | 增加问诊确认流程的判断逻辑 |

**generate_inquiry_questions 的LLM Prompt要点**：
- 输入：疾病名 + KG中的专业症状列表
- 输出：每个症状对应的通俗问诊词
- 约束：必须用日常语言，避免中医术语

**evaluate_user_response 的LLM Prompt要点**：
- 输入：疾病名 + 症状列表 + 用户回答
- 输出：确认/排除 + 匹配的症状 + 置信度

**run() 修改逻辑**：
```
if payload中有candidate_diseases:
    → 对每个候选疾病调用generate_inquiry_questions
    → 返回need_inquiry=True + inquiry_questions
elif payload中有user_answers:
    → 调用evaluate_user_response
    → 如果确认疾病 → 返回confirmed_diseases
    → 如果排除 → 返回excluded_diseases
else:
    → 正常5步推理链（原有逻辑不变）
```

---

### 第4步：调度Agent（orchestrator.py）

**改动类型**：重大修改，从查表器变为运行时中枢

| 方法 | 类型 | 说明 |
|------|------|------|
| `run()` | 修改 | 仍生成初始plan，但返回更多上下文 |
| `checkpoint_review(step_name, step_result, plan_state)` | 新增 | 审查每步结果，返回决策 |
| `split_subgraph(subgraph)` | 新增 | 将KG查询结果拆分为三个专属子图 |
| `decide_after_diagnosis(diagnosis_result)` | 新增 | 根据辨证结果决定后续调用哪些Agent |
| `decide_after_review(review_result)` | 新增 | 根据审核结果决定是否辩论或回退 |

**checkpoint_review 决策类型**：
| 决策 | 含义 | 触发场景 |
|------|------|---------|
| `continue` | 按原计划继续 | 正常流程 |
| `skip` | 跳过某些Agent | 辨证置信度低 |
| `add_task` | 追加新任务 | 需要补充KG查询 |
| `wait_user` | 暂停等用户 | 需要用户确认疾病 |
| `debate` | 触发辩论 | 审核发现严重冲突 |
| `done` | 完成 | 所有任务结束 |

**split_subgraph 拆分规则**：
| 目标Agent | 注入的关系key | 注入的实体类型 |
|-----------|-------------|-------------|
| 方剂Agent | `治疗_from_PRE`, `治疗_from_MED`, `组成_from_MED`, `组成_PRE` | SYM, DIS, SYN, PRE, MED |
| 针灸Agent | `治疗_from_ACU`, `归属于_MER` | SYM, DIS, SYN, ACU |
| 养生Agent | `治疗_from_MED`, 体质实体整体 | SYM, DIS, SYN, CON |

---

### 第5步：方剂/针灸/养生Agent（formula.py, acupuncture.py, regimen.py）

**改动类型**：小修改

| 改动 | 说明 |
|------|------|
| 删除 `_extract_xxx_from_subgraph()` | 拆分职责已交给调度Agent |
| 简化 `run()` 中subgraph分支 | 直接使用注入的专属子图，无需自行提取 |
| 保留 `elif self.kg` 兜底 | 无subgraph时仍可自行查询 |

---

### 第6步：应用层（app_agent.py）

**改动类型**：重大修改

| 改动 | 说明 |
|------|------|
| 主流程 | 从一次性execute改为循环调度 |
| 新增SSE事件 | `inquiry`, `checkpoint`, `plan_update` |
| 新增用户交互 | 接收用户回答，传回辨证Agent |
| 新增问诊API端点 | `/api/agent/inquiry_response` |

**主流程伪代码**：
```
1. 调度Agent生成初始plan
2. while not dag.all_done():
     step = dag.execute_step(bus)
     decision = orchestrator.checkpoint_review(step, dag.get_state())
     if decision == continue: continue
     if decision == wait_user: yield inquiry event, wait
     if decision == add_task: dag.add_task_by_def(...)
     if decision == skip: dag.skip_task(...)
     if decision == done: break
3. 生成最终答案
```

---

## 完整执行流程示例

用户问"我最近心烦失眠，口干舌燥"：

```
① 调度Agent: 生成初始plan
② 执行 entity_recognition → 结果回到调度Agent
③ 执行 kg_query → 结果回到调度Agent
④ 调度Agent审查: need_confirmation=True
   → 将candidate_diseases交给辨证Agent
⑤ 辨证Agent: generate_inquiry_questions("心积", ["潮热","五心烦热",...])
   → 问诊词: ["您是否下午感觉身体发热？", "您是否手心脚心发热？", ...]
   → 返回wait_user
⑥ 用户回答 → 辨证Agent: evaluate_user_response → 确认心积
⑦ 调度Agent: 请求kg_query补充查询心积
⑧ 调度Agent: split_subgraph拆分为三个专属子图
⑨ 执行 diagnosis(完整辨证) → 结果回到调度Agent
⑩ 调度Agent: decide_after_diagnosis → 继续
⑪ 执行 formula + acupuncture + regimen (并行)
⑫ 执行 review
⑬ 调度Agent: decide_after_review → done
⑭ 生成最终答案
```