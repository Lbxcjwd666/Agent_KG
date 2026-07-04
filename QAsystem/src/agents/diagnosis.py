"""
辨证推理Agent — 5步辨证推理链 + 多轮追问 + KG证据关联 + 问诊管理

合并自原 diagnosis.py 和 diagnosis_reasoning.py，统一辨证推理职责。
"""

from core.base_agent import BaseAgent
from typing import Dict, List

DIAGNOSIS_SYSTEM = """你是一位资深中医辨证专家。请根据患者信息进行系统辨证。

【辨证步骤】
1. 症状聚类：识别主症、兼症、舌象(TNG)、脉象(PUL)，归类到脏腑经络
2. 证候匹配：在知识图谱中查询症状→证候(SYN)关联，计算匹配度排序
3. 病因推导：舌象→病因病机(TNG→reflect→BEC)，脉象→经脉(PUL→abpulse→MER)
4. 鉴别诊断：列出2-3个相似证候及其区分要点
5. 治则确定：基于最终证候确定治疗原则

【输出格式】严格输出JSON:
{
    "chief_complaint": "主诉概括",
    "symptom_clusters": [
        {"group": "热象症状", "symptoms": ["面红", "目赤", "口干"], "meridian": "肝经"}
    ],
    "syndrome": {
        "primary": {"name": "证候名", "label": "SYN", "confidence": 0.91},
        "alternatives": [{"name": "备选证候", "confidence": 0.72}]
    },
    "etiology": {
        "cause": "病因",
        "mechanism": "病机演变",
        "pathway": ["A→B→C"],
        "evidence": ["舌红苔黄→reflect→肝火上炎"]
    },
    "differential": [
        {"syndrome": "相似证候", "key_difference": "区分要点"}
    ],
    "treatment_principle": "治则概括",
    "missing_info": ["缺失的四诊信息，如舌象、脉象等"],
    "follow_up_questions": ["追问1", "追问2"],
    "reasoning_chain": [
        {
            "step": 1,
            "name": "症状聚类",
            "conclusion": "归类结论",
            "evidence": ["KG三元组1", "KG三元组2"],
            "confidence": 0.90
        }
    ],
    "overall_confidence": 0.85
}

【重要】
- 如果四诊信息不足（缺舌象/脉象等），在missing_info中列出，在follow_up_questions中生成追问
- 每一步推理必须在evidence中引用具体的KG查询路径（如 TNG→reflect→BEC）
- 无KG证据的推理标注为"模型推断"
- confidence基于证据强度和症状覆盖度综合评估"""


