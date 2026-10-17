"""Source-only import with per-item transactions and conservative deduplication."""

from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from app.repositories.imports import ImportRepository
from app.services.content import ContentService
from app.services.import_types import (
    ImportItemResult, ImportReport, ImportUnavailable, ParsedZhihuItem,
)
from app.services.zhihu_parser import normalize_zhihu_url

COMPARABLE_FIELDS = ("title", "author", "content")


def differences(existing, incoming: dict) -> list[str]:
    return [field for field in COMPARABLE_FIELDS
            if getattr(existing, field) != incoming.get(field)]


class ImportService:
    def __init__(self, database, lock) -> None:
        self.database, self.lock = database, lock

    def run(self, entries: list[ParsedZhihuItem | ImportItemResult], *, dry_run: bool = False) -> ImportReport:
        report = ImportReport(dry_run=dry_run, total=len(entries))
        simulated: dict[tuple[str, str], dict] = {}
        for entry in entries:
            if isinstance(entry, ImportItemResult):
                report.add(entry)
                continue
            try:
                result = self._item(entry, dry_run, simulated)
            except (SQLAlchemyError, RuntimeError):
                # Earlier items were committed separately and are safe to report.
                report.add(self._result(entry, "failed", "database_unavailable"))
                raise ImportUnavailable(report) from None
            report.add(result)
        return report

    def _item(self, entry: ParsedZhihuItem, dry_run: bool, simulated: dict) -> ImportItemResult:
        key = (entry.resource_type, entry.external_id)
        if dry_run and key in simulated:
            previous = simulated[key]
            return self._result(
                entry, "skipped", "duplicate_in_batch",
                differing_fields=[field for field in COMPARABLE_FIELDS
                                  if previous.get(field) != entry.values.get(field)],
            )
        # Only one small lookup/write unit holds the app's shared lock. Parsing
        # the document has already finished, and no vault or network IO occurs.
        with self.lock:
            try:
                with self.database.session() as session:
                    repository = ImportRepository(session)
                    existing = self._existing(repository, entry)
                    if existing is not None:
                        return existing
                    if dry_run:
                        simulated[key] = dict(entry.values)
                        return self._result(entry, "would_create", "new_source")
                    source = ContentService(session).create_source(dict(entry.values))
                    repository.add_origin(source_id=source["id"], resource_type=entry.resource_type,
                                          external_id=entry.external_id)
                    session.commit()
                    return self._result(entry, "created", "new_source",
                                        source_id=source["id"], version=source["version"])
            except IntegrityError:
                # Closing the failed session rolls back BOTH the new Source and
                # its origin. A competing writer may now own the unique key.
                with self.database.session() as session:
                    existing = self._existing(ImportRepository(session), entry)
                    if existing is not None:
                        return existing
                raise

    def _existing(self, repository: ImportRepository, entry: ParsedZhihuItem) -> ImportItemResult | None:
        origin = repository.origin(entry.resource_type, entry.external_id)
        if origin is not None:
            source = repository.source(origin.source_id)
            if source is None:
                raise RuntimeError("Import identity references a missing Source.")
            return self._result(
                entry, "skipped", "deleted_source" if source.deleted_at is not None else "already_imported",
                source_id=source.id, version=source.version,
                differing_fields=differences(source, entry.values),
            )
        matches = []
        for source_id, url in repository.unmapped_urls(entry.resource_type, entry.external_id):
            try:
                identity = normalize_zhihu_url(url)
            except ValueError:
                continue
            if (identity.resource_type, identity.external_id) == (entry.resource_type, entry.external_id):
                matches.append(source_id)
        if len(matches) > 1:
            return self._result(entry, "skipped", "ambiguous_legacy_match",
                                matched_source_ids=matches)
        if matches:
            source = repository.source(matches[0])
            if source is None:
                raise RuntimeError("A matching Source disappeared during import.")
            return self._result(
                entry, "skipped", "legacy_deleted" if source.deleted_at is not None else "legacy_match",
                source_id=source.id, version=source.version, matched_source_ids=matches,
                differing_fields=differences(source, entry.values),
            )
        return None

    @staticmethod
    def _result(entry: ParsedZhihuItem, status: str, reason: str, **values) -> ImportItemResult:
        return ImportItemResult(index=entry.index, status=status, reason=reason,
                                resource_type=entry.resource_type, external_id=entry.external_id,
                                **values)
