import React, { useReducer, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import './QuestionAnswer.css';
import { useNavigate } from 'react-router-dom';
import ErrorBoundary from './ErrorBoundary';
import { useToast } from './Toast';
import ToastContainer from './Toast';

const KnowledgeGraphVisualization = lazy(() => import('./KnowledgeGraphVisualization'));
const ReasoningPathVisualization = lazy(() => import('./ReasoningPathVisualization'));

const HISTORY_KEY = 'tcm_qa_history';
const MAX_HISTORY_ROUNDS = 50;

function loadHistory() {
    try {
        const raw = localStorage.getItem(HISTORY_KEY);
        if (raw) {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) return parsed.slice(-MAX_HISTORY_ROUNDS);
        }
    } catch (e) { /* ignore */ }
    return [];
}

function saveHistory(questions) {
    try {
        localStorage.setItem(HISTORY_KEY, JSON.stringify(questions.slice(-MAX_HISTORY_ROUNDS)));
    } catch (e) { /* ignore */ }
}

// --- Reducer ---
const initialState = {
    questions: loadHistory(),
    inputValue: '',
    status: 'idle',         // idle | loading | streaming | done | error
    currentAnswer: '',
    entities: [],
    kgContext: '',
    visualizationData: null,
    reasoningPath: [],
    suggestedQuestions: [],
    activeTab: 'chat',
    sessionId: null,
    error: null,
};

function reducer(state, action) {
    switch (action.type) {
        case 'SET_INPUT':
            return { ...state, inputValue: action.payload };

        case 'SUBMIT_START':
            return {
                ...state,
                status: 'loading',
                currentAnswer: '',
                entities: [],
                kgContext: '',
                visualizationData: null,
                reasoningPath: [],
                suggestedQuestions: [],
                activeTab: 'chat',
                error: null,
            };

        case 'ENTITIES_RECEIVED':
            return { ...state, entities: action.payload };

        case 'KG_DONE':
            return { ...state, kgContext: action.payload, status: 'streaming' };

        case 'ANSWER_TOKEN':
            return { ...state, currentAnswer: state.currentAnswer + action.payload };

        case 'STREAM_DONE': {
            const newQ = {
                question: state.inputValue,
                answer: state.currentAnswer,
                entities: state.entities,
                kg_context: state.kgContext || null,
                visualization_data: action.payload.visualizationData || null,
                reasoning_path: action.payload.reasoningPath || [],
            };
            const questions = [...state.questions, newQ];
            saveHistory(questions);
            let tab = 'chat';
            if (action.payload.visualizationData) tab = 'visualization';
            else if (action.payload.reasoningPath?.length) tab = 'reasoning';
            else if (state.kgContext) tab = 'kg';
            return {
                ...state,
                questions,
                inputValue: '',
                status: 'done',
                visualizationData: action.payload.visualizationData || null,
                reasoningPath: action.payload.reasoningPath || [],
                suggestedQuestions: action.payload.suggestedQuestions || [],
                sessionId: action.payload.sessionId || state.sessionId,
                activeTab: tab,
            };
        }

        case 'STREAM_ERROR':
            return { ...state, status: 'error', error: action.payload };

        case 'SET_ACTIVE_TAB':
            return { ...state, activeTab: action.payload };

        case 'CLEAR_HISTORY':
            localStorage.removeItem(HISTORY_KEY);
            return { ...state, questions: [], status: 'idle', currentAnswer: '', entities: [],
                      kgContext: '', visualizationData: null, reasoningPath: [],
                      suggestedQuestions: [], activeTab: 'chat', error: null };

        default:
            return state;
    }
}

