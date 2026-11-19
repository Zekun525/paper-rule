from __future__ import annotations

import difflib
import io
from hashlib import sha256
from pathlib import Path, PureWindowsPath
from uuid import uuid4
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from paperrule.domain.models import (
    Classification,
    FeedbackItem,
    FeedbackKind,
    Location,
    RevisionPairReference,
    SourceRecord,
)
from paperrule.persistence.store import MemoryStore

MAX_BYTES = 25 * 1024 * 1024
MAX_XML_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {'.txt', '.md', '.tex', '.pdf', '.docx'}
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
W = '{' + NS['w'] + '}'


def validate_filename(filename: str) -> str:
    if not filename or Path(filename).name != filename or PureWindowsPath(filename).name != filename:
        raise ValueError('Use a plain filename without directory components')
    if ':' in filename or '\x00' in filename or filename in {'.', '..'}:
        raise ValueError('Invalid filename')
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError('Supported files: TXT, Markdown, LaTeX, PDF, DOCX')
    return suffix


def _xml(data: bytes):
    if len(data) > MAX_XML_BYTES or b'<!DOCTYPE' in data or b'<!ENTITY' in data:
        raise ValueError('Unsafe or oversized XML part')
    return ET.fromstring(data)


def _node_text(node) -> str:
    return ''.join(item.text or '' for item in node.iter() if item.tag in {W + 't', W + 'delText'})


def _extract_docx(data: bytes) -> tuple[list[dict], list[str]]:
    records: list[dict] = []
    warnings: list[str] = []
    try:
        archive = ZipFile(io.BytesIO(data))
    except BadZipFile as exc:
        raise ValueError('The DOCX file is not a valid OOXML archive') from exc
    with archive:
        entries = archive.infolist()
        if len(entries) > 10000 or sum(entry.file_size for entry in entries) > MAX_XML_BYTES:
            raise ValueError('DOCX expanded-size limit exceeded')
        names = set(archive.namelist())
        if 'word/document.xml' not in names or '[Content_Types].xml' not in names:
            raise ValueError('DOCX is missing required OOXML parts')
        document = _xml(archive.read('word/document.xml'))
        anchors: dict[str, tuple[str, str]] = {}
        for number, paragraph in enumerate(document.findall('.//w:p', NS), 1):
            paragraph_text = _node_text(paragraph)
            location = f'paragraph-{number}'
            for marker in paragraph.findall('.//w:commentRangeStart', NS):
                anchors[marker.get(W + 'id', '')] = (location, paragraph_text)
            for tag, label in [('ins', 'insertion'), ('del', 'deletion')]:
                for revision in paragraph.findall(f'.//w:{tag}', NS):
                    records.append({
                        'quote': _node_text(revision), 'method': 'ooxml_revision',
                        'location': Location(section=location, anchor_text=paragraph_text),
                        'details': {'revision_type': label, 'author': revision.get(W + 'author', ''),
                                    'date': revision.get(W + 'date', ''),
                                    'revision_id': revision.get(W + 'id', '')},
                    })
            if paragraph_text.strip():
                records.append({'quote': paragraph_text, 'method': 'ooxml_paragraph',
                                'location': Location(section=location, anchor_text=paragraph_text)})
        comment_count = 0
        located_count = 0
        if 'word/comments.xml' in names:
            comments = _xml(archive.read('word/comments.xml'))
            for comment in comments.findall('w:comment', NS):
                comment_count += 1
                comment_id = comment.get(W + 'id', '')
                anchor = anchors.get(comment_id)
                located_count += bool(anchor)
                records.append({
                    'quote': _node_text(comment), 'method': 'ooxml_comment',
                    'location': Location(section=anchor[0], anchor_text=anchor[1]) if anchor else Location(),
                    'details': {'comment_id': comment_id, 'author': comment.get(W + 'author', ''),
                                'date': comment.get(W + 'date', ''), 'location_resolved': bool(anchor)},
                })
            if comment_count != located_count:
                warnings.append(f'Located {located_count}/{comment_count} comments; unresolved locations need manual correction.')
        unsupported = {'moveFrom', 'moveTo', 'pPrChange', 'rPrChange', 'tblPrChange', 'sectPrChange'}
        found = sorted({node.tag.removeprefix(W) for node in document.iter()
                        if node.tag.removeprefix(W) in unsupported})
        if found:
            warnings.append('Revision formats retained in the original but not interpreted: ' + ', '.join(found))
        if any(name.startswith('word/comments') and name != 'word/comments.xml' for name in names):
            warnings.append('Extended comment metadata is retained in the original; thread resolution metadata is not interpreted.')
    return records, warnings


