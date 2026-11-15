"""Synthetic bookshelf fixtures and shared real-browser checks; no model calls."""

from io import BytesIO
import hashlib
import json
from pathlib import Path
from threading import RLock
from PIL import Image, ImageDraw
from playwright.sync_api import expect
from sqlalchemy import select
from app.models import OrganizationControl, OrganizationItem, Knowledge
from app.repositories.database import Database
from app.repositories.migrations import upgrade_database
from app.services.content import ContentService
from app.services.organization.publication import Publication, body
from app.services.organization.store import Store, defaults


def seed(root, settings):
    upgrade_database(settings.database_url)
    database = Database(settings.database_url); database.initialize()
    source = root / 'articles'; output = root / 'organized'
    source.mkdir(parents=True); (output / 'assets').mkdir(parents=True)
    images = []
    for number, color in enumerate(['#557a5a', '#9e8253', '#758c9a'], 1):
        image = Image.new('RGB', (560, 320), color)
        draw = ImageDraw.Draw(image); draw.rectangle((30, 30, 530, 290), outline='white', width=3)
        draw.text((80, 140), 'LOCAL READING IMAGE ' + str(number), fill='white', font_size=30)
        stream = BytesIO(); image.save(stream, format='PNG'); content = stream.getvalue()
        digest = hashlib.sha256(content).hexdigest(); name = f'photo-{number}.png'
        (source / name).write_bytes(content); (output / 'assets' / (digest + '.png')).write_bytes(content)
        images.append({'reference': name, 'hash': digest, 'relative_path': name})
    store = Store(database, RLock(), root)
    config = {**defaults()['config'], 'input_dir': str(source), 'output_dir': str(output)}
    identifiers = []
    with store.transaction() as session:
        session.add(OrganizationControl(id=1, value={**defaults(), 'config': config, 'paused': True}))
        content = ContentService(session)
        for number in range(1, 36):
            original = ('仅原文命中标记。完整的原始论据。\n\n' + '\n'.join(f'![图 {i}](photo-{i}.png)' for i in range(1, 4))) if number == 1 else f'这是原文 {number}。原文专用标记。'
            values = {'title': f'原始题目 {number}', 'author': '合成作者', 'url': f'https://zhuanlan.zhihu.com/p/{number}', 'content': original, 'source_type': 'zhihu'}
            snapshot = {'values': values, 'images': images if number == 1 else [], 'resource_type': 'article', 'external_id': str(number), 'body_chars': len(original), 'text_chars': len(original)}
            source_note = content.create_source(values)
            summary = {'title': '长文与配图阅读验收' if number == 1 else f'收藏文章 {number:02d}',
                'summary': '从已有收藏出发，保留原文依据和实际适用条件。', 'category': '技术/数据库' if number <= 22 else '生活/日常',
                'tags': ['实践', '共同'] if number <= 22 else ['生活'], 'points': ['保留原始资料。', '结合证据阅读。'],
                'conditions': '这是离线验收数据。', 'quotes': ['完整的原始论据。'] if number == 1 else []}
            original_body = original
            for image in images:
                original_body = original_body.replace(image['reference'], '/api/v1/collection-organization/assets/' + image['hash'] + '.png')
            rendered = body(snapshot, summary, original_body)
            if number == 1:
                # More than the editor's 100k preview limit, with real Markdown block boundaries.
                long_text = '\n\n'.join(f'### 阅读段落 {index}\n' + '长文中的完整段落需要逐步阅读，保留全部内容。' * 16 for index in range(350))
                rendered = rendered.replace('## 原文', long_text + '\n\n长文末尾验收标记。\n\n## 原文', 1)
                rendered += '\n\n<script>window.readingInjected=true</script>\n[危险链接](javascript:alert(1))\n![远程图](https://invalid.example/p.png)'
            note = content.create_knowledge({'source_ids': [source_note['id']], 'title': summary['title'], 'summary': summary['summary'],
                'category': summary['category'], 'tags': summary['tags'], 'concepts': [], 'body': rendered})
            session.get(Knowledge, note['id']).updated_at = f'2026-11-{1+(35-number)//2:02d}T12:00:00+00:00'
            item = OrganizationItem(identity=f'article:{number}', snapshot=snapshot, input_hash=hashlib.sha256(original.encode()).hexdigest(),
                source_id=source_note['id'], knowledge_id=note['id'], result={**summary, 'title': '旧模型标题不应覆盖当前笔记'}, status='ready')
            session.add(item); session.flush(); identifiers.append((item.id, note['id']))
    publication = Publication(store)
    for item_id, _ in identifiers: publication.export(item_id, config)
    database.dispose()
    return identifiers[0][1]


