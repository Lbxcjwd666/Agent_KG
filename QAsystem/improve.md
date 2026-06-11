# 优化建议

---

## 技术路线概述

本系统采用 **KG-RAG（知识图谱增强检索生成）** 架构，整体分为两条主线：

### 一、数据管线（离线）

```
中医古籍(.txt, 701本)
    │
    ▼
┌─────────────────────────────────┐
│  tcm_extraction.py              │
│  千问API (qwen-plus)             │
│  按段落切分 → Prompt Engineering │
│  抽取16类实体 + 21类关系         │
│  支持断点续传（checkpoint）       │
└──────────────┬──────────────────┘
               │ entities_*.csv / relations_*.csv
               ▼
┌─────────────────────────────────┐
│  中医RE去重/merge_merge.py       │
│  三步合并：合并 → 实体去重+ID映射 │
│           → 关系去重             │
│  fix_test.py: 关系类型修正       │
└──────────────┬──────────────────┘
               │ final_merged_entities.csv (~45.5万)
               │ final_merged_relations_fixed1.csv (~55万)
               ▼
┌─────────────────────────────────┐
│  graph_test.py                  │
│  Neo4j 批量导入                  │
│  节点按Label分16类，边按类型分21类│
│  支持图片Base64嵌入节点          │
└─────────────────────────────────┘
```

### 二、问答服务（在线）

```
用户提问
    │
    ▼
┌────────────────────────────┐
│  React 前端 (端口3000)      │
│  QuestionAnswer.js          │
│  - 打字机效果展示            │
│  - KG可视化 (SVG)           │
│  - 推理路径时间线            │
│  - 追问建议                  │
└────────────┬───────────────┘
             │ POST /api/chat
             ▼
┌────────────────────────────┐
│  Flask 后端 (端口5000)      │
│  app.py                     │
├────────────────────────────┤
│  ① qwen_api.extract_entities() │  ← 千问API识别问题中的中医实体
│  ② kg_enhancer.query_relations()│  ← Neo4j双向查询+多跳查询
│  ③ kg_enhancer.format_kg_context()│ ← 格式化KG结果为自然语言
│  ④ qwen_api.generate_answer()    │  ← 千问API + KG上下文 → 最终答案
│  ⑤ 生成可视化数据 + 推理路径     │
│  ⑥ qwen_api.generate_suggested_questions() │ ← 追问建议
└────────────┬───────────────┘
             │
             ▼
         用户看到答案 + KG信息 + 推理路径 + 追问
```

### 三、核心技术选型

| 层级 | 技术 | 版本 |
|------|------|------|
| 大模型 | 阿里云通义千问 (qwen-max) | 兼容OpenAI SDK |
| 图数据库 | Neo4j | 5.x, bolt协议 |
| 后端 | Flask + flask-cors | 3.0.0 |
| 前端 | React + react-router-dom | 18.3.1 |
| 数据格式 | CSV / JSONL | - |
| 实体类型 | 16种（DIS/SYM/SYN/SIG/BEC/PRE/MED/ACU/MER/VIS/PUL/BDP/TNG/CON/FOO/LIT） | - |
| 关系类型 | 21种（treat/comp/from/belongto/related/abpulse/pulse_diagnosis/visual_diagnosis/inandex/perf/cause/oname/reflect/assist_diag/guide_med/guide_pre/acupoints/mapped_part/food_to_eat/Food_to_avoid） | - |

---

## 知识图谱层优化

### 1. 检索效率瓶颈
`kg_enhancer.py` 的 `query_relations` 方法在未指定关系时，会对16种实体类型和21种关系类型做嵌套循环遍历，产生大量Cypher查询（最坏情况 ~672次查询），每次问答可能触发上百次数据库往返，延迟显著。

**优化建议：**
- 将单次请求中的多个 Cypher 查询用 `UNION ALL` 合并为一次数据库往返
- 利用 Neo4j 的 `CALL { } IN TRANSACTIONS` 进行批量子查询
- 引入查询结果缓存（如 Redis），对高频实体的关系查询结果设置 TTL
- 对不需要全量关系检索的场景，默认只查核心关系类型（treat/perf/cause/belongto），按需展开