def _extract_pdf(data: bytes, kind: FeedbackKind) -> tuple[list[dict], list[str]]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError('Install PDF support with pip install paperrule[ingest]') from exc
    records: list[dict] = []
    warnings: list[str] = []
    with pymupdf.open(stream=data, filetype='pdf') as document:
        if document.needs_pass:
            raise ValueError('Encrypted PDF requires an unlocked copy')
        for index, page in enumerate(document):
            if kind == FeedbackKind.EXEMPLAR:
                text = page.get_text()
                if text.strip():
                    records.append({'quote': text, 'method': 'pymupdf_text',
                                    'classification': Classification.EXEMPLAR,
                                    'location': Location(page=index + 1, page_index=index)})
                else:
                    warnings.append(f'Page {index + 1} has no text layer. Transcribe it manually or use an optional OCR tool.')
                continue
            for annotation in page.annots() or []:
                info = annotation.info or {}
                quote = info.get('content') or ''
                rect = annotation.rect
                vertices = annotation.vertices or []
                if vertices:
                    selected = []
                    for start in range(0, len(vertices) - 3, 4):
                        quad = pymupdf.Quad(vertices[start:start + 4])
                        selected.append(page.get_textbox(quad.rect))
                    anchor = '\n'.join(selected)
                else:
                    anchor = page.get_textbox(rect)
                records.append({
                    'quote': quote, 'method': 'pymupdf_annotation',
                    'location': Location(page=index + 1, page_index=index,
                                         bbox=list(rect), anchor_text=anchor),
                    'details': {'annotation_type': annotation.type[1], 'author': info.get('title', ''),
                                'created': info.get('creationDate', ''),
                                'modified': info.get('modDate', ''), 'vertices': vertices,
                                'needs_intent': not quote.strip()},
                })
            if not page.get_text().strip():
                warnings.append(f'Page {index + 1} has no text layer; OCR or manual transcription is required.')
    return records, warnings


