"""Prompt CRUD, immutable revisions and built-in resources without model calls."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from app.models import PromptRevision, PromptTemplate, utcnow
from app.paths import resource_root
from app.services.content import ContentError, ContentService

DEEP_ANALYSIS_ID = "dca64f01-e2d8-52c5-9d61-ff85f71c5d12"
LEGACY_ID = "a84eef60-7b38-5683-9190-c5e31e7ca1f1"
FIELDS = ("id", "version", "name", "description", "content", "content_hash", "output_schema_version",
          "is_default", "archived_at", "created_at", "updated_at")
REVISION_FIELDS = ("version", "name", "description", "content", "content_hash", "output_schema_version", "created_at")


def content_hash(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def template_dict(template):
    return {key: getattr(template, key) for key in FIELDS}


def snapshot_template(session, template_id=None, version=None):
    template = session.get(PromptTemplate, template_id) if template_id else session.scalar(
        select(PromptTemplate).where(PromptTemplate.is_default.is_(True), PromptTemplate.archived_at.is_(None)))
    if template is None:
        raise ContentError(404, "Prompt template not found.")
    if template.archived_at is not None:
        raise ContentError(409, "An archived prompt cannot start a new generation.")
    revision = session.get(PromptRevision, (template.id, version if version is not None else template.version))
    if revision is None:
        raise ContentError(409, "Prompt revision not found; reload the template.")
    return {"id": template.id, **{key: getattr(revision, key) for key in REVISION_FIELDS}}


def _revision(session, record):
    session.flush()
    session.add(PromptRevision(template_id=record.id,
        **{key: getattr(record, key) for key in REVISION_FIELDS if key != "created_at"}))


class PromptTemplateService:
    def __init__(self, database, lock):
        self.database, self.lock = database, lock

    def ensure_builtins(self):
        with self.lock, self.database.session() as session:
            default_exists = session.scalar(select(PromptTemplate.id).where(PromptTemplate.is_default.is_(True)))
            for identifier, filename, name, schema in (
                (DEEP_ANALYSIS_ID, "zhihu_deep_analysis_v1.md", "知乎观点深度解析 · 八阶段", 2),
                (LEGACY_ID, "knowledge_v1.md", "基础知识提取 · 兼容 v1", 1)):
                if session.get(PromptTemplate, identifier) is not None:
                    continue
                content = (resource_root() / "app/prompts" / filename).read_text(encoding="utf-8")
                record = PromptTemplate(id=identifier, name=name, description="项目内置模板，可复制和版本化编辑。",
                    content=content, content_hash=content_hash(content), output_schema_version=schema,
                    is_default=identifier == DEEP_ANALYSIS_ID and not default_exists)
                session.add(record)
                _revision(session, record)
            session.commit()

    def list(self, *, include_archived=False, offset=0, limit=20):
        self.ensure_builtins()
        with self.lock, self.database.session() as session:
            where = [] if include_archived else [PromptTemplate.archived_at.is_(None)]
            total = session.scalar(select(func.count()).select_from(PromptTemplate).where(*where))
            rows = session.scalars(select(PromptTemplate).where(*where).order_by(
                PromptTemplate.is_default.desc(), PromptTemplate.created_at, PromptTemplate.id).offset(offset).limit(limit))
            return {"items": [template_dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}

    def get(self, identifier):
        self.ensure_builtins()
        with self.lock, self.database.session() as session:
            return template_dict(self._require(session, identifier))

    @staticmethod
    def _require(session, identifier):
        record = session.get(PromptTemplate, identifier)
        if record is None:
            raise ContentError(404, "Prompt template not found.")
        return record

    def create(self, values):
        self.ensure_builtins()
        with self.lock, self.database.session() as session:
            record = PromptTemplate(**values, content_hash=content_hash(values["content"]))
            session.add(record)
            _revision(session, record)
            session.commit()
            return template_dict(record)

    def change(self, identifier, expected_version, values=None, *, action=None):
        self.ensure_builtins()
        try:
            with self.lock, self.database.session() as session:
                record = self._require(session, identifier)
                ContentService.require_version(record, expected_version)
                if record.archived_at is not None:
                    raise ContentError(409, "Archived prompts cannot be edited or selected as default; copy one instead.")
                if action == "archive":
                    if record.is_default:
                        raise ContentError(409, "Select another default before archiving this prompt.")
                    record.archived_at = utcnow()
                elif action == "default":
                    if record.is_default:
                        return template_dict(record)
                    for previous in session.scalars(select(PromptTemplate).where(PromptTemplate.is_default.is_(True))):
                        previous.is_default = False
                        _revision(session, previous)
                    record.is_default = True
                else:
                    for key, value in (values or {}).items():
                        setattr(record, key, value)
                    record.content_hash = content_hash(record.content)
                record.updated_at = utcnow()
                _revision(session, record)
                session.commit()
                return template_dict(record)
        except StaleDataError:
            raise ContentError(409, "The prompt changed; reload its current version.") from None

    def revisions(self, identifier):
        with self.lock, self.database.session() as session:
            self._require(session, identifier)
            rows = session.scalars(select(PromptRevision).where(PromptRevision.template_id == identifier)
                                   .order_by(PromptRevision.version.desc()))
            return {"items": [{key: getattr(row, key) for key in REVISION_FIELDS} for row in rows]}
