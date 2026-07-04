"""
协调者 Agent — 意图分类 + 复杂度评估 + DAG 执行计划生成 + 运行时调度
调度Agent作为中枢，全程参与决策，动态调整任务流程
"""

from core.base_agent import BaseAgent
from typing import Dict, List


INTENT_TEMPLATE = """你是一位中医临床决策协调专家。请分析用户问题，输出JSON格式。

用户问题: {question}

请输出:
{{
    "intent": "diagnosis" | "prescription" | "acupuncture" | "simple_qa" | "knowledge_learning",
    "complexity": "simple" | "medium" | "complex",
    "reason": "简述分类理由"
}}

分类标准:
- diagnosis: 包含症状、舌脉、体征，寻求证候判断
- prescription: 已明确证候/病名，寻求方剂或药物治疗
- acupuncture: 涉及腧穴、经脉、针灸治疗
- simple_qa: 简单的知识问答（"人参有什么功效"、"什么是经络"）
- knowledge_learning: 涉及引入新知识、纠正或补充"""


class OrchestratorAgent(BaseAgent):
    """协调者 Agent"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("orchestrator", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        question = payload.get("question", "")
        conversation_history = payload.get("conversation_history", [])

        # 1. 意图分类
        classification = self._classify_intent(question)
        intent = classification.get("intent", "simple_qa")
        complexity = classification.get("complexity", "simple")

        # 2. 生成执行计划 DAG
        plan = self._build_plan(intent, complexity, question, conversation_history)

        return {
            "intent": intent,
            "complexity": complexity,
            "reason": classification.get("reason", ""),
            "plan": plan,
            "plan_summary": " → ".join([t["task_id"] for t in plan])
        }

    def _classify_intent(self, question: str) -> Dict:
        prompt = INTENT_TEMPLATE.format(question=question)
        messages = [{"role": "user", "content": prompt}]
        try:
            response = self._llm_call(messages, temperature=0.2, max_tokens=300)
            return self._parse_json_response(response)
        except Exception:
            return {"intent": "simple_qa", "complexity": "simple"}

    def _build_plan(self, intent: str, complexity: str,
                    question: str, history: list) -> list:
        """根据意图和复杂度生成 DAG 执行计划"""

        plans = {
            "simple_qa": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "L1"}, "depends_on": ["entity_recognition"]},
                {"task_id": "generate_answer", "agent": "explanation",
                 "params": {"question": question, "layer": "simple"},
                 "depends_on": ["kg_query"]},
            ],

            "diagnosis": {
                "simple": [
                    {"task_id": "entity_recognition", "agent": "entity_recognition",
                     "params": {"question": question}, "depends_on": []},
                    {"task_id": "kg_query", "agent": "kg_query",
                     "params": {"layer": "L2"}, "depends_on": ["entity_recognition"]},
                    {"task_id": "diagnosis", "agent": "diagnosis",
                     "params": {"question": question, "complexity": "simple"},
                     "depends_on": ["kg_query"]},
                    {"task_id": "review", "agent": "review",
                     "params": {}, "depends_on": ["diagnosis"]},
                    {"task_id": "explanation", "agent": "explanation",
                     "params": {"question": question, "layer": "full"},
                     "depends_on": ["diagnosis", "review"]},
                ],
                "medium": [
                    {"task_id": "entity_recognition", "agent": "entity_recognition",
                     "params": {"question": question}, "depends_on": []},
                    {"task_id": "kg_query", "agent": "kg_query",
                     "params": {"layer": "ALL"}, "depends_on": ["entity_recognition"]},
                    {"task_id": "diagnosis", "agent": "diagnosis",
                     "params": {"question": question, "complexity": "medium"},
                     "depends_on": ["kg_query"]},
                    {"task_id": "formula", "agent": "formula",
                     "params": {}, "depends_on": ["diagnosis"]},
                    {"task_id": "review", "agent": "review",
                     "params": {}, "depends_on": ["diagnosis", "formula"]},
                    {"task_id": "explanation", "agent": "explanation",
                     "params": {"question": question, "layer": "full"},
                     "depends_on": ["diagnosis", "formula", "review"]},
                ],
                "complex": [
                    {"task_id": "entity_recognition", "agent": "entity_recognition",
                     "params": {"question": question}, "depends_on": []},
                    {"task_id": "kg_query", "agent": "kg_query",
                     "params": {"layer": "ALL"}, "depends_on": ["entity_recognition"]},
                    {"task_id": "diagnosis", "agent": "diagnosis",
                     "params": {"question": question, "complexity": "complex"},
                     "depends_on": ["kg_query"]},
                    {"task_id": "formula", "agent": "formula",
                     "params": {"include_acupuncture": True},
                     "depends_on": ["diagnosis"]},
                    {"task_id": "review", "agent": "review",
                     "params": {"strict": True},
                     "depends_on": ["diagnosis", "formula"]},
                    {"task_id": "explanation", "agent": "explanation",
                     "params": {"question": question, "layer": "full"},
                     "depends_on": ["diagnosis", "formula", "review"]},
                    {"task_id": "continuous_learning", "agent": "continuous_learning",
                     "params": {}, "depends_on": ["explanation"]},
                ],
            },

            "prescription": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "L2"}, "depends_on": ["entity_recognition"]},
                {"task_id": "formula", "agent": "formula",
                 "params": {"question": question},
                 "depends_on": ["kg_query"]},
                {"task_id": "review", "agent": "review",
                 "params": {}, "depends_on": ["formula"]},
                {"task_id": "explanation", "agent": "explanation",
                 "params": {"question": question, "layer": "full"},
                 "depends_on": ["formula", "review"]},
            ],

            "acupuncture": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "ALL"}, "depends_on": ["entity_recognition"]},
                {"task_id": "acupuncture", "agent": "acupuncture",
                 "params": {"question": question, "mode": "acupuncture"},
                 "depends_on": ["kg_query"]},
                {"task_id": "explanation", "agent": "explanation",
                 "params": {"question": question, "layer": "full"},
                 "depends_on": ["acupuncture"]},
            ],

            "knowledge_learning": [
                {"task_id": "entity_recognition", "agent": "entity_recognition",
                 "params": {"question": question}, "depends_on": []},
                {"task_id": "kg_query", "agent": "kg_query",
                 "params": {"layer": "L2"}, "depends_on": ["entity_recognition"]},
                {"task_id": "generate_answer", "agent": "explanation",
                 "params": {"question": question, "layer": "simple"},
                 "depends_on": ["kg_query"]},
                {"task_id": "continuous_learning", "agent": "continuous_learning",
                 "params": {"source": "user_query"},
                 "depends_on": ["generate_answer"]},
            ],
        }

        if intent in plans:
            if intent == "diagnosis" and complexity in plans["diagnosis"]:
                return plans["diagnosis"][complexity]
            return plans[intent]

        return plans["simple_qa"]

    # ══════════════════════════════════════════════════════════
    # 运行时调度接口 — 调度Agent作为中枢，全程参与
    # ══════════════════════════════════════════════════════════

    def checkpoint_review(self, step_name: str, step_result: Dict,
                          plan_state: Dict) -> Dict:
        """
        审查每步结果，返回决策

        Args:
            step_name: 当前步骤的agent名称
            step_result: 当前步骤的执行结果
            plan_state: DAG执行状态快照

        Returns:
            {"action": "continue"|"wait_user"|"add_task"|"skip"|"done",
             ...附加信息}
        """
        if step_name == "kg_query":
            return self._review_kg_query(step_result, plan_state)
        elif step_name == "diagnosis":
            return self._review_diagnosis(step_result, plan_state)
        elif step_name == "review":
            return self._review_review_result(step_result, plan_state)
        elif step_name in ("formula", "acupuncture", "regimen"):
            return {"action": "continue"}
        elif step_name == "entity_recognition":
            return {"action": "continue"}
        return {"action": "continue"}

    def _review_kg_query(self, step_result: Dict, plan_state: Dict) -> Dict:
        """审查KG查询结果，扫描 subgraph 中的候选疾病标记"""
        if not step_result:
            return {"action": "continue"}

        subgraph = step_result.get("subgraph", {})
        # 扫描 subgraph 中标记为候选的疾病
        candidate_diseases = []
        for entity_text, data in subgraph.items():
            if isinstance(data, dict) and data.get("candidate", False):
                candidate_diseases.append({
                    "disease": entity_text.replace("(候选)", ""),
                    "hit_count": data.get("hit_count", 0),
                    "symptoms": data.get("symptoms", []),
                    "symptom_count": data.get("symptom_count", 0)
                })

        if candidate_diseases:
            return {
                "action": "add_task",
                "reason": f"KG发现{len(candidate_diseases)}个候选疾病，需要辨证Agent问诊确认",
                "new_tasks": [{
                    "task_id": "diagnosis_inquiry",
                    "agent": "diagnosis",
                    "params": {
                        "mode": "inquiry",
                        "candidate_diseases": candidate_diseases
                    },
                    "depends_on": ["kg_query"]
                }],
                "candidate_diseases": candidate_diseases
            }

        return {"action": "continue"}

    def _generate_disease_inquiry(self, candidate_diseases: List) -> List[str]:
        """生成简单的疾病确认问题"""
        questions = []
        for disease in candidate_diseases[:3]:
            name = disease.get("name", "") if isinstance(disease, dict) else str(disease)
            if name:
                questions.append(f"您是否有以下疾病：{name}？")
        return questions

    def _review_diagnosis(self, step_result: Dict, plan_state: Dict) -> Dict:
        """审查辨证结果"""
        if not step_result:
            return {"action": "continue"}

        # 如果是问诊任务（diagnosis_inquiry 产生的结果）
        if step_result.get("need_inquiry") and step_result.get("inquiries"):
            return {
                "action": "wait_user",
                "reason": "辨证Agent生成了问诊问题，等待用户回答",
                "inquiries": step_result.get("inquiries", []),
                "candidate_diseases": step_result.get("candidate_diseases", [])
            }

        # 如果是用户回答后的确认结果
        confirmed_diseases = step_result.get("confirmed_diseases", [])
        if confirmed_diseases and step_result.get("request_kg_supplement"):
            new_tasks = []
            for disease in confirmed_diseases:
                disease_name = disease.get("name", "") if isinstance(disease, dict) else str(disease)
                if disease_name:
                    new_tasks.append({
                        "task_id": f"kg_supplement_{disease_name}",
                        "agent": "kg_query",
                        "params": {
                            "entity_text": disease_name,
                            "entity_type": "疾病",
                            "layer": "ALL",
                            "mode": "supplement"
                        },
                        "depends_on": ["diagnosis"]
                    })
            return {
                "action": "add_task",
                "reason": f"确认疾病后补充KG查询: {', '.join(d.get('name','') if isinstance(d, dict) else str(d) for d in confirmed_diseases)}",
                "new_tasks": new_tasks,
                "confirmed_diseases": confirmed_diseases
            }

        # 正常辨证推理结果 — 继续原有逻辑
        return self.decide_after_diagnosis(step_result, plan_state)

    def decide_after_diagnosis(self, diagnosis_result: Dict,
                               plan_state: Dict) -> Dict:
        """根据辨证结果决定后续调用哪些Agent"""
        if not diagnosis_result:
            return {"action": "continue"}

        overall_confidence = diagnosis_result.get("overall_confidence", 0.5)
        syndrome = diagnosis_result.get("syndrome", {})
        primary = syndrome.get("primary", {})
        primary_name = primary.get("name", "")
        primary_label = primary.get("label", "")

        tasks_to_add = []

        if primary_label == "DIS" and primary_name:
            tasks_to_add.append({
                "task_id": "kg_supplement_diagnosis",
                "agent": "kg_query",
                "params": {
                    "entity_text": primary_name,
                    "entity_type": "疾病",
                    "layer": "ALL",
                    "mode": "supplement"
                },
                "depends_on": []
            })

        if overall_confidence < 0.4:
            return {
                "action": "skip",
                "reason": f"辨证置信度过低({overall_confidence})，跳过治疗推荐",
                "skip_tasks": ["formula", "acupuncture", "regimen"]
            }

        return {"action": "continue"}

    def _review_review_result(self, step_result: Dict,
                              plan_state: Dict) -> Dict:
        """审查审核结果"""
        if not step_result:
            return {"action": "continue"}
        return self.decide_after_review(step_result, plan_state)

    def decide_after_review(self, review_result: Dict,
                            plan_state: Dict) -> Dict:
        """根据审核结果决定是否辩论或回退"""
        if not review_result:
            return {"action": "continue"}

        conflicts = review_result.get("conflicts", [])
        if not conflicts:
            return {"action": "continue"}

        severe_conflicts = [c for c in conflicts
                           if c.get("severity") in ("high", "critical")]
        if severe_conflicts:
            return {
                "action": "debate",
                "reason": f"发现{len(severe_conflicts)}个严重冲突，需要辩论",
                "conflicts": severe_conflicts
            }

        return {"action": "continue"}

    def split_subgraph(self, subgraph: Dict) -> Dict:
        """
        将KG查询结果拆分为三个专属子图

        拆分规则:
        - 方剂子图: 治疗_from_PRE, 治疗_from_MED, 组成_from_MED, 组成_PRE
        - 针灸子图: 治疗_from_ACU, 归属于_MER
        - 养生子图: 治疗_from_MED, 体质实体整体
        """
        formula_subgraph = {}
        acupuncture_subgraph = {}
        regimen_subgraph = {}

        formula_rel_keys = ["治疗_from_PRE", "治疗_from_MED", "组成_from_MED", "组成_PRE"]
        acupuncture_rel_keys = ["治疗_from_ACU", "归属于_MER"]
        regimen_rel_keys = ["治疗_from_MED"]

        for entity_text, data in subgraph.items():
            entity_type = data.get("type", "")
            relations = data.get("relations", {})

            formula_filtered = {}
            for key, values in relations.items():
                if any(rel_key in key for rel_key in formula_rel_keys):
                    formula_filtered[key] = values
            if formula_filtered or entity_type in ("PRE", "MED"):
                if formula_filtered:
                    formula_subgraph[entity_text] = {
                        "type": entity_type,
                        "relations": formula_filtered,
                        "relation_count": sum(len(v) for v in formula_filtered.values())
                    }

            acupuncture_filtered = {}
            for key, values in relations.items():
                if any(rel_key in key for rel_key in acupuncture_rel_keys):
                    acupuncture_filtered[key] = values
            if acupuncture_filtered or entity_type == "ACU":
                if acupuncture_filtered:
                    acupuncture_subgraph[entity_text] = {
                        "type": entity_type,
                        "relations": acupuncture_filtered,
                        "relation_count": sum(len(v) for v in acupuncture_filtered.values())
                    }

            regimen_filtered = {}
            for key, values in relations.items():
                if any(rel_key in key for rel_key in regimen_rel_keys):
                    regimen_filtered[key] = values
                elif entity_type == "CON":
                    regimen_filtered[key] = values
            if regimen_filtered or entity_type == "CON":
                regimen_subgraph[entity_text] = {
                    "type": entity_type,
                    "relations": regimen_filtered,
                    "relation_count": sum(len(v) for v in regimen_filtered.values())
                }

        return {
            "formula_subgraph": formula_subgraph,
            "acupuncture_subgraph": acupuncture_subgraph,
            "regimen_subgraph": regimen_subgraph
        }

    def generate_final_answer(self, all_results: Dict, question: str) -> Dict:
        """
        汇总所有Agent结果，生成最终答案

        Args:
            all_results: 各Agent的执行结果
            question: 用户原始问题

        Returns:
            最终答案结构
        """
        diagnosis = all_results.get("diagnosis", {})
        formula = all_results.get("formula", {})
        acupuncture = all_results.get("acupuncture", {})
        regimen = all_results.get("regimen", {})
        review = all_results.get("review", {})

        syndrome = diagnosis.get("syndrome", {})
        primary = syndrome.get("primary", {})
        treatment_principle = diagnosis.get("treatment_principle", "")

        prompt = f"""请根据以下中医诊疗信息，生成对患者友好的综合回答：