def ingest_bytes(data: bytes, filename: str, store: MemoryStore, reviewer_id: str = 'author',
                 reviewer_role: str = 'author', paper_id: str | None = None,
                 source_kind: FeedbackKind | str = FeedbackKind.TEXT, intent: str = '',
                 date: str = '') -> tuple[SourceRecord, list[FeedbackItem]]:
    suffix = validate_filename(filename)
    if len(data) > MAX_BYTES:
        raise ValueError('File exceeds the 25 MiB upload limit')
    if not data:
        raise ValueError('Empty files cannot be imported')
    kind = FeedbackKind(str(source_kind).replace('-', '_'))
    if suffix == '.pdf' and kind != FeedbackKind.EXEMPLAR:
        kind = FeedbackKind.ANNOTATED_PDF
    if suffix == '.docx':
        kind = FeedbackKind.DOCX
    store.initialize()
    source_id = 'SRC-' + uuid4().hex[:12]
    attachment = f'attachments/{source_id}{suffix}'
    original = store.root / attachment
    original.write_bytes(data)
    source = SourceRecord(id=source_id, filename=filename, sha256=sha256(data).hexdigest(),
                          kind=kind, reviewer_id=reviewer_id, paper_id=paper_id, intent=intent,
                          reviewer_role=reviewer_role, date=date, attachment=attachment)
    records: list[dict] = []
    try:
        if suffix == '.pdf':
            if not data.startswith(b'%PDF-'):
                raise ValueError('PDF header does not match its extension')
            records, source.warnings = _extract_pdf(data, kind)
        elif suffix == '.docx':
            records, source.warnings = _extract_docx(data)
        else:
            text = data.decode('utf-8-sig')
            records = [{'quote': line, 'method': 'plain_text',
                        'location': Location(section=f'line-{index}', anchor_text=line)}
                       for index, line in enumerate(text.splitlines(), 1) if line.strip()]
            if kind == FeedbackKind.EXEMPLAR:
                for record in records:
                    record['classification'] = Classification.EXEMPLAR
        if not records:
            source.extraction_status = 'pending_transcription'
            source.warnings.append('No extractable feedback. The original is preserved; enter a manual transcription.')
        elif source.warnings:
            source.extraction_status = 'partial'
    except (ValueError, RuntimeError, OSError, UnicodeError, ET.ParseError) as exc:
        source.extraction_status = 'failed'
        source.warnings.append(str(exc))
        store.save_source(source)
        return source, []
    items = []
    for record in records:
        item = FeedbackItem(
            id='F-' + uuid4().hex[:12], source_id=source.id, source_kind=kind,
            reviewer_id=reviewer_id, reviewer_role=reviewer_role, paper_id=paper_id,
            quote=record['quote'], location=record.get('location', Location()),
            extraction_method=record['method'], extraction_details=record.get('details', {}),
            classification=record.get('classification', Classification.CLARIFICATION_NEEDED),
            confidence='high' if record['method'] in {'plain_text', 'ooxml_comment'} else 'medium')
        store.save_feedback(item)
        items.append(item)
    store.save_source(source)
    return source, items


def ingest_text(text: str, store: MemoryStore, **kwargs) -> list[FeedbackItem]:
    return ingest_bytes(text.encode('utf-8'), 'pasted-feedback.txt', store, **kwargs)[1]


def ingest_file(path: Path, store: MemoryStore, **kwargs) -> list[FeedbackItem]:
    path = path.resolve(strict=True)
    validate_filename(path.name)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('File exceeds the 25 MiB limit')
    return ingest_bytes(path.read_bytes(), path.name, store, **kwargs)[1]


