"""
多Agent协同 SSE API — DAG驱动并行管线 + 辩论机制
"""

from flask import Blueprint, request, jsonify, Response
from kg_enhancer import KnowledgeGraphEnhancer
from qwen_api import QwenAPI
from core.agent_bus import AgentBus
from core.task_plan import DAGExecutor
from agents.diagnosis import DiagnosisAgent
from agents.formula import FormulaAgent
from agents.acupuncture import AcupunctureAgent
from agents.regimen import RegimenAgent
from agents.review import ReviewAgent
from agents.entity_recognition import EntityRecognitionAgent
from agents.kg_query import KGQueryAgent
from agents.orchestrator import OrchestratorAgent
from entity_linker import EntityLinker
from config import VECTOR_INDEX_CONFIG, ENTITY_TYPES
import json
import sys
import uuid
import traceback

MAX_DEBATE_ROUNDS = 3

agent_bp = Blueprint("agent", __name__, url_prefix="/api/agent")


def _create_agents(qwen_api, kg_enhancer):
    """创建所有Agent实例"""
    agents = {
        "orchestrator": OrchestratorAgent(qwen_api, kg_enhancer),
        "entity_recognition": EntityRecognitionAgent(qwen_api, kg_enhancer),
        "kg_query": KGQueryAgent(qwen_api, kg_enhancer),
        "diagnosis": DiagnosisAgent(qwen_api, kg_enhancer),
        "formula": FormulaAgent(qwen_api, kg_enhancer),
        "acupuncture": AcupunctureAgent(qwen_api, kg_enhancer),
        "regimen": RegimenAgent(qwen_api, kg_enhancer),
        "review": ReviewAgent(qwen_api, kg_enhancer),
    }
    return agents


def _build_clinical_dag(question: str, entities: list, kg_context: str,
                        complexity: str, subgraph: dict = None) -> list:
    """
    构建临床管线 DAG 计划
    diagnosis 依赖 kg_query，formula/acupuncture/regimen 依赖 diagnosis（三者可并行），review 依赖三者
    subgraph: kg_query的结构化子图结果，传递给下游Agent避免重复查询
    """
    subgraph = subgraph or {}
    return [
        {
            "task_id": "entity_recognition",
            "agent": "entity_recognition",
            "params": {"question": question},
            "depends_on": []
        },
        {
            "task_id": "kg_query",
            "agent": "kg_query",
            "params": {
                "entities": entities,
                "question": question,
                "layer": "L2" if complexity in ("medium", "complex") else "L1"
            },
            "depends_on": ["entity_recognition"]
        },
        {
            "task_id": "diagnosis",
            "agent": "diagnosis",
            "params": {
                "question": question,
                "kg_context": kg_context,
                "subgraph": subgraph,
                "entities": entities,
                "conversation_history": [],
                "collected_info": {},
                "complexity": complexity
            },
            "depends_on": ["kg_query"]
        },
        {
            "task_id": "formula",
            "agent": "formula",
            "params": {"question": question, "kg_context": kg_context, "subgraph": subgraph, "entities": entities},
            "depends_on": ["diagnosis"]
        },
        {
            "task_id": "acupuncture",
            "agent": "acupuncture",
            "params": {"question": question, "kg_context": kg_context, "subgraph": subgraph, "entities": entities},
            "depends_on": ["diagnosis"]
        },
        {
            "task_id": "regimen",
            "agent": "regimen",
            "params": {"question": question, "kg_context": kg_context, "subgraph": subgraph, "entities": entities},
            "depends_on": ["diagnosis"]
        },
        {
            "task_id": "review",
            "agent": "review",
            "params": {"question": question},
            "depends_on": ["formula", "acupuncture", "regimen"]
        },
    ]


@agent_bp.route("/chat/stream", methods=["POST"])
def agent_chat_stream():
    """多Agent协同 SSE 流式端点"""
    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())
    use_debate = data.get("use_debate", True)

    if not question:
        return jsonify({"error": "问题不能为空"}), 400

    qwen_api = QwenAPI()
    kg_enhancer = KnowledgeGraphEnhancer()
    agents = _create_agents(qwen_api, kg_enhancer)
    bus = AgentBus()
    for name, agent in agents.items():
        bus.register(name, agent)

    def sse_event(event_type: str, payload: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def generate():
        # ── Phase 1: Orchestrator ──
        yield sse_event("agent_start", {"agent": "orchestrator"})

        orchestration = agents["orchestrator"].run({
            "question": question,
            "session_id": session_id
        })

        intent = orchestration.get("intent", "simple_qa")
        complexity = orchestration.get("complexity", "simple")

        yield sse_event("agent_done", {
            "agent": "orchestrator",
            "intent": intent,
            "complexity": complexity,
            "plan": orchestration.get("plan_summary", "")
        })

        # ── Phase 2: Entity Recognition + Entity Linking ──
        yield sse_event("agent_start", {"agent": "entity_recognition"})

        raw_entities = qwen_api.extract_entities(question)
        raw_list = []
        for e in (raw_entities or []):
            raw_list.append({
                "text": e.get("text", ""),
                "label": e.get("label", e.get("type", "")),
                "type": e.get("type", e.get("label", ""))
            })

        # 实体链接: 将 LLM 提取的 Mention 链接到 KG 标准实体
        linker = EntityLinker(kg_enhancer, embedding_api=qwen_api)
        linked = linker.link_entities(raw_list)

        entities = []
        for e in linked:
            entities.append({
                "text": e.get("linked_text", e.get("text", "")),
                "label": e.get("linked_label", e.get("label", "")),
                "type": e.get("linked_label", e.get("label", "")),
                "original_text": e.get("original_text", e.get("text", "")),
                "matched_via": e.get("matched_via", "llm_only"),
                "confidence": e.get("confidence", 0.5)
            })

        linking_stats = {
            "exact_match": sum(1 for e in entities if e["matched_via"] == "exact"),
            "alias_match": sum(1 for e in entities if e["matched_via"] == "alias"),
            "vector_match": sum(1 for e in entities if e["matched_via"] == "vector"),
            "fuzzy_match": sum(1 for e in entities if e["matched_via"] == "fuzzy"),
            "unlinked": sum(1 for e in entities if e["matched_via"] == "llm_only")
        }

        yield sse_event("agent_done", {
            "agent": "entity_recognition",
            "entity_count": len(entities),
            "entities": [{"text": e["text"], "type": e["label"], "original_text": e.get("original_text", ""), "matched_via": e.get("matched_via", "")} for e in entities[:10]],
            "linking_stats": linking_stats
        })

        # ── Phase 3: KG Query (提前执行，结果供 DAG 和简单问答共用) ──
        yield sse_event("agent_start", {"agent": "kg_query"})

        kg_context = ""
        kg_full_result = {}
        if entities and kg_enhancer:
            kg_results = agents["kg_query"].run({
                "entities": entities,
                "question": question,
                "layer": "L2" if complexity in ("medium", "complex") else "L1"
            })
            kg_context = kg_results.get("kg_context", "")
            kg_full_result = kg_results

        yield sse_event("agent_done", {
            "agent": "kg_query",
            "has_results": bool(kg_context),
            "relation_count": kg_full_result.get("relation_count", 0),
            "entity_count": kg_full_result.get("entity_count", 0)
        })

        # Simple QA: short-circuit
        if intent in ("simple_qa", "knowledge_learning"):
            yield from _stream_answer(qwen_api, question, kg_context, session_id, sse_event)
            return

        # ── Phase 4-7: 循环调度 — 调度Agent全程参与 ──
        subgraph = kg_full_result.get("subgraph", {})
        dag_plan = _build_clinical_dag(question, entities, kg_context, complexity, subgraph)
        dag = DAGExecutor.from_plan(dag_plan, max_workers=3)

        dag.tasks["entity_recognition"].status = "done"
        dag.tasks["entity_recognition"].result = {"entities": entities, "entity_count": len(entities)}
        dag.tasks["kg_query"].status = "done"
        dag.tasks["kg_query"].result = kg_full_result

        # 调度Agent审查KG查询结果
        kg_decision = agents["orchestrator"].checkpoint_review("kg_query", kg_full_result, dag.get_state())

        if kg_decision.get("action") == "add_task":
            for new_task in kg_decision.get("new_tasks", []):
                dag.add_task_by_def(new_task)
            yield sse_event("plan_update", {
                "reason": kg_decision.get("reason", ""),
                "added_tasks": [t.get("task_id", "") for t in kg_decision.get("new_tasks", [])]
            })

        # 循环执行DAG，每步审查
        all_results = {
            "entity_recognition": {"entities": entities, "entity_count": len(entities)},
            "kg_query": kg_full_result
        }

        while not dag.all_done():
            step_result = dag.execute_step(bus)
            executed = step_result.get("executed", [])

            for exec_info in executed:
                task_id = exec_info.get("task_id", "")
                agent_name = exec_info.get("agent", "")
                status = exec_info.get("status", "")
                result = exec_info.get("result")

                yield sse_event("agent_done", {
                    "agent": agent_name,
                    "status": status
                })

                if status == "done" and result:
                    all_results[agent_name] = result

                    decision = agents["orchestrator"].checkpoint_review(
                        agent_name, result, dag.get_state()
                    )

                    action = decision.get("action", "continue")

                    if action == "wait_user":
                        # 问诊环节：辨证Agent生成了问诊问题
                        inquiries = decision.get("inquiries", [])
                        candidate_diseases = decision.get("candidate_diseases", [])

                        yield sse_event("inquiry", {
                            "reason": decision.get("reason", ""),
                            "candidate_diseases": candidate_diseases,
                            "inquiries": inquiries
                        })
                        return

                    elif action == "add_task":
                        for new_task in decision.get("new_tasks", []):
                            dag.add_task_by_def(new_task)
                        yield sse_event("plan_update", {
                            "reason": decision.get("reason", ""),
                            "added_tasks": [t.get("task_id", "") for t in decision.get("new_tasks", [])]
                        })

                    elif action == "skip":
                        for skip_id in decision.get("skip_tasks", []):
                            dag.skip_task(skip_id)

                    elif action == "done":
                        break

            if step_result.get("all_done"):
                break

        # 拆分子图注入三个Agent
        if kg_full_result.get("subgraph"):
            split_result = agents["orchestrator"].split_subgraph(kg_full_result["subgraph"])
            for key in ("formula_subgraph", "acupuncture_subgraph", "regimen_subgraph"):
                if split_result.get(key):
                    kg_full_result[key] = split_result[key]

        # 补充查询结果合并到子图
        for task_id, task in dag.tasks.items():
            if task_id.startswith("kg_supplement") and task.status == "done" and task.result:
                supplement_subgraph = task.result.get("subgraph", {})
                if supplement_subgraph:
                    kg_full_result.setdefault("subgraph", {}).update(supplement_subgraph)

        # 重新拆分子图
        if kg_full_result.get("subgraph"):
            split_result = agents["orchestrator"].split_subgraph(kg_full_result["subgraph"])
            for key in ("formula_subgraph", "acupuncture_subgraph", "regimen_subgraph"):
                if split_result.get(key):
                    kg_full_result[key] = split_result[key]

        diagnosis = all_results.get("diagnosis", {})
        formula = all_results.get("formula", {})
        acupuncture = all_results.get("acupuncture", {})
        regimen = all_results.get("regimen", {})
        review = all_results.get("review", all_results.get("verification", {}))

        # ── Phase 7: Debate Loop (if conflicts exist and debate enabled) ──
        debate_log = []
        if use_debate and review.get("need_debate") and review.get("debate_items"):
            debate_items = review["debate_items"]
            yield sse_event("debate_start", {
                "conflicts": [{
                    "type": d["conflict_type"],
                    "severity": d["severity"],
                    "agent_a": d["agent_a"],
                    "agent_b": d["agent_b"]
                } for d in debate_items],
                "total_conflicts": len(debate_items)
            })

            for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
                round_args = []
                resolved_all = True

                for item in debate_items:
                    debate_ctx = {
                        "round": round_num,
                        "conflict_type": item["conflict_type"],
                        "kg_evidence": item["kg_evidence"]
                    }

                    # Ask agent_a to reconsider
                    agent_a_name = item["agent_a"]
                    if agent_a_name in agents:
                        yield sse_event("debate_round", {
                            "round": round_num,
                            "agent": agent_a_name,
                            "status": "reconsidering"
                        })

                        debate_payload_a = {
                            "question": question,
                            "diagnosis": diagnosis,
                            "formula": formula,
                            "acupuncture": acupuncture,
                            "regimen": regimen,
                            "debate_context": {
                                **debate_ctx,
                                "role": "defend",
                                "challenge": item["claim_b"],
                                "your_claim": item["claim_a"]
                            }
                        }
                        revised_a = agents[agent_a_name].execute(debate_payload_a, bus=bus)
                        round_args.append({
                            "agent": agent_a_name,
                            "claim": item["claim_a"],
                            "revised_output": _summarize_agent_output(agent_a_name, revised_a)
                        })

                    # Ask agent_b to reconsider
                    agent_b_name = item["agent_b"]
                    if agent_b_name in agents and agent_b_name != agent_a_name:
                        yield sse_event("debate_round", {
                            "round": round_num,
                            "agent": agent_b_name,
                            "status": "reconsidering"
                        })

                        debate_payload_b = {
                            "question": question,
                            "diagnosis": diagnosis,
                            "formula": formula,
                            "acupuncture": acupuncture,
                            "regimen": regimen,
                            "debate_context": {
                                **debate_ctx,
                                "role": "defend",
                                "challenge": item["claim_a"],
                                "your_claim": item["claim_b"]
                            }
                        }
                        revised_b = agents[agent_b_name].execute(debate_payload_b, bus=bus)
                        round_args.append({
                            "agent": agent_b_name,
                            "claim": item["claim_b"],
                            "revised_output": _summarize_agent_output(agent_b_name, revised_b)
                        })

                    # Re-review
                    updated_review = agents["review"].run({
                        "question": question,
                        "diagnosis": diagnosis,
                        "formula": formula,
                        "acupuncture": acupuncture,
                        "regimen": regimen,
                        "debate_context": {
                            "round": round_num,
                            "previous_conflicts": debate_items,
                            "round_arguments": round_args
                        }
                    })

                    # Check if this conflict is resolved
                    still_conflicts = [c for c in updated_review.get("conflicts", [])
                                       if c.get("type") == item["conflict_type"]]
                    if still_conflicts:
                        resolved_all = False

                    debate_log.append({
                        "round": round_num,
                        "conflict_type": item["conflict_type"],
                        "arguments": round_args,
                        "resolved": len(still_conflicts) == 0
                    })

                if resolved_all:
                    yield sse_event("debate_resolved", {
                        "result": "consensus",
                        "rounds": round_num,
                        "log": debate_log
                    })
                    break
            else:
                # Max rounds reached — review agent arbitrates
                yield sse_event("debate_resolved", {
                    "result": "arbitration",
                    "reason": f"辩论{MAX_DEBATE_ROUNDS}轮未达成一致，审核Agent最终仲裁",
                    "log": debate_log
                })

        # ── Phase 8: Generate final answer ──
        yield from _stream_final_answer(
            qwen_api, diagnosis, formula, acupuncture,
            regimen, review, debate_log, sse_event
        )

        yield sse_event("done", {
            "session_id": session_id,
            "intent": intent,
            "agents_executed": list(agents.keys()),
            "debate_rounds": len(debate_log)
        })

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


def _stream_final_answer(qwen_api, diagnosis, formula, acupuncture,
                         regimen, review, debate_log, sse_event):
    """生成最终临床方案文本并流式输出"""
    syndrome_name = ""
    if isinstance(diagnosis.get("syndrome", {}).get("primary"), dict):
        syndrome_name = diagnosis["syndrome"]["primary"].get("name", "")

    formula_name = formula.get("primary_formula", {}).get("name", "")
    formula_comp = formula.get("primary_formula", {}).get("composition", [])
    herbs_str = "、".join([h.get("herb", "") for h in formula_comp[:8]])

    primary_pts = "、".join([p.get("name", "") for p in acupuncture.get("primary_points", [])[:5]])

    dietary = regimen.get("dietary_advice", {})
    rec_foods = "、".join([f.get("food", "") for f in dietary.get("recommended", [])[:5]])
    avoid_foods = "、".join([f.get("food", "") for f in dietary.get("avoid", [])[:5]])

    treatment = diagnosis.get("treatment_principle", "")
    assessment = review.get("overall_assessment", "")
    hallucination_notes = [
        h for h in review.get("hallucination_checks", [])
        if not h.get("exists_in_kg")
    ]

    context_parts = []
    if syndrome_name:
        context_parts.append(f"辨证结果: {syndrome_name}")
    if treatment:
        context_parts.append(f"治则: {treatment}")
    if formula_name:
        context_parts.append(f"推荐方剂: {formula_name}，组成: {herbs_str}")
    if primary_pts:
        context_parts.append(f"针灸主穴: {primary_pts}")
    if rec_foods or avoid_foods:
        context_parts.append(f"饮食建议: 宜{rec_foods or '无'}，忌{avoid_foods or '无'}")
    if assessment:
        context_parts.append(f"审核意见: {assessment}")
    if debate_log:
        context_parts.append(f"经过{len(debate_log)}轮辩论达成方案")
    if hallucination_notes:
        inferred = [h["entity"] for h in hallucination_notes]
        context_parts.append(f"以下为模型推断(非KG证实): {', '.join(inferred)}")

    system = """你是一位资深中医临床专家。请根据各专科Agent的诊疗方案，整合输出一份完整的临床决策报告。

要求：
1. 用自然的中文段落呈现，不使用JSON
2. 标明哪些结论有知识图谱证据支持，哪些是模型推断
3. 末尾附免责提示

请输出完整临床报告："""

    prompt = "\n".join(context_parts)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"请整合以下诊疗方案输出临床报告:\n\n{prompt}"}
    ]

    try:
        full = ""
        for token in qwen_api.chat_stream(messages, temperature=0.5, max_tokens=2000):
            full += token
            yield sse_event("answer_token", {"token": token})

        if "建议咨询执业医师" not in full and "仅供参考" not in full:
            tail = "\n\n---\n免责提示：本报告由AI辅助生成，仅供参考，具体诊疗请咨询执业中医师。"
            for ch in tail:
                yield sse_event("answer_token", {"token": ch})
    except Exception:
        yield sse_event("answer_token", {"token": "\n\n系统生成报告时遇到错误，请重试。"})


