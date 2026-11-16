"""Compatibility entry points for the evidence-preserving ingestion pipeline."""

from paperrule.ingestion.pipeline import ingest_file, ingest_text

__all__ = ["ingest_file", "ingest_text"]
