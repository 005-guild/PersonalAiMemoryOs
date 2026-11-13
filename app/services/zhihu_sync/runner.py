"""One bounded export operation; browser and storage are independently testable."""

from datetime import datetime, timezone
from pathlib import Path

from app.services.zhihu_sync.export import Exporter, render
from app.services.zhihu_sync.storage import Ledger, SyncError, identity_key, writer_lock


def run_collection(config, browser, cancelled, publish, *, preview=False):
    ledger = Ledger(Path(config.target_dir), config.collection_id)
    report = {'total':0, 'created':0, 'skipped':0, 'would_create':0, 'failed':0, 'unsupported':0, 'unlisted':0, 'errors':[]}

    def run():
        ledger.load()
        # Verify that the entire list is available before declaring a scan complete.
        identities = browser.collection(config.collection_url)
        unique = {identity_key(item):item for item in identities}
        report['unsupported'] = getattr(browser, 'unsupported_count', 0)
        report['unlisted'] = getattr(browser, 'unlisted_count', 0)
        report['total'] = len(unique) + report['unsupported'] + report['unlisted']
        if not preview:
            ledger.save()
        exporter = Exporter(ledger)
        for key, identity in unique.items():
            if cancelled():
                raise SyncError('cancelled')
            if key in ledger.records:
                report['skipped'] += 1
            elif preview:
                report['would_create'] += 1
            else:
                try:
                    payload = exporter.staged(identity)
                    if payload is None:
                        item = browser.article(identity)
                        payload = render(identity, item['title'], item.get('author'), item['html'],
                                         datetime.now(timezone.utc).isoformat())
                    exporter.finish(identity, payload, browser.image, cancelled)
                    report['created'] += 1
                except SyncError as error:
                    if str(error) in {'cancelled', 'login_required', 'rate_limited', 'verification_required'}:
                        raise
                    report['failed'] += 1
                    report['errors'].append({'key':key, 'code':str(error)})
                except ValueError:
                    report['failed'] += 1
                    report['errors'].append({'key':key, 'code':'source_invalid'})
            publish(dict(report))
        publish(dict(report))
        return report

    if preview:
        return run()
    with writer_lock(ledger.directory):
        return run()
