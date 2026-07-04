# -*- coding: utf-8 -*-
"""
中医多智能体系统实验评估脚本

用法:
  1. 先启动后端服务: python app.py
  2. 运行实验:       python eval_experiment.py
  3. 可选参数:
     --count N        只测试前N条（默认全部100条）
     --output PATH    输出文件路径（默认 eval/results.json）
     --mode MODE      运行模式: full(默认) | simple | debug
     --delay SECONDS  每条问题间隔秒数（默认5秒，避免限流）

输出:
  - 每条问题的完整Agent执行结果
  - 汇总统计：实体识别率、KG命中率、各Agent耗时、辨证准确率等
  - 实验报告: eval/experiment_report.txt
"""

import requests
import json
import time
import sys
import os
import argparse
from datetime import datetime
from collections import defaultdict, Counter

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.json")
DEFAULT_OUTPUT = os.path.join(os.path.dirname(__file__), "results.json")

STREAM_URL = "http://localhost:5000/api/agent/chat/stream"
DEBUG_URL = "http://localhost:5000/api/agent/debug"


def load_dataset(path: str, count: int = None) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if count:
        data = data[:count]
    return data


def call_stream_api(question: str, timeout: int = 180) -> dict:
    start_time = time.time()
    events = []
    final_answer = ""
    agent_timings = {}
    entities = []
    kg_context = ""
    diagnosis_result = {}
    formula_result = {}
    acupuncture_result = {}
    regimen_result = {}
    review_result = {}
    inquiry_data = None

    try:
        resp = requests.post(
            STREAM_URL,
            json={"question": question, "use_debate": False},
            stream=True,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

        event_type = None
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    data = {"raw": line[6:]}

                elapsed = time.time() - start_time
                events.append({"event": event_type, "data": data, "elapsed_s": round(elapsed, 3)})

                if event_type == "agent_start":
                    agent_name = data.get("agent", "unknown")
                    agent_timings[agent_name] = {"start": elapsed, "end": None}
                elif event_type == "agent_done":
                    agent_name = data.get("agent", "unknown")
                    if agent_name in agent_timings:
                        agent_timings[agent_name]["end"] = elapsed
                        agent_timings[agent_name]["duration"] = round(elapsed - agent_timings[agent_name]["start"], 3)
                elif event_type == "entities":
                    entities = data.get("entities", [])
                elif event_type == "kg_result":
                    kg_context = data.get("kg_context", "")
                elif event_type == "answer":
                    final_answer = data.get("answer", "")
                elif event_type == "inquiry":
                    inquiry_data = data

                event_type = None

    except requests.exceptions.ConnectionError:
        return {"error": "无法连接服务，请先启动: python app.py"}
    except Exception as e:
        return {"error": str(e)}

    total_time = time.time() - start_time

    for ev in events:
        et = ev["event"]
        d = ev["data"]
        if et == "agent_done":
            agent_name = d.get("agent", "")
            result = d.get("result", {})
            if agent_name == "diagnosis":
                diagnosis_result = result
            elif agent_name == "formula":
                formula_result = result
            elif agent_name == "acupuncture":
                acupuncture_result = result
            elif agent_name == "regimen":
                regimen_result = result
            elif agent_name == "review":
                review_result = result

    return {
        "total_s": round(total_time, 3),
        "events": events,
        "agent_timings": agent_timings,
        "entities": entities,
        "kg_context_len": len(kg_context),
        "final_answer": final_answer,
        "diagnosis": diagnosis_result,
        "formula": formula_result,
        "acupuncture": acupuncture_result,
        "regimen": regimen_result,
        "review": review_result,
        "inquiry_triggered": inquiry_data is not None,
        "inquiry_data": inquiry_data,
    }


def call_debug_api(question: str, timeout: int = 180) -> dict:
    try:
        resp = requests.post(
            DEBUG_URL,
            json={"question": question},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"error": "无法连接服务，请先启动: python app.py"}
    except Exception as e:
        return {"error": str(e)}


def evaluate_entity_recognition(result: dict, expected_entities: list) -> dict:
    recognized = []
    for ent in result.get("entities", []):
        if isinstance(ent, dict):
            recognized.append(ent.get("text", ""))
        else:
            recognized.append(str(ent))

    expected_set = set(e.lower().strip() for e in expected_entities)
    recognized_set = set(e.lower().strip() for e in recognized)

    if not expected_set:
        return {"precision": 0, "recall": 0, "f1": 0, "matched": [], "missed": list(expected_set)}

    matched = expected_set & recognized_set
    missed = expected_set - recognized_set

    precision = len(matched) / len(recognized_set) if recognized_set else 0
    recall = len(matched) / len(expected_set) if expected_set else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "matched": sorted(matched),
        "missed": sorted(missed),
    }


