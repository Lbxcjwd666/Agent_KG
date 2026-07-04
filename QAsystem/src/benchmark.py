"""
性能基准测试 — 验证 DAG 并行管线 vs 串行管线的响应时间

用法:
  1. 先启动服务: python app.py
  2. 运行测试:   python benchmark.py

输出:
  - 各 Agent 阶段的开始/结束时间
  - formula/acupuncture/regimen 的并行度分析
  - 总响应时间
"""

import requests
import time
import json
import sys

API_URL = "http://localhost:5000/api/agent/chat/stream"

TEST_QUESTIONS = [
    "我最近头痛，口干口苦，心烦易怒，舌红苔黄，脉弦数，请问这是什么证？该怎么治疗？",
    "患者女性，35岁，面色萎黄，头晕目眩，心悸失眠，食欲不振，舌淡苔白，脉细弱",
    "我腰膝酸软，手足心热，盗汗，口干咽燥，舌红少苔，脉细数",
]


def run_stream_test(question: str) -> dict:
    """调用 SSE 流式端点，记录每个事件的时间戳"""
    start_time = time.time()
    events = []

    try:
        resp = requests.post(
            API_URL,
            json={"question": question, "use_debate": False},
            stream=True,
            timeout=120,
            headers={"Content-Type": "application/json"}
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
                events.append({
                    "event": event_type,
                    "data": data,
                    "elapsed_s": round(elapsed, 3)
                })
                event_type = None

    except requests.exceptions.ConnectionError:
        print("ERROR: 无法连接服务，请先启动: python app.py")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    total_time = time.time() - start_time
    return {"events": events, "total_s": round(total_time, 3)}


def analyze_result(result: dict) -> None:
    """分析测试结果，输出性能报告"""
    events = result["events"]
    total = result["total_s"]

    agent_timings = {}
    for ev in events:
        if ev["event"] == "agent_start":
            agent_name = ev["data"].get("agent", "unknown")
            agent_timings[agent_name] = {"start": ev["elapsed_s"], "end": None}
        elif ev["event"] == "agent_done":
            agent_name = ev["data"].get("agent", "unknown")
            if agent_name in agent_timings:
                agent_timings[agent_name]["end"] = ev["elapsed_s"]
                agent_timings[agent_name]["duration"] = round(
                    ev["elapsed_s"] - agent_timings[agent_name]["start"], 3
                )

    print("\n" + "=" * 70)
    print("  性能基准测试报告")
    print("=" * 70)

    print(f"\n总响应时间: {total}s\n")

    print(f"{'Agent':<20} {'开始(s)':<10} {'结束(s)':<10} {'耗时(s)':<10} {'状态'}")
    print("-" * 70)
    for name, timing in agent_timings.items():
        start = timing.get("start", "?")
        end = timing.get("end", "?")
        dur = timing.get("duration", "?")
        print(f"{name:<20} {str(start):<10} {str(end):<10} {str(dur):<10}")

    parallel_agents = ["formula", "acupuncture", "regimen"]
    parallel_starts = []
    parallel_ends = []
    for name in parallel_agents:
        if name in agent_timings and agent_timings[name].get("duration"):
            parallel_starts.append(agent_timings[name]["start"])
            parallel_ends.append(agent_timings[name]["end"])

    if len(parallel_starts) >= 2:
        print("\n" + "-" * 70)
        print("  并行度分析 (formula / acupuncture / regimen)")
        print("-" * 70)

        earliest_start = min(parallel_starts)
        latest_end = max(parallel_ends)
        parallel_wall_time = round(latest_end - earliest_start, 3)

        sum_serial = sum(
            agent_timings[name]["duration"]
            for name in parallel_agents
            if name in agent_timings and agent_timings[name].get("duration")
        )

        print(f"  并行实际墙钟时间:  {parallel_wall_time}s")
        print(f"  串行理论总耗时:    {round(sum_serial, 3)}s")

        if sum_serial > 0:
            speedup = round(sum_serial / parallel_wall_time, 2)
            saved = round(sum_serial - parallel_wall_time, 3)
            print(f"  加速比:            {speedup}x")
            print(f"  节省时间:          {saved}s")

        overlap_start = max(parallel_starts) - min(parallel_starts)
        print(f"  启动时间差:        {round(overlap_start, 3)}s (越小越并行)")

        if overlap_start < 1.0:
            print("  ✅ 三个 Agent 近乎同时启动，确认并行执行")
        elif overlap_start < 3.0:
            print("  ⚠️ 启动有一定间隔，部分并行")
        else:
            print("  ❌ 启动间隔较大，可能未真正并行")

    print("\n" + "=" * 70)


def main():
    print("DAG 并行管线性能基准测试")
    print(f"API: {API_URL}")
    print(f"测试问题数: {len(TEST_QUESTIONS)}")

    for i, question in enumerate(TEST_QUESTIONS):
        print(f"\n{'#' * 70}")
        print(f"测试 {i + 1}/{len(TEST_QUESTIONS)}: {question[:50]}...")
        print(f"{'#' * 70}")

        result = run_stream_test(question)
        analyze_result(result)

    print("\n测试完成。")


if __name__ == "__main__":
    main()