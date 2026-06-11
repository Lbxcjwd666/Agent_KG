"""
DAG 任务规划与执行引擎
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
import time
import logging


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


class DAGExecutor:
    """DAG 任务执行器"""

    def __init__(self):
        self.tasks: Dict[str, TaskNode] = {}
        self.logger = logging.getLogger("dag_executor")

    @classmethod
    def from_plan(cls, plan: List[Dict]) -> "DAGExecutor":
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
        executor = cls()
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
        # 简单环检测：拓扑排序
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
            if all(self.tasks[dep].status == "done" for dep in task.depends_on):
                ready.append(task)
        return ready

    def _has_failed_dependency(self, task: TaskNode) -> bool:
        """检查是否有依赖失败"""
        return any(
            self.tasks[dep].status == "failed"
            for dep in task.depends_on
        )

    def execute(self, bus) -> Dict:
        """
        执行 DAG

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
                # 检查是否还有 pending 任务（依赖失败导致无法执行）
                pending = [t for t in self.tasks.values() if t.status == "pending"]
                if not pending:
                    break
                # 标记依赖失败的任务为 skipped
                for task in pending:
                    if self._has_failed_dependency(task):
                        task.status = "skipped"
                        self.logger.warning(f"跳过任务 '{task.task_id}' (依赖失败)")
                if all(t.status != "pending" for t in self.tasks.values()):
                    break
                # 还有 pending 但没 ready，等待（不应该在同步执行中发生）
                break

            for task in ready:
                self.logger.info(f"执行任务: {task.task_id} -> {task.agent_name}")
                task.status = "running"

                bus.publish("agent_start", {
                    "agent": task.agent_name,
                    "task_id": task.task_id,
                    "params_summary": list(task.params.keys())
                })

                t0 = time.time()
                result = bus.request(task.agent_name, task.params)
                task.duration_ms = int((time.time() - t0) * 1000)

                meta = result.get("_meta", {})
                if meta.get("status") == "error":
                    task.status = "failed"
                    self.logger.error(f"任务 '{task.task_id}' 失败: {meta.get('error')}")
                else:
                    task.status = "done"
                    task.result = result
                    results[task.task_id] = result

                bus.publish("agent_done", {
                    "agent": task.agent_name,
                    "task_id": task.task_id,
                    "status": task.status,
                    "duration_ms": task.duration_ms
                })

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
