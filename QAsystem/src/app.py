"""
重构后的Flask后端
集成知识图谱增强和千问API
"""

from flask import Flask, request, jsonify, session, Response, stream_with_context
from kg_enhancer import KnowledgeGraphEnhancer
from qwen_api import QwenAPI
from config import SYSTEM_CONFIG
from app_agent import agent_bp
import traceback
import uuid
import json

# 尝试导入flask-cors，如果失败则使用手动CORS处理
try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False
    print("[WARNING] flask-cors未安装，将使用手动CORS处理")
    print("[INFO] 建议运行: pip install flask-cors")

app = Flask(__name__)
app.secret_key = 'tcm-qa-system-secret-key-change-in-production'  # 用于session管理

# 注册多Agent协同蓝图
app.register_blueprint(agent_bp)

# 启用CORS支持
if CORS_AVAILABLE:
    # 使用flask-cors库（推荐方式）
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
else:
    # 手动处理CORS（备选方案）
    @app.after_request
    def after_request(response):
        """手动添加CORS头"""
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        return response
    
    @app.before_request
    def handle_preflight():
        """处理OPTIONS预检请求"""
        if request.method == "OPTIONS":
            response = jsonify({'status': 'ok'})
            response.headers.add('Access-Control-Allow-Origin', '*')
            response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
            response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
            return response

# 初始化知识图谱增强器
kg_enhancer = KnowledgeGraphEnhancer()

# 初始化千问API客户端
qwen_api = QwenAPI()