def evaluate_diagnosis(result: dict, expected_category: str) -> dict:
    diagnosis = result.get("diagnosis", {})
    syndrome = diagnosis.get("syndrome", "") or diagnosis.get("primary_syndrome", "")
    disease = diagnosis.get("disease", "") or diagnosis.get("primary_disease", "")
    all_syndromes = diagnosis.get("all_syndromes", [])

    category_lower = expected_category.lower()
    matched = False
    match_source = ""

    for field_val in [syndrome, disease] + all_syndromes:
        if field_val and category_lower in str(field_val).lower():
            matched = True
            match_source = field_val
            break

    return {
        "category_match": matched,
        "syndrome": syndrome,
        "disease": disease,
        "all_syndromes": all_syndromes,
        "expected_category": expected_category,
    }


def run_experiment(dataset: list, mode: str = "full", delay: float = 5.0) -> list:
    results = []
    total = len(dataset)

    for i, item in enumerate(dataset):
        qid = item["id"]
        question = item["question"]
        expected_entities = item.get("expected_entities", [])
        expected_category = item.get("category", "")
        difficulty = item.get("difficulty", "medium")

        print(f"\n[{i+1}/{total}] ID={qid} | 难度={difficulty} | 类别={expected_category}")
        print(f"  问题: {question[:60]}...")

        if mode == "debug":
            result = call_debug_api(question)
        else:
            result = call_stream_api(question)

        if "error" in result:
            print(f"  ❌ 错误: {result['error']}")
            results.append({
                "id": qid,
                "question": question,
                "error": result["error"],
                "category": expected_category,
                "difficulty": difficulty,
            })
            time.sleep(delay)
            continue

        entity_eval = evaluate_entity_recognition(result, expected_entities)
        diagnosis_eval = evaluate_diagnosis(result, expected_category)

        total_s = result.get("total_s", 0)
        agent_timings = result.get("agent_timings", {})
        inquiry_triggered = result.get("inquiry_triggered", False)

        print(f"  耗时: {total_s}s | 实体F1: {entity_eval['f1']} | 辨证匹配: {'✅' if diagnosis_eval['category_match'] else '❌'}")
        print(f"  识别实体: {entity_eval['matched']} | 遗漏: {entity_eval['missed'][:5]}")
        print(f"  辨证结果: {diagnosis_eval['syndrome'] or diagnosis_eval['disease']}")
        if inquiry_triggered:
            print(f"  ⚠️ 触发了问诊确认")

        results.append({
            "id": qid,
            "question": question,
            "category": expected_category,
            "difficulty": difficulty,
            "total_s": total_s,
            "agent_timings": agent_timings,
            "entity_eval": entity_eval,
            "diagnosis_eval": diagnosis_eval,
            "inquiry_triggered": inquiry_triggered,
            "final_answer_len": len(result.get("final_answer", "")),
            "has_formula": bool(result.get("formula")),
            "has_acupuncture": bool(result.get("acupuncture")),
            "has_regimen": bool(result.get("regimen")),
            "has_review": bool(result.get("review")),
        })

        if i < total - 1:
            time.sleep(delay)

    return results


