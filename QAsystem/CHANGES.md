# 高优先级优化改动说明

## 改动概述

本次优化针对改进文档中的两项高优先级问题：

1. **合并 diagnosis 和 diagnosis_reasoning，消除职责重叠**
2. **让 DAGExecutor 真正工作，替代 app_agent.py 中的手动串行调用**

---

## 改动一：合并辨证推理Agent

### 问题

原系统中 `diagnosis.py` 和 `diagnosis_reasoning.py` 职责重叠：

| 文件 | 功能 | 问题 |
|---|---|---|
| `diagnosis.py` | 5步推理链 + 多轮追问 + 对话历史 | 无多跳KG查询，推理链格式不规范 |
| `diagnosis_reasoning.py` | 5步推理链 + KG证据关联 | 无多轮追问，无对话历史，无fallback |

两者都做辨证推理，但各缺一部分功能，且被不同流程调用，导致结果格式不统一。

### 改动

**合并到 `agents/diagnosis.py`**，统一为一个完整的辨证推理Agent，新增以下能力：

- **多跳KG查询**：根据复杂度自动启用 `query_multi_hop`，获取症状→证候→治法→方剂的关联路径
- **推理链自动构建**：当LLM未输出 `reasoning_chain` 时，`_build_reasoning_chain()` 从结果字段自动补全5步推理链
- **复杂度参数**：`complexity` 参数控制KG查询深度（simple→L1, medium/complex→ALL+多跳）
- **多跳结果摘要**：`_summarize_kg()` 将多跳查询结果转为自然语言供LLM参考
- **完整fallback**：降级时也输出规范的推理链格式

**`agents/diagnosis_reasoning.py`** 不再被任何代码引用，保留文件作为历史参考。

### 同步更新

`agents/orchestrator.py` 中所有DAG计划的agent名称统一：

| 旧名称 | 新名称 | 说明 |
|---|---|---|
| `diagnosis_reasoning` | `diagnosis` | 合并为统一辨证Agent |
| `verification` | `review` | 统一为审核Agent |
| `prescription` | `formula` | 统一为方剂Agent |

---

## 改动二：DAG并行执行引擎

### 问题

原 `app_agent.py` 中虽然定义了 DAG 计划，但实际执行是手动串行调用：

```python
# 原代码 — 串行执行
diagnosis = agents["diagnosis"].execute(...)
formula = agents["formula"].execute(...)        # 等 diagnosis 完成
acupuncture = agents["acupuncture"].execute(...) # 等 formula 完成
regimen = agents["regimen"].execute(...)         # 等 acupuncture 完成
review = agents["review"].execute(...)           # 等 regimen 完成
```

formula/acupuncture/regimen 三者之间没有依赖关系，完全可以并行，但实际是串行等待。

### 改动

#### 2.1 增强 `core/task_plan.py` — DAGExecutor

新增能力：

| 功能 | 方法 | 说明 |
|---|---|---|
| **并行执行** | `ThreadPoolExecutor` | 无依赖的任务同时执行，max_workers=3 |
| **依赖结果注入** | `_inject_dependency_results()` | 自动将上游Agent的输出注入下游Agent的参数 |
| **流式回调** | `execute_stream()` | 通过 `on_task_start`/`on_task_done` 回调通知任务状态变更 |
| **智能跳过** | 依赖失败的任务自动标记为 `skipped` | 不会因单个Agent失败阻塞整个管线 |

依赖注入映射规则：

```
entity_recognition → entities, entity_count
kg_query          → kg_context, subgraph
diagnosis         → diagnosis, syndrome, treatment_principle
formula           → formula
acupuncture       → acupuncture
regimen           → regimen
review            → review
```

#### 2.2 重构 `app_agent.py` — DAG驱动管线

**SSE流式端点** (`/chat/stream`)：

- Phase 1-3（orchestrator、entity_recognition、kg_query）保持串行，结果预注入DAG
- Phase 4-7 使用 DAGExecutor 驱动，通过 `queue` + `threading` 实现实时SSE推送
- DAG 在后台线程执行，主线程通过队列消费事件并 yield SSE

**非流式端点** (`/chat`)：

- 同样使用 `DAGExecutor.execute()` 替代手动串行调用

**DAG结构**：

```
entity_recognition (预完成)
       ↓
    kg_query (预完成)
       ↓
    diagnosis
      ↙  ↓  ↘
formula  acupuncture  regimen   ← 三者并行
      ↘  ↓  ↙
      review
```

### 性能提升

| 指标 | 串行 | 并行 |
|---|---|---|
| formula+acupuncture+regimen 耗时 | 三者之和 (~15s) | 取决于最慢的 (~6s) |
| 预计加速比 | 1x | ~2.5x |
| 预计节省时间 | — | ~9s |

---

## 修改文件清单

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `agents/diagnosis.py` | 重写 | 合并diagnosis_reasoning功能，新增多跳查询、推理链自动构建、复杂度参数 |
| `core/task_plan.py` | 重写 | DAGExecutor增加并行执行、依赖注入、流式回调 |
| `agents/orchestrator.py` | 修改 | DAG计划中agent名称统一 |
| `app_agent.py` | 重构 | SSE端点和非流式端点改为DAG驱动，新增`_build_clinical_dag()` |
| `benchmark.py` | 新增 | 性能基准测试脚本 |

---

## 验证方法

### 1. 语法验证

```powershell
python -c "import py_compile; py_compile.compile('app_agent.py', doraise=True); py_compile.compile('core/task_plan.py', doraise=True); py_compile.compile('agents/diagnosis.py', doraise=True); print('All OK')"
```

### 2. 功能验证

启动服务后，发送一个临床问题，检查返回结果中是否包含完整的辨证推理链：

```powershell
curl -X POST http://localhost:5000/api/agent/chat -H "Content-Type: application/json" -d "{\"question\": \"我头痛口苦心烦易怒舌红苔黄脉弦数\"}"
```

预期返回中包含：
- `diagnosis.reasoning_chain`：5步推理链
- `diagnosis.kg_context_used`：是否使用了KG上下文
- `formula`、`acupuncture`、`regimen`：三个专科结果

### 3. 性能验证

```powershell
python benchmark.py
```

关注输出中的：
- **启动时间差** < 1s → 确认并行执行
- **加速比** > 2x → 确认性能提升

---

## 向后兼容性

- `diagnosis_reasoning.py` 文件保留但不再被引用，不影响现有代码
- SSE事件格式不变（`agent_start`/`agent_done`），前端无需修改
- 非流式端点返回格式不变