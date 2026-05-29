import pytest
from pathlib import Path
import tempfile
import zipfile
from app.utils.files import validate_file_signature, detect_file_kind, detect_mime_type, _validate_docx_archive, get_extension
from app.modules.materials.enums import FileKind
from app.core.exceptions import ValidationAppError


def test_get_extension():
    assert get_extension("foo.png") == "png"
    assert get_extension("foo.BAR") == "bar"

def test_detect_file_kind_and_mime():
    assert detect_file_kind("png") == FileKind.IMAGE
    assert detect_file_kind("pdf") == FileKind.DOCUMENT
    assert detect_file_kind("unknown") == FileKind.OTHER
    
    assert detect_mime_type("png") == "image/png"
    assert detect_mime_type("unknown") == "application/octet-stream"

def test_validate_signature_unsupported():
    with pytest.raises(ValidationAppError, match="Unsupported file type"):
        validate_file_signature("xyz", b"123", Path("dummy"))

def test_validate_signature_jpg():
    with pytest.raises(ValidationAppError, match="not match JPEG"):
        validate_file_signature("jpg", b"123", Path("dummy"))
    kind, mime = validate_file_signature("jpg", b"\xff\xd8\xff", Path("dummy"))
    assert kind == FileKind.IMAGE
    assert mime == "image/jpeg"

def test_validate_signature_png():
    with pytest.raises(ValidationAppError, match="not match PNG"):
        validate_file_signature("png", b"123", Path("dummy"))
    kind, mime = validate_file_signature("png", b"\x89PNG\r\n\x1a\n", Path("dummy"))
    assert kind == FileKind.IMAGE
    assert mime == "image/png"

def test_validate_signature_webp():
    with pytest.raises(ValidationAppError, match="not match WEBP"):
        validate_file_signature("webp", b"123", Path("dummy"))
    kind, mime = validate_file_signature("webp", b"RIFF1234WEBP", Path("dummy"))
    assert kind == FileKind.IMAGE
    assert mime == "image/webp"

def test_validate_signature_pdf():
    with pytest.raises(ValidationAppError, match="not match PDF"):
        validate_file_signature("pdf", b"123", Path("dummy"))
    kind, mime = validate_file_signature("pdf", b"%PDF-1.4", Path("dummy"))
    assert kind == FileKind.DOCUMENT
    assert mime == "application/pdf"

def test_validate_signature_djvu():
    with pytest.raises(ValidationAppError, match="not match DJVU"):
        validate_file_signature("djvu", b"123", Path("dummy"))
    kind, mime = validate_file_signature("djvu", b"AT&TFORM123", Path("dummy"))
    assert kind == FileKind.DOCUMENT
    assert mime == "image/vnd.djvu"

def test_validate_signature_docx_invalid_sig():
    with pytest.raises(ValidationAppError, match="not match DOCX"):
        validate_file_signature("docx", b"123", Path("dummy"))

def test_validate_signature_docx_bad_zip():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"not a zip")
        tmp.flush()
        with pytest.raises(ValidationAppError, match="Invalid DOCX file"):
            _validate_docx_archive(Path(tmp.name))

def test_validate_signature_docx_missing_members():
    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(tmp.name, 'w') as z:
            z.writestr("dummy.txt", b"hello")
        
        with pytest.raises(ValidationAppError, match="not a valid DOCX document"):
            _validate_docx_archive(Path(tmp.name))