def generate_report(results: list) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("  中医多智能体系统实验评估报告")
    lines.append(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  测试样本数: {len(results)}")
    lines.append("=" * 80)

    valid = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]

    lines.append(f"\n有效测试: {len(valid)} | 错误: {len(errors)}")
    if errors:
        for e in errors:
            lines.append(f"  ❌ ID={e['id']}: {e['error']}")

    # 1. 实体识别评估
    lines.append("\n" + "-" * 80)
    lines.append("  一、实体识别评估")
    lines.append("-" * 80)

    if valid:
        precisions = [r["entity_eval"]["precision"] for r in valid]
        recalls = [r["entity_eval"]["recall"] for r in valid]
        f1s = [r["entity_eval"]["f1"] for r in valid]

        lines.append(f"  平均精确率: {sum(precisions)/len(precisions):.4f}")
        lines.append(f"  平均召回率: {sum(recalls)/len(recalls):.4f}")
        lines.append(f"  平均F1:     {sum(f1s)/len(f1s):.4f}")

        perfect = sum(1 for f in f1s if f >= 0.999)
        lines.append(f"  完美匹配数: {perfect}/{len(valid)} ({perfect/len(valid)*100:.1f}%)")

        zero_recall = sum(1 for r in recalls if r < 0.001)
        lines.append(f"  零召回数:   {zero_recall}/{len(valid)} ({zero_recall/len(valid)*100:.1f}%)")

    # 2. 辨证准确率
    lines.append("\n" + "-" * 80)
    lines.append("  二、辨证准确率")
    lines.append("-" * 80)

    if valid:
        matched = sum(1 for r in valid if r["diagnosis_eval"]["category_match"])
        lines.append(f"  类别匹配: {matched}/{len(valid)} ({matched/len(valid)*100:.1f}%)")

        by_difficulty = defaultdict(list)
        for r in valid:
            by_difficulty[r["difficulty"]].append(r["diagnosis_eval"]["category_match"])

        for diff in ["simple", "medium", "complex"]:
            if diff in by_difficulty:
                vals = by_difficulty[diff]
                m = sum(1 for v in vals if v)
                lines.append(f"    {diff}: {m}/{len(vals)} ({m/len(vals)*100:.1f}%)")

    # 3. 各Agent耗时统计
    lines.append("\n" + "-" * 80)
    lines.append("  三、各Agent耗时统计")
    lines.append("-" * 80)

    if valid:
        agent_durations = defaultdict(list)
        for r in valid:
            for name, timing in r.get("agent_timings", {}).items():
                if timing.get("duration"):
                    agent_durations[name].append(timing["duration"])

        lines.append(f"  {'Agent':<20} {'平均(s)':<10} {'最小(s)':<10} {'最大(s)':<10} {'次数'}")
        lines.append("  " + "-" * 60)
        for name in sorted(agent_durations.keys()):
            durs = agent_durations[name]
            lines.append(f"  {name:<20} {sum(durs)/len(durs):<10.3f} {min(durs):<10.3f} {max(durs):<10.3f} {len(durs)}")

        total_times = [r["total_s"] for r in valid]
        lines.append(f"\n  总响应时间: 平均={sum(total_times)/len(total_times):.3f}s, "
                     f"最小={min(total_times):.3f}s, 最大={max(total_times):.3f}s")

    # 4. 治疗推荐覆盖率
    lines.append("\n" + "-" * 80)
    lines.append("  四、治疗推荐覆盖率")
    lines.append("-" * 80)

    if valid:
        has_formula = sum(1 for r in valid if r.get("has_formula"))
        has_acupuncture = sum(1 for r in valid if r.get("has_acupuncture"))
        has_regimen = sum(1 for r in valid if r.get("has_regimen"))
        has_review = sum(1 for r in valid if r.get("has_review"))

        lines.append(f"  方剂推荐:   {has_formula}/{len(valid)} ({has_formula/len(valid)*100:.1f}%)")
        lines.append(f"  针灸推荐:   {has_acupuncture}/{len(valid)} ({has_acupuncture/len(valid)*100:.1f}%)")
        lines.append(f"  养生推荐:   {has_regimen}/{len(valid)} ({has_regimen/len(valid)*100:.1f}%)")
        lines.append(f"  审核通过:   {has_review}/{len(valid)} ({has_review/len(valid)*100:.1f}%)")

    # 5. 问诊触发统计
    lines.append("\n" + "-" * 80)
    lines.append("  五、问诊确认触发统计")
    lines.append("-" * 80)

    if valid:
        inquiry_count = sum(1 for r in valid if r.get("inquiry_triggered"))
        lines.append(f"  触发问诊: {inquiry_count}/{len(valid)} ({inquiry_count/len(valid)*100:.1f}%)")

        by_difficulty = defaultdict(list)
        for r in valid:
            by_difficulty[r["difficulty"]].append(r.get("inquiry_triggered", False))

        for diff in ["simple", "medium", "complex"]:
            if diff in by_difficulty:
                vals = by_difficulty[diff]
                ic = sum(1 for v in vals if v)
                lines.append(f"    {diff}: {ic}/{len(vals)} ({ic/len(vals)*100:.1f}%)")

    # 6. 按类别统计
    lines.append("\n" + "-" * 80)
    lines.append("  六、按证候类别统计")
    lines.append("-" * 80)

    if valid:
        by_category = defaultdict(list)
        for r in valid:
            by_category[r["category"]].append(r)

        for cat in sorted(by_category.keys()):
            items = by_category[cat]
            matched = sum(1 for r in items if r["diagnosis_eval"]["category_match"])
            avg_f1 = sum(r["entity_eval"]["f1"] for r in items) / len(items)
            avg_time = sum(r["total_s"] for r in items) / len(items)
            lines.append(f"  {cat:<15} 数量={len(items):<3} 辨证匹配={matched}/{len(items)} "
                        f"实体F1={avg_f1:.3f} 平均耗时={avg_time:.1f}s")

    lines.append("\n" + "=" * 80)
    lines.append("  报告结束")
    lines.append("=" * 80)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="中医多智能体系统实验评估")
    parser.add_argument("--count", type=int, default=None, help="测试条数（默认全部）")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT, help="输出文件路径")
    parser.add_argument("--mode", type=str, default="full", choices=["full", "debug"], help="运行模式")
    parser.add_argument("--delay", type=float, default=5.0, help="每条问题间隔秒数")
    args = parser.parse_args()

    print("=" * 80)
    print("  中医多智能体系统实验评估")
    print("=" * 80)
    print(f"  数据集: {DATASET_PATH}")
    print(f"  输出:   {args.output}")
    print(f"  模式:   {args.mode}")
    print(f"  间隔:   {args.delay}s")

    dataset = load_dataset(DATASET_PATH, args.count)
    print(f"  加载数据: {len(dataset)} 条")
    print()

    difficulty_dist = Counter(d.get("difficulty", "unknown") for d in dataset)
    print("  难度分布:")
    for diff, cnt in sorted(difficulty_dist.items()):
        print(f"    {diff}: {cnt}")

    results = run_experiment(dataset, mode=args.mode, delay=args.delay)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {args.output}")

    report = generate_report(results)
    report_path = os.path.join(os.path.dirname(__file__), "experiment_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已保存: {report_path}")

    print("\n" + report)


if __name__ == "__main__":
    main()