from fastapi.testclient import TestClient
from app.main import create_app

class Gateway:
    solves=0
    async def extract(self,images):
        return [dict(number='1',kind='single',text='电压翻倍，其他条件不变，功率变化？',options=[dict(key='A',text='2倍'),dict(key='B',text='4倍')],user_answer='A',reasoning='一次关系',confidence='unsure',subject='电力系统分析',chapter='线路',knowledge='自然功率')]
    async def solve(self,q):
        self.solves+=1
        return dict(answer='B',explanation='平方关系',valid=True)
    async def diagnose(self,q,solution,history):
        return dict(reasoning_ok=False,diagnosis='忽略平方',knowledge_point='功率与电压平方成正比',distinction='平方而非一次',hint='检查指数',error_type='formula_error')
    async def chat(self,context,text,mode):return {'content':'检查题目条件。'}
    async def generate(self,context,purpose):return dict(kind='single',text='电压3倍，功率？',options=[dict(key='A',text='3倍'),dict(key='B',text='9倍')],answer='B',explanation='平方')
    async def verify(self,q):return dict(valid=True,answer='B',explanation='平方')


def client(tmp_path):
    gw=Gateway()
    app=create_app(tmp_path,lambda settings:gw)
    return TestClient(app),gw


def test_real_flow_hint_persistence_and_manual_training(tmp_path):
    c,g=client(tmp_path)
    s=c.post('/api/sessions',json={'mode':'hint'}).json(); sid=s['id']
    upload=c.post(f'/api/sessions/{sid}/upload',files={'files':('page.png',b'\x89PNG\r\n\x1a\nhello','image/png')})
    assert upload.status_code==200
    r=c.post(f'/api/sessions/{sid}/analyze',json={})
    assert r.status_code==200,r.text
    data=r.json();q=data['questions'][0]
    assert 'answer' not in q['analysis']
    assert len([m for m in data['messages'] if m['type']=='quiz'])==0
    assert len(c.get('/api/knowledge').json())==1
    c.post(f'/api/sessions/{sid}/analyze',json={})
    assert g.solves==1
    trained=c.post(f'/api/sessions/{sid}/train',json={'question_id':q['id'],'purpose':'variant'}).json()
    quiz=trained['messages'][-1]['quiz'];assert 'answer' not in quiz['question']
    answered=c.post(f'/api/sessions/{sid}/quiz/{quiz["id"]}/answer',json={'answer':'B'}).json()
    assert answered['messages'][-1]['quiz']['correct'] is True
    assert len([m for m in answered['messages'] if m['type']=='quiz'])==1
    assert c.post(f'/api/sessions/{sid}/quiz/{quiz["id"]}/answer',json={'answer':'A'}).status_code==400
    c.patch(f'/api/sessions/{sid}/questions/{q["id"]}',json={'user_answer':'B'})
    assert c.get('/api/knowledge').json()==[] # including dependent quiz evidence revoked


def test_settings_redaction_and_validation(tmp_path):
    c,g=client(tmp_path)
    settings={'profiles':[{'id':'p','name':'主模型','base_url':'https://example.com/v1','model':'m','api_key':'secret-value'}],
              'tasks':{'vision':'p','solve':'p','chat':'p','generate':'p','verify':'p'},'mode':'direct'}
    r=c.put('/api/settings',json=settings)
    assert r.status_code==200,r.text
    assert 'secret-value' not in r.text
    assert r.json()['profiles'][0]['has_key']
    settings['profiles'][0]['api_key']=''
    assert c.put('/api/settings',json=settings).json()['profiles'][0]['has_key']
    settings['profiles'][0]['base_url']='file:///etc/passwd'
    assert c.put('/api/settings',json=settings).status_code==422


def test_validation_errors_do_not_echo_keys(tmp_path):
    c,g=client(tmp_path)
    r=c.put('/api/settings',json={'profiles':[{'id':'p','name':'n','model':'m','base_url':'invalid','api_key':'private-key'}],
        'tasks':{},'mode':'direct','unexpected_secret':'another-secret'})
    assert r.status_code==422
    assert 'private-key' not in r.text and 'another-secret' not in r.text


def test_reference_screenshot_not_in_question_extraction(tmp_path):
    class ReferenceGateway(Gateway):
        async def extract_reference(self,images):return {'content':'本章适用条件。'}
    c=TestClient(create_app(tmp_path,lambda _:ReferenceGateway()))
    s=c.post('/api/sessions',json={}).json()
    r=c.post(f'/api/sessions/{s["id"]}/reference-upload',files={'files':('reference.png',b'\x89PNG\r\n\x1a\nabc','image/png')})
    assert r.status_code==200,r.text
    assert not r.json()['questions']
    assert r.json()['references'][0]['text']=='本章适用条件。'
    assert r.json()['attachments'][0]['reference'] is True


def test_mode_change_keeps_already_exposed_answers_and_new_default(tmp_path):
    c,g=client(tmp_path)
    s=c.post('/api/demo').json()
    sid=s['id']
    changed=c.patch(f'/api/sessions/{sid}',json={'mode':'hint'}).json()
    assert changed['questions'][2]['analysis']['answer']=='B'
    assert c.post('/api/sessions',json={}).json()['mode']=='hint'


def test_local_origin_guard_and_upload_bounds(tmp_path):
    c,g=client(tmp_path)
    assert c.post('/api/sessions',json={},headers={'origin':'https://evil.example'}).status_code==403
    s=c.post('/api/sessions',json={}).json()
    assert c.post(f'/api/sessions/{s["id"]}/upload',files={'files':('a.svg',b'<svg/>','image/svg+xml')}).status_code==400
    assert c.patch(f'/api/sessions/{s["id"]}',json={'mode':'invalid'}).status_code==422


def test_demo_is_explicit_and_isolated(tmp_path):
    c,g=client(tmp_path)
    s=c.post('/api/demo').json()
    assert s['demo'] is True and s['questions']
    assert not c.get('/api/knowledge').json()
    assert c.delete('/api/sessions/'+s['id']).status_code==200