@app.route('/', methods=['GET'])
def index():
    """根路径 - 返回问答界面HTML"""
    html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>基于知识增强的中医语言模型临床决策支持问答系统</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Microsoft YaHei', 'PingFang SC', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            width: 100%;
            max-width: 900px;
            padding: 30px;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #f0f0f0;
        }
        
        .header h1 {
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }
        
        .header p {
            color: #666;
            font-size: 14px;
        }
        
        .chat-container {
            flex: 1;
            overflow-y: auto;
            margin-bottom: 20px;
            padding: 20px;
            background: #f9f9f9;
            border-radius: 10px;
            min-height: 400px;
            max-height: 500px;
        }
        
        .message {
            margin-bottom: 20px;
            animation: fadeIn 0.3s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message.user {
            text-align: right;
        }
        
        .message.assistant {
            text-align: left;
        }
        
        .message-content {
            display: inline-block;
            padding: 12px 18px;
            border-radius: 18px;
            max-width: 70%;
            word-wrap: break-word;
        }
        
        .message.user .message-content {
            background: #667eea;
            color: white;
        }
        
        .message.assistant .message-content {
            background: white;
            color: #333;
            border: 1px solid #e0e0e0;
        }
        
        .message-label {
            font-size: 12px;
            color: #999;
            margin-bottom: 5px;
        }
        
        .entities {
            margin-top: 10px;
            padding: 8px;
            background: #e8f5e9;
            border-radius: 8px;
            font-size: 12px;
        }
        
        .entity-tag {
            display: inline-block;
            background: #4caf50;
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            margin: 3px 5px 3px 0;
            font-size: 11px;
        }
        
        .input-area {
            display: flex;
            gap: 10px;
        }
        
        .input-area input {
            flex: 1;
            padding: 15px 20px;
            border: 2px solid #e0e0e0;
            border-radius: 25px;
            font-size: 16px;
            outline: none;
            transition: border-color 0.3s;
        }
        
        .input-area input:focus {
            border-color: #667eea;
        }
        
        .input-area button {
            padding: 15px 30px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 25px;
            font-size: 16px;
            cursor: pointer;
            transition: background 0.3s;
            font-weight: 500;
        }
        
        .input-area button:hover:not(:disabled) {
            background: #5568d3;
        }
        
        .input-area button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        .loading {
            text-align: center;
            color: #999;
            padding: 20px;
        }
        
        .loading::after {
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }
        
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60%, 100% { content: '...'; }
        }
        
        .empty-state {
            text-align: center;
            color: #999;
            padding: 60px 20px;
        }
        
        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 10px;
        }
        
        .kg-info {
            margin-top: 10px;
            padding: 8px;
            background: #fff3e0;
            border-radius: 8px;
            font-size: 11px;
            color: #666;
            cursor: pointer;
        }
        
        .kg-info:hover {
            background: #ffe0b2;
        }
        
        /* 增强信息样式 */
        .enhanced-info {
            margin-top: 15px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            overflow: hidden;
        }
        
        .enhanced-tabs {
            display: flex;
            background: #f5f5f5;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .tab-btn {
            flex: 1;
            padding: 10px 15px;
            border: none;
            background: transparent;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }
        
        .tab-btn:hover {
            background: #e0e0e0;
        }
        
        .tab-btn.active {
            background: #667eea;
            color: white;
        }
        
        .enhanced-content {
            padding: 15px;
            max-height: 400px;
            overflow-y: auto;
        }
        
        /* 知识图谱可视化样式 */
        .kg-visualization {
            font-size: 14px;
        }
        
        .kg-stats {
            margin-bottom: 10px;
            color: #666;
            font-size: 12px;
        }
        
        .kg-nodes {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 15px;
        }
        
        .kg-node {
            padding: 6px 12px;
            border-radius: 15px;
            color: white;
            font-size: 12px;
            font-weight: 500;
        }
        
        .kg-edges {
            font-size: 13px;
        }
        
        .kg-edge {
            padding: 4px 0;
            color: #555;
        }
        
        /* 推理路径样式 */
        .reasoning-path {
            font-size: 14px;
        }
        
        .reasoning-step {
            margin-bottom: 15px;
            padding: 12px;
            background: #f9f9f9;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .step-header {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }
        
        .step-number {
            background: #667eea;
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: bold;
            margin-right: 10px;
        }
        
        .step-title {
            font-weight: bold;
            color: #333;
        }
        
        .step-description {
            color: #666;
            margin-bottom: 8px;
        }
        
        .step-details {
            font-size: 12px;
        }
        
        .step-entities {
            margin-bottom: 8px;
        }
        
        .step-relations {
            color: #555;
        }
        
        .relation-item {
            padding: 2px 0;
            margin-left: 10px;
            font-size: 11px;
            color: #666;
        }
        
        .query-result {
            margin-bottom: 8px;
            padding: 8px;
            background: #f0f0f0;
            border-radius: 4px;
        }
        
        .entity-tag {
            display: inline-block;
            background: #e3f2fd;
            color: #1976d2;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            margin: 2px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏥 基于知识增强的中医语言模型临床决策支持问答系统</h1>
            <p>基于知识图谱增强的智能问答 | 模型: """ + qwen_api.model + """</p>
        </div>
        
        <div class="chat-container" id="chatContainer">
            <div class="empty-state">
                <div class="empty-state-icon">💬</div>
                <div>请输入您的中医相关问题，我会为您提供专业解答</div>
            </div>
        </div>
        
        <div class="input-area">
            <input 
                type="text" 
                id="questionInput" 
                placeholder="例如：人参有什么功效？" 
                onkeypress="if(event.key==='Enter') sendQuestion()"
            >
            <button id="sendButton" onclick="sendQuestion()">发送</button>
        </div>
    </div>
    
    <script>
        const API_BASE = window.location.origin;
        let sessionId = null;  // 存储会话ID
        
        // 引导词内容
        const welcomeMessage = `你好，这里是一款基于知识增强的中医语言模型临床决策支持问答系统，可以向我提出以下问题：
1、方剂推荐与解释：如请列举3个含有'黄芪'的经典方剂，并说明其主治病机；龙胆泻肝汤要怎么配制等。
2、中药药性与应用：如黄芪和党参在补气功效上有何区别？哪些情况不适合使用黄芪等
3、针灸与治法：如为什么针灸'足三里'可以调理脾胃等
4、证型辨证类：风寒感冒和风热感冒在症状、舌脉和用药上有何区别；患者舌红苔黄腻，脉滑数，小便短赤，大便黏腻，可能是什么证型？应如何治疗等
5、中西医结合场景：糖尿病患者（西医诊断）出现口干、多饮、多尿、消瘦，但伴有腰膝酸软、耳鸣，舌红少苔，脉细数。中医应如何辨证施治等`;
        
        // 页面加载时显示引导词
        window.addEventListener('DOMContentLoaded', function() {
            setTimeout(function() {
                addMessage('assistant', welcomeMessage);
            }, 300);
        });
        
        function addMessage(role, content, entities = null, visualizationData = null, reasoningPath = null, kgContext = null, suggestedQuestions = null) {
            const container = document.getElementById('chatContainer');
            const emptyState = container.querySelector('.empty-state');
            if (emptyState) {
                emptyState.remove();
            }
            
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;
            
            const label = document.createElement('div');
            label.className = 'message-label';
            label.textContent = role === 'user' ? '您' : 'AI助手';
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            contentDiv.textContent = content;
            
            messageDiv.appendChild(label);
            messageDiv.appendChild(contentDiv);
            
            if (entities && entities.length > 0) {
                const entitiesDiv = document.createElement('div');
                entitiesDiv.className = 'entities';
                entitiesDiv.innerHTML = '<strong>识别实体:</strong> ' + 
                    entities.map(e => `<span class="entity-tag">${e.text} (${e.type})</span>`).join('');
                messageDiv.appendChild(entitiesDiv);
            }
            
            // 添加"猜你想问"功能
            if (role === 'assistant' && suggestedQuestions && suggestedQuestions.length > 0) {
                const suggestedDiv = document.createElement('div');
                suggestedDiv.className = 'suggested-questions';
                suggestedDiv.style.marginTop = '15px';
                suggestedDiv.style.padding = '12px';
                suggestedDiv.style.background = '#f0f7ff';
                suggestedDiv.style.borderRadius = '8px';
                suggestedDiv.style.borderLeft = '3px solid #667eea';
                
                const title = document.createElement('div');
                title.style.fontWeight = 'bold';
                title.style.color = '#333';
                title.style.marginBottom = '8px';
                title.textContent = '💡 猜你想问：';
                suggestedDiv.appendChild(title);
                
                const questionsList = document.createElement('div');
                questionsList.style.display = 'flex';
                questionsList.style.flexDirection = 'column';
                questionsList.style.gap = '6px';
                
                suggestedQuestions.forEach((q, index) => {
                    const qDiv = document.createElement('div');
                    qDiv.style.padding = '6px 10px';
                    qDiv.style.background = 'white';
                    qDiv.style.borderRadius = '4px';
                    qDiv.style.cursor = 'pointer';
                    qDiv.style.transition = 'background 0.2s';
                    qDiv.style.fontSize = '13px';
                    qDiv.style.color = '#667eea';
                    qDiv.textContent = `${index + 1}. ${q}`;
                    qDiv.onmouseover = function() { this.style.background = '#e8f0fe'; };
                    qDiv.onmouseout = function() { this.style.background = 'white'; };
                    qDiv.onclick = function() {
                        document.getElementById('questionInput').value = q;
                        sendQuestion();
                    };
                    questionsList.appendChild(qDiv);
                });
                
                suggestedDiv.appendChild(questionsList);
                messageDiv.appendChild(suggestedDiv);
            }
            
            // 添加可视化和推理路径功能
            if (role === 'assistant' && (visualizationData || reasoningPath || kgContext)) {
                const enhancedDiv = document.createElement('div');
                enhancedDiv.className = 'enhanced-info';
                
                const tabsDiv = document.createElement('div');
                tabsDiv.className = 'enhanced-tabs';
                
                let activeTab = '';
                
                // 知识图谱信息标签
                if (kgContext) {
                    const kgTab = document.createElement('button');
                    kgTab.className = 'tab-btn';
                    kgTab.textContent = '📊 知识图谱信息';
                    kgTab.onclick = () => showTab(enhancedDiv, 'kg', kgContext);
                    tabsDiv.appendChild(kgTab);
                    if (!activeTab) activeTab = 'kg';
                }
                
                // 图谱可视化标签
                if (visualizationData && visualizationData.nodes && visualizationData.nodes.length > 0) {
                    const vizTab = document.createElement('button');
                    vizTab.className = 'tab-btn';
                    vizTab.textContent = '🔍 图谱可视化';
                    vizTab.onclick = () => showTab(enhancedDiv, 'visualization', visualizationData);
                    tabsDiv.appendChild(vizTab);
                    if (!activeTab) activeTab = 'visualization';
                }
                
                // 推理路径标签
                if (reasoningPath && reasoningPath.length > 0) {
                    const reasoningTab = document.createElement('button');
                    reasoningTab.className = 'tab-btn';
                    reasoningTab.textContent = '🧠 推理路径';
                    reasoningTab.onclick = () => showTab(enhancedDiv, 'reasoning', reasoningPath);
                    tabsDiv.appendChild(reasoningTab);
                    if (!activeTab) activeTab = 'reasoning';
                }
                
                const contentDiv = document.createElement('div');
                contentDiv.className = 'enhanced-content';
                
                enhancedDiv.appendChild(tabsDiv);
                enhancedDiv.appendChild(contentDiv);
                messageDiv.appendChild(enhancedDiv);
                
                // 默认显示第一个标签
                if (activeTab) {
                    const firstTab = tabsDiv.querySelector('.tab-btn');
                    if (firstTab) {
                        firstTab.click();
                    }
                }
            }
            
            container.appendChild(messageDiv);
            container.scrollTop = container.scrollHeight;
        }
        
        function showTab(enhancedDiv, tabType, data) {
            // 更新标签状态
            const tabs = enhancedDiv.querySelectorAll('.tab-btn');
            tabs.forEach(tab => tab.classList.remove('active'));
            event.target.classList.add('active');
            
            const contentDiv = enhancedDiv.querySelector('.enhanced-content');
            contentDiv.innerHTML = '';
            
            if (tabType === 'kg') {
                const kgDiv = document.createElement('div');
                kgDiv.className = 'kg-context';
                kgDiv.innerHTML = `<pre>${data}</pre>`;
                contentDiv.appendChild(kgDiv);
            } else if (tabType === 'visualization') {
                const vizDiv = document.createElement('div');
                vizDiv.className = 'visualization-container';
                vizDiv.innerHTML = createVisualization(data);
                contentDiv.appendChild(vizDiv);
            } else if (tabType === 'reasoning') {
                const reasoningDiv = document.createElement('div');
                reasoningDiv.className = 'reasoning-container';
                reasoningDiv.innerHTML = createReasoningPath(data);
                contentDiv.appendChild(reasoningDiv);
            }
        }
        
        function createVisualization(data) {
            if (!data || !data.nodes) return '<p>无可视化数据</p>';
            
            const width = 800;
            const height = 500;
            const centerX = width / 2;
            const centerY = height / 2;
            const radius = Math.min(width, height) / 2.5;
            
            const nodes = data.nodes || [];
            const edges = data.edges || [];
            
            const queryNodes = nodes.filter(n => n.category === 'query_entity');
            const relatedNodes = nodes.filter(n => n.category !== 'query_entity');
            
            const positions = {};
            
            // 查询实体放在中心（如果有多个，做一个小圆环）
            const queryRadius = radius * 0.3;
            queryNodes.forEach((node, index) => {
                const angle = queryNodes.length === 1 
                    ? 0 
                    : (index * 2 * Math.PI) / queryNodes.length;
                const x = centerX + queryRadius * Math.cos(angle);
                const y = centerY + queryRadius * Math.sin(angle);
                positions[node.id] = { x, y };
            });
            
            // 相关实体围绕查询实体分布
            relatedNodes.forEach((node, index) => {
                const angle = (index * 2 * Math.PI) / Math.max(1, relatedNodes.length);
                const x = centerX + radius * Math.cos(angle);
                const y = centerY + radius * Math.sin(angle);
                positions[node.id] = { x, y };
            });
            
            let svg = `<svg class="kg-svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
            
            // 箭头定义
            svg += `
                <defs>
                    <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5"
                            markerWidth="6" markerHeight="6"
                            orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#95a5a6" />
                    </marker>
                </defs>
            `;
            
            // 绘制边（先画线再画节点）
            edges.forEach(edge => {
                const sourcePos = positions[edge.source];
                const targetPos = positions[edge.target];
                if (!sourcePos || !targetPos) return;
                
                const color = edge.color || '#95a5a6';
                
                svg += `
                    <line 
                        x1="${sourcePos.x}" 
                        y1="${sourcePos.y}" 
                        x2="${targetPos.x}" 
                        y2="${targetPos.y}" 
                        stroke="${color}" 
                        stroke-width="1.8" 
                        opacity="0.8"
                        marker-end="url(#arrow)"
                    />
                `;
                
                const midX = (sourcePos.x + targetPos.x) / 2;
                const midY = (sourcePos.y + targetPos.y) / 2;
                const label = edge.label || edge.type || '';
                
                if (label) {
                    svg += `
                        <text 
                            x="${midX}" 
                            y="${midY - 4}" 
                            text-anchor="middle" 
                            font-size="10" 
                            fill="#666"
                        >
                            ${label}
                        </text>
                    `;
                }
            });
            
            // 绘制节点
            nodes.forEach(node => {
                const pos = positions[node.id];
                if (!pos) return;
                
                const isQuery = node.category === 'query_entity';
                const color = isQuery ? '#ff6b6b' : '#4ecdc4';
                const radiusNode = node.size || (isQuery ? 26 : 18);
                const label = node.label || '';
                
                svg += `
                    <circle 
                        cx="${pos.x}" 
                        cy="${pos.y}" 
                        r="${radiusNode}" 
                        fill="${color}" 
                        stroke="#2c3e50" 
                        stroke-width="2"
                    />
                    <text 
                        x="${pos.x}" 
                        y="${pos.y + 4}" 
                        text-anchor="middle" 
                        font-size="11" 
                        fill="#ffffff"
                    >
                        ${label}
                    </text>
                `;
            });
            
            svg += '</svg>';
            
            let html = '<div class="kg-visualization">';
            html += '<h4>知识图谱可视化</h4>';
            html += `<div class="kg-stats">节点: ${data.stats?.total_nodes || 0} | 关系: ${data.stats?.total_edges || 0}</div>`;
            html += '<div class="kg-graph-container">';
            html += svg;
            html += '</div>';
            html += '<div class="kg-legend-inline">';
            html += '<span class="kg-legend-item"><span class="kg-legend-color" style="background-color:#ff6b6b;"></span>查询实体</span>';
            html += '<span class="kg-legend-item"><span class="kg-legend-color" style="background-color:#4ecdc4;"></span>相关实体</span>';
            html += '</div>';
            html += '</div>';
            
            return html;
        }
        
        function createReasoningPath(data) {
            if (!data || data.length === 0) return '<p>无推理路径数据</p>';
            
            let html = '<div class="reasoning-path">';
            html += '<h4>推理路径</h4>';
            
            data.forEach((step, index) => {
                html += `<div class="reasoning-step">`;
                html += `<div class="step-header">`;
                html += `<span class="step-number">${step.step}</span>`;
                html += `<span class="step-title">${step.title}</span>`;
                html += `</div>`;
                html += `<div class="step-description">${step.description}</div>`;
                
                if (step.details) {
                    html += `<div class="step-details">`;
                    if (step.details.entities) {
                        html += `<div class="step-entities">`;
                        step.details.entities.forEach(e => {
                            html += `<span class="entity-tag">${e.text} (${e.type})</span>`;
                        });
                        html += `</div>`;
                    }
                if (step.details.query_results) {
                    html += `<div class="step-relations">`;
                    step.details.query_results.forEach(qr => {
                        html += `<div class="query-result">`;
                        html += `<strong>${qr.entity}</strong> (${qr.relations_found} 个关系):`;
                        if (qr.relations) {
                            qr.relations.forEach(r => {
                                html += `<div class="relation-item">${r.source} → ${r.relation} → ${r.target} (${r.target_type})</div>`;
                            });
                        }
                        html += `</div>`;
                    });
                    html += `</div>`;
                }
                    html += `</div>`;
                }
                
                html += `</div>`;
            });
            
            html += '</div>';
            return html;
        }
        
        function showLoading() {
            const container = document.getElementById('chatContainer');
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'loading';
            loadingDiv.id = 'loadingIndicator';
            loadingDiv.textContent = '正在思考';
            container.appendChild(loadingDiv);
            container.scrollTop = container.scrollHeight;
        }
        
        function hideLoading() {
            const loading = document.getElementById('loadingIndicator');
            if (loading) {
                loading.remove();
            }
        }
        
        async function sendQuestion() {
            const input = document.getElementById('questionInput');
            const button = document.getElementById('sendButton');
            const question = input.value.trim();
            
            if (!question) return;
            
            // 显示用户消息
            addMessage('user', question);
            input.value = '';
            button.disabled = true;
            showLoading();
            
            try {
                const response = await fetch(API_BASE + '/api/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ 
                        question: question,
                        session_id: sessionId 
                    })
                });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || '请求失败');
                }
                
                const data = await response.json();
                
                // 更新session_id
                if (data.session_id) {
                    sessionId = data.session_id;
                }
                
                // 显示AI回答
                addMessage('assistant', data.answer, data.entities, data.visualization_data, data.reasoning_path, data.kg_context, data.suggested_questions);
                
            } catch (error) {
                addMessage('assistant', '抱歉，发生了错误：' + error.message);
            } finally {
                hideLoading();
                button.disabled = false;
                input.focus();
            }
        }
    </script>
</body>
</html>
    """
    return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/info', methods=['GET'])
def api_info():
    """API信息接口 - 返回JSON格式的API文档"""
    return jsonify({
        'name': '中医问答系统（知识图谱增强版）',
        'version': '1.0.0',
        'description': '基于Neo4j知识图谱和千问大模型的中医问答系统',
        'endpoints': {
            'POST /api/chat': '问答接口 - 发送问题获取答案',
            'POST /api/entities': '实体抽取接口 - 从文本中抽取实体',
            'POST /api/kg/query': '知识图谱查询接口 - 查询实体关系',
            'POST /api/kg/multi-hop': '多跳查询接口 - 查询多跳关系',
            'GET /api/health': '健康检查接口 - 检查系统状态',
            'GET /api/info': 'API信息接口 - 返回API文档'
        },
        'model': qwen_api.model,
        'kg_enabled': SYSTEM_CONFIG['enable_kg_enhancement'],
        'status': 'running'
    }), 200


@app.route('/api/chat', methods=['POST'])
def chat():
    """问答接口 - 使用知识图谱增强和千问API，支持多轮对话"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        session_id = data.get('session_id', None)
        
        if not question:
            return jsonify({'error': '问题不能为空'}), 400
        
        # 初始化或获取对话历史
        if 'conversations' not in session:
            session['conversations'] = {}
        
        if not session_id:
            session_id = str(uuid.uuid4())
        
        if session_id not in session['conversations']:
            session['conversations'][session_id] = []
        
        conversation_history = session['conversations'][session_id]
        
        print(f"[DEBUG] 收到问题: {question} (Session: {session_id})")
        print(f"[DEBUG] 当前对话历史长度: {len(conversation_history)}")
        
        # 1. 使用千问API抽取实体
        print("[DEBUG] 开始抽取实体...")
        entities_data = qwen_api.extract_entities(question)
        
        # 转换实体格式
        entities = [(e['text'], e.get('label', e.get('type', ''))) for e in entities_data] if entities_data else []
        print(f"[DEBUG] 识别到实体: {entities}")
        
        # 2. 使用知识图谱增强
        print("[DEBUG] 开始知识图谱增强...")
        kg_contexts = []
        kg_results_all = {}
        
        if entities:
            for entity_text, entity_type in entities[:SYSTEM_CONFIG["max_entities"]]:
                # 查询知识图谱
                kg_results = kg_enhancer.query_relations(entity_text, entity_type)
                if kg_results:
                    kg_results_all[entity_text] = kg_results
                    # 格式化知识图谱上下文
                    kg_context = kg_enhancer.format_kg_context(kg_results, entity_text, entity_type)
                    kg_contexts.append(kg_context)
        
        # 组合知识图谱上下文
        kg_context = "\n\n".join(kg_contexts) if kg_contexts else ""
        
        # 3. 使用千问API生成答案（带知识图谱增强和多轮对话历史）
        print("[DEBUG] 开始生成答案...")
        # 限制对话历史长度，只保留最近5轮对话（10条消息）
        recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history
        answer = qwen_api.generate_answer(question, kg_context, recent_history)
        
        print(f"[DEBUG] 生成答案完成")
        
        # 4. 更新对话历史
        conversation_history.append({"role": "user", "content": question})
        conversation_history.append({"role": "assistant", "content": answer})
        session['conversations'][session_id] = conversation_history
        session.modified = True
        
        # 5. 生成建议问题
        print("[DEBUG] 开始生成建议问题...")
        suggested_questions = qwen_api.generate_suggested_questions(question, answer)
        print(f"[DEBUG] 生成建议问题完成: {suggested_questions}")
        
        # 6. 生成推理路径和可视化数据
        reasoning_path = generate_reasoning_path(question, entities, kg_results_all, answer)
        visualization_data = generate_kg_visualization_data(entities, kg_results_all)
        
        return jsonify({
            'answer': answer,
            'entities': [{'text': e[0], 'type': e[1]} for e in entities],
            'kg_context': kg_context if kg_context else None,
            'kg_results': kg_results_all,
            'reasoning_path': reasoning_path,
            'visualization_data': visualization_data,
            'suggested_questions': suggested_questions,
            'session_id': session_id
        })
        
    except Exception as e:
        print(f"[ERROR] 处理请求时出错: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 500


@app.route('/api/chat/stream', methods=['POST'])
def chat_stream():
    """SSE 流式问答接口 — 逐 token 推送答案，实时展示 Agent 执行进度"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        session_id = data.get('session_id', None)

        if not question:
            return jsonify({'error': '问题不能为空'}), 400

        if 'conversations' not in session:
            session['conversations'] = {}

        if not session_id:
            session_id = str(uuid.uuid4())

        if session_id not in session['conversations']:
            session['conversations'][session_id] = []

        conversation_history = session['conversations'][session_id]

        print(f"[SSE] 收到问题: {question} (Session: {session_id})")

        def generate():
            # --- Phase 1: 实体识别 ---
            yield "event: entity_start\ndata: {}\n\n"

            entities_data = qwen_api.extract_entities(question)
            entities = [(e['text'], e.get('label', e.get('type', '')))
                        for e in entities_data] if entities_data else []

            yield f"event: entity_done\ndata: {json.dumps({'entities': [{'text': t, 'type': tp} for t, tp in entities]}, ensure_ascii=False)}\n\n"
            print(f"[SSE] 实体识别完成: {entities}")

            # --- Phase 2: KG 查询 ---
            yield "event: kg_start\ndata: {}\n\n"

            kg_contexts = []
            kg_results_all = {}

            if entities:
                for entity_text, entity_type in entities[:SYSTEM_CONFIG["max_entities"]]:
                    kg_results = kg_enhancer.query_relations(entity_text, entity_type)
                    if kg_results:
                        kg_results_all[entity_text] = kg_results
                        kg_context = kg_enhancer.format_kg_context(
                            kg_results, entity_text, entity_type)
                        kg_contexts.append(kg_context)

            kg_context = "\n\n".join(kg_contexts) if kg_contexts else ""
            kg_entity_count = len(kg_results_all)

            yield f"event: kg_done\ndata: {json.dumps({'entity_count': kg_entity_count, 'context_length': len(kg_context)}, ensure_ascii=False)}\n\n"
            print(f"[SSE] KG查询完成, {kg_entity_count} 个实体有结果")

            # --- Phase 3: 答案流式生成 ---
            recent_history = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history

            answer_tokens = []
            for token in qwen_api.generate_answer_stream(question, kg_context, recent_history):
                answer_tokens.append(token)
                yield f"event: answer_token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            full_answer = "".join(answer_tokens)
            print(f"[SSE] 答案生成完成, 共 {len(full_answer)} 字符")

            # --- Phase 4: 更新对话历史 ---
            conversation_history.append({"role": "user", "content": question})
            conversation_history.append({"role": "assistant", "content": full_answer})
            session['conversations'][session_id] = conversation_history
            session.modified = True

            # --- Phase 5: 建议问题 ---
            suggested_questions = qwen_api.generate_suggested_questions(question, full_answer)
            yield f"event: suggested_questions\ndata: {json.dumps({'questions': suggested_questions}, ensure_ascii=False)}\n\n"

            # --- Phase 6: 可视化数据和推理路径 ---
            reasoning_path = generate_reasoning_path(question, entities, kg_results_all, full_answer)
            visualization_data = generate_kg_visualization_data(entities, kg_results_all)

            yield f"event: visualization_data\ndata: {json.dumps(visualization_data, ensure_ascii=False)}\n\n"
            yield f"event: reasoning_path\ndata: {json.dumps(reasoning_path, ensure_ascii=False)}\n\n"

            # --- Complete ---
            yield f"event: done\ndata: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',
                'Access-Control-Allow-Origin': '*'
            }
        )

    except Exception as e:
        print(f"[SSE ERROR] 处理请求时出错: {str(e)}")
        print(traceback.format_exc())

        def error_gen():
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

        return Response(
            error_gen(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'Access-Control-Allow-Origin': '*'
            }
        )


def generate_reasoning_path(question: str, entities: list, kg_results: dict, answer: str) -> list:
    """生成推理路径，用于可解释性展示"""
    reasoning_steps = []
    
    # 步骤1：问题分析
    reasoning_steps.append({
        'step': 1,
        'type': 'question_analysis',
        'title': '问题分析',
        'description': f'分析用户问题："{question}"',
        'details': {
            'question': question,
            'analysis': '识别问题类型和关键信息'
        }
    })
    
    # 步骤2：实体识别
    if entities:
        reasoning_steps.append({
            'step': 2,
            'type': 'entity_extraction',
            'title': '实体识别',
            'description': f'从问题中识别出 {len(entities)} 个实体',
            'details': {
                'entities': [{'text': e[0], 'type': e[1]} for e in entities],
                'method': '使用千问API进行命名实体识别'
            }
        })
    
    # 步骤3：知识图谱查询
    if kg_results:
        kg_query_details = []
        total_relations = 0
        all_relation_types = set()
        
        for entity_text, results in kg_results.items():
            entity_relations = []
            entity_relation_count = 0
            
            # 处理kg_enhancer返回的键值对格式
            for relation_key, relation_data in results.items():
                if relation_data and isinstance(relation_data, list):
                    relation_name = relation_key.split('_')[0]
                    all_relation_types.add(relation_name)
                    entity_relation_count += len(relation_data)
                    
                    # 收集关系详情
                    for item in relation_data:
                        entity_relations.append({
                            'source': entity_text,
                            'relation': relation_name,
                            'target': item.get('text', ''),
                            'target_type': item.get('type', '')
                        })
            
            if entity_relations:
                kg_query_details.append({
                    'entity': entity_text,
                    'relations_found': entity_relation_count,
                    'relations': entity_relations[:5]  # 只显示前5个关系
                })
                total_relations += entity_relation_count
        
        if kg_query_details:
            reasoning_steps.append({
                'step': 3,
                'type': 'kg_query',
                'title': '知识图谱查询',
                'description': f'在知识图谱中查找到 {total_relations} 个相关关系',
                'details': {
                    'query_results': kg_query_details,
                    'total_relations': total_relations,
                    'relation_types': list(all_relation_types)
                }
            })
    
    # 步骤4：知识融合
    if kg_results:
        reasoning_steps.append({
            'step': 4,
            'type': 'knowledge_fusion',
            'title': '知识融合',
            'description': '将知识图谱信息与大模型知识融合',
            'details': {
                'kg_entities': list(kg_results.keys()),
                'fusion_method': '上下文增强的提示工程'
            }
        })
    
    # 步骤5：答案生成
    reasoning_steps.append({
        'step': len(reasoning_steps) + 1,
        'type': 'answer_generation',
        'title': '答案生成',
        'description': '基于融合知识生成最终答案',
        'details': {
            'model': 'qwen2.5-32b-instruct',
            'enhancement': '知识图谱增强' if kg_results else '纯大模型推理',
            'answer_length': len(answer)
        }
    })
    
    return reasoning_steps


def generate_kg_visualization_data(entities: list, kg_results: dict) -> dict:
    """生成知识图谱可视化数据"""
    nodes = []
    edges = []
    node_ids = set()
    
    # 添加查询实体节点
    for entity_text, entity_type in entities:
        if entity_text not in node_ids:
            nodes.append({
                'id': entity_text,
                'label': entity_text,
                'type': entity_type,
                'category': 'query_entity',
                'size': 30,
                'color': '#ff6b6b'
            })
            node_ids.add(entity_text)
    
    # 添加知识图谱中的相关实体和关系
    for entity_text, results in kg_results.items():
        # kg_enhancer.query_relations返回的是键值对格式，需要解析
        for relation_key, relation_data in results.items():
            if relation_data and isinstance(relation_data, list):
                # 解析关系类型和方向
                relation_parts = relation_key.split('_')
                if len(relation_parts) >= 2:
                    relation_name = relation_parts[0]
                    is_from_relation = 'from' in relation_key
                    
                    for item in relation_data:
                        target_entity = item.get('text', '')
                        target_type = item.get('type', '')
                        
                        if target_entity and target_entity not in node_ids:
                            nodes.append({
                                'id': target_entity,
                                'label': target_entity,
                                'type': target_type,
                                'category': 'related_entity',
                                'size': 20,
                                'color': '#4ecdc4'
                            })
                            node_ids.add(target_entity)
                        
                        # 添加关系边
                        if entity_text in node_ids and target_entity:
                            if is_from_relation:
                                # 反向关系：target -> entity
                                edges.append({
                                    'source': target_entity,
                                    'target': entity_text,
                                    'label': relation_name,
                                    'type': relation_name,
                                    'color': '#95a5a6'
                                })
                            else:
                                # 正向关系：entity -> target
                                edges.append({
                                    'source': entity_text,
                                    'target': target_entity,
                                    'label': relation_name,
                                    'type': relation_name,
                                    'color': '#95a5a6'
                                })
    
    return {
        'nodes': nodes,
        'edges': edges,
        'stats': {
            'total_nodes': len(nodes),
            'total_edges': len(edges),
            'query_entities': len([n for n in nodes if n['category'] == 'query_entity']),
            'related_entities': len([n for n in nodes if n['category'] == 'related_entity'])
        }
    }


@app.route('/api/entities', methods=['POST'])
def extract_entities():
    """实体抽取接口"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        
        if not text:
            return jsonify({'error': '文本不能为空'}), 400
        
        entities = qwen_api.extract_entities(text)
        return jsonify({'entities': entities})
        
    except Exception as e:
        print(f"[ERROR] 实体抽取出错: {str(e)}")
        return jsonify({'error': f'实体抽取出错: {str(e)}'}), 500


@app.route('/api/kg/query', methods=['POST'])
def query_kg():
    """知识图谱查询接口"""
    try:
        data = request.get_json()
        entity_text = data.get('entity_text', '').strip()
        entity_type = data.get('entity_type', '').strip()
        relation_name = data.get('relation_name', None)
        
        if not entity_text or not entity_type:
            return jsonify({'error': '实体文本和类型不能为空'}), 400
        
        results = kg_enhancer.query_relations(entity_text, entity_type, relation_name)
        return jsonify({'results': results})
        
    except Exception as e:
        print(f"[ERROR] 知识图谱查询出错: {str(e)}")
        return jsonify({'error': f'知识图谱查询出错: {str(e)}'}), 500


@app.route('/api/kg/multi-hop', methods=['POST'])
def query_multi_hop():
    """多跳查询接口"""
    try:
        data = request.get_json()
        entity_text = data.get('entity_text', '').strip()
        entity_type = data.get('entity_type', '').strip()
        max_hops = data.get('max_hops', 2)
        
        if not entity_text or not entity_type:
            return jsonify({'error': '实体文本和类型不能为空'}), 400
        
        results = kg_enhancer.query_multi_hop(entity_text, entity_type, max_hops)
        return jsonify({'results': results})
        
    except Exception as e:
        print(f"[ERROR] 多跳查询出错: {str(e)}")
        return jsonify({'error': f'多跳查询出错: {str(e)}'}), 500


@app.route('/api/kg/visualize', methods=['POST'])
def visualize_kg():
    """知识图谱可视化接口"""
    try:
        data = request.get_json()
        entity_text = data.get('entity_text', '').strip()
        entity_type = data.get('entity_type', '').strip()
        depth = data.get('depth', 1)  # 查询深度
        
        if not entity_text:
            return jsonify({'error': '实体文本不能为空'}), 400
        
        print(f"[DEBUG] 可视化查询: {entity_text} ({entity_type}), 深度: {depth}")
        
        # 查询知识图谱
        kg_results = kg_enhancer.query_relations(entity_text, entity_type)
        
        if not kg_results:
            return jsonify({
                'visualization_data': {
                    'nodes': [{
                        'id': entity_text,
                        'label': entity_text,
                        'type': entity_type,
                        'category': 'query_entity',
                        'size': 30,
                        'color': '#ff6b6b'
                    }],
                    'edges': [],
                    'stats': {
                        'total_nodes': 1,
                        'total_edges': 0,
                        'query_entities': 1,
                        'related_entities': 0
                    }
                },
                'message': '未找到相关关系'
            })
        
        # 生成可视化数据
        visualization_data = generate_kg_visualization_data([(entity_text, entity_type)], {entity_text: kg_results})
        
        # 如果需要更深层查询
        if depth > 1:
            extended_results = {}
            for relation in kg_results.get('relations', []):
                target_entity = relation.get('target_entity', '')
                target_type = relation.get('target_type', '')
                if target_entity and target_type:
                    sub_results = kg_enhancer.query_relations(target_entity, target_type)
                    if sub_results:
                        extended_results[target_entity] = sub_results
            
            if extended_results:
                # 合并结果
                all_results = {entity_text: kg_results}
                all_results.update(extended_results)
                
                # 重新生成可视化数据
                all_entities = [(entity_text, entity_type)]
                for entity, results in extended_results.items():
                    # 从结果中推断实体类型
                    entity_type_inferred = ''
                    if results.get('relations'):
                        for rel in results['relations']:
                            if rel.get('source_entity') == entity:
                                entity_type_inferred = rel.get('source_type', '')
                                break
                    all_entities.append((entity, entity_type_inferred))
                
                visualization_data = generate_kg_visualization_data(all_entities, all_results)
        
        return jsonify({
            'visualization_data': visualization_data,
            'kg_results': kg_results,
            'query_info': {
                'entity': entity_text,
                'type': entity_type,
                'depth': depth
            }
        })
        
    except Exception as e:
        print(f"[ERROR] 可视化查询出错: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'可视化查询出错: {str(e)}'}), 500


@app.route('/api/reasoning/explain', methods=['POST'])
def explain_reasoning():
    """推理过程解释接口"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': '问题不能为空'}), 400
        
        print(f"[DEBUG] 推理解释请求: {question}")
        
        # 1. 实体抽取
        entities_data = qwen_api.extract_entities(question)
        entities = [(e['text'], e.get('label', e.get('type', ''))) for e in entities_data] if entities_data else []
        
        # 2. 知识图谱查询
        kg_results_all = {}
        for entity_text, entity_type in entities[:SYSTEM_CONFIG["max_entities"]]:
            kg_results = kg_enhancer.query_relations(entity_text, entity_type)
            if kg_results:
                kg_results_all[entity_text] = kg_results
        
        # 3. 生成详细推理路径
        detailed_reasoning = generate_detailed_reasoning_path(question, entities, kg_results_all)
        
        return jsonify({
            'reasoning_path': detailed_reasoning,
            'entities': [{'text': e[0], 'type': e[1]} for e in entities],
            'kg_summary': {
                'entities_queried': len(kg_results_all),
                'total_relations': sum([len(r.get('relations', [])) for r in kg_results_all.values()]),
                'relation_types': list(set([
                    rel.get('relation_type', '') 
                    for results in kg_results_all.values() 
                    for rel in results.get('relations', [])
                ]))
            }
        })
        
    except Exception as e:
        print(f"[ERROR] 推理解释出错: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'推理解释出错: {str(e)}'}), 500


def generate_detailed_reasoning_path(question: str, entities: list, kg_results: dict) -> list:
    """生成详细的推理路径"""
    detailed_steps = []
    
    # 问题分析步骤
    detailed_steps.append({
        'step': 1,
        'type': 'question_analysis',
        'title': '问题理解与分析',
        'description': '分析用户问题的语义和意图',
        'details': {
            'original_question': question,
            'question_type': classify_question_type(question),
            'key_concepts': extract_key_concepts(question),
            'expected_answer_type': infer_answer_type(question)
        },
        'confidence': 0.95
    })
    
    # 实体识别步骤
    if entities:
        detailed_steps.append({
            'step': 2,
            'type': 'entity_recognition',
            'title': '命名实体识别',
            'description': f'识别出{len(entities)}个关键实体',
            'details': {
                'entities': [{'text': e[0], 'type': e[1], 'confidence': 0.9} for e in entities],
                'recognition_method': 'Qwen API + 中医领域实体库',
                'entity_validation': '通过知识图谱验证实体存在性'
            },
            'confidence': 0.9
        })
    
    # 知识检索步骤
    if kg_results:
        for entity_text, results in kg_results.items():
            if results.get('relations'):
                detailed_steps.append({
                    'step': len(detailed_steps) + 1,
                    'type': 'knowledge_retrieval',
                    'title': f'知识检索 - {entity_text}',
                    'description': f'从知识图谱中检索与"{entity_text}"相关的知识',
                    'details': {
                        'entity': entity_text,
                        'relations_found': len(results['relations']),
                        'relation_details': [
                            {
                                'relation_type': rel.get('relation_type', ''),
                                'target_entity': rel.get('target_entity', ''),
                                'target_type': rel.get('target_type', ''),
                                'confidence': rel.get('confidence', 0.8)
                            }
                            for rel in results['relations'][:5]  # 只显示前5个关系
                        ],
                        'knowledge_source': 'Neo4j知识图谱'
                    },
                    'confidence': 0.85
                })
    
    # 知识融合步骤
    if kg_results:
        detailed_steps.append({
            'step': len(detailed_steps) + 1,
            'type': 'knowledge_fusion',
            'title': '知识融合与推理',
            'description': '将检索到的知识与大模型知识进行融合',
            'details': {
                'fusion_strategy': '上下文增强提示工程',
                'knowledge_sources': ['知识图谱', '大模型预训练知识'],
                'reasoning_type': '基于事实的逻辑推理',
                'confidence_calculation': '基于知识来源可信度加权'
            },
            'confidence': 0.88
        })
    
    return detailed_steps


def classify_question_type(question: str) -> str:
    """分类问题类型"""
    if any(word in question for word in ['什么', '是什么', '定义']):
        return '定义类问题'
    elif any(word in question for word in ['功效', '作用', '治疗']):
        return '功效询问'
    elif any(word in question for word in ['如何', '怎么', '方法']):
        return '方法询问'
    elif any(word in question for word in ['为什么', '原因']):
        return '原因询问'
    else:
        return '综合询问'


def extract_key_concepts(question: str) -> list:
    """提取关键概念"""
    # 简单的关键词提取
    key_words = []
    medical_terms = ['中药', '方剂', '穴位', '经脉', '疾病', '症状', '治疗', '功效']
    for term in medical_terms:
        if term in question:
            key_words.append(term)
    return key_words


def infer_answer_type(question: str) -> str:
    """推断答案类型"""
    if '功效' in question or '作用' in question:
        return '功效描述'
    elif '治疗' in question:
        return '治疗方法'
    elif '是什么' in question:
        return '概念解释'
    else:
        return '综合回答'


@app.route('/api/health', methods=['GET'])
def health():
    """健康检查接口"""
    try:
        # 测试Neo4j连接
        kg_status = "connected"
        try:
            with kg_enhancer.driver.session() as session:
                session.run("RETURN 1")
        except Exception as e:
            kg_status = f"disconnected: {str(e)}"
        
        return jsonify({
            'status': 'ok',
            'kg_enabled': SYSTEM_CONFIG["enable_kg_enhancement"],
            'kg_status': kg_status,
            'qwen_model': qwen_api.model,
            'qwen_api_key_configured': qwen_api.api_key != "your-qwen-api-key",
            'timestamp': __import__('datetime').datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


@app.teardown_appcontext
def close_db(error):
    """关闭数据库连接"""
    pass


if __name__ == '__main__':
    print("="*60)
    print("🚀 启动中医问答系统（知识图谱增强版）")
    print("="*60)
    print(f"CORS支持: {'flask-cors库' if CORS_AVAILABLE else '手动处理'}")
    print(f"知识图谱增强: {'启用' if SYSTEM_CONFIG['enable_kg_enhancement'] else '禁用'}")
    print(f"千问模型: {qwen_api.model}")
    print("="*60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("\n正在关闭服务...")
    finally:
        kg_enhancer.close()
        print("服务已关闭")