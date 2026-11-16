import base64

from fastapi.testclient import TestClient

from paperrule.api.app import create_app


def test_import_create_discuss_approve_history_through_api(tmp_path):
    client = TestClient(create_app(tmp_path / 'memory'))
    imported = client.post('/api/sources', json={
        'filename': 'synthetic.txt',
        'content_base64': base64.b64encode(b'Explain each implication.').decode(),
    })
    assert imported.status_code == 200
    feedback_id = imported.json()['feedback'][0]['id']
    assert len(client.get('/api/sources').json()) == 1
    created = client.post('/api/proposals', json={
        'rule': {'id': 'G-API', 'short_title': 'Synthetic clarity',
                 'statement': 'Explain each implication.', 'source_feedback_ids': [feedback_id]},
        'feedback_ids': [feedback_id],
    })
    assert created.status_code == 200
    proposal = created.json()
    proposal_id = proposal['proposal_id']
    discussed = client.post(f'/api/proposals/{proposal_id}/chat', json={'message': 'Agree'})
    assert discussed.status_code == 200
    assert client.get('/api/rules').json() == []
    stale = client.post(f'/api/proposals/{proposal_id}/approve',
                        json={'proposal_hash': proposal['proposal_hash']})
    assert stale.status_code == 409
    approved_hash = discussed.json()['proposal_hash']
    approved = client.post(f'/api/proposals/{proposal_id}/approve',
                           json={'proposal_hash': approved_hash})
    assert approved.status_code == 200
    assert client.get('/api/rules/G-API/history').json()[0]['version'] == 1
    duplicate = client.post(f'/api/proposals/{proposal_id}/approve',
                            json={'proposal_hash': approved_hash})
    assert duplicate.status_code == 200
    assert duplicate.json()[1] == 'already-applied'


def test_import_rejects_traversal_and_invalid_base64(tmp_path):
    client = TestClient(create_app(tmp_path / 'memory'))
    bad_path = client.post('/api/sources', json={
        'filename': '../outside.txt',
        'content_base64': base64.b64encode(b'Synthetic feedback').decode(),
    })
    assert bad_path.status_code == 400
    bad_encoding = client.post('/api/sources', json={
        'filename': 'synthetic.txt', 'content_base64': '%%%invalid',
    })
    assert bad_encoding.status_code == 422
    assert client.get('/api/sources').json() == []
