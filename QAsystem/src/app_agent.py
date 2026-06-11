"""
多Agent协同 SSE API — 5 Agent 串行/并行管线 + 辩论机制
"""

from flask import Blueprint, request, jsonify, Response, stream_with_context
from kg_enhancer import KnowledgeGraphEnhancer
from qwen_api import QwenAPI
from core.agent_bus import AgentBus
from agents.diagnosis import DiagnosisAgent
from agents.formula import FormulaAgent
from agents.acupuncture import AcupunctureAgent
from agents.regimen import RegimenAgent
from agents.review import ReviewAgent
from agents.entity_recognition import EntityRecognitionAgent
from agents.kg_query import KGQueryAgent
from agents.orchestrator import OrchestratorAgent
from config import SYSTEM_CONFIG
import json
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

        # ── Phase 2: Entity Recognition ──
        yield sse_event("agent_start", {"agent": "entity_recognition"})

        entities_data = qwen_api.extract_entities(question)
        entities = []
        for e in (entities_data or []):
            entities.append({
                "text": e.get("text", ""),
                "label": e.get("label", e.get("type", "")),
                "type": e.get("type", e.get("label", ""))
            })

        yield sse_event("agent_done", {
            "agent": "entity_recognition",
            "entity_count": len(entities),
            "entities": [{"text": e["text"], "type": e["label"]} for e in entities[:10]]
        })

        # ── Phase 3: KG Query ──
        yield sse_event("agent_start", {"agent": "kg_query"})

        kg_context = ""
        if entities and kg_enhancer:
            kg_results = agents["kg_query"].run({
                "entities": entities,
                "question": question,
                "layer": "L2" if complexity in ("medium", "complex") else "L1"
            })
            kg_context = kg_results.get("kg_context", "")

        yield sse_event("agent_done", {
            "agent": "kg_query",
            "has_results": bool(kg_context)
        })

        # Simple QA: short-circuit
        if intent == "simple_qa" or intent == "knowledge_learning":
            yield from _stream_answer(qwen_api, question, kg_context, session_id, sse_event)
            return

        # ── Phase 4: Diagnosis Agent (always first in clinical pipeline) ──
        yield sse_event("agent_start", {"agent": "diagnosis"})

        diag_payload = {
            "question": question,
            "kg_context": kg_context,
            "entities": entities,
            "conversation_history": [],
            "collected_info": {}
        }
        diagnosis = agents["diagnosis"].execute(diag_payload, bus=bus)

        yield sse_event("agent_done", {
            "agent": "diagnosis",
            "syndrome": diagnosis.get("syndrome", {}).get("primary", {}).get("name", "") if isinstance(diagnosis.get("syndrome", {}).get("primary"), dict) else "",
            "confidence": diagnosis.get("overall_confidence", 0),
            "need_followup": diagnosis.get("need_followup", False)
        })

        if diagnosis.get("need_followup"):
            yield sse_event("followup_required", {
                "missing_info": diagnosis.get("missing_info", []),
                "follow_up_questions": diagnosis.get("follow_up_questions", [])
            })

        # ── Phase 5: Formula, Acupuncture, Regimen (parallel after diagnosis) ──
        downstream_payload = {
            "question": question,
            "diagnosis": diagnosis,
            "kg_context": kg_context,
            "entities": entities
        }

        # Formula
        yield sse_event("agent_start", {"agent": "formula"})
        formula = agents["formula"].execute(downstream_payload, bus=bus)
        yield sse_event("agent_done", {
            "agent": "formula",
            "formula": formula.get("primary_formula", {}).get("name", ""),
            "confidence": formula.get("overall_confidence", 0)
        })

        # Acupuncture
        yield sse_event("agent_start", {"agent": "acupuncture"})
        acupuncture = agents["acupuncture"].execute(downstream_payload, bus=bus)
        yield sse_event("agent_done", {
            "agent": "acupuncture",
            "points": [p.get("name", "") for p in acupuncture.get("primary_points", [])],
            "confidence": acupuncture.get("overall_confidence", 0)
        })

        # Regimen
        yield sse_event("agent_start", {"agent": "regimen"})
        regimen = agents["regimen"].execute(downstream_payload, bus=bus)
        yield sse_event("agent_done", {
            "agent": "regimen",
            "confidence": regimen.get("overall_confidence", 0)
        })

        # ── Phase 6: Review Agent ──
        yield sse_event("agent_start", {"agent": "review"})

        review_payload = {
            "question": question,
            "diagnosis": diagnosis,
            "formula": formula,
            "acupuncture": acupuncture,
            "regimen": regimen
        }
        review = agents["review"].execute(review_payload, bus=bus)

        yield sse_event("agent_done", {
            "agent": "review",
            "confidence": review.get("overall_confidence", 0),
            "conflicts_found": len(review.get("conflicts", [])),
            "need_debate": review.get("need_debate", False),
            "assessment": review.get("overall_assessment", "")
        })

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
            qwen_api, question, diagnosis, formula, acupuncture,
            regimen, review, debate_log, session_id, sse_event
        )

        yield sse_event("done", {
            "session_id": session_id,
            "intent": intent,
            "agents_executed": list(agents.keys()),
            "debate_rounds": len(debate_log)
        })

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*"
        }
    )


