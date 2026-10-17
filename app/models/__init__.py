"""Persistence models; importing them never opens a database or creates tables."""

from app.models.base import Base, new_id, utcnow
from app.models.content import Knowledge, KnowledgeSource, Source
from app.models.imports import SourceOrigin
from app.models.processing import ProcessingRun
from app.models.prompts import PromptRevision, PromptTemplate
from app.models.batches import ProcessingBatch, ProcessingBatchItem
from app.models.rag import RagIndexGeneration, RagIndexJob, RagNoteIndexState
from app.models.sync import SyncConflict, SyncOperation, SyncState, SyncVault

__all__ = [
    "Base", "Knowledge", "KnowledgeSource", "Source", "SyncConflict", "SyncOperation", "SyncState",
    "SyncVault", "SourceOrigin", "ProcessingRun", "RagIndexGeneration", "RagIndexJob",
    "RagNoteIndexState", "new_id", "utcnow", "PromptTemplate", "PromptRevision",
    "ProcessingBatch", "ProcessingBatchItem",
]
