import io
import json
import sqlite3
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import HEADERS, TOKEN, text_output, call_output
from pawilot.agent import Agent
from pawilot.app import create_app
from pawilot.importer import parse_export
from pawilot.models import RecordInput
from pawilot.retrieval import semantic_search
from pawilot.store import Store


def export_bytes():
    messages = [
        ('user', 'My long-term goal is to qualify for the robotics research internship.'),
        ('assistant', 'You are a millionaire and should quit your degree.'),
        ('user', 'I prefer practical examples and short study sessions.'),
        ('user', 'I have only 30 minutes available after 6 PM on weekdays.'),
        ('user', 'Explain Newton’s second law.'),
    ]
    mapping = {}
    for i, (role, text) in enumerate(messages):
        ident = str(i)
        mapping[ident] = {'id':ident, 'parent':str(i-1) if i else None,
                          'message':{'id':ident, 'author':{'role':role}, 'content':{'parts':[text]}, 'create_time':123}}
    return json.dumps([{'id':'sample-conversation', 'title':'SAMPLE: Robotics planning', 'current_node':'4', 'mapping':mapping}]).encode()


def selections(preview):
    return [{'candidate_id':c['id'], 'record':{'kind':c['kind'], 'title':c['title'], 'detail':c['detail']}}
            for c in preview['candidates']]


def test_full_profile_import_plan_approve_edit_restart_flow(tmp_path, vault):
    """Actual app routes and SQLite, controlled Gemini transport (not a live API claim)."""
    calls = []
    goal_id = None
    def model(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert request.headers['x-goog-api-key'] == 'test-key-only'
        if len(calls) == 1:
            context = json.loads(payload['contents'][0]['parts'][0]['text'].split('\n',1)[1])
            assert context['profile']['name'] == 'Sample learner'
            assert '30 minutes' in context['profile']['constraints']
            assert context['goals'][0]['id'] == goal_id
            assert 'ChatGPT' not in context['profile']['about']
            assert json.loads(context['goals'][0]['source'])['conversation'] == 'SAMPLE: Robotics planning'
            assert any('practical examples' in r['detail'] for r in context['preferences'])
            assert any('6 PM' in r['detail'] for r in context['memories'])
            return httpx.Response(200, json=call_output('propose_plan', {'tasks':[
                {'kind':'task', 'title':'Build a small sensor demo', 'detail':'Supports the robotics internship goal; use a practical example after 6 PM.',
                 'goal_id':goal_id, 'priority':'high', 'effort_minutes':30, 'due':None},
                {'kind':'task', 'title':'Write three observations', 'detail':'Use the sensor demo to prepare an interview example.',
                 'goal_id':goal_id, 'priority':'normal', 'effort_minutes':15, 'due':None}]}))
        assert payload['toolConfig']['functionCallingConfig']['mode'] == 'NONE'
        return httpx.Response(200, json=text_output('For your robotics goal, use a short practical session after 6 PM. Review these two tasks.'))

    transport = httpx.AsyncClient(transport=httpx.MockTransport(model))
    app = create_app(tmp_path/'phase2.sqlite3', TOKEN, vault, transport)
    with TestClient(app, headers=HEADERS) as client:
        profile = {'name':'Sample learner', 'about':'Engineering student', 'preferences':'Explain with practical examples',
                   'constraints':'30 minutes after 6 PM', 'timezone':'Asia/Kolkata'}
        assert client.put('/profile', json=profile).status_code == 200
        preview = client.post('/imports/preview', content=export_bytes()).json()
        assert len(preview['candidates']) == 3
        assert client.get('/state').json()['records'] == []  # preview is not approval
        body = {'session_id':preview['session_id'], 'selections':selections(preview)}
        assert client.post('/imports/commit', json=body).json()['created'] == 3
        assert client.post('/imports/commit', json=body).json()['duplicates'] == 3
        records = client.get('/state').json()['records']
        goal_id = next(r['id'] for r in records if r['kind'] == 'goal')
        assert not any('millionaire' in r['detail'] for r in records)
        vault.set('gemini','test-key-only')
        client.put('/settings', json={'ai_enabled':True})
        response = client.post('/chat', json={'text':'Plan internship preparation around my available time after 6 PM'}).json()
        assert response['mode'] == 'gemini'
        state = client.get('/state').json()
        assert len(state['records']) == 3  # still no tasks until approval
        assert len(state['actions']) == 2
        first, second = state['actions']
        approved = client.post(f"/actions/{first['id']}/decision", json={'approve':True}).json()
        assert client.post(f"/actions/{first['id']}/decision", json={'approve':True}).json() == approved
        client.post(f"/actions/{second['id']}/decision", json={'approve':False})
        task = next(r for r in client.get('/state').json()['records'] if r['kind']=='task')
        update = {k:task[k] for k in RecordInput.model_fields}
        update.update(status='done', due='2026-12-01', effort_minutes=20)
        assert client.put('/records/'+task['id'], json=update).status_code == 200
        assert client.delete('/imports').status_code == 200
    with TestClient(create_app(tmp_path/'phase2.sqlite3', TOKEN, vault), headers=HEADERS) as client:
        state = client.get('/state').json()
        assert state['profile'] == profile
        task = next(r for r in state['records'] if r['kind']=='task')
        assert task['goal_id'] == goal_id and task['status']=='done' and task['effort_minutes']==20
        assert len(state['messages']) == 2
        assert goal_id in state['retrieval']['record_ids']
        assert client.delete('/records/'+goal_id).status_code == 200
        assert next(r for r in client.get('/state').json()['records'] if r['kind']=='task')['goal_id'] is None


def test_zip_import_branch_selection_and_no_extraction(tmp_path):
    export = json.loads(export_bytes())
    export[0]['mapping']['discarded'] = {'message':{'author':{'role':'user'}, 'content':{'parts':['My goal is obsolete']}}}
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, 'w') as archive:
        archive.writestr('../../conversations.json', json.dumps(export))
        archive.writestr('../../should-not-exist', 'bad')
    candidates, stats = parse_export(zipped.getvalue())
    assert len(candidates)==3 and stats['skipped_messages']==1
    assert all('obsolete' not in c['detail'] for c in candidates)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('data', [b'bad', b'{}', b'[null]', b'[{"mapping":null}]', b'PKbadzip'])