### 2. 缺乏实体链接
LLM抽取的实体名称稍有变体（如"人参"vs"人参片"vs"高丽参"）就会匹配不到，缺乏实体链接（Entity Linking）或向量相似度检索兜底。

**优化建议：**
- 为所有 KG 实体预计算 embedding（可用千问 text-embedding API），存入 Neo4j 节点属性或独立向量库
- 用户问题抽取实体后，先做 embedding 相似度检索召回 top-K 候选实体，再做精确匹配
- 建立中医同义词词典（如"高丽参"→"人参"、"锦纹"→"大黄"），在匹配前做别名展开
- 利用 KG 中已有的 `oname`（别名）关系辅助实体消歧

### 3. 实体抽取准确度
当前实体抽取完全依赖千问API的 Prompt Engineering，缺乏对抽取结果的质量校验机制。抽取 Prompt 中实体/关系数量描述也与 `config.py` 不一致（Prompt说14种实体实际16种，关系说17种实际19种）。

**优化建议：**
- 统一 Prompt 中实体/关系定义与 `config.py`，消除数量不一致
- 建立小规模人工标注 Golden Set（建议每种实体类型各50条，每种关系类型各30条），用于定期评估抽取质量
- 对抽取结果做后处理校验：实体类型是否在16种内、关系头尾实体类型是否符合约束、实体文本是否为空或过短
- 对低置信度结果增加二次确认机制（换用 qwen-max 做复核）

### 4. 数据质量与覆盖
- 数据源仅限于古籍，缺乏现代临床指南、药典、RCT证据，回答可能偏古方而脱离现代循证实践
- 无实体/关系去重的语义校验——同名异义（如"伤寒"同时是病名和书名）未做区分
- 55万关系中可能存在抽取幻觉（LLM编造的关系），无自动化过滤机制

**优化建议：**
- 补充现代数据源（中国药典、中医临床诊疗指南、中医方剂大辞典结构化数据）
- 引入关系频次阈值过滤：同一关系类型在同一实体对间出现次数低于阈值的标记为低置信度
- 对 `oname`（别名）和 `related`（相关）等语义宽泛的关系类型做专项清洗



---

## 前端使用层优化

### 1. 缺乏流式输出（SSE），用户等待体验差
当前 `QuestionAnswer.js` 通过 `fetch('/api/chat')` 一次性等待完整响应，后端 `qwen_api.chat()` 也是同步阻塞调用（`timeout=30`）。用户提问后需等待 5~30 秒才能看到完整答案，期间仅有一个旋转加载图标。

**优化建议：**
- 后端 `qwen_api.py` 改用千问 API 的 `stream: true` 参数，通过 Flask SSE（Server-Sent Events）逐 token 推送
- 前端改用 `EventSource` 或 `fetch` + `ReadableStream` 接收流式数据，实现逐字实时渲染
- 现有的 `TypeWriter` 组件可直接替换为流式渲染，无需模拟打字效果

### 2. KG 可视化使用命令式 DOM 操作，背离 React 范式
`KnowledgeGraphVisualization.js` 第17行使用 `svg.innerHTML = ''` 清空再通过 `document.createElementNS` 手动构建 SVG 节点（第46-142行）。这种命令式写法无法享受 React 的虚拟 DOM diff 优化，节点点击事件绑定在 DOM 上而非 React 合成事件系统，调试和维护困难。

**优化建议：**
- 改用声明式 JSX 生成 SVG 元素：`<svg>{nodes.map(n => <circle .../>)}</svg>`
- 或引入轻量级 React 可视化库（如 `@nivo/network`、`react-force-graph`），用配置替代 DOM 操作
- 力导向布局计算可用 `d3-force` 的纯算法部分，计算完成后将 `(x, y)` 坐标传入 React state 驱动渲染

### 3. TypeWriter 组件无效重渲染
`TypeWriter.js` 每显示一个字符触发一次 `setState` → 一次重渲染，对于500字的答案就是500次渲染。同时 `QuestionAnswer.js` 第118-131行又用 `useEffect` + `setInterval` 做了一遍打字效果，与 `TypeWriter` 组件功能重叠，且两套打字逻辑各自运行。

