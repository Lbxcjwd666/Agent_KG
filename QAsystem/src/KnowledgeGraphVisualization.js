import React, { useState, useMemo } from 'react';
import './KnowledgeGraphVisualization.css';

const SVG_WIDTH = 800;
const SVG_HEIGHT = 600;

function computeLayout(nodes) {
    const centerX = SVG_WIDTH / 2;
    const centerY = SVG_HEIGHT / 2;
    const radius = Math.min(SVG_WIDTH, SVG_HEIGHT) / 3;

    return nodes.map((node, index) => {
        if (node.category === 'query_entity') {
            return { ...node, x: centerX, y: centerY };
        }
        const angle = (index * 2 * Math.PI) / nodes.length;
        return {
            ...node,
            x: centerX + radius * Math.cos(angle),
            y: centerY + radius * Math.sin(angle),
        };
    });
}

const KnowledgeGraphVisualization = ({ visualizationData, onNodeClick }) => {
    const [selectedNode, setSelectedNode] = useState(null);
    const [tooltip, setTooltip] = useState({ show: false, x: 0, y: 0, content: '' });
    const [hoveredNode, setHoveredNode] = useState(null);

    const positionedNodes = useMemo(() => {
        if (!visualizationData?.nodes?.length) return [];
        return computeLayout(visualizationData.nodes);
    }, [visualizationData]);

    const nodeMap = useMemo(() => {
        const map = {};
        positionedNodes.forEach(n => { map[n.id] = n; });
        return map;
    }, [positionedNodes]);

    if (!visualizationData?.nodes?.length) {
        return (
            <div className="kg-visualization-empty">
                <div className="empty-icon">&#128269;</div>
                <div className="empty-text">暂无知识图谱数据</div>
            </div>
        );
    }

    const edges = visualizationData.edges || [];

    const handleMouseEnter = (node, e) => {
        setHoveredNode(node.id);
        setTooltip({
            show: true,
            x: e.clientX,
            y: e.clientY,
            content: `${node.label} (${node.type})`,
        });
    };

    const handleMouseLeave = () => {
        setHoveredNode(null);
        setTooltip({ show: false, x: 0, y: 0, content: '' });
    };

    const handleNodeClick = (node) => {
        setSelectedNode(node);
        if (onNodeClick) onNodeClick(node);
    };

    return (
        <div className="kg-visualization-container">
            <div className="kg-visualization-header">
                <h3>知识图谱可视化</h3>
                <div className="kg-stats">
                    <span className="stat-item">
                        <span className="stat-label">节点:</span>
                        <span className="stat-value">{visualizationData.stats?.total_nodes || positionedNodes.length}</span>
                    </span>
                    <span className="stat-item">
                        <span className="stat-label">关系:</span>
                        <span className="stat-value">{visualizationData.stats?.total_edges || edges.length}</span>
                    </span>
                </div>
            </div>

            <div className="kg-visualization-content">
                <svg
                    viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
                    className="kg-svg"
                    role="img"
                    aria-label="知识图谱关系图"
                >
                    {/* Edges */}
                    {edges.map((edge, i) => {
                        const src = nodeMap[edge.source];
                        const tgt = nodeMap[edge.target];
                        if (!src || !tgt) return null;
                        const mx = (src.x + tgt.x) / 2;
                        const my = (src.y + tgt.y) / 2;
                        return (
                            <g key={`edge-${i}`}>
                                <line
                                    x1={src.x} y1={src.y}
                                    x2={tgt.x} y2={tgt.y}
                                    stroke={edge.color || '#95a5a6'}
                                    strokeWidth="2"
                                    opacity="0.7"
                                />
                                <rect
                                    x={mx - 22} y={my - 10}
                                    width="44" height="16"
                                    fill="white" opacity="0.85" rx="3"
                                />
                                <text
                                    x={mx} y={my + 2}
                                    textAnchor="middle"
                                    fontSize="10"
                                    fill="#555"
                                >
                                    {edge.label || edge.type || ''}
                                </text>
                            </g>
                        );
                    })}

                    {/* Nodes */}
                    {positionedNodes.map((node) => (
                        <g
                            key={node.id}
                            className="kg-node-group"
                            onClick={() => handleNodeClick(node)}
                            onMouseEnter={(e) => handleMouseEnter(node, e)}
                            onMouseLeave={handleMouseLeave}
                        >
                            <title>{node.label} ({node.type})</title>
                            <circle
                                cx={node.x} cy={node.y}
                                r={node.size || 20}
                                fill={node.color || '#3498db'}
                                stroke={hoveredNode === node.id ? '#ff6b6b' : '#2c3e50'}
                                strokeWidth={hoveredNode === node.id ? 3 : 2}
                                opacity={hoveredNode === node.id ? 1 : 0.9}
                                style={{ cursor: 'pointer', transition: 'opacity 0.15s, stroke-width 0.15s' }}
                                tabIndex={0}
                                aria-label={`${node.label}, 类型${node.type}`}
                            />
                            <text
                                x={node.x}
                                y={node.y + (node.size || 20) + 15}
                                textAnchor="middle"
                                fontSize="12"
                                fontWeight="bold"
                                fill="#2c3e50"
                            >
                                {node.label.length > 8 ? node.label.substring(0, 8) + '...' : node.label}
                            </text>
                        </g>
                    ))}
                </svg>

                {tooltip.show && (
                    <div
                        className="kg-tooltip"
                        style={{
                            left: tooltip.x + 10,
                            top: tooltip.y - 30,
                            position: 'fixed',
                            zIndex: 1000,
                        }}
                    >
                        {tooltip.content}
                    </div>
                )}
            </div>

            <div className="kg-legend">
                <div className="legend-item">
                    <div className="legend-color" style={{ backgroundColor: '#ff6b6b' }} />
                    <span>查询实体</span>
                </div>
                <div className="legend-item">
                    <div className="legend-color" style={{ backgroundColor: '#4ecdc4' }} />
                    <span>相关实体</span>
                </div>
            </div>

            {selectedNode && (
                <div className="selected-node-info">
                    <h4>节点信息</h4>
                    <p><strong>名称:</strong> {selectedNode.label}</p>
                    <p><strong>类型:</strong> {selectedNode.type}</p>
                    <p><strong>分类:</strong> {selectedNode.category === 'query_entity' ? '查询实体' : '相关实体'}</p>
                </div>
            )}
        </div>
    );
};

export default KnowledgeGraphVisualization;
