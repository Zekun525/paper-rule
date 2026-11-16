import io
from hashlib import sha256
from zipfile import ZipFile

import pymupdf
import pytest

from paperrule.domain.models import FeedbackKind
from paperrule.ingestion.pipeline import ingest_bytes, ingest_revision_pair
from paperrule.persistence.store import MemoryStore


def test_text_keeps_original_bytes_hash_and_line_locations(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    original = b'Explain the assumption.\n\nKeep the equation.\nAsk about scope.\n'
    source, items = ingest_bytes(original, 'synthetic.txt', store, reviewer_id='synthetic-advisor')
    assert len(items) == 3
    assert source.sha256 == sha256(original).hexdigest()
    assert (store.root / source.attachment).read_bytes() == original
    assert [item.location.section for item in items] == ['line-1', 'line-3', 'line-4']
    assert {item.reviewer_id for item in items} == {'synthetic-advisor'}
    assert store.rules() == []


def test_pdf_annotations_preserve_locations_and_do_not_invent_highlight_intent(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 90), 'Synthetic evidence text for annotation testing.')
        page.add_text_annot((70, 120), 'Explain the assumption.')
        free = page.add_freetext_annot(pymupdf.Rect(70, 150, 290, 190), 'Synthetic FreeText')
        free.update()
        match = page.search_for('evidence')[0]
        annotated = page.add_highlight_annot(match)
        annotated.set_info(content='Preserve this evidence.')
        annotated.update()
        page.add_highlight_annot(page.search_for('testing')[0])
        data = document.tobytes()
    source, items = ingest_bytes(data, 'synthetic-annotated.pdf', store)
    assert source.extraction_status == 'ready'
    assert len(items) == 4
    assert all(item.location.page == 1 and len(item.location.bbox) == 4 for item in items)
    assert any(item.quote == 'Explain the assumption.' for item in items)
    silent = [item for item in items if item.extraction_details['needs_intent']]
    assert len(silent) == 1
    assert silent[0].quote == ''
    assert silent[0].classification.value == 'clarification_needed'
    assert 'testing' in silent[0].location.anchor_text


def test_pdf_without_text_is_pending_and_preserved(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    with pymupdf.open() as document:
        document.new_page()
        data = document.tobytes()
    source, items = ingest_bytes(data, 'synthetic-scan.pdf', store)
    assert items == []
    assert source.extraction_status == 'pending_transcription'
    assert source.warnings
    assert (store.root / source.attachment).read_bytes() == data


def test_exemplar_is_evidence_and_not_an_active_rule(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 90), 'Synthetic introduction: compare the assumptions before stating the contribution.')
        data = document.tobytes()
    source, items = ingest_bytes(data, 'synthetic-exemplar.pdf', store,
                                 source_kind=FeedbackKind.EXEMPLAR, intent='Study introduction structure')
    assert source.intent == 'Study introduction structure'
    assert items[0].classification.value == 'exemplar'
    assert items[0].location.page == 1
    assert store.rules() == []


def test_docx_comments_and_insertions_deletions_preserve_metadata(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    namespace = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    document = ('<w:document xmlns:w=' + '"' + namespace + '"' + '><w:body><w:p>'
                '<w:commentRangeStart w:id="0"/><w:r><w:t>Synthetic original.</w:t></w:r>'
                '<w:commentRangeEnd w:id="0"/>'
                '<w:ins w:id="1" w:author="Synthetic Author"><w:r><w:t>Added.</w:t></w:r></w:ins>'
                '<w:del w:id="2"><w:r><w:delText>Removed.</w:delText></w:r></w:del>'
                '</w:p></w:body></w:document>')
    comments = ('<w:comments xmlns:w="' + namespace + '"><w:comment w:id="0" w:author="Synthetic Reviewer">'
                '<w:p><w:r><w:t>Explain this assumption.</w:t></w:r></w:p></w:comment></w:comments>')
    buffer = io.BytesIO()
    with ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', document)
        archive.writestr('word/comments.xml', comments)
    source, items = ingest_bytes(buffer.getvalue(), 'synthetic-comments.docx', store)
    assert source.extraction_status == 'ready'
    comments_found = [item for item in items if item.extraction_method == 'ooxml_comment']
    assert len(comments_found) == 1
    assert comments_found[0].extraction_details['author'] == 'Synthetic Reviewer'
    assert comments_found[0].location.section == 'paragraph-1'
    revisions = [item for item in items if item.extraction_method == 'ooxml_revision']
    assert {item.extraction_details['revision_type'] for item in revisions} == {'insertion', 'deletion'}


def test_latex_revision_pair_does_not_normalize_formula_bytes(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    before = b'Assume $x \\le y$.\n'
    after = b'Assume $x \\le y$, by the stated condition.\n'
    result = ingest_revision_pair(before, after, 'synthetic.tex', store)
    assert '-Assume $x \\le y$.' in result['diff']
    assert '+Assume $x \\le y$, by the stated condition.' in result['diff']
    assert len(store.sources()) == 3
    assert store.rules() == []


@pytest.mark.parametrize('name', ['../outside.txt', 'C:\\outside.txt', 'nested/file.txt', 'file.txt:stream'])
def test_upload_filename_traversal_is_rejected_before_writing(tmp_path, name):
    store = MemoryStore(tmp_path / 'memory')
    with pytest.raises(ValueError):
        ingest_bytes(b'Synthetic feedback', name, store)
    assert not store.root.exists()


def test_invalid_pdf_preserves_original_and_failure_status(tmp_path):
    store = MemoryStore(tmp_path / 'memory')
    source, items = ingest_bytes(b'not a PDF', 'synthetic-invalid.pdf', store)
    assert source.extraction_status == 'failed'
    assert items == []
    assert (store.root / source.attachment).read_bytes() == b'not a PDF'
