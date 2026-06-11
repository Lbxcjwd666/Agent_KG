"""
重构后的Flask后端
集成知识图谱增强和千问API
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from kg_enhancer import KnowledgeGraphEnhancer
from qwen_api import QwenAPI
from config import SYSTEM_CONFIG
import traceback

app = Flask(__name__)
CORS(app)  # 启用CORS

# 初始化知识图谱增强器
kg_enhancer = KnowledgeGraphEnhancer()

# 初始化千问API客户端
qwen_api = QwenAPI()


@app.route('/api/chat', methods=['POST'])
def chat():
    """问答接口 - 使用知识图谱增强和千问API"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({'error': '问题不能为空'}), 400
        
        print(f"[DEBUG] 收到问题: {question}")
        
        # 1. 使用千问API抽取实体
        print("[DEBUG] 开始抽取实体...")
        entities_data = qwen_api.extract_entities(question)
        
        if not entities_data:
            # 如果没有识别到实体，直接使用千问API回答
            print("[DEBUG] 未识别到实体，直接使用千问API回答")
            answer = qwen_api.generate_answer(question)
            return jsonify({
                'answer': answer,
                'entities': [],
                'kg_context': None
            })
        
        # 转换实体格式
        entities = [(e['text'], e.get('label', e.get('type', ''))) for e in entities_data]
        print(f"[DEBUG] 识别到实体: {entities}")
        
        # 2. 使用知识图谱增强
        print("[DEBUG] 开始知识图谱增强...")
        kg_contexts = []
        kg_results_all = {}
        
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
        
        # 3. 使用千问API生成答案（带知识图谱增强）
        print("[DEBUG] 开始生成答案...")
        answer = qwen_api.generate_answer(question, kg_context)
        
        print(f"[DEBUG] 生成答案完成")
        
        return jsonify({
            'answer': answer,
            'entities': [{'text': e[0], 'type': e[1]} for e in entities],
            'kg_context': kg_context if kg_context else None,
            'kg_results': kg_results_all
        })
        
    except Exception as e:
        print(f"[ERROR] 处理请求时出错: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 500


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


@app.route('/api/health', methods=['GET'])
def health():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'kg_enabled': SYSTEM_CONFIG["enable_kg_enhancement"],
        'qwen_model': qwen_api.model
    })


@app.teardown_appcontext
def close_db(error):
    """关闭数据库连接"""
    pass


if __name__ == '__main__':
    print("="*60)
    print("🚀 启动中医问答系统（知识图谱增强版）")
    print("="*60)
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