// --- Component ---
const QuestionAnswer = () => {
    const [state, dispatch] = useReducer(reducer, initialState);
    const { toasts, removeToast, toast } = useToast();
    const navigate = useNavigate();
    const abortRef = useRef(null);

    // Scroll to bottom when streaming
    const historyEndRef = useRef(null);
    useEffect(() => {
        if (state.status === 'streaming' || state.status === 'done') {
            historyEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [state.currentAnswer, state.status]);

    const handleSubmitStream = useCallback(async () => {
        const question = state.inputValue.trim();
        if (!question || state.status === 'loading' || state.status === 'streaming') return;

        dispatch({ type: 'SUBMIT_START' });
        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question, session_id: state.sessionId }),
                signal: controller.signal,
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            let vizData = null;
            let reasonPath = [];
            let suggestions = [];
            let sessId = state.sessionId;

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                let eventType = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ')) {
                        const raw = line.slice(6);
                        try {
                            const data = JSON.parse(raw);
                            switch (eventType) {
                                case 'entity_done':
                                    dispatch({ type: 'ENTITIES_RECEIVED', payload: data.entities || [] });
                                    break;
                                case 'kg_done':
                                    // kg_context is built progressively; we signal streaming start here
                                    dispatch({ type: 'KG_DONE', payload: '' });
                                    break;
                                case 'answer_token':
                                    dispatch({ type: 'ANSWER_TOKEN', payload: data.token });
                                    break;
                                case 'suggested_questions':
                                    suggestions = data.questions || [];
                                    break;
                                case 'visualization_data':
                                    vizData = data;
                                    break;
                                case 'reasoning_path':
                                    reasonPath = data;
                                    break;
                                case 'done':
                                    sessId = data.session_id || sessId;
                                    break;
                                case 'error':
                                    throw new Error(data.error || '服务器流式错误');
                                default:
                                    break;
                            }
                        } catch (e) {
                            if (e.message && !e.message.includes('JSON')) throw e;
                        }
                    }
                }
            }

            // Fetch KG context from regular endpoint since SSE doesn't send it inline
            // We use the entities we collected
            let kgCtx = '';
            if (state.entities.length > 0) {
                try {
                    const kgRes = await fetch('/api/kg/query', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            entity_text: state.entities[0].text,
                            entity_type: state.entities[0].type
                        }),
                        signal: controller.signal,
                    });
                    if (kgRes.ok) {
                        const kgData = await kgRes.json();
                        if (kgData.kg_context) kgCtx = kgData.kg_context;
                    }
                } catch (e) { /* ignore kg fetch failure */ }
            }

            dispatch({
                type: 'STREAM_DONE',
                payload: {
                    visualizationData: vizData,
                    reasoningPath: reasonPath,
                    suggestedQuestions: suggestions,
                    sessionId: sessId,
                },
            });

            // Update kgContext after done
            if (kgCtx) {
                // Mini state patch: we accept the kgContext directly
                dispatch({ type: 'KG_DONE', payload: kgCtx });
            }

        } catch (error) {
            if (error.name === 'AbortError') return;
            dispatch({ type: 'STREAM_ERROR', payload: error.message });
            toast.error(`请求失败: ${error.message}`);
        }
    }, [state.inputValue, state.sessionId, state.status, state.entities, toast]);

    const handleSubmit = () => handleSubmitStream();

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const handleNodeClick = (node) => {
        console.log('Node clicked:', node);
    };

    const handleStepClick = (step, index) => {
        console.log('Reasoning step clicked:', step, index);
    };

    const handleClearHistory = () => {
        dispatch({ type: 'CLEAR_HISTORY' });
        toast.info('对话历史已清空');
    };

    const handleExportHistory = () => {
        const text = state.questions
            .map((q, i) => `[${i + 1}] Q: ${q.question}\nA: ${q.answer}\n`)
            .join('\n---\n');
        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `tcm-qa-history-${new Date().toISOString().slice(0, 10)}.txt`;
        a.click();
        URL.revokeObjectURL(url);
        toast.success('对话记录已导出');
    };

    const isLoading = state.status === 'loading' || state.status === 'streaming';
    const lastQ = state.questions.length > 0 ? state.questions[state.questions.length - 1] : null;

    return (
        <div className="qa-container">
            <ToastContainer toasts={toasts} onRemove={removeToast} />

            <div className="qa-history">
                <div className="qa-history-title">
                    历史问答记录
                    {state.questions.length > 0 && (
                        <span className="qa-history-actions">
                            <button className="action-btn" onClick={handleClearHistory} title="清空对话">
                                清空
                            </button>
                            <button className="action-btn" onClick={handleExportHistory} title="导出对话">
                                导出
                            </button>
                        </span>
                    )}
                </div>
                {state.questions.length === 0 ? (
                    <div className="qa-empty">暂无记录</div>
                ) : (
                    state.questions.map((qa, index) => (
                        <div key={index} className="qa-item">
                            <div className="qa-question">
                                <strong>Q:</strong> {qa.question}
                            </div>
                            {qa.entities && qa.entities.length > 0 && (
                                <div className="qa-entities">
                                    <strong>识别实体:</strong> {qa.entities.map((e, i) => (
                                        <span key={i} className={`entity-tag entity-${e.type}`} title={e.type}>
                                            <span className="entity-icon" aria-hidden="true">&#9679;</span>
                                            {e.text} ({e.type})
                                        </span>
                                    ))}
                                </div>
                            )}
                            <div className="qa-answer">
                                <strong>A:</strong> {qa.answer}
                            </div>
                        </div>
                    ))
                )}
                <div ref={historyEndRef} />
            </div>

            <div className="qa-input-area">
                <div className="qa-input">
                    <input
                        type="text"
                        value={state.inputValue}
                        onChange={(e) => dispatch({ type: 'SET_INPUT', payload: e.target.value })}
                        onKeyDown={handleKeyDown}
                        placeholder="输入你的问题..."
                        disabled={isLoading}
                        aria-label="输入中医问题"
                    />
                    <button
                        onClick={handleSubmit}
                        disabled={isLoading || !state.inputValue.trim()}
                        aria-busy={isLoading}
                    >
                        {isLoading ? '处理中...' : '提交'}
                    </button>
                </div>

                <div className="qa-current">
                    {state.status === 'loading' && (
                        <div className="qa-loading">
                            <div className="loading-spinner"></div>
                            <span>正在分析问题并查询知识图谱...</span>
                        </div>
                    )}

                    {(state.status === 'streaming' || state.status === 'done') && (
                        <div className="qa-item qa-current-item">
                            <div className="qa-question">
                                <strong>Q:</strong> {lastQ?.question || ''}
                            </div>
                            {state.entities.length > 0 && (
                                <div className="qa-entities">
                                    <strong>识别实体:</strong> {state.entities.map((e, i) => (
                                        <span key={i} className={`entity-tag entity-${e.type}`} title={e.type}>
                                            <span className="entity-icon" aria-hidden="true">&#9679;</span>
                                            {e.text} ({e.type})
                                        </span>
                                    ))}
                                </div>
                            )}
                            <div className="qa-answer">
                                <strong>A:</strong> {state.currentAnswer}
                                {state.status === 'streaming' && <span className="cursor-blink">|</span>}
                            </div>

                            {(state.kgContext || state.visualizationData || state.reasoningPath.length > 0) && (
                                <div className="qa-enhanced-info">
                                    <div className="enhanced-info-tabs">
                                        {state.kgContext && (
                                            <button
                                                className={`tab-btn ${state.activeTab === 'kg' ? 'active' : ''}`}
                                                onClick={() => dispatch({ type: 'SET_ACTIVE_TAB', payload: 'kg' })}
                                            >
                                                KG 信息
                                            </button>
                                        )}
                                        {state.visualizationData && (
                                            <button
                                                className={`tab-btn ${state.activeTab === 'visualization' ? 'active' : ''}`}
                                                onClick={() => dispatch({ type: 'SET_ACTIVE_TAB', payload: 'visualization' })}
                                            >
                                                图谱可视化
                                            </button>
                                        )}
                                        {state.reasoningPath.length > 0 && (
                                            <button
                                                className={`tab-btn ${state.activeTab === 'reasoning' ? 'active' : ''}`}
                                                onClick={() => dispatch({ type: 'SET_ACTIVE_TAB', payload: 'reasoning' })}
                                            >
                                                推理路径
                                            </button>
                                        )}
                                    </div>

                                    <div className="enhanced-info-content">
                                        {state.activeTab === 'kg' && state.kgContext && (
                                            <div className="kg-context">
                                                <pre>{state.kgContext}</pre>
                                            </div>
                                        )}

                                        {state.activeTab === 'visualization' && state.visualizationData && (
                                            <ErrorBoundary message="知识图谱可视化加载失败">
                                                <Suspense fallback={<div className="viz-loading">加载可视化...</div>}>
                                                    <KnowledgeGraphVisualization
                                                        visualizationData={state.visualizationData}
                                                        onNodeClick={handleNodeClick}
                                                    />
                                                </Suspense>
                                            </ErrorBoundary>
                                        )}

                                        {state.activeTab === 'reasoning' && state.reasoningPath.length > 0 && (
                                            <ErrorBoundary message="推理路径加载失败">
                                                <Suspense fallback={<div className="viz-loading">加载推理路径...</div>}>
                                                    <ReasoningPathVisualization
                                                        reasoningPath={state.reasoningPath}
                                                        onStepClick={handleStepClick}
                                                    />
                                                </Suspense>
                                            </ErrorBoundary>
                                        )}
                                    </div>
                                </div>
                            )}

                            {state.suggestedQuestions.length > 0 && (
                                <div className="qa-suggested">
                                    <strong>追问建议:</strong>
                                    {state.suggestedQuestions.map((q, i) => (
                                        <button
                                            key={i}
                                            className="suggested-q-btn"
                                            onClick={() => dispatch({ type: 'SET_INPUT', payload: q })}
                                        >
                                            {q}
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {state.status === 'error' && state.error && (
                        <div className="qa-error">
                            <p>请求失败: {state.error}</p>
                            <button onClick={() => dispatch({ type: 'STREAM_ERROR', payload: null })}>
                                重试
                            </button>
                        </div>
                    )}
                </div>
            </div>

            <button onClick={() => navigate('/tcm/DIS')} className="tcm-button">
                跳转中医药界面
            </button>
        </div>
    );
};

export default QuestionAnswer;