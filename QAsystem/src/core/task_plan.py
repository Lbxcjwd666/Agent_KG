"""
DAG 任务规划与执行引擎
支持依赖结果自动注入 + 并行执行 + 运行时动态调度
"""

from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging
import copy


@dataclass
class TaskNode:
    """DAG 任务节点"""
    task_id: str
    agent_name: str
    params: Dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    status: str = "pending"     # pending | running | done | skipped | failed
    result: Optional[Dict] = None
    duration_ms: int = 0
    injected_params: Optional[Dict] = None


class DAGExecutor:
    """DAG 任务执行器 — 支持并行调度与依赖结果注入"""

    def __init__(self, max_workers: int = 4):
        self.tasks: Dict[str, TaskNode] = {}
        self.max_workers = max_workers
        self.logger = logging.getLogger("dag_executor")

    @classmethod
    def from_plan(cls, plan: List[Dict], max_workers: int = 4) -> "DAGExecutor":
        """
        从 JSON 计划构建执行器

        plan 格式:
        [
            {
                "task_id": "entity_recognition",
                "agent": "entity_recognition",
                "params": {"question": "..."},
                "depends_on": []
            },
            ...
        ]
        """
        executor = cls(max_workers=max_workers)
        for item in plan:
            task = TaskNode(
                task_id=item["task_id"],
                agent_name=item.get("agent", item["task_id"]),
                params=item.get("params", {}),
                depends_on=item.get("depends_on", [])
            )
            executor.add_task(task)
        return executor

    def add_task(self, task: TaskNode):
        """添加任务"""
        self.tasks[task.task_id] = task

    def validate(self) -> bool:
        """验证 DAG 合法性（无环、无缺失依赖）"""
        task_ids = set(self.tasks.keys())
        for task in self.tasks.values():
            for dep in task.depends_on:
                if dep not in task_ids:
                    self.logger.error(f"任务 '{task.task_id}' 依赖的 '{dep}' 不存在")
                    return False
        in_degree = {tid: len(t.depends_on) for tid, t in self.tasks.items()}
        q = deque([tid for tid, deg in in_degree.items() if deg == 0])
        visited = 0
        while q:
            tid = q.popleft()
            visited += 1
            for t in self.tasks.values():
                if tid in t.depends_on:
                    in_degree[t.task_id] -= 1
                    if in_degree[t.task_id] == 0:
                        q.append(t.task_id)
        if visited != len(self.tasks):
            self.logger.error("DAG 存在环")
            return False
        return True

    def _ready_tasks(self) -> List[TaskNode]:
        """获取所有依赖已满足的待执行任务"""
        ready = []
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            if all(self.tasks[dep].status in ("done", "skipped") for dep in task.depends_on):
                ready.append(task)
        return ready

    def _has_failed_dependency(self, task: TaskNode) -> bool:
        """检查是否有依赖失败"""
        return any(
            self.tasks[dep].status == "failed"
            for dep in task.depends_on
        )

    def _inject_dependency_results(self, task: TaskNode) -> Dict:
        """
        将依赖任务的输出结果注入到当前任务的参数中

        注入规则:
        - 将每个依赖任务的结果以 task_id 为 key 合并到 params 中
        - 特殊映射: diagnosis → diagnosis, kg_query → kg_context 等
        """
        params = copy.deepcopy(task.params)

        for dep_id in task.depends_on:
            dep_task = self.tasks.get(dep_id)
            if not dep_task or not dep_task.result:
                continue

            dep_result = {k: v for k, v in dep_task.result.items() if not k.startswith("_")}

            if dep_id == "entity_recognition":
                params["entities"] = dep_result.get("entities", [])
                params["entity_count"] = dep_result.get("entity_count", 0)
            elif dep_id == "kg_query":
                params["kg_context"] = dep_result.get("kg_context", "")
                params["subgraph"] = dep_result.get("subgraph", {})
                agent_name = task.agent_name
                if agent_name == "formula" and "formula_subgraph" in dep_result:
                    params["subgraph"] = dep_result["formula_subgraph"]
                elif agent_name == "acupuncture" and "acupuncture_subgraph" in dep_result:
                    params["subgraph"] = dep_result["acupuncture_subgraph"]
                elif agent_name == "regimen" and "regimen_subgraph" in dep_result:
                    params["subgraph"] = dep_result["regimen_subgraph"]
            elif dep_id == "diagnosis":
                params["diagnosis"] = dep_result
                params["syndrome"] = dep_result.get("syndrome", {})
                params["treatment_principle"] = dep_result.get("treatment_principle", "")
                # 问诊任务注入候选疾病
                if task.task_id == "diagnosis_inquiry":
                    params["candidate_diseases"] = dep_result.get("candidate_diseases", [])
            elif dep_id.startswith("kg_supplement_"):
                # 补充查询任务结果合并到 kg_query 的 subgraph
                params["subgraph"] = dep_result.get("subgraph", {})
            elif dep_id in ("formula", "prescription"):
                params["formula"] = dep_result
            elif dep_id == "acupuncture":
                params["acupuncture"] = dep_result
            elif dep_id == "regimen":
                params["regimen"] = dep_result
            elif dep_id in ("review", "verification"):
                params["review"] = dep_result
            else:
                params[dep_id] = dep_result

        return params

    def _execute_task(self, task: TaskNode, bus) -> Dict:
        """执行单个任务"""
        self.logger.info(f"执行任务: {task.task_id} -> {task.agent_name}")
        task.status = "running"

        bus.publish("agent_start", {
            "agent": task.agent_name,
            "task_id": task.task_id,
            "params_summary": list(task.params.keys())
        })

        injected_params = self._inject_dependency_results(task)

        t0 = time.time()
        result = bus.request(task.agent_name, injected_params)
        task.duration_ms = int((time.time() - t0) * 1000)

        task.injected_params = _truncate_dict(injected_params, max_str=500)

        meta = result.get("_meta", {})
        if meta.get("status") == "error":
            task.status = "failed"
            self.logger.error(f"任务 '{task.task_id}' 失败: {meta.get('error')}")
        else:
            task.status = "done"
            task.result = result

        bus.publish("agent_done", {
            "agent": task.agent_name,
            "task_id": task.task_id,
            "status": task.status,
            "duration_ms": task.duration_ms
        })

        return result

    def execute(self, bus) -> Dict:
        """
        同步执行 DAG（内部并行调度无依赖的任务）

        Args:
            bus: AgentBus 实例

        Returns:
            所有任务的汇总结果
        """
        if not self.validate():
            return {"_meta": {"status": "error", "error": "DAG 验证失败"}}

        results = {}
        start_time = time.time()

        while True:
            ready = self._ready_tasks()
            if not ready:
                pending = [t for t in self.tasks.values() if t.status == "pending"]
                if not pending:
                    break
                for task in pending:
                    if self._has_failed_dependency(task):
                        task.status = "skipped"
                        self.logger.warning(f"跳过任务 '{task.task_id}' (依赖失败)")
                if all(t.status != "pending" for t in self.tasks.values()):
                    break
                break

            if len(ready) == 1:
                result = self._execute_task(ready[0], bus)
                if ready[0].status == "done":
                    results[ready[0].task_id] = result
            else:
                with ThreadPoolExecutor(max_workers=min(len(ready), self.max_workers)) as pool:
                    futures = {
                        pool.submit(self._execute_task, task, bus): task
                        for task in ready
                    }
                    for future in as_completed(futures):
                        task = futures[future]
                        try:
                            result = future.result()
                            if task.status == "done":
                                results[task.task_id] = result
                        except Exception as e:
                            task.status = "failed"
                            self.logger.error(f"并行任务 '{task.task_id}' 异常: {e}")

        total_ms = int((time.time() - start_time) * 1000)
        return {
            "results": results,
            "_meta": {
                "status": "ok",
                "total_duration_ms": total_ms,
                "task_count": len(self.tasks),
                "done_count": sum(1 for t in self.tasks.values() if t.status == "done"),
                "failed_count": sum(1 for t in self.tasks.values() if t.status == "failed"),
                "skipped_count": sum(1 for t in self.tasks.values() if t.status == "skipped"),
            }
        }

    def execute_stream(self, bus, on_task_start: Callable = None,
                       on_task_done: Callable = None) -> Dict:
        """
        流式执行 DAG，通过回调通知任务状态变更（用于 SSE）

        Args:
            bus: AgentBus 实例
            on_task_start: 任务开始回调 (task_id, agent_name) -> None
            on_task_done: 任务完成回调 (task_id, agent_name, status, result) -> None

        Returns:
            所有任务的汇总结果
        """
        if not self.validate():
            return {"_meta": {"status": "error", "error": "DAG 验证失败"}}

        results = {}
        start_time = time.time()

        while True:
            ready = self._ready_tasks()
            if not ready:
                pending = [t for t in self.tasks.values() if t.status == "pending"]
                if not pending:
                    break
                for task in pending:
                    if self._has_failed_dependency(task):
                        task.status = "skipped"
                        self.logger.warning(f"跳过任务 '{task.task_id}' (依赖失败)")
                if all(t.status != "pending" for t in self.tasks.values()):
                    break
                break

            if len(ready) == 1:
                task = ready[0]
                if on_task_start:
                    on_task_start(task.task_id, task.agent_name)
                result = self._execute_task(task, bus)
                if task.status == "done":
                    results[task.task_id] = result
                if on_task_done:
                    on_task_done(task.task_id, task.agent_name, task.status, result)
            else:
                with ThreadPoolExecutor(max_workers=min(len(ready), self.max_workers)) as pool:
                    futures = {}
                    for task in ready:
                        if on_task_start:
                            on_task_start(task.task_id, task.agent_name)
                        fut = pool.submit(self._execute_task, task, bus)
                        futures[fut] = task

                    for future in as_completed(futures):
                        task = futures[future]
                        try:
                            result = future.result()
                            if task.status == "done":
                                results[task.task_id] = result
                            if on_task_done:
                                on_task_done(task.task_id, task.agent_name, task.status, result)
                        except Exception as e:
                            task.status = "failed"
                            self.logger.error(f"并行任务 '{task.task_id}' 异常: {e}")
                            if on_task_done:
                                on_task_done(task.task_id, task.agent_name, "failed", {})

        total_ms = int((time.time() - start_time) * 1000)
        return {
            "results": results,
            "_meta": {
                "status": "ok",
                "total_duration_ms": total_ms,
                "task_count": len(self.tasks),
                "done_count": sum(1 for t in self.tasks.values() if t.status == "done"),
                "failed_count": sum(1 for t in self.tasks.values() if t.status == "failed"),
                "skipped_count": sum(1 for t in self.tasks.values() if t.status == "skipped"),
            }
        }

    def get_trace(self) -> List[Dict]:
        """获取所有任务的输入输出trace（用于调试可视化）"""
        trace = []
        for task in self.tasks.values():
            entry = {
                "task_id": task.task_id,
                "agent": task.agent_name,
                "status": task.status,
                "depends_on": task.depends_on,
                "duration_ms": task.duration_ms,
                "input": task.injected_params or task.params,
                "output": _truncate_dict(task.result, max_str=500) if task.result else None,
            }
            trace.append(entry)
        return trace

    # ══════════════════════════════════════════════════════════
    # 运行时调度接口 — 供调度Agent逐步控制执行
    # ══════════════════════════════════════════════════════════

    def all_done(self) -> bool:
        """判断是否所有任务都已完成（done/skipped/failed）"""
        return all(t.status in ("done", "skipped", "failed") for t in self.tasks.values())

    def get_state(self) -> Dict:
        """返回当前执行状态快照"""
        return {
            "total": len(self.tasks),
            "done": sum(1 for t in self.tasks.values() if t.status == "done"),
            "pending": sum(1 for t in self.tasks.values() if t.status == "pending"),
            "running": sum(1 for t in self.tasks.values() if t.status == "running"),
            "failed": sum(1 for t in self.tasks.values() if t.status == "failed"),
            "skipped": sum(1 for t in self.tasks.values() if t.status == "skipped"),
            "tasks": {
                tid: {
                    "agent": t.agent_name,
                    "status": t.status,
                    "depends_on": t.depends_on,
                    "duration_ms": t.duration_ms
                }
                for tid, t in self.tasks.items()
            }
        }

    def get_ready_agents(self) -> List[Dict]:
        """返回当前可执行的Agent列表（依赖已满足且pending）"""
        ready = self._ready_tasks()
        return [
            {
                "task_id": t.task_id,
                "agent": t.agent_name,
                "depends_on": t.depends_on,
                "params": t.params
            }
            for t in ready
        ]

    def execute_step(self, bus, on_task_start: Callable = None,
                     on_task_done: Callable = None) -> Dict:
        """
        逐步执行：执行当前可执行的一批任务（无依赖的单个执行，有并行则并行）
        返回本步执行结果和剩余状态

        Returns:
            {
                "executed": [{"task_id": ..., "agent": ..., "status": ..., "result": ...}],
                "remaining": [task_id, ...],
                "all_done": bool
            }
        """
        ready = self._ready_tasks()
        if not ready:
            pending = [t for t in self.tasks.values() if t.status == "pending"]
            if pending:
                for task in pending:
                    if self._has_failed_dependency(task):
                        task.status = "skipped"
                        self.logger.warning(f"跳过任务 '{task.task_id}' (依赖失败)")
            return {
                "executed": [],
                "remaining": [t.task_id for t in self.tasks.values() if t.status == "pending"],
                "all_done": self.all_done()
            }

        executed = []

        if len(ready) == 1:
            task = ready[0]
            if on_task_start:
                on_task_start(task.task_id, task.agent_name)
            result = self._execute_task(task, bus)
            if on_task_done:
                on_task_done(task.task_id, task.agent_name, task.status, result)
            executed.append({
                "task_id": task.task_id,
                "agent": task.agent_name,
                "status": task.status,
                "result": result if task.status == "done" else None
            })
        else:
            with ThreadPoolExecutor(max_workers=min(len(ready), self.max_workers)) as pool:
                futures = {}
                for task in ready:
                    if on_task_start:
                        on_task_start(task.task_id, task.agent_name)
                    fut = pool.submit(self._execute_task, task, bus)
                    futures[fut] = task

                for future in as_completed(futures):
                    task = futures[future]
                    try:
                        result = future.result()
                        executed.append({
                            "task_id": task.task_id,
                            "agent": task.agent_name,
                            "status": task.status,
                            "result": result if task.status == "done" else None
                        })
                        if on_task_done:
                            on_task_done(task.task_id, task.agent_name, task.status, result)
                    except Exception as e:
                        task.status = "failed"
                        self.logger.error(f"并行任务 '{task.task_id}' 异常: {e}")
                        executed.append({
                            "task_id": task.task_id,
                            "agent": task.agent_name,
                            "status": "failed",
                            "result": None
                        })
                        if on_task_done:
                            on_task_done(task.task_id, task.agent_name, "failed", {})

        return {
            "executed": executed,
            "remaining": [t.task_id for t in self.tasks.values() if t.status == "pending"],
            "all_done": self.all_done()
        }

    def add_task_by_def(self, task_def: Dict):
        """
        动态追加任务

        task_def 格式:
        {
            "task_id": "kg_supplement",
            "agent": "kg_query",
            "params": {"entity_text": "心积", "entity_type": "疾病"},
            "depends_on": ["diagnosis"]
        }
        """
        task_id = task_def.get("task_id", f"dynamic_{int(time.time()*1000)}")
        if task_id in self.tasks:
            self.logger.warning(f"任务 '{task_id}' 已存在，跳过追加")
            return

        task = TaskNode(
            task_id=task_id,
            agent_name=task_def.get("agent", task_id),
            params=task_def.get("params", {}),
            depends_on=task_def.get("depends_on", [])
        )
        self.tasks[task_id] = task
        self.logger.info(f"动态追加任务: {task_id} -> {task.agent_name}")

    def skip_task(self, task_id: str):
        """跳过指定任务"""
        task = self.tasks.get(task_id)
        if task and task.status == "pending":
            task.status = "skipped"
            self.logger.info(f"跳过任务: {task_id}")

    def modify_task_params(self, task_id: str, new_params: Dict):
        """修改任务的参数（合并，不覆盖已有值除非显式指定）"""
        task = self.tasks.get(task_id)
        if task:
            task.params.update(new_params)
            self.logger.info(f"修改任务参数: {task_id}, 新增keys: {list(new_params.keys())}")

    def set_task_result(self, task_id: str, result: Dict):
        """
        外部设置任务结果（用于注入已完成步骤，如entity_recognition在DAG外已执行）
        """
        task = self.tasks.get(task_id)
        if task:
            task.status = "done"
            task.result = result
            task.injected_params = task.params
            self.logger.info(f"外部注入任务结果: {task_id}")

    def get_task_result(self, task_id: str) -> Optional[Dict]:
        """获取指定任务的结果"""
        task = self.tasks.get(task_id)
        if task and task.status == "done":
            return task.result
        return None


def _truncate_dict(obj, max_str=500, max_list=20, depth=0):
    """截断过长的字典值，防止trace数据过大"""
    if depth > 5:
        return "..."
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj[:max_str] + "..." if len(obj) > max_str else obj
    if isinstance(obj, list):
        truncated = [_truncate_dict(item, max_str, max_list, depth + 1) for item in obj[:max_list]]
        if len(obj) > max_list:
            truncated.append(f"...({len(obj)} items total)")
        return truncated
    if isinstance(obj, dict):
        return {k: _truncate_dict(v, max_str, max_list, depth + 1) for k, v in obj.items()}
    return obj