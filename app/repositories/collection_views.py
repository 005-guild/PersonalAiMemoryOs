"""Shared eligibility and literal keyword rules for collection read views."""

ELIGIBLE = ("o.status='published' AND o.error IS NULL AND o.exported_version=k.version "
            "AND k.deleted_at IS NULL AND (s.status IS NULL OR s.status NOT IN ('conflict','error'))")
INDEXED_FROM = (' FROM organization_fts CROSS JOIN organization_items o ON o.id=organization_fts.item_id '
                'CROSS JOIN knowledge k ON k.id=o.knowledge_id '
                'LEFT JOIN sync_states s ON s.knowledge_id=k.id')


def keyword_condition(query, params):
    """Keep the FTS scan outermost, including short escaped LIKE queries."""
    if len(query) >= 3:
        params['match'] = '"' + query.replace('"', '""') + '"'
        return ' AND organization_fts MATCH :match'
    if query:
        params['q'] = '%' + query.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
        return (" AND (organization_fts.title LIKE :q ESCAPE '!' OR organization_fts.summary LIKE :q ESCAPE '!'"
                " OR organization_fts.original LIKE :q ESCAPE '!' OR organization_fts.tags LIKE :q ESCAPE '!')")
    return ''