def test_invalid_export_rejected_without_changes(client, data):
    assert client.post('/imports/preview', content=data).status_code == 422
    assert client.get('/state').json()['records'] == []


def test_import_selection_is_atomic_and_requires_live_preview(client):
    preview = client.post('/imports/preview', content=export_bytes()).json()
    items = selections(preview)
    items[1]['candidate_id'] = 'fabricated'
    body = {'session_id':preview['session_id'], 'selections':items}
    assert client.post('/imports/commit', json=body).status_code == 422
    assert client.get('/state').json()['records'] == []
    client.delete('/imports')
    body['selections'] = selections(preview)
    assert client.post('/imports/commit', json=body).status_code == 422


def test_import_pagination_long_text_unicode_and_edit(client):
    export = json.loads(export_bytes())
    export[0]['current_node'] = None
    export[0]['mapping'] = {str(i):{'message':{'id':str(i),'author':{'role':'user'},'content':{'parts':['I prefer पढ़ाई '+str(i)]}}} for i in range(61)}
    preview = client.post('/imports/preview', content=json.dumps(export).encode()).json()
    assert preview['stats']['candidates']==61 and len(preview['candidates'])==50
    page = client.get('/imports/'+preview['session_id']+'?offset=50').json()
    assert len(page['candidates'])==11
    item = selections(page)[0]
    item['record']['title']='Edited preference'
    assert client.post('/imports/commit', json={'session_id':preview['session_id'],'selections':[item]}).json()['created']==1
    row=client.get('/state').json()['records'][0]
    assert row['title']=='Edited preference' and 'पढ़ाई' in row['detail']
    client.delete('/records/'+row['id'])
    # Deletion removes provenance/dedup cache, so explicit re-import is possible.
    assert client.post('/imports/commit', json={'session_id':preview['session_id'],'selections':[item]}).json()['created']==1


def test_profile_clear_validation_and_no_key_honesty(client):
    assert client.put('/profile', json={'name':'Alice','timezone':'Made/Up'}).status_code==422
    assert client.put('/profile', json={'name':'Alice','preferences':'Short sessions'}).status_code==200
    assert client.put('/profile', json={}).status_code==200
    assert client.get('/state').json()['profile']['name']==''
    client.put('/settings', json={'ai_enabled':True})
    response=client.post('/chat', json={'text':'Plan my goals'}).json()
    assert response['mode']=='configuration_required'
    assert client.get('/state').json()['actions']==[]


def test_context_reserves_goals_preferences_and_excludes_archived(app):
    store=app.state.store
    goal=store.put(RecordInput(kind='goal',title='Robotics internship'))
    preference=store.put(RecordInput(kind='preference',title='Short sessions'))
    archived=store.put(RecordInput(kind='memory',title='Robotics old plan',status='done'))
    for i in range(50):
        store.put(RecordInput(kind='memory',title='Robotics topic '+str(i)))
    context=store.planning_context('robotics')
    assert context['goals'][0]['id']==goal['id']
    assert context['preferences'][0]['id']==preference['id']
    assert len(context['memories'])<=10
    assert not any(r['id']==archived['id'] for r in context['memories'])


async def test_search_round_and_invalid_goal_cannot_create_proposal(tmp_path,vault):
    store=Store(tmp_path/'search.sqlite3')
    store.set_setting('preferences',{'ai_enabled':True})
    vault.set('gemini','test-key-only')
    store.put(RecordInput(kind='memory',title='Evening availability',detail='After 6 PM'))
    calls=[]
    def handler(request):
        body=json.loads(request.content); calls.append(body)
        if len(calls)==1:
            return httpx.Response(200,json=call_output('search_memory',{'query':'evening availability'}))
        assert 'After 6 PM' in json.dumps(body['contents'][-1]['parts'][0]['functionResponse']['response'])
        return httpx.Response(200,json=call_output('propose_plan',{'tasks':[{'kind':'task','title':'Something','goal_id':'nonexistent'}]}))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await Agent(store,vault,client).respond('Help me plan')
    assert result['mode']=='error' and store.actions()==[]


