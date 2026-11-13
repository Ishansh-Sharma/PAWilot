"""Optional semantic ranking with locally cached embeddings; lexical fallback remains usable."""
import hashlib
import json
import math

import httpx

MODEL = 'gemini-embedding-001'


def record_text(row):
    return row['kind'] + ': ' + row['title'] + '\n' + row['detail']


async def semantic_search(store, query, key, client=None):
    rows = [r for r in store.records() if r['status'] == 'active']
    if not rows:
        return [], {'mode':'semantic', 'indexed':0, 'total':0}
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False)
    try:
        with store.db() as db:
            cache = {r['record_id']:dict(r) for r in db.execute('SELECT * FROM embeddings WHERE model=?', (MODEL,))}
        digests = {r['id']:hashlib.sha256(record_text(r).encode()).hexdigest() for r in rows}
        missing = [r for r in rows if r['id'] not in cache or cache[r['id']]['digest'] != digests[r['id']]][:64]
        texts = [record_text(r) for r in missing] + [query]
        response = await client.post('https://generativelanguage.googleapis.com/v1beta/models/'+MODEL+':batchEmbedContents',
                                     headers={'x-goog-api-key':key},
                                     json={'requests':[{'model':'models/'+MODEL,
                                            'content':{'parts':[{'text':text}]}, 'outputDimensionality':768,
                                            'taskType':'RETRIEVAL_QUERY' if i == len(texts)-1 else 'RETRIEVAL_DOCUMENT'}
                                            for i,text in enumerate(texts)]})
        response.raise_for_status()
        data = response.json()['embeddings']
        if len(data) != len(texts):
            raise ValueError('Incomplete embedding response')
        vectors = [v['values'] for v in data]
        if any(len(v) != 768 or not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v) for v in vectors):
            raise ValueError('Invalid embedding response')
        with store.db() as db:
            for row, vector in zip(missing, vectors):
                # Records may have been edited/deleted during the request; never cache stale text.
                current = db.execute('SELECT * FROM records WHERE id=?', (row['id'],)).fetchone()
                if current is None or hashlib.sha256(record_text(current).encode()).hexdigest() != digests[row['id']]:
                    continue
                db.execute('INSERT OR REPLACE INTO embeddings VALUES(?,?,?,?)',
                           (row['id'], digests[row['id']], MODEL, json.dumps(vector)))
                cache[row['id']] = {'digest':digests[row['id']], 'vector':json.dumps(vector)}
        query_vector = vectors[-1]
        def cosine(vector):
            denom = math.sqrt(sum(x*x for x in query_vector)*sum(x*x for x in vector))
            return sum(a*b for a,b in zip(query_vector, vector))/denom if denom else 0
        scored = [(cosine(json.loads(cache[r['id']]['vector'])), r) for r in rows
                  if r['id'] in cache and cache[r['id']]['digest'] == digests[r['id']]]
        scored.sort(key=lambda x:x[0], reverse=True)
        return [r for score,r in scored[:8] if score > 0.15], {'mode':'semantic', 'indexed':len(scored), 'total':len(rows)}
    finally:
        if own_client:
            await client.aclose()
