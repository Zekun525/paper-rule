import base64
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient as RawTestClient
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.persistence.store import MemoryStore

BEFORE = br'Assume $x \le y$.' + b'\r\n'
AFTER = br'Assume $x \le y$, under the stated condition.' + b'\r\n'


def body(**updates):
    value = {
        'before_filename': 'synthetic-before.tex',
        'after_filename': 'synthetic-after.tex',
        'before_content_base64': base64.b64encode(BEFORE).decode('ascii'),
        'after_content_base64': base64.b64encode(AFTER).decode('ascii'),
        'reviewer_id': 'synthetic-reviewer',
        'reviewer_role': 'collaborator',
        'intent': 'Compare the synthetic assumption clarification.',
        'date': '2026-11-19',
    }
    return value | updates


def test_revision_api_preserves_originals_bindings_and_governance(tmp_path):
    root = tmp_path / 'memory'
    store = MemoryStore(root)
    client = TestClient(create_app(root))
    commit = client.get('/api/sync').json().get('commit')
    response = client.post('/api/revision-pairs', json=body())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['text_changed'] is True
    assert r'-Assume $x \le y$.' in result['diff']
    assert r'+Assume $x \le y$, under the stated condition.' in result['diff']
    assert len(result['feedback']) == 1
    item = result['feedback'][0]
    assert item['quote'] == result['diff']
    assert item['classification'] == 'clarification_needed'
    assert item['reviewer_role'] == 'collaborator'
    assert item['extraction_method'] == 'revision_diff'
    sources = {source.id: source for source in store.sources()}
    assert len(sources) == 3
    for source_id, original in ((result['before_source'], BEFORE), (result['after_source'], AFTER)):
        source = sources[source_id]
        assert (root / source.attachment).read_bytes() == original
        assert source.sha256 == sha256(original).hexdigest()
        assert source.date == '2026-11-19'
        assert source.reviewer_role == 'collaborator'
    reference = result['source']['revision_pair']
    assert reference['before_source_id'] == result['before_source']
    assert reference['after_source_id'] == result['after_source']
    assert reference['before_sha256'] == sha256(BEFORE).hexdigest()
    assert reference['after_sha256'] == sha256(AFTER).hexdigest()
    restarted = TestClient(create_app(root))
    restored = restarted.get('/api/revision-pairs/' + result['diff_source'])
    assert restored.status_code == 200
    assert restored.json() == result
    assert store.rules() == []
    assert store.proposals() == []
    assert list((root / 'decisions').glob('*.json')) == []
    assert client.get('/api/sync').json().get('commit') == commit


@pytest.mark.parametrize('updates, expected', [
    ({'before_filename': '../outside.tex'}, 400),
    ({'after_filename': 'C:/outside.tex'}, 400),
    ({'after_filename': 'synthetic-after.tex:stream'}, 400),
    ({'after_filename': 'synthetic-after.md'}, 400),
    ({'before_filename': 'synthetic.pdf', 'after_filename': 'synthetic-new.pdf'}, 400),
    ({'before_content_base64': 'not base64!'}, 422),
    ({'after_content_base64': '/w=='}, 400),
    ({'paper_id': 'missing-synthetic-paper'}, 404),
    ({'unexpected': 'untrusted extra field'}, 422),
])
def test_invalid_revision_inputs_do_not_persist_partial_sources(tmp_path, updates, expected):
    root = tmp_path / 'memory'
    client = TestClient(create_app(root))
    response = client.post('/api/revision-pairs', json=body(**updates))
    assert response.status_code == expected
    store = MemoryStore(root)
    assert store.sources() == []
    assert store.feedback() == []
    assert list((root / 'attachments').iterdir()) == []


def test_unchanged_revision_has_no_invented_feedback(tmp_path):
    root = tmp_path / 'memory'
    client = TestClient(create_app(root))
    response = client.post('/api/revision-pairs', json=body(
        after_content_base64=base64.b64encode(BEFORE).decode('ascii'),
    ))
    assert response.status_code == 200
    result = response.json()
    assert result['diff'] == ''
    assert result['text_changed'] is False
    assert result['feedback'] == []
    assert MemoryStore(root).feedback() == []
    assert client.get('/api/revision-pairs/' + result['diff_source']).json() == result


def test_empty_before_revision_supports_a_new_fragment(tmp_path):
    client = TestClient(create_app(tmp_path / 'memory'))
    result = client.post('/api/revision-pairs', json=body(before_content_base64=''))
    assert result.status_code == 200
    assert '+Assume' in result.json()['diff']


def test_tampered_revision_attachment_is_not_presented_as_verified(tmp_path):
    root = tmp_path / 'memory'
    client = TestClient(create_app(root))
    result = client.post('/api/revision-pairs', json=body()).json()
    source = next(source for source in MemoryStore(root).sources()
                  if source.id == result['after_source'])
    (root / source.attachment).write_bytes(b'Synthetic tampering.')
    response = client.get('/api/revision-pairs/' + result['diff_source'])
    assert response.status_code == 409
    assert response.json() == {'detail': 'Persisted revision evidence failed validation'}


def test_revision_import_requires_owner_access(tmp_path):
    root = tmp_path / 'memory'
    client = RawTestClient(
        create_app(root), base_url='http://127.0.0.1', client=('127.0.0.1', 50000),
    )
    assert client.post('/api/revision-pairs', json=body()).status_code == 401
    assert MemoryStore(root).sources() == []


def test_regular_source_import_preserves_supplied_date_and_role(tmp_path):
    root = tmp_path / 'memory'
    client = TestClient(create_app(root))
    response = client.post('/api/sources', json={
        'filename': 'synthetic-dated-feedback.txt',
        'content_base64': base64.b64encode(b'Synthetic dated feedback.').decode('ascii'),
        'reviewer_id': 'synthetic-advisor', 'reviewer_role': 'advisor', 'date': '2026-11-19',
    })
    assert response.status_code == 200
    source = response.json()['source']
    assert source['date'] == '2026-11-19'
    assert source['reviewer_role'] == 'advisor'
    assert MemoryStore(root).sources()[0].date == '2026-11-19'
    assert MemoryStore(root).feedback()[0].reviewer_role == 'advisor'
    assert MemoryStore(root).rules() == []
    assert MemoryStore(root).proposals() == []