class DiagnosisAgent(BaseAgent):
    """辨证推理Agent — 5步推理链 + KG证据关联 + 问诊管理"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("diagnosis", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        mode = payload.get("mode", "diagnose")

        if mode == "inquiry":
            return self._handle_inquiry(payload)
        elif mode == "confirm":
            return self._handle_user_confirmation(payload)
        else:
            return self._handle_diagnosis(payload)

    # ══════════════════════════════════════════════════════════
    # 模式一：正常辨证推理
    # ══════════════════════════════════════════════════════════

    def _handle_diagnosis(self, payload: Dict) -> Dict:
        """正常辨证推理流程"""
        question = payload.get("question", "")
        kg_context = payload.get("kg_context", "")
        entities = payload.get("entities", [])
        conversation_history = payload.get("conversation_history", [])
        collected_info = payload.get("collected_info", {})
        complexity = payload.get("complexity", "simple")
        subgraph = payload.get("subgraph", {})

        patient_info = self._build_patient_context(question, entities, collected_info)

        if not kg_context and self.kg and entities:
            kg_context = self._query_kg_for_diagnosis(entities, complexity)

        if kg_context and self.kg and entities and not subgraph:
            supplement = self._query_kg_supplement(entities, kg_context, complexity)
            if supplement:
                kg_context = kg_context + "\n" + supplement

        prompt = self._build_prompt(patient_info, kg_context, conversation_history)
        messages = [
            {"role": "system", "content": DIAGNOSIS_SYSTEM},
            {"role": "user", "content": prompt}
        ]

        max_tokens = 2500 if complexity == "complex" else 2000
        response = self._llm_call(messages, temperature=0.3, max_tokens=max_tokens)
        result = self._parse_json_response(response)

        if not result:
            return self._fallback(question, kg_context)

        missing = result.get("missing_info", [])
        need_followup = len(missing) > 0 and len(conversation_history) < 6

        reasoning_chain = result.get("reasoning_chain", [])
        if not reasoning_chain:
            reasoning_chain = self._build_reasoning_chain(result)

        return {
            "chief_complaint": result.get("chief_complaint", question),
            "symptom_clusters": result.get("symptom_clusters", []),
            "syndrome": result.get("syndrome", {}),
            "etiology": result.get("etiology", {}),
            "differential": result.get("differential", []),
            "treatment_principle": result.get("treatment_principle", ""),
            "reasoning_chain": reasoning_chain,
            "overall_confidence": result.get("overall_confidence", 0.7),
            "missing_info": missing,
            "follow_up_questions": result.get("follow_up_questions", []),
            "need_followup": need_followup,
            "kg_context_used": bool(kg_context)
        }

    # ══════════════════════════════════════════════════════════
    # 模式二：问诊生成 — 为候选疾病生成通俗问诊词
    # ══════════════════════════════════════════════════════════

    def _handle_inquiry(self, payload: Dict) -> Dict:
        """
        处理问诊生成：为每个候选疾病生成通俗问诊问题
        输入: candidate_diseases (subgraph中标记的候选疾病列表)
        输出: {need_inquiry: True, inquiries: [...]}
        """
        candidate_diseases = payload.get("candidate_diseases", [])
        # entities 参数保留用于未来扩展，当前由 KG Query 提供症状信息
        payload.get("entities", [])

        if not candidate_diseases:
            return {
                "need_inquiry": False,
                "inquiries": [],
                "chief_complaint": "",
                "syndrome": {},
                "treatment_principle": "",
                "overall_confidence": 0.0,
                "reasoning_chain": [{
                    "step": 0,
                    "name": "问诊生成",
                    "conclusion": "无候选疾病，跳过问诊",
                    "evidence": [],
                    "confidence": 0.0
                }]
            }

        all_inquiries = []

        for cand in candidate_diseases[:5]:
            disease_name = cand.get("disease", "") if isinstance(cand, dict) else str(cand)
            symptoms = cand.get("symptoms", [])
            hit_count = cand.get("hit_count", 0)

            if not disease_name:
                continue

            questions = self.generate_inquiry_questions(disease_name, symptoms)
            all_inquiries.append({
                "disease": disease_name,
                "hit_count": hit_count,
                "symptoms_from_kg": symptoms,
                "questions": questions
            })

        return {
            "need_inquiry": True,
            "inquiries": all_inquiries,
            "candidate_diseases": candidate_diseases,
            "chief_complaint": f"发现{len(all_inquiries)}个候选疾病，需进一步问诊确认",
            "syndrome": {},
            "treatment_principle": "",
            "overall_confidence": 0.0,
            "reasoning_chain": [{
                "step": 0,
                "name": "问诊确认",
                "conclusion": f"生成{len(all_inquiries)}个疾病的问诊词，等待用户回答",
                "evidence": [f"候选疾病: {d.get('disease', '')}" for d in all_inquiries],
                "confidence": 0.0
            }]
        }

    def generate_inquiry_questions(self, disease_name: str,
                                   disease_symptoms: List[str]) -> List[str]:
        """将专业术语症状转为通俗易懂的问诊问题"""
        if not disease_symptoms:
            return [f"您是否被诊断过{disease_name}？"]

        prompt = f"""你是一位经验丰富的中医问诊医生。请将以下中医疾病症状术语转换为通俗易懂的问诊问题。

疾病：{disease_name}
该疾病的典型症状（专业术语）：{', '.join(disease_symptoms[:15])}

