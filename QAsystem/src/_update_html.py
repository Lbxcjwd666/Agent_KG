import sys

NEW_HTML = r'''_DEBUG_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>中医智能问诊系统</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }

.header { background: #1e293b; border-bottom: 1px solid #334155; padding: 12px 20px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.header-left { display: flex; align-items: center; gap: 12px; }
.header h1 { font-size: 18px; color: #38bdf8; font-weight: 600; }
.header-badge { font-size: 11px; padding: 3px 8px; border-radius: 10px; background: #1e3a5f; color: #7dd3fc; }
.header-right { display: flex; gap: 8px; }
.header-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid #334155; background: #1e293b; color: #94a3b8; font-size: 13px; cursor: pointer; transition: all 0.15s; }
.header-btn:hover { border-color: #38bdf8; color: #38bdf8; }
.header-btn.active { border-color: #38bdf8; color: #38bdf8; background: #0c4a6e; }

.main { flex: 1; display: flex; overflow: hidden; }

.chat-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.chat-messages::-webkit-scrollbar { width: 6px; }
.chat-messages::-webkit-scrollbar-track { background: transparent; }
.chat-messages::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }

.welcome { text-align: center; padding: 60px 20px; color: #475569; }
.welcome .icon { font-size: 56px; margin-bottom: 16px; }
.welcome h2 { color: #94a3b8; font-size: 20px; margin-bottom: 8px; }
.welcome p { font-size: 14px; line-height: 1.6; }

.msg { display: flex; gap: 12px; max-width: 85%; animation: fadeIn 0.3s; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.msg.user { align-self: flex-end; flex-direction: row-reverse; }
.msg-avatar { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0; }
.msg.user .msg-avatar { background: #1e3a5f; }
.msg.assistant .msg-avatar { background: #166534; }
.msg-body { flex: 1; min-width: 0; }
.msg-name { font-size: 12px; color: #64748b; margin-bottom: 4px; }
.msg.user .msg-name { text-align: right; }
.msg-bubble { padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.7; word-break: break-word; white-space: pre-wrap; }
.msg.user .msg-bubble { background: #1e3a5f; color: #e2e8f0; border-bottom-right-radius: 4px; }
.msg.assistant .msg-bubble { background: #1e293b; color: #cbd5e1; border: 1px solid #334155; border-bottom-left-radius: 4px; }

.msg-meta { display: flex; gap: 8px; margin-top: 6px; flex-wrap: wrap; }
.msg-meta-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: #0f172a; color: #94a3b8; border: 1px solid #334155; }

.typing-indicator { display: flex; gap: 4px; padding: 8px 0; }
.typing-dot { width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; animation: typingBounce 1.4s infinite; }
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typingBounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-6px); } }

.input-area { padding: 16px 20px; background: #1e293b; border-top: 1px solid #334155; flex-shrink: 0; }
.input-row { display: flex; gap: 10px; align-items: flex-end; }
.input-row textarea { flex: 1; padding: 12px 16px; border-radius: 12px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 15px; line-height: 1.5; resize: none; outline: none; font-family: inherit; max-height: 120px; min-height: 46px; }
.input-row textarea:focus { border-color: #38bdf8; }
.send-btn { padding: 12px 20px; border-radius: 12px; border: none; background: #38bdf8; color: #0f172a; font-weight: 600; cursor: pointer; font-size: 15px; white-space: nowrap; transition: background 0.15s; }
.send-btn:hover { background: #7dd3fc; }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.input-hint { font-size: 12px; color: #475569; margin-top: 6px; }

.debug-panel { width: 420px; background: #0f172a; border-left: 1px solid #334155; display: flex; flex-direction: column; overflow: hidden; transition: width 0.3s; }
.debug-panel.hidden { width: 0; border-left: none; }
.debug-header { padding: 12px 16px; background: #1e293b; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; flex-shrink: 0; }
.debug-header h3 { font-size: 14px; color: #38bdf8; }
.debug-close { background: none; border: none; color: #94a3b8; font-size: 18px; cursor: pointer; }
.debug-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.debug-body::-webkit-scrollbar { width: 5px; }
.debug-body::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }

.debug-status { text-align: center; color: #94a3b8; font-size: 13px; padding: 8px; background: #1e293b; border-radius: 8px; }
.debug-status.error { color: #f87171; }

.dag-flow { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.dag-row { display: flex; gap: 10px; justify-content: center; align-items: flex-start; }
.dag-arrow { text-align: center; color: #475569; font-size: 16px; line-height: 1; padding: 1px 0; }
.dag-arrow.parallel { display: flex; justify-content: center; gap: 50px; }

.agent-node { background: #1e293b; border: 2px solid #334155; border-radius: 10px; padding: 10px 14px; min-width: 140px; cursor: pointer; transition: all 0.2s; }
.agent-node:hover { border-color: #38bdf8; transform: translateY(-1px); }
.agent-node.selected { border-color: #38bdf8; box-shadow: 0 0 0 3px rgba(56,189,248,0.3); }
.agent-node.done { border-color: #22c55e; }
.agent-node.failed { border-color: #ef4444; }
.agent-node.skipped { border-color: #64748b; opacity: 0.5; }
.agent-node.running { border-color: #38bdf8; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(56,189,248,0.4); } 50% { box-shadow: 0 0 0 6px rgba(56,189,248,0); } }
.agent-name { font-weight: 600; font-size: 12px; margin-bottom: 4px; display: flex; align-items: center; gap: 4px; }
.agent-icon { font-size: 14px; }
.agent-status { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 500; }
.agent-status.done { background: #166534; color: #86efac; }
.agent-status.failed { background: #7f1d1d; color: #fca5a5; }
.agent-status.skipped { background: #374151; color: #9ca3af; }
.agent-status.running { background: #1e3a5f; color: #7dd3fc; }
.agent-duration { font-size: 11px; color: #64748b; margin-top: 2px; }
.agent-summary { font-size: 11px; color: #94a3b8; margin-top: 2px; max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.section-panel { background: #1e293b; border-radius: 10px; border: 1px solid #334155; overflow: hidden; }
.section-header { padding: 10px 14px; background: #334155; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
.section-header h4 { font-size: 13px; color: #38bdf8; }
.section-header .toggle-icon { color: #94a3b8; font-size: 12px; transition: transform 0.2s; }
.section-header.collapsed .toggle-icon { transform: rotate(-90deg); }
.section-body { padding: 14px; }
.section-body.collapsed { display: none; }

.checkpoint-timeline { display: flex; flex-direction: column; gap: 8px; }
.checkpoint-item { display: flex; gap: 8px; align-items: flex-start; padding: 8px 10px; background: #0f172a; border-radius: 6px; border-left: 3px solid #334155; font-size: 12px; }
.checkpoint-item.action-continue { border-left-color: #22c55e; }
.checkpoint-item.action-wait_user { border-left-color: #f59e0b; }
.checkpoint-item.action-add_task { border-left-color: #8b5cf6; }
.checkpoint-item.action-skip { border-left-color: #64748b; }
.checkpoint-item.action-done { border-left-color: #38bdf8; }
.cp-step { font-weight: 600; min-width: 70px; }
.cp-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 600; }
.cp-badge.continue { background: #166534; color: #86efac; }
.cp-badge.wait_user { background: #78350f; color: #fbbf24; }
.cp-badge.add_task { background: #4c1d95; color: #c4b5fd; }
.cp-badge.skip { background: #374151; color: #9ca3af; }
.cp-badge.done { background: #1e3a5f; color: #7dd3fc; }
.cp-reason { color: #94a3b8; flex: 1; }

.split-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
.split-card { background: #0f172a; border-radius: 6px; padding: 10px; border: 1px solid #334155; }
.split-card h5 { font-size: 12px; margin-bottom: 6px; }
.split-card h5.formula { color: #f472b6; }
.split-card h5.acupuncture { color: #34d399; }
.split-card h5.regimen { color: #fbbf24; }
.split-count { font-size: 18px; font-weight: 700; color: #e2e8f0; }

.debate-round { background: #0f172a; border-radius: 6px; padding: 10px; margin-bottom: 8px; border: 1px solid #334155; font-size: 12px; }
.debate-round-num { font-weight: 600; color: #f87171; }
.debate-resolved { font-size: 11px; padding: 2px 6px; border-radius: 4px; display: inline-block; }
.debate-resolved.yes { background: #166534; color: #86efac; }
.debate-resolved.no { background: #7f1d1d; color: #fca5a5; }

.confirm-panel { background: #1e293b; border-radius: 10px; border: 2px solid #f59e0b; overflow: hidden; }
.confirm-header { padding: 10px 14px; background: #78350f; display: flex; justify-content: space-between; align-items: center; }
.confirm-header h3 { font-size: 14px; color: #fbbf24; }
.confirm-body { padding: 14px; }
.confirm-desc { color: #d1d5db; margin-bottom: 12px; font-size: 13px; line-height: 1.6; }
.disease-card { background: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 10px; margin-bottom: 8px; }
.disease-card.selected { border-color: #22c55e; background: #052e16; }
.disease-name { font-weight: 600; font-size: 14px; color: #fbbf24; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.disease-hit { font-size: 11px; color: #94a3b8; }
.symptom-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.symptom-tag { padding: 3px 8px; border-radius: 4px; font-size: 11px; background: #1e293b; border: 1px solid #475569; color: #cbd5e1; cursor: pointer; transition: all 0.15s; }
.symptom-tag.checked { background: #166534; border-color: #22c55e; color: #86efac; }
.symptom-tag.original { background: #1e3a5f; border-color: #38bdf8; color: #7dd3fc; cursor: default; }
.confirm-actions { margin-top: 12px; display: flex; gap: 8px; justify-content: flex-end; }
.confirm-actions button { padding: 8px 16px; border-radius: 6px; border: none; font-weight: 600; cursor: pointer; font-size: 13px; }
.btn-confirm { background: #22c55e; color: #052e16; }
.btn-confirm:hover { background: #4ade80; }
.btn-skip { background: #475569; color: #e2e8f0; }
.btn-skip:hover { background: #64748b; }

.inquiry-textarea { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: #e2e8f0; font-size: 13px; line-height: 1.5; resize: vertical; outline: none; font-family: inherit; }
.inquiry-textarea:focus { border-color: #38bdf8; }

.detail-panel { background: #1e293b; border-radius: 10px; border: 1px solid #334155; overflow: hidden; }
.detail-header { padding: 10px 14px; background: #334155; display: flex; justify-content: space-between; align-items: center; }
.detail-header h4 { font-size: 13px; color: #38bdf8; }
.detail-close { background: none; border: none; color: #94a3b8; font-size: 18px; cursor: pointer; }
.detail-body { display: flex; gap: 0; }
.detail-col { flex: 1; padding: 12px; overflow: auto; max-height: 300px; }
.detail-col:first-child { border-right: 1px solid #334155; }
.detail-col h5 { font-size: 11px; color: #64748b; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.detail-col pre { font-size: 11px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; color: #cbd5e1; font-family: "Cascadia Code", "Fira Code", monospace; }

.dynamic-task-list { display: flex; flex-wrap: wrap; gap: 8px; }
.dynamic-task-card { background: #0f172a; border-radius: 6px; padding: 8px 12px; border: 1px solid #8b5cf6; font-size: 12px; }
.dynamic-task-id { font-weight: 600; color: #c4b5fd; }
.dynamic-task-info { color: #94a3b8; margin-top: 2px; font-size: 11px; }
</style>
</head>
<body>
<div class="header">
    <div class="header-left">
        <h1>中医智能问诊系统</h1>
        <span class="header-badge">Multi-Agent</span>
    </div>
    <div class="header-right">
        <button class="header-btn" id="btnNewChat" onclick="newChat()">新对话</button>
        <button class="header-btn active" id="btnDebug" onclick="toggleDebug()">调试面板</button>
    </div>
</div>
<div class="main">
    <div class="chat-area">
        <div class="chat-messages" id="chatMessages">
            <div class="welcome">
                <div class="icon">🏥</div>
                <h2>中医智能问诊系统</h2>
                <p>基于多Agent协作与知识图谱增强的中医临床决策支持系统<br>请输入您的健康问题，如：感冒头痛怎么办、我口苦心烦易怒</p>
            </div>
        </div>
        <div class="input-area">
            <div class="input-row">
                <textarea id="questionInput" placeholder="输入您的中医问题..." rows="1" onkeydown="handleKeyDown(event)" oninput="autoResize(this)"></textarea>
                <button class="send-btn" id="sendBtn" onclick="sendMessage()">发送</button>
            </div>
            <div class="input-hint">按 Enter 发送，Shift+Enter 换行</div>
        </div>
    </div>
    <div class="debug-panel" id="debugPanel">
        <div class="debug-header">
            <h3>Agent 协作流程</h3>
            <button class="debug-close" onclick="toggleDebug()">&times;</button>
        </div>
        <div class="debug-body" id="debugBody">
            <div class="debug-status" id="debugStatus">等待提问...</div>
            <div id="dagFlow" class="dag-flow"></div>
            <div id="confirmPanel" class="confirm-panel" style="display:none"></div>
            <div id="checkpointPanel" class="section-panel" style="display:none"></div>
            <div id="splitPanel" class="section-panel" style="display:none"></div>
            <div id="debatePanel" class="section-panel" style="display:none"></div>
            <div id="dynamicPanel" class="section-panel" style="display:none"></div>
            <div id="detailPanel" class="detail-panel" style="display:none"></div>
        </div>
    </div>
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

let chatHistory = [];
let traceData = [];
let selectedAgent = null;
let pendingConfirm = null;
let checkedSymptoms = {};
let lastResponse = {};
let debugVisible = true;
let isProcessing = false;

function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
}

function toggleDebug() {
    debugVisible = !debugVisible;
    const panel = document.getElementById("debugPanel");
    const btn = document.getElementById("btnDebug");
    if (debugVisible) {
        panel.classList.remove("hidden");
        btn.classList.add("active");
    } else {
        panel.classList.add("hidden");
        btn.classList.remove("active");
    }
}

function newChat() {
    chatHistory = [];
    traceData = [];
    selectedAgent = null;
    pendingConfirm = null;
    lastResponse = {};
    const msgs = document.getElementById("chatMessages");
    msgs.innerHTML = '<div class="welcome"><div class="icon">🏥</div><h2>中医智能问诊系统</h2><p>基于多Agent协作与知识图谱增强的中医临床决策支持系统<br>请输入您的健康问题，如：感冒头痛怎么办、我口苦心烦易怒</p></div>';
    document.getElementById("debugStatus").textContent = "等待提问...";
    document.getElementById("dagFlow").innerHTML = "";
    document.getElementById("confirmPanel").style.display = "none";
    document.getElementById("checkpointPanel").style.display = "none";
    document.getElementById("splitPanel").style.display = "none";
    document.getElementById("debatePanel").style.display = "none";
    document.getElementById("dynamicPanel").style.display = "none";
    document.getElementById("detailPanel").style.display = "none";
}

function addUserMessage(text) {
    const msgs = document.getElementById("chatMessages");
    const welcome = msgs.querySelector(".welcome");
    if (welcome) welcome.remove();
    const div = document.createElement("div");
    div.className = "msg user";
    const time = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    div.innerHTML = '<div class="msg-avatar">👤</div><div class="msg-body"><div class="msg-name">您 ' + time + '</div><div class="msg-bubble">' + escapeHtml(text) + '</div></div>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    chatHistory.push({ role: "user", content: text });
}

function addAssistantPlaceholder() {
    const msgs = document.getElementById("chatMessages");
    const div = document.createElement("div");
    div.className = "msg assistant";
    div.id = "currentResponse";
    const time = new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
    div.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-body"><div class="msg-name">中医AI ' + time + '</div><div class="msg-bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div><div class="msg-meta" id="currentMeta"></div></div>';
    msgs.appendChild(div);
    msgs.scrollTop = msgs.scrollHeight;
    return div;
}

function appendAssistantToken(token) {
    const resp = document.getElementById("currentResponse");
    if (!resp) return;
    const bubble = resp.querySelector(".msg-bubble");
    if (bubble.querySelector(".typing-indicator")) {
        bubble.textContent = "";
    }
    bubble.textContent += token;
    const msgs = document.getElementById("chatMessages");
    msgs.scrollTop = msgs.scrollHeight;
}

function finalizeAssistantMessage(metaTags) {
    const resp = document.getElementById("currentResponse");
    if (!resp) return;
    resp.removeAttribute("id");
    if (metaTags) {
        const meta = resp.querySelector(".msg-meta");
        if (meta) meta.innerHTML = metaTags.map(t => '<span class="msg-meta-tag">' + t + '</span>').join("");
    }
    const bubble = resp.querySelector(".msg-bubble");
    chatHistory.push({ role: "assistant", content: bubble.textContent });
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function sendMessage() {
    const input = document.getElementById("questionInput");
    const q = input.value.trim();
    if (!q || isProcessing) return;

    input.value = "";
    input.style.height = "auto";
    isProcessing = true;
    document.getElementById("sendBtn").disabled = true;

    addUserMessage(q);
    addAssistantPlaceholder();

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

    const statusEl = document.getElementById("debugStatus");

    function setDebugStatus(msg, isError) {
        statusEl.textContent = msg;
        statusEl.className = "debug-status" + (isError ? " error" : "");
    }

    try {
        setDebugStatus("🔄 正在连接...");
        const resp = await fetch("/api/agent/debug", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: q }),
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let fullBuffer = "";
        let finalResult = null;
        let inquiryPending = null;
        let answerText = "";
        let metaTags = [];

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            fullBuffer += decoder.decode(value, { stream: true });
            const blocks = fullBuffer.split("\n\n");
            fullBuffer = blocks.pop() || "";

            for (const block of blocks) {
                if (!block.trim()) continue;
                const eventRegex = /event:\s*(\S+)\s*\ndata:\s*(.+?)\s*$/gs;
                let match;
                while ((match = eventRegex.exec(block)) !== null) {
                    const eventType = match[1];
                    const eventData = match[2];
                    let data;
                    try { data = JSON.parse(eventData); } catch(e) { continue; }

                    switch (eventType) {
                        case "phase":
                            setDebugStatus("🔄 " + data.name);
                            break;
                        case "agent_start":
                            setDebugStatus("▶️ " + (AGENT_META[data.agent]?.label || data.agent) + " 执行中...");
                            break;
                        case "agent_done": {
                            const label = AGENT_META[data.agent]?.label || data.agent;
                            const dur = data.duration_ms ? " (" + (data.duration_ms/1000).toFixed(1) + "s)" : "";
                            if (data.status === "done" || data.agent) {
                                setDebugStatus("✅ " + label + " 完成" + dur);
                                traceData.push({
                                    agent: data.agent,
                                    task_id: data.task_id || data.agent,
                                    status: data.status || "done",
                                    depends_on: [],
                                    duration_ms: data.duration_ms || 0,
                                    input: {},
                                    output: data
                                });
                                renderDag();
                            }
                            break;
                        }
                        case "plan_update":
                            setDebugStatus("📋 追加: " + (data.added_tasks || []).join(", "));
                            break;
                        case "inquiry":
                            inquiryPending = data;
                            setDebugStatus("📋 需要问诊确认");
                            renderConfirmation(data);
                            break;
                        case "debate_start":
                            setDebugStatus("⚖️ 辩论开始 (" + (data.total_conflicts||0) + " 冲突)");
                            break;
                        case "debate_end":
                            setDebugStatus("✅ 辩论完成 (" + (data.total_rounds||0) + " 轮)");
                            break;
                        case "final_result":
                            finalResult = data;
                            break;
                        case "answer_token":
                            appendAssistantToken(data.token || "");
                            answerText += (data.token || "");
                            break;
                        case "done": {
                            if (finalResult) {
                                traceData = finalResult.trace || [];
                                lastResponse = finalResult;
                                const intent = finalResult.intent || "";
                                const complexity = finalResult.complexity || "";
                                if (intent) metaTags.push("意图:" + intent);
                                if (complexity) metaTags.push("复杂度:" + complexity);
                                if (finalResult.checkpoint_decisions && finalResult.checkpoint_decisions.length) {
                                    metaTags.push("决策点:" + finalResult.checkpoint_decisions.length);
                                }
                                if (finalResult.debate_log && finalResult.debate_log.length) {
                                    metaTags.push("辩论:" + finalResult.debate_log.length + "轮");
                                }
                                setDebugStatus("✅ 完成" + (intent ? " | " + intent : ""));
                                renderCheckpoints(finalResult.checkpoint_decisions || []);
                                renderSubgraphSplit(finalResult.subgraph_split || {});
                                renderDebate(finalResult.debate_log || []);
                                renderDynamicTasks(finalResult.dynamic_tasks || []);
                                renderDag();
                            }
                            finalizeAssistantMessage(metaTags);
                            break;
                        }
                        case "error":
                            setDebugStatus("❌ " + (data.error || "错误"), true);
                            appendAssistantToken("\n\n抱歉，处理时遇到错误：" + (data.error || "未知错误"));
                            finalizeAssistantMessage([]);
                            break;
                    }
                }
            }
        }
    } catch (e) {
        setDebugStatus("❌ 连接失败: " + e.message, true);
        const resp = document.getElementById("currentResponse");
        if (resp) {
            appendAssistantToken("\n\n连接失败：" + e.message);
            finalizeAssistantMessage([]);
        }
    } finally {
        isProcessing = false;
        document.getElementById("sendBtn").disabled = false;
        document.getElementById("questionInput").focus();
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
    document.getElementById("sendBtn").disabled = true;
    isProcessing = true;
    document.getElementById("confirmPanel").style.display = "none";
    document.getElementById("debugStatus").textContent = "🔄 根据确认结果继续...";

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
        let metaTags = [];
        if (confirmedDiseases && confirmedDiseases.length) metaTags.push("确认: " + confirmedDiseases.join("、"));
        if (data.intent) metaTags.push("意图:" + data.intent);
        if (data.complexity) metaTags.push("复杂度:" + data.complexity);
        document.getElementById("debugStatus").textContent = "✅ 完成" + (data.intent ? " | " + data.intent : "");
        renderCheckpoints(data.checkpoint_decisions || []);
        renderSubgraphSplit(data.subgraph_split || {});
        renderDebate(data.debate_log || []);
        renderDynamicTasks(data.dynamic_tasks || []);
    } catch (e) {
        document.getElementById("debugStatus").textContent = "❌ " + e.message;
        document.getElementById("debugStatus").className = "debug-status error";
    }
    isProcessing = false;
    document.getElementById("sendBtn").disabled = false;
    pendingConfirm = null;
    renderDag();
}

function getSummary(agent, output) {
    if (!output) return "无输出";
    const o = output;
    switch(agent) {
        case "orchestrator": return "意图: " + (o.intent || "");
        case "entity_recognition": return (o.entity_count || 0) + " 个实体";
        case "kg_query": return o.has_results ? "有KG结果" : "无KG结果";
        case "diagnosis": {
            const s = o.syndrome && o.syndrome.primary;
            return s ? s.name + " (" + Math.round((s.confidence||0)*100) + "%)" : "辨证完成";
        }
        case "formula": { const f = o.primary_formula; return f ? f.name : "方剂完成"; }
        case "acupuncture": { const pts = o.primary_points || []; return pts.length ? pts.map(p=>p.name).join(",") : "针灸完成"; }
        case "regimen": return o.dietary_advice ? "养生完成" : "无建议";
        case "review": { const c = (o.conflicts||[]).length; return c ? c + " 冲突" : "审核通过"; }
        default: return "";
    }
}

function renderDag() {
    const container = document.getElementById("dagFlow");
    if (!traceData.length) { container.innerHTML = ""; return; }
    const rows = [
        ["orchestrator"],
        ["entity_recognition"],
        ["kg_query"],
        ["diagnosis"],
        ["formula", "acupuncture", "regimen"],
        ["review"],
    ];
    const inquiryTask = traceData.find(x => x.agent === "diagnosis_inquiry");
    if (inquiryTask && inquiryTask.status !== "skipped") {
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
        '<div class="detail-header"><h4>' + meta.icon + ' ' + meta.label + '</h4>' +
        '<button class="detail-close" onclick="closeDetail()">&times;</button></div>' +
        '<div class="detail-body">' +
        '<div class="detail-col"><h5>Input</h5><pre>' + formatJson(t.input) + '</pre></div>' +
        '<div class="detail-col"><h5>Output</h5><pre>' + formatJson(t.output) + '</pre></div>' +
        '</div>';
}

function closeDetail() {
    selectedAgent = null;
    document.getElementById("detailPanel").style.display = "none";
    renderDag();
}

function formatJson(obj) {
    if (!obj) return "null";
    try { return JSON.stringify(obj, null, 2); } catch(e) { return String(obj); }
}

function toggleSection(panelId) {
    const panel = document.getElementById(panelId);
    const header = panel.querySelector('.section-header');
    const body = panel.querySelector('.section-body');
    if (header && body) { header.classList.toggle('collapsed'); body.classList.toggle('collapsed'); }
}

const ACTION_LABELS = { continue: "继续", wait_user: "等待用户", add_task: "追加任务", skip: "跳过", done: "结束" };

function renderCheckpoints(decisions) {
    const panel = document.getElementById("checkpointPanel");
    if (!decisions.length) { panel.style.display = "none"; return; }
    panel.style.display = "block";
    let html = '<div class="section-header" onclick="toggleSection(\'checkpointPanel\')"><h4>🎯 调度决策</h4><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body"><div class="checkpoint-timeline">';
    for (const d of decisions) {
        const meta = AGENT_META[d.step] || { icon: "📋", label: d.step };
        const action = d.action || "continue";
        html += '<div class="checkpoint-item action-' + action + '">';
        html += '<div class="cp-step">' + meta.icon + ' ' + meta.label + '</div>';
        html += '<span class="cp-badge ' + action + '">' + (ACTION_LABELS[action] || action) + '</span>';
        html += '<div class="cp-reason">' + (d.reason || "—") + '</div>';
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
    let html = '<div class="section-header" onclick="toggleSection(\'splitPanel\')"><h4>🔀 子图拆分</h4><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body"><div class="split-grid">';
    for (const [key, data] of Object.entries(split)) {
        html += '<div class="split-card">';
        html += '<h5 class="' + key + '">' + (icons[key]||"") + ' ' + (labels[key]||key) + '</h5>';
        html += '<div class="split-count">' + (data.entity_count || 0) + ' 实体</div>';
        html += '</div>';
    }
    html += '</div></div>';
    panel.innerHTML = html;
}

function renderDebate(log) {
    const panel = document.getElementById("debatePanel");
    if (!log || !log.length) { panel.style.display = "none"; return; }
    panel.style.display = "block";
    let html = '<div class="section-header" onclick="toggleSection(\'debatePanel\')"><h4>⚖️ 辩论</h4><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body">';
    for (const r of log) {
        html += '<div class="debate-round">';
        html += '<span class="debate-round-num">第' + r.round + '轮</span> ';
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
    let html = '<div class="section-header" onclick="toggleSection(\'dynamicPanel\')"><h4>➕ 动态任务</h4><span class="toggle-icon">▼</span></div>';
    html += '<div class="section-body"><div class="dynamic-task-list">';
    for (const t of tasks) {
        const meta = AGENT_META[t.agent] || { icon: "📋", label: t.agent };
        html += '<div class="dynamic-task-card">';
        html += '<div class="dynamic-task-id">' + meta.icon + ' ' + t.task_id + '</div>';
        html += '<div class="dynamic-task-info">' + meta.label + ' | ' + (t.status || "") + '</div>';
        html += '</div>';
    }
    html += '</div></div>';
    panel.innerHTML = html;
}

function renderConfirmation(data) {
    const panel = document.getElementById("confirmPanel");
    panel.style.display = "block";
    pendingConfirm = data;
    checkedSymptoms = {};

    let html = '<div class="confirm-header"><h3>📋 问诊确认</h3></div>';
    html += '<div class="confirm-body">';
    html += '<div class="confirm-desc">系统发现了多个候选疾病，请确认您的症状：</div>';

    const candidates = data.candidate_diseases || [];
    for (let i = 0; i < candidates.length; i++) {
        const c = candidates[i];
        const name = typeof c === 'string' ? c : (c.disease || c.name || '');
        const symptoms = (typeof c === 'object' && c.symptoms) ? c.symptoms : [];
        html += '<div class="disease-card" id="disease_' + i + '">';
        html += '<div class="disease-name">' + name + '</div>';
        if (symptoms.length) {
            html += '<div class="symptom-list">';
            for (const s of symptoms) {
                const sText = typeof s === 'string' ? s : (s.symptom || s.name || '');
                const key = name + '_' + sText;
                html += '<span class="symptom-tag" data-key="' + key + '" onclick="toggleSymptom(this, \'' + name + '\')">' + sText + '</span>';
            }
            html += '</div>';
        }
        html += '</div>';
    }

    html += '<div class="confirm-actions">';
    html += '<button class="btn-skip" onclick="skipConfirm()">跳过</button>';
    html += '<button class="btn-confirm" onclick="continueAfterInquiry()">确认</button>';
    html += '</div>';
    html += '</div>';
    panel.innerHTML = html;
}

function toggleSymptom(el, disease) {
    el.classList.toggle("checked");
    const key = el.getAttribute("data-key");
    checkedSymptoms[key] = !checkedSymptoms[key];
    if (checkedSymptoms[key]) {
        if (!pendingConfirm._confirmedDiseases) pendingConfirm._confirmedDiseases = [];
        if (!pendingConfirm._confirmedDiseases.includes(disease)) {
            pendingConfirm._confirmedDiseases.push(disease);
        }
    }
}

document.getElementById("questionInput").focus();
</script>
</body>
</html>
"""
'''

filepath = r'd:\Inovation\TCM-QAsystem\QAsystem\src\app_agent.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start_line = None
end_line = None
for i, line in enumerate(lines):
    if line.strip().startswith('_DEBUG_HTML = r"""'):
        start_line = i
    if start_line is not None and line.strip() == '"""':
        end_line = i
        break

if start_line is None or end_line is None:
    print("ERROR: Could not find _DEBUG_HTML boundaries")
    sys.exit(1)

print(f"Found _DEBUG_HTML from line {start_line+1} to {end_line+1}")
print(f"Replacing {end_line - start_line + 1} lines with new content")

new_lines = lines[:start_line] + [NEW_HTML + '\n'] + lines[end_line+1:]

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Done! _DEBUG_HTML replaced successfully.")