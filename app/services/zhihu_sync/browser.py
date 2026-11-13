"""Browser-backed collection access; login challenges always require the user."""

import json
from pathlib import Path
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.paths import resource_root
from app.services.zhihu_parser import normalize_zhihu_url
from app.services.zhihu_sync.export import image_url
from app.services.zhihu_sync.collection_pages import CollectionPages
from app.services.zhihu_sync.collection_content import collection_body
from app.services.zhihu_sync.storage import SyncError, safe_path


class ZhihuBrowser:
    collection_rows = ('.CollectionsDetailPage-list .CollectionDetailPageItem:not(.PlaceHolder), '
                       '.CollectionsDetailPage-list .List-item:not(.PlaceHolder)')

    def __init__(self, root, *, visible=False, cancelled=lambda:False):
        self.root, self.visible, self.cancelled = Path(root), visible, cancelled
        self.manager = self.context = None
        self.unsupported_count = 0
        self.unlisted_count = 0
        self.collection_contents = {}

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
            self.manager = sync_playwright().start()
            # Packaged builds ship their own matching browser; development uses its cache.
            base = resource_root()
            import playwright
            manifest = Path(playwright.__file__).parent / 'driver/package/browsers.json'
            revision = next(item['revision'] for item in json.loads(manifest.read_text())['browsers'] if item['name']=='chromium')
            relative = f'chromium-{revision}/chrome-win64/chrome.exe'
            candidates = [base / 'browsers' / relative, base / '.cache/playwright' / relative]
            executable = next((path for path in candidates if path.is_file()), None)
            options = {'executable_path':str(executable)} if executable else {}
            profile = safe_path(self.root / 'data/zhihu-sync/browser-profile')
            self.context = self.manager.chromium.launch_persistent_context(str(profile),
                headless=not self.visible, locale='zh-CN', viewport={'width':1280,'height':900}, **options)
            self.context.set_default_timeout(15000)
            self.page = self.context.pages[0]
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise SyncError('browser_unavailable') from None

    def __exit__(self, *_):
        try:
            if self.context:
                self.context.close()
        finally:
            if self.manager:
                self.manager.stop()

    def check_cancelled(self):
        if self.cancelled():
            raise SyncError('cancelled')

    def _access(self):
        self.check_cancelled()
        text = self.page.locator('body').inner_text()
        if (self.page.locator('.Captcha, .Captcha-englishContainer, .Unhuman').count()
                or (len(text) < 2000 and any(value in text for value in ('安全验证', '请完成验证', '访问异常', '异常请求')))):
            raise SyncError('verification_required')
        if '/signin' in self.page.url or '请登录后查看' in text:
            raise SyncError('login_required')

    def _goto(self, url):
        self.check_cancelled()
        try:
            response = self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            if response and response.status == 429:
                raise SyncError('rate_limited')
            if response and response.status in {401,403}:
                raise SyncError('verification_required')
            if response and response.status >= 400:
                raise SyncError('source_unavailable')
        except SyncError:
            raise
        except Exception:
            raise SyncError('network_error') from None

    def login(self, collection_url):
        self._goto(collection_url)
        # User clicks login and completes any authentication in this visible window.
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            self.check_cancelled()
            if self.page.is_closed():
                raise SyncError('cancelled')
            try:
                self._access()
                if self.page.locator(self.collection_rows).count():
                    return
                data = self._initial_state()
                if data.get('currentUser') and self._count(data, collection_url) == 0:
                    return
            except SyncError as error:
                if str(error) not in {'login_required','verification_required','page_structure_changed'}:
                    raise
            self.page.wait_for_timeout(1000)
        raise SyncError('login_required')

    def _initial_state(self):
        try:
            raw = self.page.locator('script#js-initialData').text_content()
            return json.loads(raw)['initialState']
        except Exception:
            raise SyncError('page_structure_changed') from None

    @staticmethod
    def _count(data, url):
        try:
            value = data['entities']['favlists'][url.rstrip('/').rsplit('/',1)[-1]]['itemCount']
            if type(value) is not int or value < 0:
                raise ValueError()
            return value
        except (TypeError, KeyError, ValueError):
            raise SyncError('page_structure_changed') from None

    def collection(self, url):
        pages = CollectionPages(url.rstrip('/').rsplit('/', 1)[-1])
        self.page.on('response', pages.observe)
        try:
            return self._collection(url, pages)
        finally:
            self.page.remove_listener('response', pages.observe)

    def _collection(self, url, pages):
        self._goto(url)
        self._access()
        expected = self._count(self._initial_state(), url)
        seen, page_signatures = {}, set()
        unsupported = set()
        while True:
            self._access()
            if expected:
                try:
                    self.page.locator(self.collection_rows).first.wait_for()
                except Exception:
                    self._access()
                    raise SyncError('page_structure_changed') from None
            html = self.page.locator('.CollectionsDetailPage-list').inner_html()
            soup = BeautifulSoup(html, 'html.parser')
            page_keys = []
            for row in soup.select('.CollectionDetailPageItem:not(.PlaceHolder), .List-item:not(.PlaceHolder)'):
                identity = None
                for link in row.select('a[href]'):
                    try:
                        identity = normalize_zhihu_url(urljoin(url,link['href']))
                        break
                    except ValueError:
                        pass
                if identity is None:
                    video = row.select_one('a[href*="/zvideo/"], a[href*="/video/"]')
                    if video:
                        unsupported.add(video['href'])
                        page_keys.append(('unsupported', video['href']))
                        continue
                    raise SyncError('unsupported_collection_item')
                key = (identity.resource_type, identity.external_id)
                page_keys.append(key)
                seen[key] = identity
            signature = tuple(page_keys)
            if signature in page_signatures:
                raise SyncError('pagination_stalled')
            page_signatures.add(signature)
            following = self.page.get_by_role('button', name='下一页', exact=True)
            if not following.count() or not following.is_enabled():
                break
            self.check_cancelled()
            following.click()
            self.page.wait_for_timeout(2500)
        self.unlisted_count = 0
        if len(seen) + len(unsupported) != expected:
            self.unlisted_count = pages.unlisted(expected, seen, len(unsupported))
        self.unsupported_count = len(unsupported)
        self.collection_contents = pages.contents
        return list(seen.values())

    def article(self, identity):
        cached = self.collection_contents.get((identity.resource_type, identity.external_id))
        if cached is not None:
            body = collection_body(cached, identity)
            if body is not None:
                return body
        self.page.wait_for_timeout(2000)
        self._goto(identity.canonical_url)
        self._access()
        selector = {'answer':'.AnswerItem', 'article':'.Post-Main', 'pin':'.PinItem'}[identity.resource_type]
        container = self.page.locator(selector).first
        try:
            container.wait_for()
            expand = container.get_by_role('button', name='阅读全文', exact=False)
            if expand.count() and expand.first.is_visible():
                expand.first.click()
            html = container.inner_html()
        except Exception:
            self._access()
            raise SyncError('page_structure_changed') from None
        soup = BeautifulSoup(html, 'html.parser')
        if soup.select('.PaidContent, .PurchaseButton'):
            raise SyncError('source_incomplete')
        body = soup.select_one('.RichContent-inner .RichText, .Post-RichText, .PinItem-content .RichText')
        if body is None:
            raise SyncError('page_structure_changed')
        if identity.resource_type == 'answer':
            title = self.page.locator('.QuestionHeader-title').inner_text()
        elif identity.resource_type == 'article':
            title = self.page.locator('.Post-Title').inner_text()
        else:
            title = body.get_text(' ',strip=True)[:100] or '知乎想法 ' + identity.external_id
        author = soup.select_one('.AuthorInfo-name')
        return {'title':title.strip(), 'author':author.get_text(strip=True) if author else None, 'html':str(body)}

    def image(self, url):
        self.check_cancelled()
        try:
            # Validate every redirect before sending a request, never send cookies to arbitrary hosts.
            for _ in range(5):
                url = image_url(url)
                response = self.context.request.get(url, timeout=30000, max_redirects=0)
                try:
                    if response.status in {301,302,303,307,308}:
                        url = urljoin(url,response.headers.get('location',''))
                        continue
                    if response.status == 429:
                        raise SyncError('rate_limited')
                    if response.status != 200 or not response.headers.get('content-type','').startswith('image/'):
                        raise SyncError('image_unavailable')
                    if int(response.headers.get('content-length','0')) > 20 * 1024 * 1024:
                        raise SyncError('image_invalid')
                    return response.body()
                finally:
                    response.dispose()
            raise SyncError('image_redirect_limit')
        except SyncError:
            raise
        except Exception:
            raise SyncError('network_error') from None