**优化建议：**
- `TypeWriter` 使用 `requestAnimationFrame` 批量更新，每帧显示多个字符（如每16ms显示3~5字），减少渲染次数
- 移除 `QuestionAnswer.js` 中重复的打字逻辑，统一使用 `TypeWriter` 组件
- 配合流式输出后，`TypeWriter` 可以直接废弃，由流式数据驱动渲染

### 4. 对话历史无分页/虚拟滚动，内存持续增长
`questions` 数组（第9行）随着对话进行只增不减，所有历史问答全部渲染在 DOM 中（第135-174行）。长对话场景下 DOM 节点数膨胀，滚动性能下降，且页面刷新后历史全部丢失。

**优化建议：**
- 历史列表引入虚拟滚动（`react-window` 或 `react-virtuoso`），仅渲染可视区域内的条目
- 对话历史持久化到 `localStorage`，页面刷新后恢复
- 提供"清空对话"和"导出对话记录"功能
- 限制前端展示的历史条数（如最近50轮），更早的按需加载

### 5. 缺少错误边界和优雅降级
前端无 `ErrorBoundary` 组件，任何一个子组件（如 `KnowledgeGraphVisualization`、`ReasoningPathVisualization`）抛出异常都会导致整个应用白屏。网络请求失败仅用 `alert()` 弹窗（第85行），用户体验差。

**优化建议：**
- 添加 React `ErrorBoundary` 包裹各功能模块，捕获异常后展示降级 UI（如"可视化加载失败，请查看文本信息"）
- 将 `alert()` 替换为内联 Toast/Notification 组件，不影响用户操作
- 网络超时/失败时提供"重试"按钮，而非仅弹窗提示

### 6. 废弃 API 使用
`QuestionAnswer.js` 第182行使用 `onKeyPress` 事件，该事件在 React 中已被标记为废弃（deprecated），在未来的 React 版本中可能被移除。

**优化建议：**
- 将 `onKeyPress` 替换为 `onKeyDown`，逻辑不变

### 7. 缺少移动端适配
CSS 使用固定像素宽度（如 `KnowledgeGraphVisualization` 中 SVG 固定 800×600），在移动设备上布局溢出，触摸交互（如 KG 节点点击、推理步骤展开）在小屏幕上操作困难。

**优化建议：**
- SVG 宽高改为百分比或 `viewBox` 自适应
- 整体布局采用 CSS Grid/Flexbox + 媒体查询做响应式断点
- 移动端下 KG 可视化可切换为列表模式，推理路径改为纵向堆叠
- 历史记录侧边栏在窄屏下改为可折叠抽屉

### 8. 组件懒加载缺失
`App.js` 中所有路由页面（`TCMPage`、`TCMDetailDisease`、`TCMDetailFormula`、`TCMDetailHerb`、`TCMDetailAcupuncture`）均在首屏同步加载，初始 bundle 体积大，首屏渲染慢。

**优化建议：**
- 使用 `React.lazy()` + `Suspense` 对非首屏路由做代码分割
- `KnowledgeGraphVisualization` 和 `ReasoningPathVisualization` 作为重型组件也做懒加载

### 9. 无障碍性（a11y）缺失
全站无 ARIA 属性、无键盘导航支持、无焦点管理。输入框无 `aria-label`，实体标签仅靠颜色区分（色盲用户无法识别），KG 可视化中的 SVG 节点无法通过键盘访问。

**优化建议：**
- 为交互元素添加 `aria-label`、`role` 属性
- 为实体类型标签在颜色之外增加图标或文字标识
- SVG 节点添加 `<title>` 子元素和 `tabindex` 支持键盘聚焦
- 提交按钮在 loading 状态下添加 `aria-busy="true"`

### 10. 状态管理随规模增长难以维护
`QuestionAnswer.js` 使用 12 个 `useState` 管理状态，状态更新逻辑分散在多个回调中。随着功能增加（用户登录、收藏、对话分支等），组件会进一步膨胀。

**优化建议：**
- 引入 `useReducer` 将相关状态聚合为有限状态机（如 `{idle, loading, streaming, done, error}`）
- 或引入轻量状态管理方案（`zustand` 或 React Context + useReducer），将问答逻辑与 UI 渲染分离