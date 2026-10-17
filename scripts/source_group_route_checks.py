"""Exercise hash changes before router cleanup, without an application router."""


def check_route_races_and_types(page, api, evidence):
    page.route('**/__source-route-check', lambda route: route.fulfill(
        content_type='text/html;charset=utf-8',
        body='<!doctype html><div id="main"></div><div id="toasts"></div>'))
    page.goto(page.url.split('#', 1)[0] + '__source-route-check')
    result = page.evaluate('''async () => {
      const {mountSources} = await import('/assets/js/pages/sources.js');
      const {mountSourceGroup} = await import('/assets/js/pages/source-group.js');
      const {sourceKind} = await import('/assets/js/pages/source-navigation.js');
      const json = value => new Response(JSON.stringify(value), {headers: {'Content-Type': 'application/json'}});
      const settle = () => new Promise(resolve => setTimeout(resolve, 20));
      const cases = [], main = document.getElementById('main');
      for (const [group, destination] of [[false, '#/knowledge'], [true, '#/knowledge'], [false, '#/sources?sort_by=title&order=asc&page=1']]) {
        const params = new URLSearchParams({page: '999', sort_by: 'source_count', order: 'desc', ...(group ? {title: 'test'} : {})});
        location.hash = group ? '#/sources/group?' + params : '#/sources?' + params;
        let complete; const navigations = [];
        window.fetch = () => new Promise(resolve => {complete = resolve;});
        const context = {params, navigate: hash => {navigations.push(hash); location.hash = hash;}};
        main.replaceChildren();
        const cleanup = (group ? mountSourceGroup : mountSources)(main, context);
        location.hash = destination;
        complete(json({items: [], total: 6, total_sources: 6}));
        await settle();
        cases.push({group, intended: destination, actual: location.hash, navigations,
          renderedResults: main.querySelectorAll('[data-testid="source-group-count"], [data-testid="source-member-count"]').length});
        cleanup();
      }
      location.hash = '#/sources/group?title=test'; main.replaceChildren();
      const bodies = [];
      window.fetch = path => path.includes('/source-groups/items?')
        ? Promise.resolve(json({items: Array.from({length: 5}, (_, i) => ({id: 'record-' + i})), total: 5}))
        : new Promise(resolve => bodies.push(resolve));
      const cleanup = mountSourceGroup(main, {params: new URLSearchParams({title: 'test'}), navigate: () => {throw new Error('Unexpected body navigation');}});
      await settle();
      const initialRequests = bodies.length;
      location.hash = '#/knowledge';
      for (const complete of bodies) complete(json({id: 'old-record', title: 'old', content: 'old', source_type: 'manual'}));
      await settle();
      const bodyRace = {initialRequests, finalRequests: bodies.length, renderedCards: main.querySelectorAll('[data-testid="source-group-card"]').length};
      cleanup();
      const types = [
        ['https://example.com/answer/123', '手动资料'], ['https://example.com/pin/123', '手动资料'],
        ['https://www.zhihu.com.evil.invalid/answer/123', '手动资料'],
        ['https://zhihu.com/question/1/answer/2', '回答'], ['https://www.zhihu.com/pin/3', '想法'],
        ['https://zhuanlan.zhihu.com/p/4', '文章']
      ].map(([url, expected]) => ({url, expected, actual: sourceKind({url, source_type: 'manual'})}));
      return {cases, bodyRace, types};
    }''')
    for case in result['cases']:
        assert case['actual'] == case['intended'] and case['navigations'] == [], case
        assert case['renderedResults'] == 0, case
    assert result['bodyRace'] == {'initialRequests': 3, 'finalRequests': 3, 'renderedCards': 0}, result
    assert all(item['actual'] == item['expected'] for item in result['types']), result['types']
    return {'status': 'passed', **result}