def ingest_revision_pair(before: bytes, after: bytes, filename: str, store: MemoryStore,
                         reviewer_id: str = 'author', paper_id: str | None = None, *,
                         after_filename: str | None = None, reviewer_role: str = 'author',
                         intent: str = '', date: str = '') -> dict:
    suffix = validate_filename(filename)
    if suffix not in {'.tex', '.md', '.txt', '.docx'}:
        raise ValueError('Revision pairs support LaTeX, Markdown, text, and DOCX')
    if after_filename is not None and validate_filename(after_filename) != suffix:
        raise ValueError('Both revision files must have the same supported extension')
    if max(len(before), len(after)) > MAX_BYTES:
        raise ValueError('Revision file exceeds the size limit')

    def text(data: bytes) -> tuple[str, list[str]]:
        if suffix == '.docx':
            try:
                records, warnings = _extract_docx(data)
            except ET.ParseError as exc:
                raise ValueError('Revision DOCX contains invalid OOXML') from exc
            warnings.append(
                'Comparison uses extracted paragraph text; tracked changes are not accepted or rejected.'
            )
            return '\n'.join(
                r['quote'] for r in records if r['method'] == 'ooxml_paragraph'
            ), warnings
        return data.decode('utf-8-sig'), []

    # Validate both inputs and the generated diff before persisting any source.
    old, old_warnings = text(before)
    new, new_warnings = text(after)
    old_name = filename if after_filename is not None else 'before' + suffix
    new_name = after_filename if after_filename is not None else 'after' + suffix
    difference = '\n'.join(difflib.unified_diff(
        old.splitlines(), new.splitlines(), fromfile=old_name, tofile=new_name, lineterm='',
    ))
    diff_bytes = difference.encode('utf-8')
    if len(diff_bytes) > MAX_BYTES:
        raise ValueError('Generated revision diff exceeds the size limit')

    with store.locked():
        def persist(data: bytes, name: str, kind: FeedbackKind, warnings: list[str],
                    reference: RevisionPairReference | None = None) -> SourceRecord:
            source_id = 'SRC-' + uuid4().hex[:12]
            attachment = 'attachments/' + source_id + Path(name).suffix.lower()
            path = (store.root / attachment).resolve()
            if not path.is_relative_to(store.root):
                raise ValueError('Invalid attachment location')
            with path.open('xb') as output:
                output.write(data)
            source = SourceRecord(
                id=source_id, filename=name, sha256=sha256(data).hexdigest(), kind=kind,
                reviewer_id=reviewer_id, reviewer_role=reviewer_role, paper_id=paper_id,
                intent=intent, date=date, attachment=attachment, warnings=warnings,
                extraction_status='partial' if warnings else 'ready', revision_pair=reference,
            )
            store.save_source(source)
            return source

        original_kind = FeedbackKind.DOCX if suffix == '.docx' else FeedbackKind.TEXT
        old_source = persist(before, old_name, original_kind, old_warnings)
        new_source = persist(after, new_name, original_kind, new_warnings)
        reference = RevisionPairReference(
            before_source_id=old_source.id, after_source_id=new_source.id,
            before_sha256=old_source.sha256, after_sha256=new_source.sha256,
        )
        source = persist(
            diff_bytes, 'revision-diff.txt', FeedbackKind.REVISION_PAIR, [], reference,
        )
        items = []
        if difference:
            item = FeedbackItem(
                id='F-' + uuid4().hex[:12], source_id=source.id,
                source_kind=FeedbackKind.REVISION_PAIR, reviewer_id=reviewer_id,
                reviewer_role=reviewer_role, paper_id=paper_id, quote=difference,
                location=Location(section='revision-diff'), extraction_method='revision_diff',
                extraction_details=reference.model_dump(mode='json'),
            )
            store.save_feedback(item)
            items.append(item)
        return {
            'before_source': old_source.id, 'after_source': new_source.id,
            'diff_source': source.id, 'source': source.model_dump(mode='json'),
            'originals': [record.model_dump(mode='json') for record in (old_source, new_source)],
            'diff': difference, 'text_changed': bool(difference),
            'feedback': [item.model_dump(mode='json') for item in items],
        }


def read_revision_pair(store: MemoryStore, source_id: str) -> dict:
    with store.locked():
        sources = {source.id: source for source in store.sources()}
        source = sources.get(source_id)
        if source is None or source.kind != FeedbackKind.REVISION_PAIR or source.revision_pair is None:
            raise LookupError('Revision pair not found')
        reference = source.revision_pair
        old_source = sources.get(reference.before_source_id)
        new_source = sources.get(reference.after_source_id)
        if (old_source is None or new_source is None
                or old_source.sha256 != reference.before_sha256
                or new_source.sha256 != reference.after_sha256):
            raise ValueError('Revision source bindings no longer match')

        def checked_bytes(record: SourceRecord) -> bytes:
            path = (store.root / record.attachment).resolve()
            if not path.is_relative_to(store.root) or path.stat().st_size > MAX_BYTES:
                raise ValueError('Invalid revision attachment')
            data = path.read_bytes()
            if len(data) > MAX_BYTES or sha256(data).hexdigest() != record.sha256:
                raise ValueError('Revision attachment hash no longer matches')
            return data

        checked_bytes(old_source)
        checked_bytes(new_source)
        difference = checked_bytes(source).decode('utf-8')
        return {
            'before_source': old_source.id, 'after_source': new_source.id,
            'diff_source': source.id, 'source': source.model_dump(mode='json'),
            'originals': [record.model_dump(mode='json') for record in (old_source, new_source)],
            'diff': difference, 'text_changed': bool(difference),
            'feedback': [
                item.model_dump(mode='json') for item in store.feedback()
                if item.source_id == source.id
            ],
        }
