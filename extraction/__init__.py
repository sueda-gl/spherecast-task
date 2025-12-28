"""
Extraction module for document processing with verification.

This module provides failsafe extraction using a two-phase approach:
1. Extractor LLM: Reads document and extracts data
2. Verifier LLM: Checks extraction against original document
"""

from .extract_and_verify import ExtractAndVerify

__all__ = ['ExtractAndVerify']

