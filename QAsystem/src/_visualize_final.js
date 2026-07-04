
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
    if (!q) return;
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
        const resp = await fetch("/api/agent/debug", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: q }),
        });
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

    } catch (e) {
        await setStatus("❌ 错误: " + e.message);
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