患者问题：{question}

辨证结果：{primary.get('name', '待确定')}（置信度：{primary.get('confidence', 0)}）
治则：{treatment_principle}

方剂推荐：{self._summarize_agent_result(formula)}
针灸方案：{self._summarize_agent_result(acupuncture)}
养生建议：{self._summarize_agent_result(regimen)}

审核结果：{self._summarize_agent_result(review)}

请生成结构化的综合回答，包含：辨证结论、治疗建议（方剂+针灸+养生）、注意事项。
输出JSON格式：{{"conclusion": "...", "treatment": {{...}}, "precautions": [...]}}"""

        messages = [{"role": "user", "content": prompt}]
        response = self._llm_call(messages, temperature=0.5, max_tokens=1500)
        result = self._parse_json_response(response)

        if not result:
            result = {
                "conclusion": primary.get("name", "待确定"),
                "treatment": {},
                "precautions": []
            }

        return {
            "answer": result,
            "diagnosis": diagnosis,
            "formula": formula,
            "acupuncture": acupuncture,
            "regimen": regimen,
            "review": review,
            "overall_confidence": diagnosis.get("overall_confidence", 0.5)
        }

    def _summarize_agent_result(self, result: Dict) -> str:
        """简要汇总Agent结果"""
        if not result:
            return "无"
        parts = []
        if "primary_formula" in result:
            parts.append(f"主方: {result['primary_formula'].get('name', '')}")
        if "primary_points" in result:
            pts = [p.get("name", "") for p in result["primary_points"][:5]]
            parts.append(f"主穴: {', '.join(pts)}")
        if "dietary_advice" in result:
            parts.append(f"饮食: {result['dietary_advice'][:100]}")
        if "conflicts" in result:
            parts.append(f"冲突: {len(result['conflicts'])}个")
        if "syndrome" in result:
            s = result["syndrome"].get("primary", {})
            parts.append(f"证候: {s.get('name', '')}")
        return " | ".join(parts) if parts else "已完成"