def _stream_answer(qwen_api, question, kg_context, session_id, sse_event):
    """简单问答流式输出"""
    system = "你是一位专业的中医专家，请基于知识图谱信息给出准确、专业的回答。"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{question}\n\n【知识图谱参考】\n{kg_context}" if kg_context else question}
    ]

    try:
        for token in qwen_api.chat_stream(messages, temperature=0.5, max_tokens=1500):
            yield sse_event("answer_token", {"token": token})
    except Exception:
        yield sse_event("answer_token", {"token": "\n\n抱歉，生成回答时遇到错误。"})

    yield sse_event("done", {"session_id": session_id})


def _summarize_agent_output(agent_name: str, output: dict) -> dict:
    """摘要Agent输出用于辩论展示"""
    if agent_name == "formula":
        pf = output.get("primary_formula", {})
        return {
            "formula": pf.get("name", ""),
            "herbs": [h.get("herb", "") for h in pf.get("composition", [])],
            "confidence": output.get("overall_confidence", 0)
        }
    elif agent_name == "regimen":
        da = output.get("dietary_advice", {})
        return {
            "recommended_foods": [f.get("food", "") for f in da.get("recommended", [])],
            "avoid_foods": [f.get("food", "") for f in da.get("avoid", [])],
            "confidence": output.get("overall_confidence", 0)
        }
    elif agent_name == "acupuncture":
        return {
            "primary_points": [p.get("name", "") for p in output.get("primary_points", [])],
            "confidence": output.get("overall_confidence", 0)
        }
    return {"confidence": output.get("overall_confidence", 0)}


def _format_agent_summary(agent_name: str, output: dict) -> str:
    """格式化Agent输出为可读中文摘要（用于前端推理链展示）"""
    if not isinstance(output, dict):
        return str(output)[:500]
    try:
        if agent_name == "orchestrator":
            intent = output.get("intent", "")
            complexity = output.get("complexity", "")
            return f"意图: {intent}\n复杂度: {complexity}"
        elif agent_name == "entity_recognition":
            entities = output.get("entities", [])
            lines = []
            for e in (entities if isinstance(entities, list) else []):
                txt = e.get("text", "") if isinstance(e, dict) else str(e)
                via = e.get("matched_via", "") if isinstance(e, dict) else ""
                kg = e.get("kg_id", "") if isinstance(e, dict) else ""
                line = f"• {txt}"
                if via: line += f" [{via}]"
                if kg: line += f" → {kg}"
                lines.append(line)
            return f"识别 {len(entities) if isinstance(entities, list) else 0} 个实体:\n" + "\n".join(lines[:10])
        elif agent_name == "kg_query":
            rc = output.get("relation_count", 0)
            ec = output.get("entity_count", 0)
            ctx = output.get("kg_context", "")
            lines = [f"查询到 {rc} 条关系, {ec} 个实体"]
            if ctx:
                lines.append("KG上下文摘要:")
                lines.append(ctx[:300])
            return "\n".join(lines)
        elif agent_name == "diagnosis":
            sy = output.get("syndrome", {})
            name = sy.get("name", "") if isinstance(sy, dict) else ""
            method = sy.get("treatment_method", "") if isinstance(sy, dict) else ""
            cd = output.get("candidate_diseases", [])
            lines = []
            if name: lines.append(f"证型: {name}")
            if method: lines.append(f"治法: {method}")
            if cd:
                lines.append("候选疾病:")
                for d in cd[:5]:
                    dn = d.get("disease", d.get("name", "")) if isinstance(d, dict) else str(d)
                    lines.append(f"  • {dn}")
            if output.get("inquiry_questions"):
                lines.append("生成了问诊问题")
            return "\n".join(lines) if lines else _json_summary(output)
        elif agent_name == "formula":
            pf = output.get("primary_formula", {})
            name = pf.get("name", "") if isinstance(pf, dict) else ""
            comp = pf.get("composition", []) if isinstance(pf, dict) else []
            herbs = [h.get("herb", "") for h in comp if isinstance(h, dict)]
            lines = []
            if name: lines.append(f"主方: {name}")
            if herbs: lines.append("组成: " + "、".join(herbs[:10]))
            conf = output.get("overall_confidence", 0)
            if conf: lines.append(f"置信度: {conf:.0%}")
            alt = output.get("alternative_formulas", [])
            if alt: lines.append(f"备选方: {len(alt)} 个")
            return "\n".join(lines) if lines else _json_summary(output)
        elif agent_name == "acupuncture":
            pp = output.get("primary_points", [])
            lines = []
            if pp:
                pts = [p.get("name", "") for p in pp if isinstance(p, dict)]
                lines.append("主穴: " + "、".join(pts[:8]))
            ap = output.get("auxiliary_points", [])
            if ap:
                pts = [p.get("name", "") for p in ap if isinstance(p, dict)]
                lines.append("配穴: " + "、".join(pts[:8]))
            method = output.get("method", "")
            if method: lines.append(f"手法: {method}")
            return "\n".join(lines) if lines else _json_summary(output)
        elif agent_name == "regimen":
            lines = []
            da = output.get("dietary_advice", {})
            if isinstance(da, dict):
                rec = [f.get("food", "") for f in da.get("recommended", []) if isinstance(f, dict)]
                avd = [f.get("food", "") for f in da.get("avoid", []) if isinstance(f, dict)]
                if rec: lines.append("宜食: " + "、".join(rec[:6]))
                if avd: lines.append("忌食: " + "、".join(avd[:6]))
            la = output.get("lifestyle_advice", {})
            if isinstance(la, dict):
                tips = la.get("recommendations", [])
                if tips: lines.append("生活建议: " + "; ".join(str(t) for t in tips[:3]))
            return "\n".join(lines) if lines else _json_summary(output)
        elif agent_name in ("review", "verification"):
            lines = []
            conf = output.get("overall_confidence", 0)
            if conf: lines.append(f"综合置信度: {conf:.0%}")
            conflicts = output.get("conflicts", [])
            if conflicts:
                lines.append(f"发现 {len(conflicts)} 个冲突:")
                for c in conflicts[:3]:
                    ct = c.get("type", "") if isinstance(c, dict) else str(c)
                    lines.append(f"  • {ct}")
            need_debate = output.get("need_debate", False)
            lines.append(f"需要辩论: {'是' if need_debate else '否'}")
            return "\n".join(lines)
        else:
            return _json_summary(output)
    except Exception:
        return _json_summary(output)


def _json_summary(d: dict, max_len: int = 500) -> str:
    """兜底：JSON截断摘要"""
    try:
        s = str(d)
        return s[:max_len] + ("..." if len(s) > max_len else "")
    except Exception:
        return "(无法序列化)"


# ──── Non-streaming batch endpoint ────

