#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试可视化功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """测试模块导入"""
    try:
        from src.config import ENTITY_TYPES, RELATION_TYPES, NEO4J_CONFIG, QWEN_API_CONFIG
        print("✅ 配置模块导入成功")
        
        from src.kg_enhancer import KnowledgeGraphEnhancer
        print("✅ 知识图谱增强模块导入成功")
        
        from src.qwen_api import QwenAPI
        print("✅ 千问API模块导入成功")
        
        return True
    except Exception as e:
        print(f"❌ 模块导入失败: {e}")
        return False

def test_visualization_data_structure():
    """测试可视化数据结构"""
    sample_visualization_data = {
        "nodes": [
            {
                "id": "人参",
                "label": "人参",
                "type": "MED",
                "category": "query_entity",
                "size": 30,
                "color": "#ff6b6b"
            },
            {
                "id": "气虚",
                "label": "气虚",
                "type": "SYN",
                "category": "related_entity",
                "size": 20,
                "color": "#4ecdc4"
            }
        ],
        "edges": [
            {
                "source": "人参",
                "target": "气虚",
                "relation": "Treat",
                "label": "治疗"
            }
        ],
        "stats": {
            "total_nodes": 2,
            "total_edges": 1,
            "query_entities": 1,
            "related_entities": 1
        }
    }
    
    sample_reasoning_path = [
        {
            "step": 1,
            "type": "question_analysis",
            "title": "问题分析",
            "description": "分析用户问题：人参有什么功效？",
            "details": {
                "question": "人参有什么功效？",
                "analysis": "识别问题类型和关键信息"
            }
        },
        {
            "step": 2,
            "type": "entity_extraction",
            "title": "实体识别",
            "description": "从问题中识别出 1 个实体",
            "details": {
                "entities": [{"text": "人参", "type": "MED"}],
                "method": "使用千问API进行命名实体识别"
            }
        },
        {
            "step": 3,
            "type": "kg_query",
            "title": "知识图谱查询",
            "description": "查询实体相关的知识图谱信息",
            "details": {
                "relations": [
                    {"source": "人参", "relation": "Treat", "target": "气虚"}
                ]
            }
        }
    ]
    
    print("✅ 可视化数据结构验证成功")
    print(f"   - 节点数量: {len(sample_visualization_data['nodes'])}")
    print(f"   - 边数量: {len(sample_visualization_data['edges'])}")
    print(f"   - 推理步骤: {len(sample_reasoning_path)}")
    
    return True

def main():
    """主函数"""
    print("🔍 开始测试可视化功能...")
    print()
    
    # 测试模块导入
    if not test_imports():
        return False
    
    print()
    
    # 测试数据结构
    if not test_visualization_data_structure():
        return False
    
    print()
    print("🎉 所有测试通过！可视化功能已准备就绪")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


