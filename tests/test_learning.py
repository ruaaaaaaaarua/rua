import json
import pytest
from app.knowledge import KnowledgeLibrary, DEFAULT_LIBRARY
from app.prompts import solve_prompt, chat_prompt
from tests.test_api import setup


def library(tmp_path, published=False, text=''):
    root = tmp_path / 'knowledge'
    root.mkdir()
    catalog = json.loads((DEFAULT_LIBRARY/'catalog.json').read_text())
    catalog['nodes'] = [catalog['nodes'][0]]
    catalog['nodes'][0].update(content_file='node.md', status='published' if published else 'draft',
                               sources=['维护者核验资料，第1页'] if published else [])
    (root/'catalog.json').write_text(json.dumps(catalog))
    (root/'node.md').write_text(text)
    return root


def test_initial_catalog_is_scaffold_not_fake_knowledge():
    wiki = KnowledgeLibrary()
    assert len(wiki.catalog()['nodes']) == 18
    assert wiki.catalog()['published_count'] == 0
    assert wiki.context('标幺值') == []


def test_draft_excluded_and_published_content_retrievable(tmp_path):
    root = library(tmp_path, text='草稿说明')
    wiki = KnowledgeLibrary(root)
    assert wiki.context('电力系统') == []
    data = json.loads((root/'catalog.json').read_text())
    data['nodes'][0].update(status='published', sources=['来源1'], version='2')
    (root/'catalog.json').write_text(json.dumps(data))
    context = wiki.context('电力系统')
    assert context[0]['version'] == '2'
    assert context[0]['content'] == '草稿说明'


def test_published_requires_actual_body_and_sources(tmp_path):
    root = library(tmp_path, published=True, text='<!-- 待填充 -->')
    with pytest.raises(ValueError, match='正文和来源'):
        KnowledgeLibrary(root)


def test_content_path_cannot_escape_library(tmp_path):
    root = library(tmp_path)
    data = json.loads((root/'catalog.json').read_text())
    data['nodes'][0]['content_file'] = '../private.md'
    (root/'catalog.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='目录内'):
        KnowledgeLibrary(root)


def test_unknown_question_does_not_create_node():
    wiki = KnowledgeLibrary()
    linked, candidates = wiki.match({'text':'这是一个完全不相关的陌生问题','knowledge':'未知'})
    assert linked == []
    assert wiki.catalog()['published_count'] == 0


def test_link_survives_renaming_node(tmp_path):
    root = library(tmp_path)
    data = json.loads((root/'catalog.json').read_text())
    original = data['nodes'][0]['id']
    data['nodes'][0]['name'] = '更准确的节点名称'
    (root/'catalog.json').write_text(json.dumps(data))
    assert KnowledgeLibrary(root).get(original)['name'] == '更准确的节点名称'


def test_retrieved_wiki_enters_actual_solve_prompt():
    prompt = solve_prompt(dict(text='题', user_answer='STUDENT_SECRET', reasoning='THOUGHT_SECRET',
                               wiki_context=[dict(id='psa-test',content='VERIFIED_BODY',version='2')]))
    assert 'VERIFIED_BODY' in prompt
    assert 'STUDENT_SECRET' not in prompt and 'THOUGHT_SECRET' not in prompt


def test_invalid_relation_is_rejected(tmp_path):
    root = library(tmp_path)
    data = json.loads((root/'catalog.json').read_text())
    data['nodes'][0]['relations'] = [{'type':'prerequisite','target':'missing'}]
    (root/'catalog.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='关系目标'):
        KnowledgeLibrary(root)


def test_published_wiki_reaches_solve_and_chat_with_versioned_citations(tmp_path):
    root = library(tmp_path, published=True, text='已审核的测试知识正文。')
    c, app, gateway, sid = setup(tmp_path / 'data')
    wiki = KnowledgeLibrary(root)
    app.state.service.library = wiki
    app.state.service.study.library = wiki
    ident = wiki.catalog()['nodes'][0]['id']
    c.put(f'/api/sessions/{sid}/questions/q1/links', json={'knowledge_ids':[ident]})
    response = c.post(f'/api/sessions/{sid}/analyze')
    assert response.status_code == 200
    assert gateway.inputs[-1]['wiki_context'][0]['content'] == '已审核的测试知识正文。'
    analysis = response.json()['questions'][0]['analysis']
    assert analysis['citations'][0]['id'] == ident
    assert analysis['knowledge_status'] == 'available'
    response = c.post(f'/api/sessions/{sid}/messages',json={'text':'继续解释','knowledge_id':ident})
    assert response.json()['messages'][-1]['citations'][0]['version'] == '1'
    assert gateway.inputs[-1]['wiki_context'][0]['sources']
