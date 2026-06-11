"""
审核Agent — 全局校验 + 冲突检测 + 辩论驱动 + 幻觉检测
"""

from core.base_agent import BaseAgent
from typing import Dict, List, Optional

REVIEW_SYSTEM = """你是一位资深中医临床审核专家。请对各Agent的输出进行全面审核。

【审核项目】
1. 方剂-证候一致性：推荐方剂与辨证结果是否匹配
2. 药物组成完整性：方剂君臣佐使配伍是否合理
3. 针灸-经脉一致性：腧穴选择与经脉分析是否一致
4. 药食禁忌冲突：方剂药物与饮食建议是否有冲突
5. 十八反十九畏：药物之间是否存在配伍禁忌
6. 整体方案协调性：诊断→方剂→针灸→养生是否逻辑自洽

【输出格式】严格输出JSON:
{
    "verified_claims": [
        {"claim": "声明", "source_agent": "agent名", "evidence": "KG证据", "status": "verified"}
    ],
    "uncertain_claims": [
        {"claim": "声明", "source_agent": "agent名", "reason": "不确定原因", "status": "uncertain"}
    ],
    "conflicts": [
        {
            "type": "drug_diet_conflict|formula_herb_mismatch|meridian_mismatch|incompatibility|other",
            "agent_a": "产出Agent A",
            "agent_b": "产出Agent B",
            "claim_a": "A的主张",
            "claim_b": "B的主张",
            "kg_evidence": "相关KG证据",
            "severity": "high|medium|low"
        }
    ],
    "warnings": ["警告信息"],
    "hallucination_checks": [
        {"entity": "被检查实体", "exists_in_kg": true, "note": "KG证实/模型推断"}
    ],
    "overall_assessment": "整体评估",
    "need_debate": false,
    "overall_confidence": 0.88
}"""

# 十八反
EIGHTEEN_ANTI = [
    (["乌头", "川乌", "草乌", "附子"], ["半夏", "瓜蒌", "贝母", "白蔹", "白及"]),
    (["甘草"], ["甘遂", "大戟", "海藻", "芫花"]),
    (["藜芦"], ["人参", "沙参", "丹参", "玄参", "细辛", "芍药"]),
]

# 十九畏
NINETEEN_FEAR = [
    ("硫磺", "朴硝"), ("水银", "砒霜"), ("狼毒", "密陀僧"),
    ("巴豆", "牵牛"), ("丁香", "郁金"), ("川乌", "犀角"),
    ("草乌", "犀角"), ("牙硝", "三棱"), ("官桂", "石脂"),
    ("人参", "五灵脂"),
]


