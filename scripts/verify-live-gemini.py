"""Live Phase 2 acceptance check. Uses only synthetic data and a saved Paw API key.

Run explicitly after saving a key in Paw. Makes paid Gemini/embedding requests.
No keys are printed, written to disk, or passed in process arguments.
"""
import asyncio
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from pawilot.agent import Agent
from pawilot.importer import parse_export
from pawilot.models import ImportSelection, RecordInput
from pawilot.store import Store
from pawilot.vault import KeychainVault

ROOT = Path(__file__).resolve().parents[1]


async def main():
    vault = KeychainVault()
    if not vault.get('gemini'):
        print('NOT VERIFIED: no Gemini API key saved in Paw. Add it through Settings, then rerun this check.')
        return 2
    with tempfile.TemporaryDirectory(prefix='pawilot-live-') as directory:
        store = Store(Path(directory)/'acceptance.sqlite3')
        store.set_setting('profile', {'name':'Sample learner', 'about':'Engineering student',
                                     'preferences':'Use practical examples', 'constraints':'Only 30 minutes after 6 PM',
                                     'timezone':'Asia/Kolkata'})
        candidates, _ = parse_export((ROOT/'fixtures/sample-chatgpt-export.json').read_bytes())
        store.import_records([ImportSelection(candidate_id=c['id'], record=RecordInput(kind=c['kind'],title=c['title'],detail=c['detail'])) for c in candidates], {c['id']:c for c in candidates})
        # Use the model chosen in the real app, if configured.
        import sqlite3
        settings_path = Path.home()/'Library/Application Support/PAWilot/pawilot.sqlite3'
        model = 'gemini-3.8-flash'
        if settings_path.exists():
            with sqlite3.connect(settings_path.as_uri()+'?mode=ro',uri=True) as db:
                row=db.execute("SELECT value FROM settings WHERE key='preferences'").fetchone()
                if row:
                    model=json.loads(row[0]).get('model',model)
        if not model.startswith('gemini-'):
            model='gemini-3.8-flash'
        store.set_setting('preferences', {'model':model, 'ai_enabled':True, 'semantic_memory':True})
        agent = Agent(store, vault)
        reply = await agent.respond('Plan exactly two concrete tasks for my saved robotics internship goal. Use my preferences and time constraints; each session must fit 30 minutes. Call propose_plan so I can review both tasks.')
        if reply['mode'] != 'gemini':
            print('NOT VERIFIED: live request failed. Check model access, billing and network in Paw settings.')
            return 2
        proposals = store.actions()
        goals = {r['id'] for r in store.records() if r['kind']=='goal'}
        assert len(proposals)==2, 'Expected two reviewable task proposals'
        assert all(a['payload']['kind']=='task' and a['payload']['goal_id'] in goals and 5<=a['payload']['effort_minutes']<=30 for a in proposals)
        assert not any(r['kind']=='task' for r in store.records()), 'Tasks must wait for approval'
        store.decide(proposals[0]['id'],True)
        store.decide(proposals[1]['id'],False)
        restarted=Store(store.path)
        assert len([r for r in restarted.records() if r['kind']=='task'])==1
        assert restarted.profile()['name']=='Sample learner'
        followup=await Agent(restarted,vault).respond('What is my goal, what planning preferences do you remember, and which task did I approve? Do not create new tasks.')
        assert followup['mode']=='gemini'
        print('LIVE RESPONSE (synthetic data):\n'+reply['message'])
        print('RECALL RESPONSE (synthetic data):\n'+followup['message'])
        print('PASS: live Gemini → goal-linked task proposals → approve/reject → restart → recall. Review response wording above for grounding.')
        print('Retrieval: '+store.setting('last_retrieval',{}).get('mode','unknown'))
    return 0


if __name__=='__main__':
    raise SystemExit(asyncio.run(main()))
