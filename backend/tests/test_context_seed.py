import importlib.util
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from conftest import HEADERS, TOKEN, text_output, call_output
from pawilot.app import create_app
from pawilot.models import RecordInput
from pawilot.store import Store

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('context_loader', ROOT/'scripts/load-personal-context.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


def document():
    return {'import_id':'sample-reviewed-v1', 'source':{'type':'user_reviewed_chat_summary','conversation':'User corrections'},
            'profile':{'name':'Sample student','about':'Engineering student; CAT 2027 then a top Indian B-school directly after college.',
                       'preferences':'First principles, practical examples','constraints':'Availability unconfirmed','timezone':'Asia/Kolkata'},
            'records':[{'kind':'goal','title':'CAT 2027 and top Indian business school','detail':'ISB, IIMs or other top Indian B-schools immediately after college.'},
                       {'kind':'memory','title':'Research interest','detail':'GEO measurement is exploratory, not a published paper.'}]}


def test_import_is_once_preserves_existing_and_does_not_resurrect_removed_context(tmp_path):
    store=Store(tmp_path/'pawilot.sqlite3')
    existing=store.put(RecordInput(kind='task',title='Keep my existing task'))
    store.message('user','Keep my conversation')
    result=loader.load_context(document(),tmp_path)
    assert result['created']==2 and Path(result['backup']).exists()
    assert store.profile()['name']=='Sample student' and len(store.records())==3
    assert store.messages()[0]['content']=='Keep my conversation'
    assert loader.load_context(document(),tmp_path)['already_imported']
    goal=next(r for r in store.records() if r['kind']=='goal')
    store.delete(goal['id'])
    store.set_setting('profile',{'name':'User correction'})
    assert loader.load_context(document(),tmp_path)['already_imported']
    assert store.profile()['name']=='User correction'
    assert len(store.records())==2
    assert any(r['id']==existing['id'] for r in store.records())


def test_invalid_seed_rolls_back_records_and_profile(tmp_path):
    original=Store(tmp_path/'pawilot.sqlite3')
    original.set_setting('profile',{'name':'Keep me'})
    data=document()
    data['records'].append({'kind':'task','title':'Bad link','goal_id':'missing'})
    with pytest.raises(ValueError): loader.load_context(data,tmp_path)
    assert original.records()==[] and original.profile()['name']=='Keep me'
    assert not original.setting('context_import:'+data['import_id'])


def test_corrected_context_to_gemini_plan_and_restart(tmp_path,vault):
    loader.load_context(document(),tmp_path)
    store=Store(tmp_path/'pawilot.sqlite3')
    goal=next(r for r in store.records() if r['kind']=='goal')
    requests=[]
    def handler(request):
        body=json.loads(request.content); requests.append(body)
        context=json.loads(body['contents'][0]['parts'][0]['text'].split('\n',1)[1])
        assert context['profile']['name']=='Sample student'
        assert 'CAT 2027' in context['profile']['about']
        assert 'ISB, IIMs' in context['goals'][0]['detail']
        assert context['profile']['constraints']=='Availability unconfirmed'
        if len(requests)==1:
            return httpx.Response(200,json=call_output('propose_plan',{'tasks':[{'kind':'task','title':'Try a short diagnostic','goal_id':goal['id'],'effort_minutes':20,'detail':'An optional CAT preparation starting point; confirm time availability.'}]}))
        return httpx.Response(200,json=text_output('For CAT 2027, try a short diagnostic. Review the proposed task.'))
    transport=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(create_app(store.path,TOKEN,vault,transport),headers=HEADERS) as client:
        assert client.put('/credentials/gemini',json={'value':'fake-test-key'}).status_code==200
        assert client.post('/chat',json={'text':'Plan my next step'}).json()['mode']=='gemini'
        assert len(store.records())==2
        action=store.actions()[0]
        approved=client.post('/actions/'+action['id']+'/decision',json={'approve':True}).json()
    with TestClient(create_app(store.path,TOKEN,vault),headers=HEADERS) as client:
        state=client.get('/state').json()
        task=next(r for r in state['records'] if r['id']==approved['result_id'])
        assert task['goal_id']==goal['id'] and state['profile']['name']=='Sample student'
        assert state['settings']['ai_enabled']