def _stream_final_answer(qwen_api, question, diagnosis, formula, acupuncture,
                         regimen, review, debate_log, session_id, sse_event):
    """生成最终临床方案文本并流式输出"""
    syndrome_name = ""
    if isinstance(diagnosis.get("syndrome", {}).get("primary"), dict):
        syndrome_name = diagnosis["syndrome"]["primary"].get("name", "")

    formula_name = formula.get("primary_formula", {}).get("name", "")
    formula_comp = formula.get("primary_formula", {}).get("composition", [])
    herbs_str = "、".join([h.get("herb", "") for h in formula_comp[:8]])

    primary_pts = "、".join([p.get("name", "") for p in acupuncture.get("primary_points", [])[:5]])
    meridian = acupuncture.get("meridian_analysis", "")

    dietary = regimen.get("dietary_advice", {})
    rec_foods = "、".join([f.get("food", "") for f in dietary.get("recommended", [])[:5]])
    avoid_foods = "、".join([f.get("food", "") for f in dietary.get("avoid", [])[:5]])

    treatment = diagnosis.get("treatment_principle", "")
    assessment = review.get("overall_assessment", "")
    confidence = review.get("overall_confidence", 0.8)
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
        if entities and kg_enhancer:
            kg_result = agents["kg_query"].run({
                "entities": entities, "question": question, "layer": "L2"
            })
            kg_context = kg_result.get("kg_context", "")
        # Simple QA
        if intent in ("simple_qa", "knowledge_learning"):
            answer = qwen_api.generate_answer(question, kg_context)
            return jsonify({
                "answer": answer,
                "entities": [{"text": e["text"], "type": e["label"]} for e in entities],
                "intent": intent,
                "session_id": session_id
            })

        # Clinical pipeline
        diag_payload = {
            "question": question, "kg_context": kg_context,
            "entities": entities, "conversation_history": [], "collected_info": {}
        }
        diagnosis = agents["diagnosis"].execute(diag_payload, bus=bus)

        ds_payload = {
            "question": question, "diagnosis": diagnosis,
            "kg_context": kg_context, "entities": entities
        }
        formula = agents["formula"].execute(ds_payload, bus=bus)
        acupuncture = agents["acupuncture"].execute(ds_payload, bus=bus)
        regimen = agents["regimen"].execute(ds_payload, bus=bus)

        review = agents["review"].execute({
            "question": question, "diagnosis": diagnosis,
            "formula": formula, "acupuncture": acupuncture, "regimen": regimen
        }, bus=bus)

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
