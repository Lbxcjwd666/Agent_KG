import React, { useState } from 'react';
import './ReasoningPathVisualization.css';

const ReasoningPathVisualization = ({ reasoningPath, onStepClick }) => {
    const [expandedSteps, setExpandedSteps] = useState(new Set());
    const [selectedStep, setSelectedStep] = useState(null);

    const toggleStepExpansion = (stepIndex) => {
        const newExpanded = new Set(expandedSteps);
        if (newExpanded.has(stepIndex)) {
            newExpanded.delete(stepIndex);
        } else {
            newExpanded.add(stepIndex);
        }
        setExpandedSteps(newExpanded);
    };

    const handleStepClick = (step, index) => {
        setSelectedStep(index);
        if (onStepClick) {
            onStepClick(step, index);
        }
    };

    const getStepIcon = (type) => {
        const icons = {
            'question_analysis': '🤔',
            'entity_extraction': '🏷️',
            'entity_recognition': '🔍',
            'kg_query': '🗂️',
            'knowledge_retrieval': '📚',
            'knowledge_fusion': '🔗',
            'answer_generation': '💡'
        };
        return icons[type] || '📋';
    };

    const getStepColor = (type) => {
        const colors = {
            'question_analysis': '#3498db',
            'entity_extraction': '#e74c3c',
            'entity_recognition': '#e74c3c',
            'kg_query': '#f39c12',
            'knowledge_retrieval': '#f39c12',
            'knowledge_fusion': '#9b59b6',
            'answer_generation': '#27ae60'
        };
        return colors[type] || '#95a5a6';
    };

    const getConfidenceColor = (confidence) => {
        if (confidence >= 0.9) return '#27ae60';
        if (confidence >= 0.8) return '#f39c12';
        if (confidence >= 0.7) return '#e67e22';
        return '#e74c3c';
    };

    if (!reasoningPath || reasoningPath.length === 0) {
        return (
            <div className="reasoning-path-empty">
                <div className="empty-icon">🧠</div>
                <div className="empty-text">暂无推理路径数据</div>
            </div>
        );
    }

    return (
        <div className="reasoning-path-container">
            <div className="reasoning-path-header">
                <h3>推理过程解析</h3>
                <div className="path-stats">
                    <span className="stat-item">
                        <span className="stat-label">步骤:</span>
                        <span className="stat-value">{reasoningPath.length}</span>
                    </span>
                    <span className="stat-item">
                        <span className="stat-label">平均置信度:</span>
                        <span className="stat-value">
                            {(reasoningPath.reduce((sum, step) => sum + (step.confidence || 0.8), 0) / reasoningPath.length * 100).toFixed(1)}%
                        </span>
                    </span>
                </div>
            </div>

            <div className="reasoning-path-timeline">
                {reasoningPath.map((step, index) => (
                    <div 
                        key={index} 
                        className={`reasoning-step ${selectedStep === index ? 'selected' : ''}`}
                        onClick={() => handleStepClick(step, index)}
                    >
                        <div className="step-connector">
                            {index < reasoningPath.length - 1 && <div className="connector-line"></div>}
                        </div>
                        
                        <div className="step-marker" style={{ backgroundColor: getStepColor(step.type) }}>
                            <span className="step-icon">{getStepIcon(step.type)}</span>
                            <span className="step-number">{step.step}</span>
                        </div>
                        
                        <div className="step-content">
                            <div className="step-header">
                                <h4 className="step-title">{step.title}</h4>
                                {step.confidence && (
                                    <div className="confidence-badge" style={{ backgroundColor: getConfidenceColor(step.confidence) }}>
                                        {(step.confidence * 100).toFixed(0)}%
                                    </div>
                                )}
                                <button 
                                    className="expand-button"
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        toggleStepExpansion(index);
                                    }}
                                >
                                    {expandedSteps.has(index) ? '▼' : '▶'}
                                </button>
                            </div>
                            
                            <p className="step-description">{step.description}</p>
                            
                            {expandedSteps.has(index) && step.details && (
                                <div className="step-details">
                                    {renderStepDetails(step.details, step.type)}
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const renderStepDetails = (details, stepType) => {
    switch (stepType) {
        case 'question_analysis':
            return (
                <div className="details-grid">
                    <div className="detail-item">
                        <strong>问题类型:</strong> {details.question_type}
                    </div>
                    <div className="detail-item">
                        <strong>关键概念:</strong> {details.key_concepts?.join(', ') || '无'}
                    </div>
                    <div className="detail-item">
                        <strong>期望答案类型:</strong> {details.expected_answer_type}
                    </div>
                </div>
            );
            
        case 'entity_extraction':
        case 'entity_recognition':
            return (
                <div className="details-grid">
                    <div className="detail-item">
                        <strong>识别方法:</strong> {details.recognition_method || details.method}
                    </div>
                    <div className="entities-list">
                        <strong>实体列表:</strong>
                        <div className="entity-tags">
                            {details.entities?.map((entity, idx) => (
                                <span key={idx} className="entity-tag">
                                    {entity.text} 
                                    <span className="entity-type">({entity.type})</span>
                                    {entity.confidence && (
                                        <span className="entity-confidence">{(entity.confidence * 100).toFixed(0)}%</span>
                                    )}
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            );
            
        case 'kg_query':
        case 'knowledge_retrieval':
            return (
                <div className="details-grid">
                    <div className="detail-item">
                        <strong>查询实体:</strong> {details.entity}
                    </div>
                    <div className="detail-item">
                        <strong>找到关系:</strong> {details.relations_found} 个
                    </div>
                    {details.relation_details && (
                        <div className="relations-list">
                            <strong>关系详情:</strong>
                            <div className="relation-items">
                                {details.relation_details.map((rel, idx) => (
                                    <div key={idx} className="relation-item">
                                        <span className="relation-type">{rel.relation_type}</span>
                                        <span className="relation-arrow">→</span>
                                        <span className="target-entity">{rel.target_entity}</span>
                                        <span className="target-type">({rel.target_type})</span>
                                        {rel.confidence && (
                                            <span className="relation-confidence">{(rel.confidence * 100).toFixed(0)}%</span>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            );
            
        case 'knowledge_fusion':
            return (
                <div className="details-grid">
                    <div className="detail-item">
                        <strong>融合策略:</strong> {details.fusion_strategy}
                    </div>
                    <div className="detail-item">
                        <strong>知识来源:</strong> {details.knowledge_sources?.join(', ')}
                    </div>
                    <div className="detail-item">
                        <strong>推理类型:</strong> {details.reasoning_type}
                    </div>
                </div>
            );
            
        case 'answer_generation':
            return (
                <div className="details-grid">
                    <div className="detail-item">
                        <strong>使用模型:</strong> {details.model}
                    </div>
                    <div className="detail-item">
                        <strong>增强方式:</strong> {details.enhancement}
                    </div>
                    <div className="detail-item">
                        <strong>答案长度:</strong> {details.answer_length} 字符
                    </div>
                </div>
            );
            
        default:
            return (
                <div className="details-raw">
                    <pre>{JSON.stringify(details, null, 2)}</pre>
                </div>
            );
    }
};

export default ReasoningPathVisualization;