要求：
1. 每个症状生成1个问题
2. 使用口语化表达，避免专业术语
3. 问题简洁明了，让患者能理解并回答
4. 优先询问患者主观感受（如"您是否觉得..."）
5. 输出JSON格式：{{"questions": [...]}}"""

        messages = [{"role": "user", "content": prompt}]
        response = self._llm_call(messages, temperature=0.3, max_tokens=500)
        result = self._parse_json_response(response)
        return result.get("questions", [f"您是否有{disease_name}相关症状？"])

    # ══════════════════════════════════════════════════════════
    # 模式三：用户回答评估 — 确认/排除疾病
    # ══════════════════════════════════════════════════════════

    def _handle_user_confirmation(self, payload: Dict) -> Dict:
        """
        处理用户回答，评估确认哪些候选疾病
        输入: candidate_diseases + user_answers
        输出: {confirmed_diseases: [...], excluded_diseases: [...]}
        """
        candidate_diseases = payload.get("candidate_diseases", [])
        # entities 参数保留用于未来扩展，当前由 KG Query 提供症状信息
        payload.get("entities", [])
        user_answers = payload.get("user_answers", "")
        question = payload.get("question", "")

        if not candidate_diseases or not user_answers:
            return {
                "need_inquiry": False,
                "confirmed_diseases": [],
                "excluded_diseases": [],
                "chief_complaint": question,
                "syndrome": {"primary": {"name": "待完善", "confidence": 0.3}},
                "treatment_principle": "请补充更多症状信息",
                "overall_confidence": 0.3,
                "reasoning_chain": [{
                    "step": 1,
                    "name": "疾病确认",
                    "conclusion": "缺少用户回答，无法确认",
                    "evidence": [],
                    "confidence": 0.3
                }],
                "request_kg_supplement": False
            }

        confirmed_diseases = []
        excluded_diseases = []

        for cand in candidate_diseases[:5]:
            disease_name = cand.get("disease", "") if isinstance(cand, dict) else str(cand)
            symptoms = cand.get("symptoms", [])

            if not disease_name:
                continue

            evaluation = self.evaluate_disease_confirmation(
                disease_name, symptoms, user_answers
            )

            if evaluation.get("confirmed", False):
                confirmed_diseases.append({
                    "name": disease_name,
                    "confidence": evaluation.get("confidence", 0.5),
                    "matched_symptoms": evaluation.get("matched_symptoms", []),
                    "reason": evaluation.get("reason", "")
                })
            else:
                excluded_diseases.append({
                    "name": disease_name,
                    "confidence": evaluation.get("confidence", 0.0),
                    "reason": evaluation.get("reason", "症状不匹配")
                })

        # 按置信度排序
        confirmed_diseases.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        excluded_diseases.sort(key=lambda x: x.get("confidence", 0), reverse=True)

        chief_complaint = ""
        syndrome = {}
        treatment_principle = ""
        overall_confidence = 0.3
        request_kg_supplement = False

        if confirmed_diseases:
            primary = confirmed_diseases[0]
            chief_complaint = f"确认疾病: {', '.join(d['name'] for d in confirmed_diseases)}"
            syndrome = {
                "primary": {
                    "name": primary["name"],
                    "label": "DIS",
                    "confidence": primary["confidence"]
                }
            }
            overall_confidence = primary["confidence"]
            request_kg_supplement = True
        else:
            chief_complaint = "未确认任何候选疾病"
            syndrome = {"primary": {"name": "待完善", "confidence": 0.3}}
            treatment_principle = "请补充更多症状信息"

        reasoning_chain = [{
            "step": 1,
            "name": "疾病确认",
            "conclusion": chief_complaint,
            "evidence": [
                f"确认: {d['name']} (置信度: {d['confidence']:.2f})"
                for d in confirmed_diseases
            ] + [
                f"排除: {d['name']} (置信度: {d['confidence']:.2f})"
                for d in excluded_diseases
            ],
            "confidence": overall_confidence
        }]

        return {
            "need_inquiry": False,
            "confirmed_diseases": confirmed_diseases,
            "excluded_diseases": excluded_diseases,
            "chief_complaint": chief_complaint,
            "syndrome": syndrome,
            "treatment_principle": treatment_principle,
            "overall_confidence": overall_confidence,
            "reasoning_chain": reasoning_chain,
            "request_kg_supplement": request_kg_supplement
        }

    def evaluate_disease_confirmation(self, disease_name: str,
                                     disease_symptoms: List[str],
                                     user_answers: str) -> Dict:
        """根据用户回答判断是否患有某疾病"""
        prompt = f"""你是一位经验丰富的中医问诊医生。请根据患者的回答，判断其是否可能患有指定疾病。