def browser_checks(page, url, identifier, evidence):
    errors, mutations, external = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def request(request):
        if request.url.startswith(url) and request.method not in {'GET', 'HEAD'}: mutations.append(request.url)
        if not request.url.startswith((url, 'data:', 'about:')): external.append(request.url)
    page.on('request', request)
    page.goto(url + '/#/reading')
    expect(page.get_by_role('heading', name='收藏之后，慢慢读。')).to_be_visible()
    expect(page.locator('.reading-card')).to_have_count(12)
    assert 'null' not in page.locator('.reading-root').inner_text()
    page.screenshot(path=str(evidence / 'home.png'), full_page=True)
    page.locator('.reading-topic').filter(has_text='技术').click()
    expect(page.get_by_role('heading', name='找到 22 篇文章')).to_be_visible()
    expect(page.locator('.reading-card')).to_have_count(20)
    page.get_by_role('button', name='下一页', exact=True).click()
    expect(page.locator('.reading-card')).to_have_count(2)
    page.locator('.reading-note-link').first.click()
    expect(page.get_by_role('tab', name='整理笔记', exact=True)).to_be_visible()
    page.get_by_role('link', name='← 返回阅读列表').click()
    expect(page.locator('.reading-card')).to_have_count(2)
    expect(page.get_by_text('第 2 / 2 页', exact=True)).to_be_visible()
    page.get_by_role('button', name='清除筛选', exact=True).click()
    expect(page.get_by_role('heading', name='找到 35 篇文章')).to_be_visible()
    page.locator('.reading-note-link').nth(10).scroll_into_view_if_needed()
    saved_scroll = page.evaluate('window.scrollY')
    page.locator('.reading-note-link').nth(10).click()
    expect(page.get_by_role('tab', name='整理笔记', exact=True)).to_be_visible()
    page.get_by_role('link', name='← 返回阅读列表').click()
    expect(page.locator('.reading-card')).to_have_count(20)
    page.wait_for_function('(expected) => Math.abs(window.scrollY-expected)<5', arg=saved_scroll)
    page.get_by_label('关键词', exact=True).fill('原文专用标记')
    expect(page.get_by_role('heading', name='找到 34 篇文章')).to_be_visible()
    expect(page.locator('.reading-excerpt mark').first).to_be_visible()
    page.get_by_label('关键词', exact=True).fill('不存在的测试词')
    expect(page.get_by_role('heading', name='没有符合条件的文章')).to_be_visible()
    page.goto(url + '/#/reading/' + identifier)
    expect(page.get_by_role('heading', name='长文与配图阅读验收', exact=True)).to_be_visible()
    assert page.locator('script').evaluate_all('(items)=>items.some(x=>x.textContent.includes("readingInjected"))') is False
    assert not page.evaluate('Boolean(window.readingInjected)')
    while page.locator('#reading-note-panel .reading-more:visible').count():
        page.locator('#reading-note-panel .reading-more:visible').first.click()
    expect(page.get_by_text('长文末尾验收标记。', exact=True)).to_be_visible()
    assert page.locator('.reading-prose a[href^="javascript:"]').count() == 0
    page.get_by_role('tab', name='整理时原文', exact=True).click()
    expect(page.get_by_role('heading', name='原始题目 1', exact=True)).to_be_visible()
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(evidence / 'original.png'), full_page=True)
    page.get_by_role('tab', name='整理时原文', exact=True).focus()
    page.keyboard.press('ArrowLeft')
    expect(page.get_by_role('tab', name='整理笔记', exact=True)).to_have_attribute('aria-selected', 'true')
    page.keyboard.press('ArrowRight')
    expect(page.get_by_role('tab', name='整理时原文', exact=True)).to_have_attribute('aria-selected', 'true')
    page.locator('.reading-thumbnail').first.click()
    expect(page.get_by_role('dialog', name='原图预览')).to_be_visible()
    page.keyboard.press('ArrowRight'); expect(page.locator('.reading-gallery-dialog>p')).to_have_text('第 2 / 3 张')
    page.get_by_role('button', name='原尺寸', exact=True).click()
    expect(page.get_by_role('button', name='适合窗口', exact=True)).to_have_attribute('aria-pressed', 'true')
    page.screenshot(path=str(evidence / 'gallery.png'))
    page.keyboard.press('Escape'); expect(page.get_by_role('dialog', name='原图预览')).not_to_be_visible()
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url + '/#/reading/browse')
    expect(page.locator('.reading-card')).to_have_count(20)
    page.wait_for_function('() => document.querySelector("#sidebar").getBoundingClientRect().right <= 1')
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(evidence / 'narrow.png'), animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
    assert not errors, errors
    assert not mutations, mutations
    assert not external, external
    return ['overview', 'topics', 'paging_return', 'scroll_restore', 'keyboard_tabs', 'keyword_excerpt', 'empty_results', 'long_complete',
            'original_snapshot', 'gallery_keyboard_zoom', 'narrow_layout', 'sanitization', 'zero_mutations', 'zero_external_requests']
