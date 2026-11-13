"""Local, review-first ChatGPT JSON/ZIP import. Never execute or extract archive paths."""
import hashlib
import io
import json
import re
import time
import zipfile
from uuid import uuid4

MAX_UPLOAD = 32 * 1024 * 1024
MAX_JSON = 64 * 1024 * 1024
PERSONAL = re.compile(r"\b(i am|i'm|my |i prefer|i want|i need|i plan|i hope|i work|i study|i like|i dislike|i have|i struggle|i can|i cannot|i don't|remember|always|never|please use|please keep)\b", re.I)


def parse_export(data):
    if len(data) > MAX_UPLOAD:
        raise ValueError("Export exceeds 32 MB. Use a smaller conversations.json file.")
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                files = [f for f in archive.infolist() if f.filename.replace('\\', '/').split('/')[-1] == 'conversations.json']
                if len(files) != 1:
                    raise ValueError("ZIP must contain exactly one conversations.json file")
                member = files[0]
                if member.file_size > MAX_JSON:
                    raise ValueError("conversations.json exceeds the 64 MB expanded limit")
                with archive.open(member) as stream:
                    data = stream.read(MAX_JSON + 1)
                if len(data) > MAX_JSON:
                    raise ValueError("Expanded export is too large")
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError):
            raise ValueError("Cannot read this ZIP. Use an unencrypted ChatGPT export.")
    try:
        conversations = json.loads(data.decode('utf-8-sig'))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise ValueError("Expected a ChatGPT conversations.json file or export ZIP")
    if isinstance(conversations, dict):
        conversations = conversations.get('conversations')
    if not isinstance(conversations, list) or not all(isinstance(c, dict) for c in conversations):
        raise ValueError("Expected a list of ChatGPT conversations")
    if len(conversations) > 20000:
        raise ValueError("Export has over 20,000 conversations; split it into smaller files")
    candidates, seen = [], set()
    messages = skipped = malformed = 0
    for conversation in conversations:
        mapping = conversation.get('mapping')
        if not isinstance(mapping, dict):
            malformed += 1
            continue
        nodes = list(mapping.values())
        current = conversation.get('current_node')
        if isinstance(current, str) and current in mapping:
            branch, visited = [], set()
            while isinstance(current, str) and current in mapping and current not in visited:
                visited.add(current)
                node = mapping[current]
                if not isinstance(node, dict):
                    break
                branch.append(node)
                current = node.get('parent')
            nodes = list(reversed(branch))
        for node in nodes:
            if not isinstance(node, dict):
                continue
            message = node.get('message')
            if not isinstance(message, dict) or not isinstance(message.get('author'), dict) or message['author'].get('role') != 'user':
                continue
            if not isinstance(message.get('content'), dict):
                continue
            parts = message['content'].get('parts', [])
            if not isinstance(parts, list):
                continue
            content = '\n'.join(p for p in parts if isinstance(p, str)).strip()
            if not content:
                continue
            messages += 1
            # Keep exact user text rather than treating assistant suggestions as user facts.
            if not PERSONAL.search(content):
                skipped += 1
                continue
            cid = str(conversation.get('id') or conversation.get('conversation_id') or '')
            mid = str(message.get('id') or node.get('id') or '')
            # Split long text without losing its contents; each chunk is explicitly reviewed.
            for offset in range(0, len(content), 3500):
                excerpt = content[offset:offset+3500]
                fingerprint = hashlib.sha256((cid+'\0'+mid+'\0'+excerpt).encode()).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                lower = excerpt.lower()
                kind = 'preference' if re.search(r'\b(prefer|always|never|like|dislike)\b', lower) else 'memory'
                if re.search(r'\b(my goal|i want to|i plan to|i hope to|long.term goal)\b', lower):
                    kind = 'goal'
                source = json.dumps({'type':'chatgpt_export', 'conversation':str(conversation.get('title') or 'Untitled')[:300],
                                     'conversation_id':cid[:100], 'message_id':mid[:100], 'created_at':str(message.get('create_time') or '')[:50]})
                candidates.append({'id':fingerprint, 'kind':kind, 'title':excerpt.split('\n')[0][:180],
                                   'detail':excerpt, 'source':source})
                if len(candidates) > 10000:
                    raise ValueError("More than 10,000 candidate passages. Split this export before importing.")
    if conversations and malformed == len(conversations):
        raise ValueError("No supported conversation mappings found in this file")
    return candidates, {'conversations':len(conversations), 'user_messages':messages,
                        'skipped_messages':skipped, 'unsupported_conversations':malformed,
                        'candidates':len(candidates)}


class ImportSessions:
    """One transient preview per app; discarded on cancellation, replacement, expiry or restart."""
    def __init__(self):
        self.session = None

    def preview(self, data):
        candidates, stats = parse_export(data)
        self.session = {'id':str(uuid4()), 'time':time.monotonic(),
                        'candidates':candidates, 'stats':stats}
        return self.page(self.session['id'], 0)

    def get(self, ident):
        if not self.session or self.session['id'] != ident or time.monotonic()-self.session['time'] > 3600:
            self.session = None
            raise ValueError("Import preview expired; load the export again")
        return self.session

    def page(self, ident, offset):
        session = self.get(ident)
        return {'session_id':ident, 'stats':session['stats'], 'offset':offset,
                'candidates':session['candidates'][offset:offset+50]}

    def cancel(self):
        self.session = None