疾病：{disease_name}
该疾病的典型症状：{', '.join(disease_symptoms[:15])}

患者回答：{user_answers}

请分析：
1. 患者回答中是否提到了{disease_name}的典型症状
2. 症状匹配的置信度（0-1）
3. 匹配了哪些具体症状
4. 简要说明判断理由

输出JSON格式：
{{
    "confirmed": true/false,
    "confidence": 0.xx,
    "matched_symptoms": ["症状1", "症状2"],
    "reason": "判断理由"
}}

判断标准：
- 患者明确提到至少1个典型症状 → confirmed=true, confidence≥0.5
- 患者否认或症状完全不匹配 → confirmed=false, confidence<0.5
- 患者描述模糊但可能相关 → confirmed=true, confidence 0.3-0.5"""

        messages = [{"role": "user", "content": prompt}]
        response = self._llm_call(messages, temperature=0.3, max_tokens=500)
        result = self._parse_json_response(response)
        if not result:
            return {"confirmed": False, "confidence": 0.0, "matched_symptoms": [], "reason": "解析失败"}
        return result

    # ══════════════════════════════════════════════════════════
    # 辅助方法
    # ══════════════════════════════════════════════════════════

    def _build_patient_context(self, question: str, entities: list,
                               collected: Dict) -> str:
        parts = [f"患者描述: {question}"]
        if entities:
            entity_str = ", ".join([f"{e.get('text','')}({e.get('label','')})"
                                    for e in entities[:10]])
            parts.append(f"已识别实体: {entity_str}")
        if collected:
            parts.append(f"已采集信息: {collected}")
        return "\n".join(parts)

    def _query_kg_for_diagnosis(self, entities: list, complexity: str = "simple") -> str:
        """根据复杂度分层查询KG获取辨证所需信息（仅在无kg_context时调用）"""
        parts = []
        layer = "ALL" if complexity in ("medium", "complex") else "L1"
        for ent in entities[:5]:
            text = ent.get("text", ent.get("original_text", ""))
            etype = ent.get("label", ent.get("type", ""))
            if not text or not etype:
                continue
            try:
                results = self.kg.query_relations_layered(text, etype, layer)
                if results:
                    ctx = self.kg.format_kg_context(results, text, etype)
                    parts.append(ctx)
            except Exception:
                continue

        if self.kg and complexity in ("medium", "complex"):
            for ent in entities[:3]:
                text = ent.get("text", "")
                etype = ent.get("label", ent.get("type", ""))
                if text and etype:
                    try:
                        hop_results = self.kg.query_multi_hop(text, etype, max_hops=2)
                        if hop_results:
                            hop_ctx = self._summarize_kg(hop_results)
                            if hop_ctx:
                                parts.append(f"【多跳关联】\n{hop_ctx}")
                    except Exception:
                        continue
        return "\n".join(parts)

    def _query_kg_supplement(self, entities: list, kg_context: str,
                             complexity: str = "simple") -> str:
        """补充查询：当kg_query已提供kg_context但未提供subgraph时"""
        if complexity not in ("medium", "complex") or not self.kg:
            return ""

        parts = []
        for ent in entities[:3]:
            text = ent.get("text", "")
            etype = ent.get("label", ent.get("type", ""))
            if text and etype:
                try:
                    hop_results = self.kg.query_multi_hop(text, etype, max_hops=2)
                    if hop_results:
                        hop_ctx = self._summarize_kg(hop_results)
                        if hop_ctx:
                            parts.append(f"【多跳关联】\n{hop_ctx}")
                except Exception:
                    continue
        return "\n".join(parts)

    def _summarize_kg(self, kg_results: Dict) -> str:
        """将KG查询结果摘要为自然语言"""
        parts = []
        for entity, data in kg_results.items():
            if isinstance(data, dict):
                for key, values in data.items():
                    if values:
                        names = [v.get("text", "") for v in values[:3]]
                        parts.append(f"{entity} {key}: {', '.join(names)}")
            elif isinstance(data, list):
                for item in data[:5]:
                    text = item.get("text", "")
                    hops = item.get("hops", 0)
                    rels = item.get("relations", [])
                    if text:
                        parts.append(f"{entity} —{'→'.join(rels)}→ {text} ({hops}跳)")
        return "\n".join(parts[:20])

    def _build_reasoning_chain(self, result: Dict) -> List[Dict]:
        """当LLM未输出reasoning_chain时，从结果字段自动构建推理链"""
        chain = []

        if result.get("symptom_clusters"):
            chain.append({
                "step": 1,
                "name": "症状聚类",
                "conclusion": f"识别{len(result['symptom_clusters'])}组症状群",
                "evidence": [sc.get("meridian", "") for sc in result["symptom_clusters"] if sc.get("meridian")],
                "confidence": 0.85
            })

        syndrome = result.get("syndrome", {})
        primary = syndrome.get("primary", {})
        if primary:
            chain.append({
                "step": 2,
                "name": "证候匹配",
                "conclusion": f"主证候: {primary.get('name', '')}",
                "evidence": [f"匹配度: {primary.get('confidence', 0)}"],
                "confidence": primary.get("confidence", 0.7)
            })

        etiology = result.get("etiology", {})
        if etiology.get("cause"):
            chain.append({
                "step": 3,
                "name": "病因推导",
                "conclusion": f"病因: {etiology['cause']}",
                "evidence": etiology.get("evidence", []),
                "confidence": etiology.get("confidence", 0.7)
            })

        if result.get("differential"):
            chain.append({
                "step": 4,
                "name": "鉴别诊断",
                "conclusion": f"列出{len(result['differential'])}个鉴别证候",
                "evidence": [d.get("key_difference", "") for d in result["differential"]],
                "confidence": 0.75
            })

        if result.get("treatment_principle"):
            chain.append({
                "step": 5,
                "name": "治则确定",
                "conclusion": result["treatment_principle"],
                "evidence": [],
                "confidence": result.get("overall_confidence", 0.7)
            })

        return chain

    def _build_prompt(self, patient_info: str, kg_context: str,
                      history: list) -> str:
        prompt = f"【患者信息】\n{patient_info}"
        if kg_context:
            prompt += f"\n\n【知识图谱参考】\n{kg_context}"
        if history:
            recent = history[-6:]
            hist_str = "\n".join([f"{m['role']}: {m['content'][:200]}"
                                  for m in recent])
            prompt += f"\n\n【对话历史】\n{hist_str}"
        prompt += "\n\n请进行系统辨证分析，输出JSON。"
        return prompt

    def _fallback(self, question: str, kg: str) -> Dict:
        return {
            "chief_complaint": question,
            "symptom_clusters": [],
            "syndrome": {"primary": {"name": "待完善", "confidence": 0.3}},
            "etiology": {"cause": "待分析", "mechanism": "待分析"},
            "differential": [],
            "treatment_principle": "请补充舌脉信息后再辨证",
            "reasoning_chain": [],
            "missing_info": ["舌象", "脉象"],
            "follow_up_questions": ["请问舌象如何？舌色、舌苔厚薄？", "请问脉象怎样？浮沉迟数？"],
            "need_followup": True,
            "overall_confidence": 0.3,
            "kg_context_used": bool(kg)
        }