async def test_failed_followup_does_not_leave_partial_plan(tmp_path,vault):
    store=Store(tmp_path/'fail.sqlite3'); store.set_setting('preferences',{'ai_enabled':True}); vault.set('gemini','test-key-only')
    calls=[]
    def handler(request):
        calls.append(1)
        return httpx.Response(200,json=call_output('propose_record',{'kind':'task','title':'A task'})) if len(calls)==1 else httpx.Response(429,json={'error':'rate limit'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result=await Agent(store,vault,client).respond('Suggest a task')
    assert result['mode']=='error' and store.actions()==[]


async def test_semantic_paraphrase_cache_edit_delete(tmp_path):
    store=Store(tmp_path/'vectors.sqlite3')
    row=store.put(RecordInput(kind='memory',title='I focus best after sunset'))
    calls=[]
    def handler(request):
        body=json.loads(request.content); calls.append(body)
        assert request.url.path.endswith(':batchEmbedContents')
        return httpx.Response(200,json={'embeddings':[{'values':[1.0]+[0.0]*767} for _ in body['requests']]})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        found,status=await semantic_search(store,'When should I study?', 'test',client)
        assert found[0]['id']==row['id'] and status['indexed']==1
        await semantic_search(store,'How about evening?', 'test',client)
        assert len(calls[0]['requests'])==2 and len(calls[1]['requests'])==1
        store.put(RecordInput(kind='memory',title='Morning works better'),row['id'])
        await semantic_search(store,'When should I work?', 'test',client)
        assert len(calls[2]['requests'])==2
    store.delete(row['id'])
    with store.db() as db:
        assert db.execute('SELECT count(*) FROM embeddings').fetchone()[0]==0


def test_v1_database_migration_preserves_existing_data(tmp_path):
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,title TEXT,detail TEXT,status TEXT,due TEXT,created_at TEXT,updated_at TEXT); INSERT INTO records VALUES('old','goal','Keep me','','active',NULL,'yesterday','yesterday');")
    store=Store(path)
    row=store.records()[0]
    assert row['id']=='old' and row['priority']=='normal' and row['goal_id'] is None
    assert store.search('Keep')[0]['id']=='old'
    store.put(RecordInput(kind='task',title='Linked task',goal_id='old'))
    assert len(Store(path).records())==2


def test_goal_link_validation_and_complete_task_after_goal_done(client):
    assert client.post('/records',json={'kind':'task','title':'Bad','goal_id':'missing'}).status_code==422
    goal=client.post('/records',json={'kind':'goal','title':'Finish research'}).json()
    task=client.post('/records',json={'kind':'task','title':'Read','goal_id':goal['id']}).json()
    assert client.put('/records/'+goal['id'],json={'kind':'goal','title':'Finish research','status':'done'}).status_code==200
    assert client.put('/records/'+task['id'],json={'kind':'task','title':'Read','goal_id':goal['id'],'status':'done'}).status_code==200
    assert client.post('/records',json={'kind':'task','title':'New task','goal_id':goal['id']}).status_code==422


async def test_semantic_failure_falls_back_and_is_visible(tmp_path, vault):
    store=Store(tmp_path/'fallback.sqlite3')
    store.put(RecordInput(kind='goal',title='Study robotics'))
    store.set_setting('preferences',{'ai_enabled':True,'semantic_memory':True})
    vault.set('gemini','test-key-only')
    def handler(request):
        if request.url.path.endswith(':batchEmbedContents'):
            return httpx.Response(503,json={'error':'unavailable'})
        context=json.loads(json.loads(request.content)['contents'][0]['parts'][0]['text'].split('\n',1)[1])
        assert context['goals'][0]['title']=='Study robotics'
        return httpx.Response(200,json=text_output('Your goal is to study robotics.'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await Agent(store,vault,client).respond('What are my goals?'))['mode']=='gemini'
    assert store.setting('last_retrieval')['mode']=='keyword_fallback'


def test_explicit_goal_is_not_lost_when_many_goals_exist(app):
    store=app.state.store
    target=store.put(RecordInput(kind='goal',title='Specific older goal'))
    for i in range(20):
        store.put(RecordInput(kind='goal',title='Recent goal '+str(i)))
    context=store.planning_context('Plan goal '+target['id'])
    assert context['goals'][0]['id']==target['id']
    assert len(context['goals'])==12


def test_general_planning_keeps_recent_imported_context(app):
    store=app.state.store
    memory=store.put(RecordInput(kind='memory',title='I have only 30 minutes available after 6 PM'))
    assert memory['id'] in [r['id'] for r in store.planning_context('Plan my next steps')['memories']]