@agent_bp.route("/chat", methods=["POST"])
def agent_chat():
    """多Agent协同 非流式端点（返回完整JSON）"""
    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())
    use_debate = data.get("use_debate", True)

    if not question:
        return jsonify({"error": "问题不能为空"}), 400

    qwen_api = QwenAPI()
    kg_enhancer = KnowledgeGraphEnhancer()
    agents = _create_agents(qwen_api, kg_enhancer)
    bus = AgentBus()
    for name, agent in agents.items():
        bus.register(name, agent)

    try:
        # Orchestrator
        orchestration = agents["orchestrator"].run({
            "question": question, "session_id": session_id
        })
        intent = orchestration.get("intent", "simple_qa")
        complexity = orchestration.get("complexity", "simple")

        # Entity recognition
        entities_data = qwen_api.extract_entities(question)
        entities = []
        for e in (entities_data or []):
            entities.append({
                "text": e.get("text", ""),
                "label": e.get("label", e.get("type", "")),
                "type": e.get("type", e.get("label", ""))
            })

        # KG query
        kg_context = ""
        kg_full_result = {}
        if entities and kg_enhancer:
            kg_result = agents["kg_query"].run({
                "entities": entities, "question": question,
                "layer": "L2" if complexity in ("medium", "complex") else "L1"
            })
            kg_context = kg_result.get("kg_context", "")
            kg_full_result = kg_result

        # Simple QA
        if intent in ("simple_qa", "knowledge_learning"):
            answer = qwen_api.generate_answer(question, kg_context)
            return jsonify({
                "answer": answer,
                "entities": [{"text": e["text"], "type": e["label"]} for e in entities],
                "intent": intent,
                "session_id": session_id
            })

        # DAG 驱动临床管线
        subgraph = kg_full_result.get("subgraph", {})
        dag_plan = _build_clinical_dag(question, entities, kg_context, complexity, subgraph)
        dag = DAGExecutor.from_plan(dag_plan, max_workers=3)

        dag.tasks["entity_recognition"].status = "done"
        dag.tasks["entity_recognition"].result = {"entities": entities, "entity_count": len(entities)}
        dag.tasks["kg_query"].status = "done"
        dag.tasks["kg_query"].result = kg_full_result

        dag_result = dag.execute(bus)
        results = dag_result.get("results", {})

        diagnosis = results.get("diagnosis", {})
        formula = results.get("formula", {})
        acupuncture = results.get("acupuncture", {})
        regimen = results.get("regimen", {})
        review = results.get("review", {})

        # Debate
        debate_log = []
        if use_debate and review.get("need_debate"):
            debate_items = review.get("debate_items", [])
            for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
                resolved_all = True
                for item in debate_items:
                    debate_ctx = {"round": round_num, "conflict_type": item["conflict_type"]}
                    # Re-run conflicting agents with debate context
                    for agent_name in [item["agent_a"], item["agent_b"]]:
                        if agent_name in agents and agent_name != "kg":
                            agents[agent_name].run({
                                "question": question, "diagnosis": diagnosis,
                                "formula": formula, "acupuncture": acupuncture,
                                "regimen": regimen,
                                "debate_context": {**debate_ctx, "role": "defend"}
                            })
                    updated = agents["review"].run({
                        "question": question, "diagnosis": diagnosis,
                        "formula": formula, "acupuncture": acupuncture,
                        "regimen": regimen,
                        "debate_context": {"round": round_num}
                    })
                    still = [c for c in updated.get("conflicts", []) if c.get("type") == item["conflict_type"]]
                    if still:
                        resolved_all = False
                    debate_log.append({"round": round_num, "resolved": len(still) == 0})
                if resolved_all:
                    break

        return jsonify({
            "diagnosis": {
                "syndrome": diagnosis.get("syndrome", {}),
                "treatment_principle": diagnosis.get("treatment_principle", ""),
                "confidence": diagnosis.get("overall_confidence", 0)
            },
            "formula": {
                "name": formula.get("primary_formula", {}).get("name", ""),
                "composition": formula.get("primary_formula", {}).get("composition", []),
                "confidence": formula.get("overall_confidence", 0)
            },
            "acupuncture": {
                "primary_points": acupuncture.get("primary_points", []),
                "meridian_analysis": acupuncture.get("meridian_analysis", ""),
                "confidence": acupuncture.get("overall_confidence", 0)
            },
            "regimen": {
                "dietary_advice": regimen.get("dietary_advice", {}),
                "lifestyle": regimen.get("lifestyle", {}),
                "confidence": regimen.get("overall_confidence", 0)
            },
            "review": {
                "assessment": review.get("overall_assessment", ""),
                "conflicts": review.get("conflicts", []),
                "hallucination_checks": review.get("hallucination_checks", []),
                "confidence": review.get("overall_confidence", 0)
            },
            "debate_log": debate_log,
            "entities": [{"text": e["text"], "type": e["label"]} for e in entities],
            "intent": intent,
            "session_id": session_id
        })

    except Exception as e:
        print(f"[Agent ERROR] {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ──── Vector Index & Entity Linking API ────

@agent_bp.route("/vector-index/status", methods=["GET"])
def vector_index_status():
    """查询向量索引状态"""
    try:
        kg_enhancer = KnowledgeGraphEnhancer()
        with kg_enhancer.driver.session() as session:
            result = session.run("SHOW INDEXES YIELD name, type, state WHERE type = 'VECTOR' RETURN name, state")
            indexes = [{"name": r["name"], "state": r["state"]} for r in result]

            entity_count = 0
            embedded_count = 0
            for _, neo4j_label in ENTITY_TYPES.items():
                cnt = session.run(f"MATCH (n:{neo4j_label}) RETURN count(n) AS cnt").single()["cnt"]
                entity_count += cnt
                emb_cnt = session.run(f"MATCH (n:{neo4j_label}) WHERE n.embedding IS NOT NULL RETURN count(n) AS cnt").single()["cnt"]
                embedded_count += emb_cnt

        return jsonify({
            "vector_indexes": indexes,
            "config": VECTOR_INDEX_CONFIG,
            "entity_total": entity_count,
            "entity_embedded": embedded_count,
            "coverage": round(embedded_count / entity_count, 4) if entity_count > 0 else 0,
            "index_ready": any(idx["name"] == VECTOR_INDEX_CONFIG["index_name"] for idx in indexes)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/vector-index/build", methods=["POST"])
def vector_index_build():
    """触发向量索引构建（异步后台执行）"""
    import subprocess
    import os

    src_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(src_dir, "build_vector_index.py")

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            cwd=src_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        return jsonify({
            "status": "started",
            "message": "向量索引构建已启动，请通过 /api/agent/vector-index/status 查看进度",
            "pid": proc.pid
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/entity-linking/test", methods=["POST"])
def entity_linking_test():
    """实体链接测试端点 — 输入文本，返回链接结果"""
    data = request.get_json(silent=True) or {}
    text = (data.get("text", "") or "").strip()
    label = data.get("label", "")

    if not text:
        return jsonify({"error": "text 不能为空"}), 400

    try:
        qwen_api = QwenAPI()
        kg_enhancer = KnowledgeGraphEnhancer()
        linker = EntityLinker(kg_enhancer, embedding_api=qwen_api)

        mention = {"text": text, "label": label, "type": label}
        result = linker._link_single(mention)

        return jsonify({
            "input": {"text": text, "label": label},
            "output": {
                "linked_text": result.get("linked_text", text),
                "linked_label": result.get("linked_label", label),
                "matched_via": result.get("matched_via", "llm_only"),
                "confidence": result.get("confidence", 0),
                "candidates": result.get("candidates", [])[:5]
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/entity-linking/batch-test", methods=["POST"])
def entity_linking_batch_test():
    """实体链接批量测试 — 输入问题，返回完整实体识别+链接结果"""
    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()

    if not question:
        return jsonify({"error": "question 不能为空"}), 400

    try:
        qwen_api = QwenAPI()
        kg_enhancer = KnowledgeGraphEnhancer()

        raw_entities = qwen_api.extract_entities(question)
        raw_list = []
        for e in (raw_entities or []):
            raw_list.append({
                "text": e.get("text", ""),
                "label": e.get("label", e.get("type", "")),
                "type": e.get("type", e.get("label", ""))
            })

        linker = EntityLinker(kg_enhancer, embedding_api=qwen_api)
        linked = linker.link_entities(raw_list)

        results = []
        for e in linked:
            results.append({
                "original_text": e.get("original_text", e.get("text", "")),
                "linked_text": e.get("linked_text", ""),
                "linked_label": e.get("linked_label", ""),
                "matched_via": e.get("matched_via", "llm_only"),
                "confidence": e.get("confidence", 0),
                "candidates": e.get("candidates", [])[:3]
            })

        stats = {
            "exact_match": sum(1 for e in linked if e.get("matched_via") == "exact"),
            "alias_match": sum(1 for e in linked if e.get("matched_via") == "alias"),
            "vector_match": sum(1 for e in linked if e.get("matched_via") == "vector"),
            "fuzzy_match": sum(1 for e in linked if e.get("matched_via") == "fuzzy"),
            "unlinked": sum(1 for e in linked if e.get("matched_via") == "llm_only")
        }

        return jsonify({
            "question": question,
            "raw_entities": raw_list,
            "linked_entities": results,
            "stats": stats,
            "vector_index_available": linker._vector_index_available
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/debug", methods=["POST"])
def agent_debug():
    """调试端点 — SSE 流式返回每个Agent的执行过程和结果"""
    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not question:
        return jsonify({"error": "问题不能为空"}), 400

    qwen_api = QwenAPI()
    kg_enhancer = KnowledgeGraphEnhancer()
    agents = _create_agents(qwen_api, kg_enhancer)
    bus = AgentBus()
    for name, agent in agents.items():
        bus.register(name, agent)

    def sse_event(event_type: str, payload: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _ts():
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _log(step, msg, emoji=""):
        print(f"[{_ts()}] [{step}] {emoji} {msg}", flush=True)

    def generate():
        all_results = {}
        checkpoint_decisions = []
        inquiry_triggered = False
        _t0 = None

        try:
            import time as _time
            _t0 = _time.time()
            # Phase 1: Orchestrator
            _log("START", f"开始处理问题: {question[:80]}", "🚀")
            yield "event: phase\ndata: " + json.dumps({"phase": 1, "name": "意图分类"}, ensure_ascii=False) + "\n\n"
            _log("Phase 1", "意图分类 (Orchestrator)", "🎯")
            yield "event: agent_start\ndata: " + json.dumps({"agent": "orchestrator"}, ensure_ascii=False) + "\n\n"
            orchestration = agents["orchestrator"].run({
                "question": question, "session_id": session_id
            })
            intent = orchestration.get("intent", "simple_qa")
            complexity = orchestration.get("complexity", "simple")
            _log("Phase 1", f"完成 → intent={intent}, complexity={complexity} ({_time.time()-_t0:.2f}s)", "✅")
            yield "event: agent_done\ndata: " + json.dumps({
                "agent": "orchestrator",
                "intent": intent,
                "complexity": complexity,
                "summary": f"意图: {intent}, 复杂度: {complexity}"
            }, ensure_ascii=False) + "\n\n"
            all_results["orchestrator"] = orchestration

            # Phase 2: Entity Recognition
            _t_phase = _time.time()
            yield "event: phase\ndata: " + json.dumps({"phase": 2, "name": "实体识别与链接"}, ensure_ascii=False) + "\n\n"
            _log("Phase 2", "实体识别与链接", "🏷️")
            yield "event: agent_start\ndata: " + json.dumps({"agent": "entity_recognition"}, ensure_ascii=False) + "\n\n"
            entities_data = qwen_api.extract_entities(question)
            raw_list = []
            for e in (entities_data or []):
                raw_list.append({
                    "text": e.get("text", ""),
                    "label": e.get("label", e.get("type", "")),
                    "type": e.get("type", e.get("label", ""))
                })
            linker = EntityLinker(kg_enhancer, embedding_api=qwen_api)
            linked = linker.link_entities(raw_list)
            entities = []
            for e in linked:
                entities.append({
                    "text": e.get("linked_text", e.get("text", "")),
                    "label": e.get("linked_label", e.get("label", "")),
                    "type": e.get("linked_label", e.get("label", "")),
                    "original_text": e.get("original_text", e.get("text", "")),
                    "matched_via": e.get("matched_via", "llm_only"),
                    "confidence": e.get("confidence", 0.5)
                })
            linking_stats = {
                "exact_match": sum(1 for e in entities if e["matched_via"] == "exact"),
                "alias_match": sum(1 for e in entities if e["matched_via"] == "alias"),
                "vector_match": sum(1 for e in entities if e["matched_via"] == "vector"),
                "fuzzy_match": sum(1 for e in entities if e["matched_via"] == "fuzzy"),
                "unlinked": sum(1 for e in entities if e["matched_via"] == "llm_only")
            }
            yield sse_event("agent_done", {
                "agent": "entity_recognition",
                "entity_count": len(entities),
                "linking_stats": linking_stats,
                "summary": ", ".join(e.get("text", "") for e in entities[:8]),
                "result_keys": ["entities", "entity_count"]
            })
            _log("Phase 2", f"完成 → {len(entities)} 个实体 (精确:{linking_stats['exact_match']} 别名:{linking_stats['alias_match']} 向量:{linking_stats['vector_match']} 模糊:{linking_stats['fuzzy_match']} 未链接:{linking_stats['unlinked']}) ({_time.time()-_t_phase:.2f}s)", "✅")
            all_results["entity_recognition"] = {"entities": entities, "entity_count": len(entities)}
            entities  # 用于后续流程传递

            # Phase 3: KG Query
            _t_phase = _time.time()
            yield sse_event("phase", {"phase": 3, "name": "知识图谱查询"})
            _log("Phase 3", "知识图谱查询 (多症状交集推理)", "🗂️")
            yield sse_event("agent_start", {"agent": "kg_query"})
            kg_context = ""
            kg_full_result = {}
            kg_layer = "L2" if complexity in ("medium", "complex") else "L1"
            if entities and kg_enhancer:
                kg_result = agents["kg_query"].run({
                    "entities": entities, "question": question, "layer": kg_layer
                })
                kg_context = kg_result.get("kg_context", "")
                kg_full_result = kg_result
            yield sse_event("agent_done", {
                "agent": "kg_query",
                "has_results": bool(kg_context),
                "relation_count": kg_full_result.get("relation_count", 0),
                "entity_count": kg_full_result.get("entity_count", 0),
                "summary": f"{kg_full_result.get('relation_count', 0)}条关系, {kg_full_result.get('entity_count', 0)}个实体",
                "result_keys": list(kg_full_result.keys()) if isinstance(kg_full_result, dict) else []
            })
            _log("Phase 3", f"完成 → {kg_full_result.get('relation_count', 0)} 条关系, {kg_full_result.get('entity_count', 0)} 个实体 ({_time.time()-_t_phase:.2f}s)", "✅")
            all_results["kg_query"] = kg_full_result

            # Phase 4: 检查是否需要问诊
            candidate_diseases = []
            for entity_text, data_item in kg_full_result.get("subgraph", {}).items():
                if isinstance(data_item, dict) and data_item.get("candidate", False):
                    candidate_diseases.append({
                        "disease": entity_text.replace("(候选)", ""),
                        "hit_count": data_item.get("hit_count", 0),
                        "symptoms": data_item.get("symptoms", [])
                    })

            if candidate_diseases:
                _t_phase = _time.time()
                yield sse_event("phase", {"phase": 4, "name": "问诊生成"})
                _log("Phase 4", f"KG发现 {len(candidate_diseases)} 个候选疾病，触发问诊流程", "⚠️")
                yield sse_event("agent_start", {"agent": "diagnosis"})
                inquiry_result = agents["diagnosis"].run({
                    "mode": "inquiry",
                    "candidate_diseases": candidate_diseases,
                    "entities": entities
                })
                yield sse_event("agent_done", {
                    "agent": "diagnosis",
                    "status": "done",
                    "need_inquiry": True,
                    "summary": f"生成{len(candidate_diseases)}个候选疾病的问诊词",
                    "candidate_diseases": [cd.get("disease", "") for cd in candidate_diseases[:5]]
                })
                _log("Phase 4", f"问诊生成完成 → {len(candidate_diseases)} 个疾病的问诊词 ({_time.time()-_t_phase:.2f}s)", "📋")
                inquiry_result_data = {
                    "need_inquiry": True,
                    "inquiries": inquiry_result.get("inquiries", []),
                    "candidate_diseases": candidate_diseases,
                    "question": question,
                    "session_id": session_id,
                    "intent": intent,
                    "complexity": complexity,
                    "entities": entities
                }
                yield sse_event("inquiry", inquiry_result_data)
                inquiry_triggered = True
                yield sse_event("done", {"session_id": session_id, "reason": "inquiry_pending"})
                return

            # Phase 5-8: DAG 执行
            subgraph = kg_full_result.get("subgraph", {})
            dag_plan = _build_clinical_dag(question, entities, kg_context, complexity, subgraph)
            dag = DAGExecutor.from_plan(dag_plan, max_workers=3)
            _log("DAG", f"构建完成，任务: {list(dag.tasks.keys())}", "🔧")
            dag.tasks["entity_recognition"].status = "done"
            dag.tasks["entity_recognition"].result = {"entities": entities, "entity_count": len(entities)}
            dag.tasks["kg_query"].status = "done"
            dag.tasks["kg_query"].result = kg_full_result

            kg_decision = agents["orchestrator"].checkpoint_review("kg_query", kg_full_result, dag.get_state())
            checkpoint_decisions.append({
                "step": "kg_query",
                "action": kg_decision.get("action", "continue"),
                "reason": kg_decision.get("reason", ""),
                "details": {k: v for k, v in kg_decision.items() if k not in ("action", "reason")}
            })

            _log("DAG", "开始执行临床管线...", "▶️")
            _dag_step = 0

            while not dag.all_done():
                _dag_step += 1
                _t_step = _time.time()
                pending_tasks = [t for t, task in dag.tasks.items() if task.status == "pending"]
                _log(f"DAG step {_dag_step}", f"待执行: {pending_tasks}", "⏳")
                step_result = dag.execute_step(bus)
                executed = step_result.get("executed", [])

                for exec_info in executed:
                    task_id = exec_info.get("task_id", "")
                    agent_name = exec_info.get("agent", "")
                    status = exec_info.get("status", "")
                    result = exec_info.get("result")

                    agent_done_data = {
                        "agent": agent_name,
                        "task_id": task_id,
                        "status": status,
                        "duration_ms": exec_info.get("duration_ms", 0)
                    }
                    if status == "done" and result:
                        agent_done_data["summary"] = _format_agent_summary(agent_name, result)
                        agent_done_data["result_keys"] = list(result.keys()) if isinstance(result, dict) else []
                    yield sse_event("agent_done", agent_done_data)

                    if status == "done" and result:
                        all_results[agent_name] = result
                        _log(f"DAG step {_dag_step}", f"✅ {agent_name} 完成 ({_time.time()-_t_step:.2f}s)", "✅")

                        decision = agents["orchestrator"].checkpoint_review(
                            agent_name, result, dag.get_state()
                        )
                        decision_entry = {
                            "step": agent_name,
                            "action": decision.get("action", "continue"),
                            "reason": decision.get("reason", ""),
                        }
                        if decision.get("new_tasks"):
                            decision_entry["new_tasks"] = [
                                {"task_id": t.get("task_id"), "agent": t.get("agent")}
                                for t in decision.get("new_tasks", [])
                            ]
                        if decision.get("skip_tasks"):
                            decision_entry["skip_tasks"] = decision.get("skip_tasks")
                        if decision.get("candidate_diseases"):
                            decision_entry["candidate_diseases"] = decision.get("candidate_diseases")
                        checkpoint_decisions.append(decision_entry)

                        action = decision.get("action", "continue")
                        if action == "add_task":
                            for new_task in decision.get("new_tasks", []):
                                dag.add_task_by_def(new_task)
                                yield sse_event("plan_update", {
                                    "reason": decision.get("reason", ""),
                                    "added_tasks": [t.get("task_id", "") for t in decision.get("new_tasks", [])]
                                })
                                _log(f"DAG step {_dag_step}", f"＋ 动态追加任务: {[t.get('task_id','') for t in decision.get('new_tasks',[])]}", "📋")
                        elif action == "skip":
                            for skip_id in decision.get("skip_tasks", []):
                                dag.skip_task(skip_id)
                                _log(f"DAG step {_dag_step}", f"⏭ 跳过任务: {skip_id}", "⏭️")
                        elif action == "done":
                            _log(f"DAG step {_dag_step}", "检查点决定提前结束", "⏹️")
                            break

                if step_result.get("all_done"):
                    break

            # 检查问诊触发
            if inquiry_triggered:
                yield sse_event("done", {"session_id": session_id, "reason": "inquiry_pending"})
                return

            # 合并 kg_supplement 结果
            subgraph_split = {}
            for task_id, task in dag.tasks.items():
                if task_id.startswith("kg_supplement") and task.status == "done" and task.result:
                    supplement_subgraph = task.result.get("subgraph", {})
                    if supplement_subgraph:
                        kg_full_result.setdefault("subgraph", {}).update(supplement_subgraph)

            if kg_full_result.get("subgraph"):
                split_result = agents["orchestrator"].split_subgraph(kg_full_result["subgraph"])
                subgraph_split = {
                    "formula": {
                        "entity_count": len(split_result.get("formula_subgraph", {})),
                        "entities": list(split_result.get("formula_subgraph", {}).keys()),
                        "relation_keys": list(set(
                            rk for data in split_result.get("formula_subgraph", {}).values()
                            if isinstance(data, dict)
                            for rk in data.get("relations", {}).keys()
                        ))
                    },
                    "acupuncture": {
                        "entity_count": len(split_result.get("acupuncture_subgraph", {})),
                        "entities": list(split_result.get("acupuncture_subgraph", {}).keys()),
                        "relation_keys": list(set(
                            rk for data in split_result.get("acupuncture_subgraph", {}).values()
                            if isinstance(data, dict)
                            for rk in data.get("relations", {}).keys()
                        ))
                    },
                    "regimen": {
                        "entity_count": len(split_result.get("regimen_subgraph", {})),
                        "entities": list(split_result.get("regimen_subgraph", {}).keys()),
                        "relation_keys": list(set(
                            rk for data in split_result.get("regimen_subgraph", {}).values()
                            if isinstance(data, dict)
                            for rk in data.get("relations", {}).keys()
                        ))
                    },
                }

            # 辩论
            debate_log = []
            review_result = all_results.get("review", all_results.get("verification", {}))
            if review_result.get("need_debate") and review_result.get("debate_items"):
                _t_debate = _time.time()
                yield sse_event("debate_start", {
                    "conflicts": [{
                        "type": d["conflict_type"],
                        "severity": d["severity"],
                        "agent_a": d["agent_a"],
                        "agent_b": d["agent_b"]
                    } for d in review_result.get("debate_items", [])],
                    "total_conflicts": len(review_result.get("debate_items", []))
                })
                _log("Debate", f"发现 {len(review_result.get('debate_items',[]))} 个冲突，开始辩论", "⚖️")
                debate_items = review_result["debate_items"]
                diagnosis = all_results.get("diagnosis", {})
                formula = all_results.get("formula", {})
                acupuncture = all_results.get("acupuncture", {})
                regimen = all_results.get("regimen", {})

                for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
                    _log("Debate", f"第 {round_num} 轮辩论", "💬")
                    resolved_all = True
                    for item in debate_items:
                        round_args = []
                        debate_ctx = {"round": round_num, "conflict_type": item["conflict_type"]}

                        for agent_name in [item["agent_a"], item["agent_b"]]:
                            if agent_name in agents:
                                is_a = agent_name == item["agent_a"]
                                debate_payload = {
                                    "question": question,
                                    "diagnosis": diagnosis,
                                    "formula": formula,
                                    "acupuncture": acupuncture,
                                    "regimen": regimen,
                                    "debate_context": {
                                        **debate_ctx,
                                        "role": "defend",
                                        "challenge": item["claim_b"] if is_a else item["claim_a"],
                                        "your_claim": item["claim_a"] if is_a else item["claim_b"]
                                    }
                                }
                                revised = agents[agent_name].execute(debate_payload, bus=bus)
                                round_args.append({
                                    "agent": agent_name,
                                    "claim": item["claim_a"] if is_a else item["claim_b"],
                                    "revised_summary": _summarize_agent_output(agent_name, revised)
                                })

                        updated_review = agents["review"].run({
                            "question": question,
                            "diagnosis": diagnosis,
                            "formula": formula,
                            "acupuncture": acupuncture,
                            "regimen": regimen,
                            "debate_context": {
                                "round": round_num,
                                "previous_conflicts": debate_items,
                                "round_arguments": round_args
                            }
                        })

                        still_conflicts = [c for c in updated_review.get("conflicts", [])
                                           if c.get("type") == item["conflict_type"]]

                        debate_log.append({
                            "round": round_num,
                            "conflict_type": item["conflict_type"],
                            "severity": item.get("severity", "medium"),
                            "agent_a": item["agent_a"],
                            "agent_b": item["agent_b"],
                            "claim_a": item["claim_a"],
                            "claim_b": item["claim_b"],
                            "arguments": round_args,
                            "resolved": len(still_conflicts) == 0
                        })

                        if still_conflicts:
                            resolved_all = False

                    if resolved_all:
                        break

                yield sse_event("debate_end", {
                    "total_rounds": len(debate_log),
                    "resolved": len(debate_log) > 0
                })
                _log("Debate", f"辩论完成 → {len(debate_log)} 轮 ({_time.time()-_t_debate:.2f}s)", "✅")

            trace = dag.get_trace()
            dynamic_tasks = []
            for task_id, task in dag.tasks.items():
                if task_id.startswith("kg_supplement"):
                    dynamic_tasks.append({
                        "task_id": task_id,
                        "agent": task.agent_name,
                        "status": task.status,
                        "duration_ms": task.duration_ms
                    })

            yield sse_event("final_result", {
                "question": question,
                "intent": intent,
                "complexity": complexity,
                "trace": trace,
                "checkpoint_decisions": checkpoint_decisions,
                "subgraph_split": subgraph_split,
                "debate_log": debate_log,
                "dynamic_tasks": dynamic_tasks,
                "session_id": session_id,
                "agent_results": {k: _format_agent_summary(k, v) for k, v in all_results.items()}
            })

            _log("Answer", "开始流式生成最终回答...", "💬")
            diagnosis = all_results.get("diagnosis", {})
            formula = all_results.get("formula", {})
            acupuncture = all_results.get("acupuncture", {})
            regimen = all_results.get("regimen", {})
            review = all_results.get("review", all_results.get("verification", {}))
            yield from _stream_final_answer(
                qwen_api, diagnosis, formula, acupuncture,
                regimen, review, debate_log, sse_event
            )

            _log("DONE", f"全部完成 → intent={intent}, complexity={complexity}, 辩论={len(debate_log)}轮, 总耗时={_time.time()-_t0:.2f}s", "🏁")
            yield sse_event("done", {"session_id": session_id, "reason": "complete"})

        except Exception as e:
            _log("ERROR", f"错误: {str(e)}", "❌")
            print(traceback.format_exc(), flush=True)
            yield sse_event("error", {"error": str(e)})
            yield sse_event("done", {"session_id": session_id, "reason": "error"})

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@agent_bp.route("/chat/inquiry-response", methods=["POST"])
def agent_inquiry_response():
    """
    问诊回答端点 — 用户回答问诊词后，辨证Agent评估并继续流程
    SSE流式返回
    """
    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())
    user_answers = (data.get("user_answers", "") or "").strip()
    candidate_diseases = data.get("candidate_diseases", [])
    # disease_symptoms 不再需要 — 症状信息已从候选疾病中提供
    _ = data.get("disease_symptoms", {})
    entities = data.get("entities", [])
    complexity = data.get("complexity", "medium")

    if not question or not user_answers:
        return jsonify({"error": "问题和用户回答不能为空"}), 400

    qwen_api = QwenAPI()
    kg_enhancer = KnowledgeGraphEnhancer()
    agents = _create_agents(qwen_api, kg_enhancer)
    bus = AgentBus()
    for name, agent in agents.items():
        bus.register(name, agent)

    def sse_event(event_type: str, payload: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    from datetime import datetime as _dt
    def _ts(): return _dt.now().strftime("%H:%M:%S.%f")[:-3]
    def _log(step, msg, emoji=""): print(f"[{_ts()}] [{step}] {emoji} {msg}", flush=True)

    def generate():
        # 调用辨证Agent评估用户回答
        _log("Inquiry", f"评估用户回答: {user_answers[:50]}", "🔍")
        yield sse_event("agent_start", {"agent": "diagnosis"})

        diagnosis_result = agents["diagnosis"].run({
            "mode": "confirm",
            "question": question,
            "candidate_diseases": candidate_diseases,
            "user_answers": user_answers,
            "entities": entities,
            "complexity": complexity
        })

        yield sse_event("agent_done", {
            "agent": "diagnosis",
            "status": "done",
            "confirmed_diseases": diagnosis_result.get("confirmed_diseases", []),
            "excluded_diseases": diagnosis_result.get("excluded_diseases", []),
            "summary": "确认: " + ", ".join(d.get("name","") for d in diagnosis_result.get("confirmed_diseases", []) if isinstance(d, dict)) + " | 排除: " + ", ".join(d.get("name","") for d in diagnosis_result.get("excluded_diseases", []) if isinstance(d, dict))
        })

        confirmed_diseases = diagnosis_result.get("confirmed_diseases", [])
        if not confirmed_diseases:
            yield sse_event("answer_token", {"token": "根据您的回答，未能确认任何疾病，请提供更多症状信息。"})
            yield sse_event("done", {"session_id": session_id})
            return

        # 对已确认的疾病，补充查询KG治疗关系
        yield sse_event("agent_start", {"agent": "kg_query"})
        kg_supplement_results = {}
        for disease in confirmed_diseases:
            disease_name = disease.get("name", "") if isinstance(disease, dict) else str(disease)
            if disease_name:
                supplement = agents["kg_query"].query_supplement(disease_name, "疾病")
                kg_supplement_results.update(supplement.get("subgraph", {}))

        yield sse_event("agent_done", {
            "agent": "kg_query",
            "status": "done",
            "supplement_entities": list(kg_supplement_results.keys()),
            "summary": f"补充查询 {len(kg_supplement_results)} 个实体"
        })

        kg_context = agents["kg_query"]._format_context(kg_supplement_results) if kg_supplement_results else ""
        subgraph = kg_supplement_results

        # 拆分子图
        split_result = agents["orchestrator"].split_subgraph(subgraph) if subgraph else {}

        # 构建DAG
        dag_plan = _build_clinical_dag(question, entities, kg_context, complexity, subgraph)
        dag = DAGExecutor.from_plan(dag_plan, max_workers=3)

        # 注入已完成步骤
        dag.tasks["entity_recognition"].status = "done"
        dag.tasks["entity_recognition"].result = {"entities": entities, "entity_count": len(entities)}
        dag.tasks["kg_query"].status = "done"
        kg_query_result = {"subgraph": subgraph, "kg_context": kg_context}
        if split_result:
            kg_query_result.update(split_result)
        dag.tasks["kg_query"].result = kg_query_result

        dag.tasks["diagnosis"].status = "done"
        dag.tasks["diagnosis"].result = diagnosis_result

        # 执行并行治疗推荐
        all_results = {
            "entity_recognition": {"entities": entities},
            "kg_query": kg_query_result,
            "diagnosis": diagnosis_result
        }

        while not dag.all_done():
            step_result = dag.execute_step(bus)
            executed = step_result.get("executed", [])

            for exec_info in executed:
                agent_name = exec_info.get("agent", "")
                status = exec_info.get("status", "")
                result = exec_info.get("result")

                yield sse_event("agent_done", {
                    "agent": agent_name,
                    "status": status,
                    "duration_ms": exec_info.get("duration_ms", 0),
                    "summary": _format_agent_summary(agent_name, result) if status == "done" and result else ""
                })

                if status == "done" and result:
                    all_results[agent_name] = result

            if step_result.get("all_done"):
                break

        formula = all_results.get("formula", {})
        acupuncture = all_results.get("acupuncture", {})
        regimen = all_results.get("regimen", {})
        review = all_results.get("review", all_results.get("verification", {}))

        yield from _stream_final_answer(
            qwen_api, diagnosis_result, formula, acupuncture,
            regimen, review, [], sse_event
        )

        yield sse_event("done", {
            "session_id": session_id,
            "confirmed_diseases": [d.get("name", "") if isinstance(d, dict) else str(d) for d in confirmed_diseases]
        })

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


@agent_bp.route("/debug/inquiry-evaluate", methods=["POST"])
def agent_debug_inquiry_evaluate():
    """问诊评估端点 — 用户回答问诊词后，辨证Agent评估并确认疾病"""
    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())
    candidate_diseases = data.get("candidate_diseases", [])
    user_answers = (data.get("user_answers", "") or "").strip()
    entities = data.get("entities", [])

    if not question or not user_answers:
        return jsonify({"error": "问题和回答不能为空"}), 400

    qwen_api = QwenAPI()
    kg_enhancer = KnowledgeGraphEnhancer()
    agents = _create_agents(qwen_api, kg_enhancer)

    try:
        confirmation_result = agents["diagnosis"].run({
            "mode": "confirm",
            "question": question,
            "candidate_diseases": candidate_diseases,
            "user_answers": user_answers,
            "entities": entities
        })

        confirmed_names = [d.get("name", "") for d in confirmation_result.get("confirmed_diseases", [])]

        return jsonify({
            "question": question,
            "session_id": session_id,
            "confirmation_result": confirmation_result,
            "confirmed_diseases": confirmed_names,
            "excluded_diseases": [d.get("name", "") for d in confirmation_result.get("excluded_diseases", [])],
            "need_continue": len(confirmed_names) > 0
        })

    except Exception as e:
        print(f"[Debug Inquiry Evaluate ERROR] {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/debug/confirm", methods=["POST"])
def agent_debug_confirm():
    """症状确认端点 — 用户确认疾病后继续执行Agent流程"""
    from datetime import datetime as _dt
    def _ts(): return _dt.now().strftime("%H:%M:%S.%f")[:-3]
    def _log(step, msg, emoji=""): print(f"[{_ts()}] [{step}] {emoji} {msg}", flush=True)

    data = request.get_json(silent=True) or {}
    question = (data.get("question", "") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())
    confirmed_diseases = data.get("confirmed_diseases", [])
    entities = data.get("entities", [])

    if not question or not confirmed_diseases:
        return jsonify({"error": "问题和确认疾病不能为空"}), 400

    _log("Confirm", f"确认疾病: {confirmed_diseases}, 继续执行流程", "📋")

    qwen_api = QwenAPI()
    kg_enhancer = KnowledgeGraphEnhancer()
    agents = _create_agents(qwen_api, kg_enhancer)
    bus = AgentBus()
    for name, agent in agents.items():
        bus.register(name, agent)

    try:
        orchestration = agents["orchestrator"].run({
            "question": question, "session_id": session_id
        })
        intent = orchestration.get("intent", "simple_qa")
        complexity = orchestration.get("complexity", "simple")

        kg_layer = "L2" if complexity in ("medium", "complex") else "L1"
        kg_result = agents["kg_query"].run({
            "entities": entities,
            "question": question,
            "layer": kg_layer,
            "confirmed_diseases": confirmed_diseases
        })
        kg_context = kg_result.get("kg_context", "")
        kg_full_result = kg_result

        subgraph = kg_full_result.get("subgraph", {})
        dag_plan = _build_clinical_dag(question, entities, kg_context, complexity, subgraph)
        dag = DAGExecutor.from_plan(dag_plan, max_workers=3)
        _log("Confirm/DAG", f"构建完成，任务: {list(dag.tasks.keys())}", "🔧")

        dag.tasks["entity_recognition"].status = "done"
        dag.tasks["entity_recognition"].result = {"entities": entities, "entity_count": len(entities)}
        dag.tasks["entity_recognition"].injected_params = {"question": question}
        dag.tasks["kg_query"].status = "done"
        dag.tasks["kg_query"].result = kg_full_result
        dag.tasks["kg_query"].injected_params = {"entities": entities, "question": question, "layer": kg_layer}

        checkpoint_decisions = []
        all_results = {
            "entity_recognition": {"entities": entities, "entity_count": len(entities)},
            "kg_query": kg_full_result
        }

        kg_decision = agents["orchestrator"].checkpoint_review("kg_query", kg_full_result, dag.get_state())
        checkpoint_decisions.append({
            "step": "kg_query",
            "action": kg_decision.get("action", "continue"),
            "reason": kg_decision.get("reason", ""),
            "details": {k: v for k, v in kg_decision.items() if k not in ("action", "reason")}
        })

        while not dag.all_done():
            step_result = dag.execute_step(bus)
            executed = step_result.get("executed", [])

            for exec_info in executed:
                agent_name = exec_info.get("agent", "")
                status = exec_info.get("status", "")
                result = exec_info.get("result")

                if status == "done" and result:
                    all_results[agent_name] = result
                    _log("Confirm/DAG", f"✅ {agent_name} 完成", "✅")

                    decision = agents["orchestrator"].checkpoint_review(
                        agent_name, result, dag.get_state()
                    )

                    decision_entry = {
                        "step": agent_name,
                        "action": decision.get("action", "continue"),
                        "reason": decision.get("reason", ""),
                    }
                    if decision.get("new_tasks"):
                        decision_entry["new_tasks"] = [
                            {"task_id": t.get("task_id"), "agent": t.get("agent")}
                            for t in decision.get("new_tasks", [])
                        ]
                    if decision.get("skip_tasks"):
                        decision_entry["skip_tasks"] = decision.get("skip_tasks")
                    checkpoint_decisions.append(decision_entry)

                    action = decision.get("action", "continue")
                    if action == "add_task":
                        for new_task in decision.get("new_tasks", []):
                            dag.add_task_by_def(new_task)
                    elif action == "skip":
                        for skip_id in decision.get("skip_tasks", []):
                            dag.skip_task(skip_id)
                    elif action == "done":
                        break

            if step_result.get("all_done"):
                break

        subgraph_split = {}
        for task_id, task in dag.tasks.items():
            if task_id.startswith("kg_supplement") and task.status == "done" and task.result:
                supplement_subgraph = task.result.get("subgraph", {})
                if supplement_subgraph:
                    kg_full_result.setdefault("subgraph", {}).update(supplement_subgraph)

        if kg_full_result.get("subgraph"):
            split_result = agents["orchestrator"].split_subgraph(kg_full_result["subgraph"])
            subgraph_split = {
                "formula": {
                    "entity_count": len(split_result.get("formula_subgraph", {})),
                    "entities": list(split_result.get("formula_subgraph", {}).keys()),
                    "relation_keys": list(set(
                        rk for data in split_result.get("formula_subgraph", {}).values()
                        if isinstance(data, dict)
                        for rk in data.get("relations", {}).keys()
                    ))
                },
                "acupuncture": {
                    "entity_count": len(split_result.get("acupuncture_subgraph", {})),
                    "entities": list(split_result.get("acupuncture_subgraph", {}).keys()),
                    "relation_keys": list(set(
                        rk for data in split_result.get("acupuncture_subgraph", {}).values()
                        if isinstance(data, dict)
                        for rk in data.get("relations", {}).keys()
                    ))
                },
                "regimen": {
                    "entity_count": len(split_result.get("regimen_subgraph", {})),
                    "entities": list(split_result.get("regimen_subgraph", {}).keys()),
                    "relation_keys": list(set(
                        rk for data in split_result.get("regimen_subgraph", {}).values()
                        if isinstance(data, dict)
                        for rk in data.get("relations", {}).keys()
                    ))
                },
            }

        debate_log = []
        review_result = all_results.get("review", all_results.get("verification", {}))
        if review_result.get("need_debate") and review_result.get("debate_items"):
            debate_items = review_result["debate_items"]
            diagnosis = all_results.get("diagnosis", {})
            formula = all_results.get("formula", {})
            acupuncture = all_results.get("acupuncture", {})
            regimen = all_results.get("regimen", {})

            for round_num in range(1, MAX_DEBATE_ROUNDS + 1):
                resolved_all = True
                for item in debate_items:
                    round_args = []
                    debate_ctx = {"round": round_num, "conflict_type": item["conflict_type"]}

                    for agent_name in [item["agent_a"], item["agent_b"]]:
                        if agent_name in agents:
                            is_a = agent_name == item["agent_a"]
                            debate_payload = {
                                "question": question,
                                "diagnosis": diagnosis,
                                "formula": formula,
                                "acupuncture": acupuncture,
                                "regimen": regimen,
                                "debate_context": {
                                    **debate_ctx,
                                    "role": "defend",
                                    "challenge": item["claim_b"] if is_a else item["claim_a"],
                                    "your_claim": item["claim_a"] if is_a else item["claim_b"]
                                }
                            }
                            revised = agents[agent_name].execute(debate_payload, bus=bus)
                            round_args.append({
                                "agent": agent_name,
                                "claim": item["claim_a"] if is_a else item["claim_b"],
                                "revised_summary": _summarize_agent_output(agent_name, revised)
                            })

                    updated_review = agents["review"].run({
                        "question": question,
                        "diagnosis": diagnosis,
                        "formula": formula,
                        "acupuncture": acupuncture,
                        "regimen": regimen,
                        "debate_context": {
                            "round": round_num,
                            "previous_conflicts": debate_items,
                            "round_arguments": round_args
                        }
                    })

                    still_conflicts = [c for c in updated_review.get("conflicts", [])
                                       if c.get("type") == item["conflict_type"]]

                    debate_log.append({
                        "round": round_num,
                        "conflict_type": item["conflict_type"],
                        "severity": item.get("severity", "medium"),
                        "agent_a": item["agent_a"],
                        "agent_b": item["agent_b"],
                        "claim_a": item["claim_a"],
                        "claim_b": item["claim_b"],
                        "arguments": round_args,
                        "resolved": len(still_conflicts) == 0
                    })

                    if still_conflicts:
                        resolved_all = False

                if resolved_all:
                    break

        trace = dag.get_trace()

        dynamic_tasks = []
        for task_id, task in dag.tasks.items():
            if task_id.startswith("kg_supplement"):
                dynamic_tasks.append({
                    "task_id": task_id,
                    "agent": task.agent_name,
                    "status": task.status,
                    "duration_ms": task.duration_ms
                })

        diagnosis = all_results.get("diagnosis", {})
        formula = all_results.get("formula", {})
        acupuncture = all_results.get("acupuncture", {})
        regimen = all_results.get("regimen", {})
        review = all_results.get("review", all_results.get("verification", {}))

        _log("Confirm/Answer", "生成最终临床报告...", "💬")
        final_answer = ""
        try:
            for event_str in _stream_final_answer(
                qwen_api, diagnosis, formula, acupuncture,
                regimen, review, debate_log,
                lambda et, p: f"event: {et}\ndata: {json.dumps(p, ensure_ascii=False)}\n\n"
            ):
                if event_str.startswith("event: answer_token"):
                    try:
                        payload_str = event_str.split("data: ", 1)[1].strip()
                        payload = json.loads(payload_str)
                        final_answer += payload.get("token", "")
                    except Exception:
                        pass
        except Exception as ans_err:
            _log("Confirm/Answer", f"生成报告出错: {ans_err}", "⚠️")
            final_answer = "生成临床报告时出错，请重试。"

        _log("Confirm/Answer", f"报告生成完成 ({len(final_answer)}字)", "✅")

        return jsonify({
            "question": question,
            "intent": intent,
            "complexity": complexity,
            "trace": trace,
            "checkpoint_decisions": checkpoint_decisions,
            "subgraph_split": subgraph_split,
            "debate_log": debate_log,
            "dynamic_tasks": dynamic_tasks,
            "session_id": session_id,
            "confirmed_diseases": confirmed_diseases,
            "agent_results": {k: _format_agent_summary(k, v) for k, v in all_results.items()},
            "final_answer": final_answer
        })

    except Exception as e:
        print(f"[Debug Confirm ERROR] {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@agent_bp.route("/debug/visualize", methods=["GET"])
def agent_debug_page():
    """调试可视化页面 — 聊天+调试双模式界面"""
    import os
    html_path = os.path.join(os.path.dirname(__file__), "templates", "debug_chat.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        html_content = _DEBUG_HTML
    return Response(html_content, mimetype="text/html; charset=utf-8")


_DEBUG_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Agent 协作调试可视化</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
h1 { text-align: center; margin-bottom: 20px; color: #38bdf8; font-size: 1.5em; }
.input-bar { display: flex; gap: 10px; margin-bottom: 24px; }
.input-bar input { flex: 1; padding: 12px 16px; border-radius: 8px; border: 1px solid #334155; background: #1e293b; color: #e2e8f0; font-size: 15px; outline: none; }
.input-bar input:focus { border-color: #38bdf8; }
.input-bar button { padding: 12px 24px; border-radius: 8px; border: none; background: #38bdf8; color: #0f172a; font-weight: 600; cursor: pointer; font-size: 15px; }
.input-bar button:hover { background: #7dd3fc; }
.input-bar button:disabled { opacity: 0.5; cursor: not-allowed; }
.status-bar { text-align: center; margin-bottom: 16px; color: #94a3b8; font-size: 14px; }
.status-bar.error { color: #f87171; }

.dag-flow { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.dag-row { display: flex; gap: 16px; justify-content: center; align-items: flex-start; }
.dag-arrow { text-align: center; color: #475569; font-size: 20px; line-height: 1; padding: 2px 0; }
.dag-arrow.parallel { display: flex; justify-content: center; gap: 80px; }

.agent-node {
    background: #1e293b; border: 2px solid #334155; border-radius: 12px;
    padding: 14px 18px; min-width: 180px; cursor: pointer;
    transition: all 0.2s; position: relative;
}
.agent-node:hover { border-color: #38bdf8; transform: translateY(-2px); box-shadow: 0 4px 20px rgba(56,189,248,0.15); }
.agent-node.selected { border-color: #38bdf8; box-shadow: 0 0 0 3px rgba(56,189,248,0.3); }
.agent-node.done { border-color: #22c55e; }
.agent-node.failed { border-color: #ef4444; }
.agent-node.skipped { border-color: #64748b; opacity: 0.5; }
.agent-node.running { border-color: #38bdf8; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(56,189,248,0.4); } 50% { box-shadow: 0 0 0 8px rgba(56,189,248,0); } }

.agent-name { font-weight: 600; font-size: 14px; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.agent-icon { font-size: 16px; }
.agent-status { font-size: 12px; padding: 2px 8px; border-radius: 10px; font-weight: 500; }
.agent-status.done { background: #166534; color: #86efac; }
.agent-status.failed { background: #7f1d1d; color: #fca5a5; }
.agent-status.skipped { background: #374151; color: #9ca3af; }
.agent-status.running { background: #1e3a5f; color: #7dd3fc; }
.agent-duration { font-size: 12px; color: #64748b; margin-top: 4px; }
.agent-summary { font-size: 12px; color: #94a3b8; margin-top: 4px; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.detail-panel {
    margin-top: 24px; background: #1e293b; border-radius: 12px;
    border: 1px solid #334155; overflow: hidden;
}
.detail-header { padding: 14px 18px; background: #334155; display: flex; justify-content: space-between; align-items: center; }
.detail-header h3 { font-size: 15px; color: #38bdf8; }
.detail-close { background: none; border: none; color: #94a3b8; font-size: 20px; cursor: pointer; }
.detail-body { display: flex; gap: 0; }
.detail-col { flex: 1; padding: 16px; overflow: auto; max-height: 500px; }
.detail-col:first-child { border-right: 1px solid #334155; }
.detail-col h4 { font-size: 13px; color: #64748b; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }
.detail-col pre { font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: #cbd5e1; font-family: "Cascadia Code", "Fira Code", monospace; }

.empty-state { text-align: center; padding: 60px 20px; color: #475569; }
.empty-state .icon { font-size: 48px; margin-bottom: 12px; }

.confirm-panel {
    margin-top: 24px; background: #1e293b; border-radius: 12px;
    border: 2px solid #f59e0b; overflow: hidden;
}
.confirm-header { padding: 14px 18px; background: #78350f; display: flex; justify-content: space-between; align-items: center; }
.confirm-header h3 { font-size: 15px; color: #fbbf24; }
.confirm-body { padding: 18px; }
.confirm-desc { color: #d1d5db; margin-bottom: 16px; font-size: 14px; line-height: 1.6; }
.disease-card {
    background: #0f172a; border: 1px solid #334155; border-radius: 8px;
    padding: 14px; margin-bottom: 12px;
}
.disease-card.selected { border-color: #22c55e; background: #052e16; }
.disease-name { font-weight: 600; font-size: 15px; color: #fbbf24; margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.disease-hit { font-size: 12px; color: #94a3b8; }
.symptom-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.symptom-tag {
    padding: 4px 10px; border-radius: 6px; font-size: 12px;
    background: #1e293b; border: 1px solid #475569; color: #cbd5e1; cursor: pointer;
    transition: all 0.15s;
}
.symptom-tag.checked { background: #166534; border-color: #22c55e; color: #86efac; }
.symptom-tag.original { background: #1e3a5f; border-color: #38bdf8; color: #7dd3fc; cursor: default; }
.confirm-actions { margin-top: 16px; display: flex; gap: 10px; justify-content: flex-end; }
.confirm-actions button { padding: 10px 20px; border-radius: 8px; border: none; font-weight: 600; cursor: pointer; font-size: 14px; }
.btn-confirm { background: #22c55e; color: #052e16; }
.btn-confirm:hover { background: #4ade80; }
.btn-confirm:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-skip { background: #475569; color: #e2e8f0; }
.btn-skip:hover { background: #64748b; }

.section-panel { margin-top: 24px; background: #1e293b; border-radius: 12px; border: 1px solid #334155; overflow: hidden; }
.section-header { padding: 14px 18px; background: #334155; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.section-header h3 { font-size: 15px; color: #38bdf8; }
.section-header .toggle-icon { color: #94a3b8; font-size: 14px; transition: transform 0.2s; }
.section-header.collapsed .toggle-icon { transform: rotate(-90deg); }
.section-body { padding: 18px; }
.section-body.collapsed { display: none; }

.checkpoint-timeline { display: flex; flex-direction: column; gap: 12px; }
.checkpoint-item { display: flex; gap: 12px; align-items: flex-start; padding: 10px 14px; background: #0f172a; border-radius: 8px; border-left: 4px solid #334155; }
.checkpoint-item.action-continue { border-left-color: #22c55e; }
.checkpoint-item.action-wait_user { border-left-color: #f59e0b; }
.checkpoint-item.action-add_task { border-left-color: #8b5cf6; }
.checkpoint-item.action-skip { border-left-color: #64748b; }
.checkpoint-item.action-done { border-left-color: #38bdf8; }
.cp-step { font-weight: 600; font-size: 13px; min-width: 100px; }
.cp-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.cp-badge.continue { background: #166534; color: #86efac; }
.cp-badge.wait_user { background: #78350f; color: #fbbf24; }
.cp-badge.add_task { background: #4c1d95; color: #c4b5fd; }
.cp-badge.skip { background: #374151; color: #9ca3af; }
.cp-badge.done { background: #1e3a5f; color: #7dd3fc; }
.cp-reason { font-size: 12px; color: #94a3b8; flex: 1; }
.cp-detail { font-size: 11px; color: #64748b; margin-top: 4px; }

.split-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
.split-card { background: #0f172a; border-radius: 8px; padding: 14px; border: 1px solid #334155; }
.split-card h4 { font-size: 14px; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.split-card h4.formula { color: #f472b6; }
.split-card h4.acupuncture { color: #34d399; }
.split-card h4.regimen { color: #fbbf24; }
.split-count { font-size: 24px; font-weight: 700; color: #e2e8f0; margin-bottom: 6px; }
.split-entities { font-size: 12px; color: #94a3b8; margin-bottom: 8px; max-height: 60px; overflow: hidden; }
.split-rels { display: flex; flex-wrap: wrap; gap: 4px; }
.split-rel-tag { font-size: 11px; padding: 2px 8px; border-radius: 4px; background: #1e293b; border: 1px solid #475569; color: #cbd5e1; }

.debate-round { background: #0f172a; border-radius: 8px; padding: 14px; margin-bottom: 12px; border: 1px solid #334155; }
.debate-round-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.debate-round-num { font-weight: 600; font-size: 14px; color: #f87171; }
.debate-conflict-type { font-size: 12px; color: #94a3b8; }
.debate-severity { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.debate-severity.high { background: #7f1d1d; color: #fca5a5; }
.debate-severity.medium { background: #78350f; color: #fbbf24; }
.debate-severity.low { background: #1e3a5f; color: #7dd3fc; }
.debate-claims { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 10px; }
.debate-claim { padding: 10px; border-radius: 6px; background: #1e293b; border: 1px solid #475569; }
.debate-claim-agent { font-weight: 600; font-size: 12px; color: #38bdf8; margin-bottom: 4px; }
.debate-claim-text { font-size: 12px; color: #cbd5e1; }
.debate-args { margin-top: 8px; }
.debate-arg { padding: 8px 10px; background: #1e293b; border-radius: 6px; margin-bottom: 6px; border-left: 3px solid #8b5cf6; }
.debate-arg-agent { font-weight: 600; font-size: 12px; color: #a78bfa; }
.debate-arg-text { font-size: 12px; color: #94a3b8; margin-top: 2px; }
.debate-resolved { font-size: 12px; padding: 4px 10px; border-radius: 6px; display: inline-block; }
.debate-resolved.yes { background: #166534; color: #86efac; }
.debate-resolved.no { background: #7f1d1d; color: #fca5a5; }

.dynamic-task-list { display: flex; flex-wrap: wrap; gap: 10px; }
.dynamic-task-card { background: #0f172a; border-radius: 8px; padding: 10px 14px; border: 1px solid #8b5cf6; min-width: 200px; }
.dynamic-task-id { font-weight: 600; font-size: 13px; color: #c4b5fd; }
.dynamic-task-info { font-size: 12px; color: #94a3b8; margin-top: 4px; }

.inquiry-questions { margin-top: 8px; }
.inquiry-q { padding: 6px 10px; margin-bottom: 4px; background: #1e293b; border-radius: 6px; font-size: 13px; color: #cbd5e1; border-left: 3px solid #38bdf8; }
.inquiry-answer-area { margin-top: 16px; }
.inquiry-label { display: block; font-size: 14px; font-weight: 600; color: #38bdf8; margin-bottom: 8px; }
.inquiry-textarea { width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 14px; line-height: 1.6; resize: vertical; outline: none; font-family: inherit; }
.inquiry-textarea:focus { border-color: #38bdf8; }
.inquiry-result-confirmed { font-size: 15px; color: #86efac; margin-bottom: 12px; }
.inquiry-result-excluded { font-size: 15px; color: #fca5a5; margin-bottom: 12px; }
.inquiry-result-excluded-list { font-size: 13px; color: #94a3b8; margin-top: 8px; }
.inquiry-match-detail { padding: 8px 12px; background: #0f172a; border-radius: 6px; margin-bottom: 6px; border-left: 3px solid #22c55e; }
.inquiry-match-name { font-weight: 600; color: #e2e8f0; font-size: 14px; }
.inquiry-match-conf { font-size: 12px; color: #fbbf24; margin-left: 8px; }
.inquiry-match-syms { font-size: 12px; color: #94a3b8; margin-top: 4px; }
</style>
</head>
<body>
<div class="container">
    <h1>Agent 协作调试可视化</h1>
    <div class="input-bar">
        <input id="question" type="text" placeholder="输入中医问题，如：我头痛口苦心烦易怒舌红苔黄脉弦数" />
        <button id="submitBtn" onclick="runDebug()">执行</button>
    </div>
    <div id="statusBar" class="status-bar"></div>
    <div id="dagFlow" class="dag-flow">
        <div class="empty-state">
            <div class="icon">🔬</div>
            <div>输入问题后点击执行，查看 Agent 协作流程</div>
        </div>
    </div>
    <div id="confirmPanel" class="confirm-panel" style="display:none"></div>
    <div id="checkpointPanel" class="section-panel" style="display:none"></div>
    <div id="splitPanel" class="section-panel" style="display:none"></div>
    <div id="debatePanel" class="section-panel" style="display:none"></div>
    <div id="dynamicPanel" class="section-panel" style="display:none"></div>
    <div id="detailPanel" class="detail-panel" style="display:none"></div>
</div>
<script>
const AGENT_META = {
    orchestrator: { icon: "🎯", label: "协调者" },
    entity_recognition: { icon: "🏷️", label: "实体识别" },
    kg_query: { icon: "🗂️", label: "KG查询" },
    diagnosis: { icon: "🩺", label: "辨证推理" },
    diagnosis_inquiry: { icon: "📋", label: "问诊生成" },
    formula: { icon: "💊", label: "方剂推荐" },
    acupuncture: { icon: "📍", label: "针灸方案" },
    regimen: { icon: "🥗", label: "养生建议" },
    review: { icon: "✅", label: "审核校验" },
    kg_supplement: { icon: "🔍", label: "KG补充查询" },
};

let traceData = [];
let selectedAgent = null;
let pendingConfirm = null;
let checkedSymptoms = {};
let lastResponse = {};

async function runDebug() {
    const q = document.getElementById("question").value.trim();
    console.log("[DEBUG] runDebug called, question:", q);
    if (!q) {
        document.getElementById("statusBar").textContent = "请输入问题后再点击执行";
        document.getElementById("statusBar").className = "status-bar error";
        return;
    }
    const btn = document.getElementById("submitBtn");
    const bar = document.getElementById("statusBar");
    btn.disabled = true;
    traceData = [];
    selectedAgent = null;
    pendingConfirm = null;
    checkedSymptoms = {};
    lastResponse = {};
    document.getElementById("detailPanel").style.display = "none";
    document.getElementById("confirmPanel").style.display = "none";
    document.getElementById("checkpointPanel").style.display = "none";
    document.getElementById("splitPanel").style.display = "none";
    document.getElementById("debatePanel").style.display = "none";
    document.getElementById("dynamicPanel").style.display = "none";
    renderDag();

    async function setStatus(msg) {
        bar.textContent = msg;
        bar.className = "status-bar";
    }

    try {
        await setStatus("🔄 正在连接...");
        console.log("[DEBUG] Sending POST to /api/agent/debug, body:", JSON.stringify({ question: q }));
        const resp = await fetch("/api/agent/debug", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: q }),
        });
        console.log("[DEBUG] Response received, status:", resp.status, "type:", resp.headers.get("content-type"));
        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullBuffer = "";
        let session_id = "";
        let intent = "";
        let complexity = "";
        let finalResult = null;
        let inquiryPending = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            fullBuffer += decoder.decode(value, { stream: true });

            // 按 "\n\n" 分割成完整事件块
            const blocks = fullBuffer.split("\n\n");
            fullBuffer = blocks.pop() || ""; // 最后一个可能是不完整的块，暂存

            for (const block of blocks) {
                if (!block.trim()) continue;

                // 一个 block 可能包含多个事件（如果网络分片刚好把两个事件拼在一起）
                // 但正常情况下每个 block 就是一个完整事件
                // 用正则提取所有 "event: xxx\ndata: xxx" 模式
                const eventRegex = /event:\s*(\S+)\s*\ndata:\s*(.+?)\s*$/gs;
                let match;
                while ((match = eventRegex.exec(block)) !== null) {
                    const eventType = match[1];
                    const eventData = match[2];

                    let data;
                    try {
                        data = JSON.parse(eventData);
                    } catch(e) {
                        console.warn("[SSE] 解析失败:", eventType, eventData.substring(0, 50));
                        continue;
                    }

                    switch (eventType) {
                        case "phase":
                            await setStatus("🔄 执行中: " + data.name);
                            break;
                        case "agent_start":
                            await setStatus("▶️ " + (AGENT_META[data.agent]?.label || data.agent) + " 开始执行...");
                            break;
                        case "agent_done": {
                            const agentLabel = AGENT_META[data.agent]?.label || data.agent;
                            const dur = data.duration_ms ? " (" + (data.duration_ms/1000).toFixed(1) + "s)" : "";
                            if (data.status === "done") {
                                await setStatus("✅ " + agentLabel + " 完成" + dur);
                                traceData.push({
                                    agent: data.agent,
                                    task_id: data.task_id || data.agent,
                                    status: "done",
                                    depends_on: [],
                                    duration_ms: data.duration_ms || 0,
                                    input: {},
                                    output: data
                                });
                                renderDag();
                            } else {
                                await setStatus("❌ " + agentLabel + " 失败" + dur);
                            }
                            break;
                        }
                        case "plan_update":
                            await setStatus("📋 动态追加任务: " + (data.added_tasks || []).join(", "));
                            break;
                        case "inquiry":
                            inquiryPending = data;
                            await setStatus("📋 需要问诊确认 — 请回答以下问题");
                            renderConfirmation(data);
                            break;
                        case "debate_start":
                            await setStatus("⚖️ 发现 " + (data.total_conflicts||0) + " 个冲突，开始辩论");
                            break;
                        case "debate_end":
                            await setStatus("✅ 辩论完成 — " + (data.total_rounds||0) + " 轮");
                            break;
                        case "final_result":
                            finalResult = data;
                            break;
                        case "done": {
                            if (inquiryPending) {
                                // inquiry 已在上面处理
                            } else if (finalResult) {
                                traceData = finalResult.trace || [];
                                lastResponse = finalResult;
                                let statusParts = ["✅ 完成"];
                                intent = finalResult.intent || "";
                                complexity = finalResult.complexity || "";
                                if (intent) statusParts.push("意图:" + intent);
                                if (complexity) statusParts.push("复杂度:" + complexity);
                                if (finalResult.checkpoint_decisions && finalResult.checkpoint_decisions.length) {
                                    statusParts.push("决策点:" + finalResult.checkpoint_decisions.length);
                                }
                                if (finalResult.debate_log && finalResult.debate_log.length) {
                                    statusParts.push("辩论:" + finalResult.debate_log.length + "轮");
                                }
                                if (finalResult.dynamic_tasks && finalResult.dynamic_tasks.length) {
                                    statusParts.push("动态任务:" + finalResult.dynamic_tasks.length);
                                }
                                await setStatus(statusParts.join(" | "));
                                renderDag();
                                renderCheckpoints(finalResult.checkpoint_decisions || []);
                                renderSubgraphSplit(finalResult.subgraph_split || {});
                                renderDebate(finalResult.debate_log || []);
                                renderDynamicTasks(finalResult.dynamic_tasks || []);
                            }
                            break;
                        }
                        case "error":
                            await setStatus("❌ 错误: " + (data.error || "未知错误"));
                            bar.className = "status-bar error";
                            break;
                    }
                }
            }
        }

    } catch (e) {
        console.error("[DEBUG] runDebug error:", e);
        await setStatus("❌ 错误: " + e.message + " (请打开浏览器F12控制台查看详情)");
        bar.className = "status-bar error";
    }
    btn.disabled = false;
}

function renderConfirmation(data) {
    const panel = document.getElementById("confirmPanel");
    panel.style.display = "block";
    const inquiries = data.inquiries || [];
    const originalSymptoms = data.original_symptoms || [];

    let html = '<div class="confirm-header"><h3>🩺 问诊确认 — 请回答以下问题</h3></div>';
    html += '<div class="confirm-body">';
    html += '<div class="confirm-desc">根据您描述的症状，系统找到了可能的疾病并生成了问诊问题。请根据您的实际情况回答：</div>';

    for (let i = 0; i < inquiries.length; i++) {
        const inq = inquiries[i];
        const diseaseName = inq.disease || "";
        const questions = inq.questions || [];

        html += '<div class="disease-card">';
        html += '<div class="disease-name">🏥 ' + diseaseName + '</div>';
        html += '<div class="inquiry-questions">';
        for (let j = 0; j < questions.length; j++) {
            html += '<div class="inquiry-q">❓ ' + questions[j] + '</div>';
        }
        html += '</div></div>';
    }

    html += '<div class="inquiry-answer-area">';
    html += '<label class="inquiry-label">请用自然语言描述您的症状和感受：</label>';
    html += '<textarea id="inquiryAnswer" class="inquiry-textarea" placeholder="例如：我经常觉得头晕，有时候会恶心，晚上睡不好..." rows="4"></textarea>';
    html += '</div>';

    html += '<div class="confirm-actions">';
    html += '<button class="btn-skip" onclick="skipConfirm()">跳过确认</button>';
    html += '<button class="btn-confirm" id="confirmBtn" onclick="submitInquiry()">提交回答</button>';
    html += '</div></div>';

    panel.innerHTML = html;
}

async function submitInquiry() {
    if (!pendingConfirm) return;
    const answer = document.getElementById("inquiryAnswer").value.trim();
    if (!answer) {
        alert("请先输入您的回答");
        return;
    }

    const btn = document.getElementById("confirmBtn");
    const bar = document.getElementById("statusBar");
    btn.disabled = true;
    bar.textContent = "🔍 辨证Agent正在评估您的回答...";
    bar.className = "status-bar";

    try {
        const resp = await fetch("/api/agent/debug/inquiry-evaluate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: pendingConfirm.question,
                session_id: pendingConfirm.session_id,
                candidate_diseases: pendingConfirm.candidate_diseases,
                user_answers: answer,
                entities: pendingConfirm.entities
            }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);

        const confirmed = data.confirmed_diseases || [];
        const excluded = data.excluded_diseases || [];
        const result = data.confirmation_result || {};

        const panel = document.getElementById("confirmPanel");
        let html = '<div class="confirm-header"><h3>🩺 问诊评估结果</h3></div>';
        html += '<div class="confirm-body">';

        if (confirmed.length > 0) {
            html += '<div class="inquiry-result-confirmed">✅ 确认疾病：<strong>' + confirmed.join("、") + '</strong></div>';
            if (result.confirmed_diseases) {
                for (const cd of result.confirmed_diseases) {
                    html += '<div class="inquiry-match-detail">';
                    html += '<span class="inquiry-match-name">' + cd.name + '</span>';
                    html += ' <span class="inquiry-match-conf">置信度 ' + Math.round((cd.confidence||0)*100) + '%</span>';
                    if (cd.matched_symptoms && cd.matched_symptoms.length) {
                        html += '<div class="inquiry-match-syms">匹配症状：' + cd.matched_symptoms.join("、") + '</div>';
                    }
                    html += '</div>';
                }
            }
        } else {
            html += '<div class="inquiry-result-excluded">❌ 未确认任何候选疾病</div>';
        }

        if (excluded.length > 0) {
            html += '<div class="inquiry-result-excluded-list">排除疾病：' + excluded.join("、") + '</div>';
        }

        if (confirmed.length > 0) {
            html += '<div class="confirm-actions">';
            html += '<button class="btn-confirm" onclick="continueAfterInquiry()">继续执行Agent流程</button>';
            html += '</div>';
        } else {
            html += '<div class="confirm-actions">';
            html += '<button class="btn-skip" onclick="skipConfirm()">使用默认疾病继续</button>';
            html += '</div>';
        }

        html += '</div>';
        panel.innerHTML = html;

        if (confirmed.length > 0) {
            pendingConfirm._confirmedDiseases = confirmed;
        }

        bar.textContent = "✅ 问诊评估完成 — " + (confirmed.length > 0 ? "确认: " + confirmed.join("、") : "未确认疾病");
        bar.className = "status-bar";

    } catch (e) {
        bar.textContent = "❌ 评估错误: " + e.message;
        bar.className = "status-bar error";
        btn.disabled = false;
    }
}

function continueAfterInquiry() {
    if (!pendingConfirm) return;
    const confirmed = pendingConfirm._confirmedDiseases || [];
    doConfirm(confirmed);
}

function skipConfirm() {
    if (!pendingConfirm) return;
    const candidates = pendingConfirm.candidate_diseases || [];
    const confirmedDiseases = candidates.slice(0, 2).map(c => typeof c === 'string' ? c : (c.disease || c.name || ''));
    doConfirm(confirmedDiseases);
}

async function doConfirm(confirmedDiseases) {
    const btn = document.getElementById("submitBtn");
    const bar = document.getElementById("statusBar");
    btn.disabled = true;
    bar.textContent = "🔄 正在根据确认结果执行 Agent 流程...";
    document.getElementById("confirmPanel").style.display = "none";

    try {
        const resp = await fetch("/api/agent/debug/confirm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: pendingConfirm.question,
                session_id: pendingConfirm.session_id,
                confirmed_diseases: confirmedDiseases,
                entities: pendingConfirm.entities
            }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        if (data.error) throw new Error(data.error);
        traceData = data.trace || [];
        lastResponse = data;
        let statusParts = ["✅ 完成"];
        if (confirmedDiseases && confirmedDiseases.length) {
            statusParts.push("确认: " + confirmedDiseases.join("、"));
        }
        if (data.intent) statusParts.push("意图:" + data.intent);
        if (data.complexity) statusParts.push("复杂度:" + data.complexity);
        if (data.checkpoint_decisions && data.checkpoint_decisions.length) {
            statusParts.push("决策点:" + data.checkpoint_decisions.length);
        }
        if (data.debate_log && data.debate_log.length) {
            statusParts.push("辩论:" + data.debate_log.length + "轮");
        }
        if (data.dynamic_tasks && data.dynamic_tasks.length) {
            statusParts.push("动态任务:" + data.dynamic_tasks.length);
        }
        bar.textContent = statusParts.join(" | ");
        bar.className = "status-bar";
        renderCheckpoints(data.checkpoint_decisions || []);
        renderSubgraphSplit(data.subgraph_split || {});
        renderDebate(data.debate_log || []);
        renderDynamicTasks(data.dynamic_tasks || []);
    } catch (e) {
        bar.textContent = "❌ 错误: " + e.message;
        bar.className = "status-bar error";
    }
    btn.disabled = false;
    pendingConfirm = null;
    renderDag();
}

function getSummary(agent, output) {
    if (!output) return "无输出";
    const o = output;
    switch(agent) {
        case "orchestrator": return "意图: " + (o.intent || "");
        case "entity_recognition": return (o.entity_count || 0) + " 个实体";
        case "kg_query": return o.kg_context ? "有KG结果" : "无KG结果";
        case "diagnosis": {
            const s = o.syndrome && o.syndrome.primary;
            return s ? s.name + " (" + Math.round((s.confidence||0)*100) + "%)" : "辨证完成";
        }
        case "diagnosis_inquiry": {
            const inquiries = o.inquiries || [];
            return inquiries.length ? "生成" + inquiries.length + "个疾病的问诊词" : "无问诊";
        }
        case "kg_supplement": {
            const sup = o.supplement_entities || [];
            return sup.length ? "补充查询" + sup.length + "个实体" : "无补充";
        }
        case "formula": {
            const f = o.primary_formula;
            return f ? f.name : "方剂推荐完成";
        }
        case "acupuncture": {
            const pts = o.primary_points || [];
            return pts.length ? pts.map(p=>p.name).join(", ") : "针灸方案完成";
        }
        case "regimen": return o.dietary_advice ? "养生建议完成" : "无建议";
        case "review": {
            const c = (o.conflicts||[]).length;
            return c ? c + " 个冲突" : "审核通过";
        }
        default: return "";
    }
}

function renderDag() {
    const container = document.getElementById("dagFlow");
    if (!traceData.length) {
        container.innerHTML = '<div class="empty-state"><div class="icon">🔬</div><div>输入问题后点击执行，查看 Agent 协作流程</div></div>';
        return;
    }

    const rows = [
        ["orchestrator"],
        ["entity_recognition"],
        ["kg_query"],
        // 问诊行（仅当存在 diagnosis_inquiry 任务时显示）
        ["diagnosis"],
        ["formula", "acupuncture", "regimen"],
        ["review"],
    ];

    // 动态插入问诊行
    const inquiryTask = traceData.find(x => x.agent === "diagnosis_inquiry");
    let inquiryRowIndex = -1;
    if (inquiryTask && inquiryTask.status !== "skipped") {
        // 在 kg_query 和 diagnosis 之间插入
        rows.splice(3, 0, ["diagnosis_inquiry"]);
    }

    let html = "";
    for (let ri = 0; ri < rows.length; ri++) {
        const row = rows[ri];
        const isParallel = row.length > 1;

        html += '<div class="dag-row">';
        for (const agent of row) {
            const t = traceData.find(x => x.agent === agent);
            const meta = AGENT_META[agent] || { icon: "📋", label: agent };
            const status = t ? t.status : "pending";
            const dur = t ? t.duration_ms : 0;
            const summary = t ? getSummary(agent, t.output) : "等待中";

            html += '<div class="agent-node ' + status + (selectedAgent===agent?' selected':'') + '" onclick="selectAgent(\'' + agent + '\')">';
            html += '<div class="agent-name"><span class="agent-icon">' + meta.icon + '</span>' + meta.label;
            html += ' <span class="agent-status ' + status + '">' + status + '</span></div>';
            if (dur > 0) html += '<div class="agent-duration">' + (dur/1000).toFixed(1) + 's</div>';
            html += '<div class="agent-summary">' + summary + '</div>';
            html += '</div>';
        }
        html += '</div>';

        if (ri < rows.length - 1) {
            html += '<div class="dag-arrow' + (isParallel ? ' parallel' : '') + '">↓</div>';
            if (isParallel) {
                html += '<div class="dag-arrow parallel">↓&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;↓</div>';
            }
        }
    }
    container.innerHTML = html;
}

function selectAgent(agent) {
    selectedAgent = agent;
    renderDag();
    const t = traceData.find(x => x.agent === agent);
    if (!t) return;

    const meta = AGENT_META[agent] || { icon: "📋", label: agent };
    const panel = document.getElementById("detailPanel");
    panel.style.display = "block";
    panel.innerHTML =
        '<div class="detail-header"><h3>' + meta.icon + ' ' + meta.label + ' (' + agent + ')</h3>' +
        '<button class="detail-close" onclick="closeDetail()">&times;</button></div>' +
        '<div class="detail-body">' +
        '<div class="detail-col"><h4>输入 (Input)</h4><pre>' + formatJson(t.input) + '</pre></div>' +
        '<div class="detail-col"><h4>输出 (Output)</h4><pre>' + formatJson(t.output) + '</pre></div>' +
        '</div>';
}

function closeDetail() {
    selectedAgent = null;
    document.getElementById("detailPanel").style.display = "none";
    renderDag();
}

function formatJson(obj) {
    if (!obj) return "null";
    try { return JSON.stringify(obj, null, 2); }
    catch(e) { return String(obj); }
}

document.getElementById("question").addEventListener("keydown", function(e) {
    if (e.key === "Enter") runDebug();
});

function toggleSection(panelId) {
    const panel = document.getElementById(panelId);
    const header = panel.querySelector('.section-header');
    const body = panel.querySelector('.section-body');
    if (header && body) {
        header.classList.toggle('collapsed');
        body.classList.toggle('collapsed');
    }
}

const ACTION_LABELS = {
    continue: "继续",
    wait_user: "等待用户",
    add_task: "追加任务",
    skip: "跳过",
    done: "结束"
};

function renderCheckpoints(decisions) {
    const panel = document.getElementById("checkpointPanel");
    if (!decisions.length) { panel.style.display = "none"; return; }
    panel.style.display = "block";

    let html = '<div class="section-header" onclick="toggleSection(\'checkpointPanel\')">' +
        '<h3>🎯 调度决策时间线</h3><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body"><div class="checkpoint-timeline">';

    for (const d of decisions) {
        const meta = AGENT_META[d.step] || { icon: "📋", label: d.step };
        const action = d.action || "continue";
        html += '<div class="checkpoint-item action-' + action + '">';
        html += '<div class="cp-step">' + meta.icon + ' ' + meta.label + '</div>';
        html += '<span class="cp-badge ' + action + '">' + (ACTION_LABELS[action] || action) + '</span>';
        html += '<div class="cp-reason">' + (d.reason || "—") + '</div>';
        if (d.new_tasks && d.new_tasks.length) {
            html += '<div class="cp-detail">追加任务: ' + d.new_tasks.map(t => t.task_id + '(' + (AGENT_META[t.agent]||{label:t.agent}).label + ')').join(", ") + '</div>';
        }
        if (d.skip_tasks && d.skip_tasks.length) {
            html += '<div class="cp-detail">跳过任务: ' + d.skip_tasks.join(", ") + '</div>';
        }
        if (d.candidate_diseases && d.candidate_diseases.length) {
            html += '<div class="cp-detail">候选疾病: ' + d.candidate_diseases.map(c => typeof c === 'string' ? c : (c.disease || c.name || '')).join(", ") + '</div>';
        }
        html += '</div>';
    }

    html += '</div></div>';
    panel.innerHTML = html;
}

function renderSubgraphSplit(split) {
    const panel = document.getElementById("splitPanel");
    if (!split || !Object.keys(split).length) { panel.style.display = "none"; return; }
    panel.style.display = "block";

    const icons = { formula: "💊", acupuncture: "📍", regimen: "🥗" };
    const labels = { formula: "方剂子图", acupuncture: "针灸子图", regimen: "养生子图" };

    let html = '<div class="section-header" onclick="toggleSection(\'splitPanel\')">' +
        '<h3>🔀 子图拆分</h3><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body"><div class="split-grid">';

    for (const [key, data] of Object.entries(split)) {
        html += '<div class="split-card">';
        html += '<h4 class="' + key + '">' + (icons[key]||"") + ' ' + (labels[key]||key) + '</h4>';
        html += '<div class="split-count">' + (data.entity_count || 0) + ' 个实体</div>';
        html += '<div class="split-entities">' + (data.entities || []).slice(0, 10).join("、") + ((data.entities||[]).length > 10 ? ' ...' : '') + '</div>';
        html += '<div class="split-rels">';
        for (const rk of (data.relation_keys || [])) {
            html += '<span class="split-rel-tag">' + rk + '</span>';
        }
        html += '</div></div>';
    }

    html += '</div></div>';
    panel.innerHTML = html;
}

function renderDebate(log) {
    const panel = document.getElementById("debatePanel");
    if (!log || !log.length) { panel.style.display = "none"; return; }
    panel.style.display = "block";

    let html = '<div class="section-header" onclick="toggleSection(\'debatePanel\')">' +
        '<h3>⚖️ 辩论过程</h3><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body">';

    for (const r of log) {
        const sev = r.severity || "medium";
        html += '<div class="debate-round">';
        html += '<div class="debate-round-header">';
        html += '<span class="debate-round-num">第 ' + r.round + ' 轮</span>';
        html += '<span class="debate-conflict-type">' + (r.conflict_type || "") + '</span>';
        html += '<span class="debate-severity ' + sev + '">' + (sev === "high" ? "严重" : sev === "medium" ? "中等" : "轻微") + '</span>';
        html += '</div>';

        html += '<div class="debate-claims">';
        const metaA = AGENT_META[r.agent_a] || { icon: "📋", label: r.agent_a };
        const metaB = AGENT_META[r.agent_b] || { icon: "📋", label: r.agent_b };
        html += '<div class="debate-claim"><div class="debate-claim-agent">' + metaA.icon + ' ' + metaA.label + '</div><div class="debate-claim-text">' + (r.claim_a || "") + '</div></div>';
        html += '<div class="debate-claim"><div class="debate-claim-agent">' + metaB.icon + ' ' + metaB.label + '</div><div class="debate-claim-text">' + (r.claim_b || "") + '</div></div>';
        html += '</div>';

        if (r.arguments && r.arguments.length) {
            html += '<div class="debate-args">';
            for (const arg of r.arguments) {
                const argMeta = AGENT_META[arg.agent] || { icon: "📋", label: arg.agent };
                html += '<div class="debate-arg">';
                html += '<div class="debate-arg-agent">' + argMeta.icon + ' ' + argMeta.label + '</div>';
                html += '<div class="debate-arg-text">' + (arg.revised_summary ? JSON.stringify(arg.revised_summary).substring(0, 200) : (arg.claim || "")) + '</div>';
                html += '</div>';
            }
            html += '</div>';
        }

        html += '<span class="debate-resolved ' + (r.resolved ? "yes" : "no") + '">' + (r.resolved ? "已解决" : "未解决") + '</span>';
        html += '</div>';
    }

    html += '</div>';
    panel.innerHTML = html;
}

function renderDynamicTasks(tasks) {
    const panel = document.getElementById("dynamicPanel");
    if (!tasks || !tasks.length) { panel.style.display = "none"; return; }
    panel.style.display = "block";

    let html = '<div class="section-header" onclick="toggleSection(\'dynamicPanel\')">' +
        '<h3>➕ 动态追加任务</h3><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body"><div class="dynamic-task-list">';

    for (const t of tasks) {
        const meta = AGENT_META[t.agent] || { icon: "📋", label: t.agent };
        html += '<div class="dynamic-task-card">';
        html += '<div class="dynamic-task-id">' + meta.icon + ' ' + t.task_id + '</div>';
        html += '<div class="dynamic-task-info">Agent: ' + meta.label + ' | 状态: ' + (t.status || "") + (t.duration_ms ? ' | ' + (t.duration_ms/1000).toFixed(1) + 's' : '') + '</div>';
        html += '</div>';
    }

    html += '</div></div>';
    panel.innerHTML = html;
}
</script>
</body>
</html>
"""