class ReviewAgent(BaseAgent):
    """审核Agent — 全局校验 + 辩论驱动"""

    def __init__(self, qwen_api, kg_enhancer=None):
        super().__init__("review", qwen_api, kg_enhancer)

    def run(self, payload: Dict) -> Dict:
        diagnosis = payload.get("diagnosis", {})
        formula = payload.get("formula", {})
        acupuncture = payload.get("acupuncture", {})
        regimen = payload.get("regimen", {})
        question = payload.get("question", "")
        debate_context = payload.get("debate_context", None)

        # Phase 1: KG-based structural verification
        verification = self._verify_all(diagnosis, formula, acupuncture, regimen)

        # Phase 2: Rule-based conflict detection
        conflicts = self._detect_conflicts(formula, regimen, acupuncture, verification)

        # Phase 3: Hallucination detection
        hallucinations = self._detect_hallucinations(formula, acupuncture, regimen)

        # Phase 4: LLM comprehensive review
        llm_review = self._llm_review(question, diagnosis, formula, acupuncture,
                                       regimen, conflicts, hallucinations,
                                       debate_context)

        if not llm_review:
            return self._fallback(conflicts, hallucinations)

        all_conflicts = conflicts + llm_review.get("conflicts", [])
        all_hallucinations = hallucinations + llm_review.get("hallucination_checks", [])

        return {
            "verified_claims": llm_review.get("verified_claims", []),
            "uncertain_claims": llm_review.get("uncertain_claims", []),
            "conflicts": all_conflicts,
            "warnings": llm_review.get("warnings", []),
            "hallucination_checks": all_hallucinations,
            "overall_assessment": llm_review.get("overall_assessment", ""),
            "need_debate": llm_review.get("need_debate", False) or len(conflicts) > 0,
            "overall_confidence": llm_review.get("overall_confidence", 0.8),
            "debate_items": self._prepare_debate(all_conflicts),
            "verification_details": verification
        }

    def _verify_all(self, diagnosis: Dict, formula: Dict,
                    acupuncture: Dict, regimen: Dict) -> Dict:
        return {
            "formula_herb": self._check_formula_herbs(formula),
            "herb_syndrome": self._check_herb_syndrome(formula, diagnosis),
            "acupuncture_meridian": self._check_acupuncture_meridian(acupuncture),
        }

    def _check_formula_herbs(self, formula: Dict) -> Dict:
        """验证方剂-药物组成：PRE→comp→MED"""
        primary = formula.get("primary_formula", {})
        formula_name = primary.get("name", "")
        composition = primary.get("composition", [])

        kg_verified = []
        kg_missing = []

        if self.kg and formula_name:
            try:
                kg_results = self.kg.query_relations(formula_name, "PRE", "comp")
                if kg_results:
                    kg_herbs = set()
                    for key, values in kg_results.items():
                        for v in values:
                            kg_herbs.add(v.get("text", ""))
                    for herb_entry in composition:
                        herb_name = herb_entry.get("herb", "")
                        if herb_name in kg_herbs:
                            kg_verified.append(herb_name)
                        else:
                            kg_missing.append(herb_name)
            except Exception:
                pass

        return {
            "formula_name": formula_name,
            "kg_verified_herbs": kg_verified,
            "kg_missing_herbs": kg_missing,
            "all_verified": len(kg_missing) == 0 and len(composition) > 0
        }

    def _check_herb_syndrome(self, formula: Dict, diagnosis: Dict) -> Dict:
        """验证药物-证候匹配：MED→treat→SYN"""
        syndrome_info = diagnosis.get("syndrome", {})
        syndrome_name = ""
        if isinstance(syndrome_info.get("primary"), dict):
            syndrome_name = syndrome_info["primary"].get("name", "")

        matched = []
        unmatched = []

        if self.kg and syndrome_name:
            primary = formula.get("primary_formula", {})
            for herb_entry in primary.get("composition", []):
                herb_name = herb_entry.get("herb", "")
                if not herb_name:
                    continue
                try:
                    results = self.kg.query_relations(herb_name, "MED", "治疗")
                    if results:
                        targets = set()
                        for key, values in results.items():
                            for v in values:
                                targets.add(v.get("text", ""))
                        if syndrome_name in targets:
                            matched.append(herb_name)
                        else:
                            unmatched.append({"herb": herb_name, "kg_targets": list(targets)[:5]})
                    else:
                        unmatched.append({"herb": herb_name, "kg_targets": []})
                except Exception:
                    unmatched.append({"herb": herb_name, "kg_targets": []})

        return {"matched": matched, "unmatched": unmatched}

    def _check_acupuncture_meridian(self, acupuncture: Dict) -> Dict:
        """验证腧穴-经脉一致性：ACU→belongto→MER"""
        verified = []
        unverified = []

        if self.kg:
            for point in acupuncture.get("primary_points", []):
                point_name = point.get("name", "")
                expected_meridian = point.get("meridian", "")
                if not point_name:
                    continue
                try:
                    results = self.kg.query_relations(point_name, "ACU", "belongto")
                    if results:
                        kg_meridians = set()
                        for key, values in results.items():
                            for v in values:
                                kg_meridians.add(v.get("text", ""))
                        if expected_meridian in kg_meridians:
                            verified.append(point_name)
                        else:
                            unverified.append({
                                "point": point_name,
                                "expected": expected_meridian,
                                "kg_meridians": list(kg_meridians)
                            })
                except Exception:
                    pass

        return {"verified": verified, "unverified": unverified}

    # ──── Conflict Detection ────

    def _detect_conflicts(self, formula: Dict, regimen: Dict,
                          acupuncture: Dict, verification: Dict) -> List[Dict]:
        conflicts = []

        primary = formula.get("primary_formula", {})
        formula_herbs = [h.get("herb", "") for h in primary.get("composition", [])]

        # 十八反十九畏
        conflicts.extend(self._check_incompatibilities(formula_herbs))

        # Formula-herb KG mismatch
        fh = verification.get("formula_herb", {})
        if fh.get("kg_missing_herbs"):
            conflicts.append({
                "type": "formula_herb_mismatch",
                "agent_a": "formula",
                "agent_b": "kg",
                "claim_a": f"方剂组成包含: {', '.join(fh['kg_missing_herbs'])}",
                "claim_b": f"KG中{fh.get('formula_name', '')}不包含这些药物",
                "kg_evidence": f"KG: {fh.get('formula_name', '')}→comp→?",
                "severity": "medium"
            })

        # Acupuncture-meridian mismatch
        am = verification.get("acupuncture_meridian", {})
        for item in am.get("unverified", []):
            conflicts.append({
                "type": "meridian_mismatch",
                "agent_a": "acupuncture",
                "agent_b": "kg",
                "claim_a": f"{item['point']}归属{item['expected']}",
                "claim_b": f"KG归属: {item['kg_meridians']}",
                "kg_evidence": f"KG: {item['point']}→belongto→{item['kg_meridians']}",
                "severity": "medium"
            })

        # Drug-diet: formula herbs vs regimen recommended foods
        dietary = regimen.get("dietary_advice", {})
        rec_foods = [f.get("food", "") for f in dietary.get("recommended", [])]
        if self.kg and formula_herbs and rec_foods:
            for herb in formula_herbs:
                if not herb:
                    continue
                try:
                    results = self.kg.query_relations(herb, "MED", "不宜吃")
                    if results:
                        for key, values in results.items():
                            for v in values:
                                conflict_food = v.get("text", "")
                                if conflict_food in rec_foods:
                                    conflicts.append({
                                        "type": "drug_diet_conflict",
                                        "agent_a": "formula",
                                        "agent_b": "regimen",
                                        "claim_a": f"推荐药物: {herb}",
                                        "claim_b": f"推荐食物: {conflict_food}",
                                        "kg_evidence": f"KG: {herb}→不宜吃→{conflict_food}",
                                        "severity": "high"
                                    })
                except Exception:
                    continue

        return conflicts

    def _check_incompatibilities(self, herbs: List[str]) -> List[Dict]:
        """十八反十九畏检测"""
        conflicts = []

        for group_a, group_b in EIGHTEEN_ANTI:
            herbs_a = [h for h in herbs if any(a in h for a in group_a)]
            herbs_b = [h for h in herbs if any(b in h for b in group_b)]
            if herbs_a and herbs_b:
                conflicts.append({
                    "type": "incompatibility",
                    "agent_a": "formula",
                    "agent_b": "formula",
                    "claim_a": f"含: {', '.join(herbs_a)}",
                    "claim_b": f"含: {', '.join(herbs_b)}",
                    "kg_evidence": "十八反",
                    "severity": "high"
                })

        for a, b in NINETEEN_FEAR:
            has_a = any(a in h for h in herbs)
            has_b = any(b in h for h in herbs)
            if has_a and has_b:
                conflicts.append({
                    "type": "incompatibility",
                    "agent_a": "formula",
                    "agent_b": "formula",
                    "claim_a": f"含: {a}",
                    "claim_b": f"含: {b}",
                    "kg_evidence": f"十九畏: {a}畏{b}",
                    "severity": "high"
                })

        return conflicts

    # ──── Hallucination Detection ────

    def _detect_hallucinations(self, formula: Dict, acupuncture: Dict,
                                regimen: Dict) -> List[Dict]:
        """检测LLM幻觉 — 输出实体是否在KG中存在"""
        checks = []
        entities_to_check = []

        primary = formula.get("primary_formula", {})
        if primary.get("name"):
            entities_to_check.append((primary["name"], "PRE", "formula"))
        for herb in primary.get("composition", []):
            if herb.get("herb"):
                entities_to_check.append((herb["herb"], "MED", "formula"))

        for alt in formula.get("alternatives", []):
            if alt.get("name"):
                entities_to_check.append((alt["name"], "PRE", "formula"))

        for point in acupuncture.get("primary_points", []):
            if point.get("name"):
                entities_to_check.append((point["name"], "ACU", "acupuncture"))
        for point in acupuncture.get("secondary_points", []):
            if point.get("name"):
                entities_to_check.append((point["name"], "ACU", "acupuncture"))

        dietary = regimen.get("dietary_advice", {})
        for food in dietary.get("recommended", []):
            if food.get("food"):
                entities_to_check.append((food["food"], "FOO", "regimen"))
        for food in dietary.get("avoid", []):
            if food.get("food"):
                entities_to_check.append((food["food"], "FOO", "regimen"))

        if self.kg:
            for name, etype, source in set(entities_to_check):
                exists = self._entity_exists_in_kg(name, etype)
                checks.append({
                    "entity": name,
                    "type": etype,
                    "source_agent": source,
                    "exists_in_kg": exists,
                    "note": "KG证实" if exists else "模型推断"
                })

        return checks

    def _entity_exists_in_kg(self, name: str, etype: str) -> bool:
        """检查实体是否在KG中存在（通过L1查询判断）"""
        try:
            results = self.kg.query_relations_layered(name, etype, "L1")
            if isinstance(results, dict):
                return any(v for v in results.values() if v)
            return bool(results)
        except Exception:
            return False

    # ──── LLM Review ────

    def _llm_review(self, question: str, diagnosis: Dict, formula: Dict,
                    acupuncture: Dict, regimen: Dict, conflicts: List[Dict],
                    hallucinations: List[Dict], debate_ctx: Optional[Dict]) -> Dict:
        parts = []
        if question:
            parts.append(f"患者问题: {question}")

        syndrome = diagnosis.get("syndrome", {})
        if isinstance(syndrome.get("primary"), dict):
            parts.append(f"辨证: {syndrome['primary'].get('name', '')} "
                         f"(置信度{syndrome['primary'].get('confidence', 0)})")
        parts.append(f"治则: {diagnosis.get('treatment_principle', '')}")

        pf = formula.get("primary_formula", {})
        parts.append(f"方剂: {pf.get('name', '')} (置信度{pf.get('confidence', 0)})")
        herbs = [f"{h.get('herb','')}({h.get('role','')})" for h in pf.get("composition", [])]
        parts.append(f"组成: {', '.join(herbs)}")

        pts = [p.get("name", "") for p in acupuncture.get("primary_points", [])]
        parts.append(f"主穴: {', '.join(pts)}")
        parts.append(f"经脉分析: {acupuncture.get('meridian_analysis', '')}")

        da = regimen.get("dietary_advice", {})
        rec = [f.get("food", "") for f in da.get("recommended", [])]
        av = [f.get("food", "") for f in da.get("avoid", [])]
        parts.append(f"饮食: 推荐{rec}, 忌口{av}")

        if conflicts:
            parts.append(f"KG检测冲突({len(conflicts)}项):")
            for c in conflicts[:5]:
                parts.append(f"  [{c['severity']}] {c['type']}: {c.get('claim_a','')} vs {c.get('claim_b','')}")

        if hallucinations:
            unchecked = [h for h in hallucinations if not h.get("exists_in_kg")]
            if unchecked:
                parts.append(f"未验证实体: {[h['entity'] for h in unchecked]}")

        if debate_ctx:
            parts.append(f"辩论上下文(第{debate_ctx.get('round',0)}轮): {debate_ctx}")

        prompt = "\n".join(parts)
        messages = [
            {"role": "system", "content": REVIEW_SYSTEM},
            {"role": "user", "content": prompt + "\n\n请进行综合审核，输出JSON。"}
        ]

        try:
            response = self._llm_call(messages, temperature=0.2, max_tokens=1500)
            return self._parse_json_response(response)
        except Exception:
            return {}

    def _prepare_debate(self, conflicts: List[Dict]) -> List[Dict]:
        """将冲突转换为辩论项"""
        return [
            {
                "conflict_type": c["type"],
                "agent_a": c.get("agent_a", ""),
                "agent_b": c.get("agent_b", ""),
                "claim_a": c.get("claim_a", ""),
                "claim_b": c.get("claim_b", ""),
                "kg_evidence": c.get("kg_evidence", ""),
                "severity": c["severity"],
                "max_rounds": 3
            }
            for c in conflicts if c.get("severity") in ("high", "medium")
        ]

    def _fallback(self, conflicts: List[Dict], hallucinations: List[Dict]) -> Dict:
        return {
            "verified_claims": [],
            "uncertain_claims": [],
            "conflicts": conflicts,
            "warnings": ["审核Agent未能完成完整审核，已执行基础规则检查"],
            "hallucination_checks": hallucinations,
            "overall_assessment": "审核不完整",
            "need_debate": len(conflicts) > 0,
            "overall_confidence": 0.3,
            "debate_items": self._prepare_debate(conflicts)
        }
