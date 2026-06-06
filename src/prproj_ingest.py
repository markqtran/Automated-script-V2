"""Patch .prproj files to disable broken Premiere Ingest settings."""

from __future__ import annotations

import gzip
import re
from pathlib import Path


def _read_prproj_xml(path: Path) -> bytes | None:
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(raw)
        except OSError:
            return None
    return raw


def _write_prproj_xml(path: Path, xml_bytes: bytes) -> None:
    path.write_bytes(gzip.compress(xml_bytes))


def _patch_ingest_xml(xml: str) -> str:
    """
    Turn off Premiere Ingest / transcode-on-import.

    Automation queues proxies via Media Encoder encodeFile — not Premiere Ingest.
    Saved ingest presets from another PC cause "Missing Preset" on open.
    """

    def _patch_ingest_block(match: re.Match[str]) -> str:
        block = match.group(0)
        block = re.sub(r"(<Enabled>)true(</Enabled>)", r"\1false\2", block, flags=re.I)
        block = re.sub(
            r"(<IngestEnabled>)true(</IngestEnabled>)",
            r"\1false\2",
            block,
            flags=re.I,
        )
        for tag in (
            "IngestPresetPath",
            "PresetPath",
            "PresetFile",
            "PresetName",
            "IngestPreset",
        ):
            block = re.sub(
                rf"(<{tag}>)[^<]*(</{tag}>)",
                r"\1\2",
                block,
                flags=re.I,
            )
        return block

    xml = re.sub(
        r"<IngestSettings\b[^>]*>.*?</IngestSettings>",
        _patch_ingest_block,
        xml,
        flags=re.S | re.I,
    )
    xml = re.sub(
        r"(<TranscodeOnIngest>)true(</TranscodeOnIngest>)",
        r"\1false\2",
        xml,
        flags=re.I,
    )
    xml = re.sub(
        r'EnableTranscodeOnIngest="true"',
        'EnableTranscodeOnIngest="false"',
        xml,
        flags=re.I,
    )
    xml = re.sub(
        r'IngestEnabled="true"',
        'IngestEnabled="false"',
        xml,
        flags=re.I,
    )
    xml = re.sub(
        r'(<IngestSettings\b[^>]*\bEnabled=")true(")',
        r'\1false\2',
        xml,
        flags=re.I,
    )
    return xml


def disable_premiere_ingest_settings(prproj_path: Path) -> bool:
    """
    Disable ingest in a .prproj before Premiere opens it.

    Returns True if the file was patched or already had ingest off.
    """
    if not prproj_path.is_file():
        return False

    xml_bytes = _read_prproj_xml(prproj_path)
    if not xml_bytes:
        return False

    try:
        text = xml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return False

    patched = _patch_ingest_xml(text)
    if patched == text:
        return True

    _write_prproj_xml(prproj_path, patched.encode("utf-8"))
    return True