def test_validate_signature_docx_valid():
    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(tmp.name, 'w') as z:
            z.writestr("[Content_Types].xml", b"hello")
            z.writestr("word/document.xml", b"hello")
        
        # Calling validate_file_signature which internally calls _validate_docx_archive
        kind, mime = validate_file_signature("docx", b"PK\x03\x04", Path(tmp.name))
        assert kind == FileKind.DOCUMENT
        assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_validate_signature_pptx():
    with pytest.raises(ValidationAppError, match="not match PPTX"):
        validate_file_signature("pptx", b"123", Path("dummy"))

    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(tmp.name, 'w') as z:
            z.writestr("[Content_Types].xml", b"hello")
            z.writestr("ppt/presentation.xml", b"hello")
        
        kind, mime = validate_file_signature("pptx", b"PK\x03\x04", Path(tmp.name))
        assert kind == FileKind.DOCUMENT
        assert mime == "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def test_validate_signature_ppt():
    with pytest.raises(ValidationAppError, match="not match PPT signature"):
        validate_file_signature("ppt", b"123", Path("dummy"))

    kind, mime = validate_file_signature("ppt", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", Path("dummy"))
    assert kind == FileKind.DOCUMENT
    assert mime == "application/vnd.ms-powerpoint"


def test_validate_signature_xlsx():
    with pytest.raises(ValidationAppError, match="not match XLSX"):
        validate_file_signature("xlsx", b"123", Path("dummy"))

    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(tmp.name, 'w') as z:
            z.writestr("[Content_Types].xml", b"hello")
            z.writestr("xl/workbook.xml", b"hello")
        kind, mime = validate_file_signature("xlsx", b"PK\x03\x04", Path(tmp.name))
        assert kind == FileKind.DOCUMENT
        assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_validate_signature_xls():
    with pytest.raises(ValidationAppError, match="not match XLS signature"):
        validate_file_signature("xls", b"123", Path("dummy"))

    kind, mime = validate_file_signature("xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", Path("dummy"))
    assert kind == FileKind.DOCUMENT
    assert mime == "application/vnd.ms-excel"


def test_validate_signature_epub():
    with pytest.raises(ValidationAppError, match="not match EPUB"):
        validate_file_signature("epub", b"123", Path("dummy"))

    with tempfile.NamedTemporaryFile() as tmp:
        with zipfile.ZipFile(tmp.name, 'w') as z:
            z.writestr("mimetype", b"application/epub+zip")
            z.writestr("META-INF/container.xml", b"hello")
        kind, mime = validate_file_signature("epub", b"PK\x03\x04", Path(tmp.name))
        assert kind == FileKind.DOCUMENT
        assert mime == "application/epub+zip"


def test_validate_signature_ipynb():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"not json")
        tmp.flush()
        with pytest.raises(ValidationAppError, match="Invalid Jupyter Notebook"):
            validate_file_signature("ipynb", b"", Path(tmp.name))

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b'{"foo": "bar"}')
        tmp.flush()
        with pytest.raises(ValidationAppError, match="not a valid Jupyter Notebook"):
            validate_file_signature("ipynb", b"", Path(tmp.name))

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b'{"cells": [], "metadata": {}}')
        tmp.flush()
        kind, mime = validate_file_signature("ipynb", b"", Path(tmp.name))
        assert kind == FileKind.DOCUMENT
        assert mime == "application/x-ipynb+json"


def test_validate_signature_txt():
    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"\xff\xfe\x00\x00invalid_utf8")
        tmp.flush()
        with pytest.raises(ValidationAppError, match="must be valid UTF-8"):
            validate_file_signature("txt", b"", Path(tmp.name))

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(b"hello world")
        tmp.flush()
        kind, mime = validate_file_signature("txt", b"", Path(tmp.name))
        assert kind == FileKind.DOCUMENT
        assert mime == "text/plain"


def test_validate_signature_audio_video():
    with pytest.raises(ValidationAppError, match="not match MP3"):
        validate_file_signature("mp3", b"123", Path("dummy"))

    kind, mime = validate_file_signature("mp3", b"ID312345", Path("dummy"))
    assert kind == FileKind.OTHER
    assert mime == "audio/mpeg"

    with pytest.raises(ValidationAppError, match="not match MP4"):
        validate_file_signature("mp4", b"1234567890", Path("dummy"))

    kind, mime = validate_file_signature("mp4", b"\x00\x00\x00\x18ftypmp42", Path("dummy"))
    assert kind == FileKind.OTHER
    assert mime == "video/mp4"
