import {api} from '../api.js';
import {el, button, field, notice, badge, empty, pageHeading, showError} from '../ui.js';
import {select, profilePicker, profileReady, jsonView, details} from './workflow-utils.js';
import {promptPicker} from './prompt-picker.js';
import {localPagination} from './list-pagination.js';

export async function mount(container, context) {
  const mountedHash = location.hash, controller = new AbortController(); let stopped = false, searching = false, asking = false;
  const alive = () => !stopped && location.hash === mountedHash;
  const [ragResult, aiResult] = await Promise.allSettled([
    api('/api/v1/rag/index/status?summary_only=true', {signal: controller.signal}), api('/api/v1/ai/profiles', {signal: controller.signal})]);
  const rag = ragResult.status === 'fulfilled' ? ragResult.value : {enabled: false};
  const ai = aiResult.status === 'fulfilled' ? aiResult.value : {enabled: false, items: []};
  const keyword = el('textarea', {rows: 3, maxLength: 2000, placeholder: '例如：如何减少并发编辑导致的数据覆盖？', 'data-testid': 'search-query'});
  const question = el('textarea', {rows: 3, maxLength: 2000, placeholder: '向你的知识库提问，回答只依据当前可用笔记。', 'data-testid': 'ask-question'});
  const topK = select(Array.from({length: 10}, (_, index) => [String(index + 1), `${index + 1} 条片段`]), '5');
  topK.setAttribute('data-testid', 'retrieval-limit');
  const retrievalLimit = field('检索数量', topK);
  retrievalLimit.classList.add('search-limit-field');
  const model = profilePicker(ai);
  const template = promptPicker({purpose: 'rag_qa', alive, onChange: () => update()});
  template.element.dataset.testid = 'ask-template';
  const searchErrors = el('div'), askErrors = el('div');
  const searchResult = el('div', {}, empty('找到相关知识片段', '输入自然语言查询，语义检索不会调用生成模型。'));
  const answerResult = el('div', {}, empty('带出处的知识库回答', '回答会附上可回溯到笔记的引用；依据不足时会明确说明。'));
  const searchButton = button('搜索知识库', search, {className: 'btn btn-primary', 'data-testid': 'search-submit'});
  const askButton = button('生成引用回答', ask, {className: 'btn btn-primary', 'data-testid': 'ask-submit'});
  function update() {
    searchButton.disabled = !rag.enabled || searching || !keyword.value.trim();
    askButton.disabled = !rag.enabled || asking || !question.value.trim() || !profileReady(ai, model.value) || !template.value();
    keyword.disabled = searching; question.disabled = asking; model.disabled = asking;
    topK.disabled = asking || searching;
    template.busy(asking);
  }
  keyword.addEventListener('input', update); question.addEventListener('input', update); model.addEventListener('change', update);
  async function search() {
    if (stopped || searchButton.disabled) return;
    const submittedQuery = keyword.value.trim();
    searching = true; update(); searchErrors.replaceChildren(); searchResult.replaceChildren(notice('正在检索知识片段…'));
    try {
      const value = await api('/api/v1/rag/search', {method: 'POST', body: {query: submittedQuery, top_k: Number(topK.value)}});
      if (stopped) return;
      searchResult.replaceChildren(...[el('p', {className: 'muted'}, `本次检索：${submittedQuery}`), value.index_incomplete && notice('索引尚未完整。以下仅展示当前已发布并核验的片段。', 'warning'),
        localPagination(value.items, rows => el('div', {className: 'stack'}, ...rows.map(hit => el('article', {className: 'card stack'},
          el('div', {className: 'detail-header'}, el('h2', {}, el('a', {href: `#/knowledge/${hit.knowledge_id}`}, hit.title)), badge(`相似度 ${Number(hit.score).toFixed(4)}`)),
          el('p', {className: 'muted'}, `v${hit.version} · ${hit.path || '等待 Markdown 路径'}${hit.source?.title ? ` · 来源：${hit.source.title}` : ''}`),
          el('pre', {className: 'text-excerpt'}, hit.text), details('片段标识', el('code', {}, hit.chunk_id))))), {label: '本次检索片段分页', key: 'search-results'}),
        !value.items.length && empty('没有可用片段', '知识库依据不足。可以新增笔记，或在系统页面查看索引状态。')].filter(Boolean));
    } catch (error) {if (!stopped) {searchResult.replaceChildren(); showError(error, searchErrors); searchErrors.append(notice('未自动重试搜索或向量调用。请确认索引和向量服务状态后手动操作。'));}}
    finally {searching = false; if (!stopped) update();}
  }
  async function ask() {
    if (stopped || askButton.disabled) return;
    const submittedQuestion = question.value.trim();
    asking = true; update(); askErrors.replaceChildren(notice('正在检索并生成回答，请等待。不会自动重新调用模型。')); answerResult.replaceChildren();
    try {
      const selected = template.value();
      const payload = {question: submittedQuestion, top_k: Number(topK.value), prompt_template_id: selected.id, prompt_template_version: selected.version}; if (model.value) payload.profile_id = model.value;
      const value = await api('/api/v1/rag/ask', {method: 'POST', body: payload});
      if (stopped) return;
      askErrors.replaceChildren();
      const citations = value.citations || [];
      const citationList = localPagination(citations, rows => el('div', {className: 'stack'}, ...rows.map(citation => el('article', {className: 'citation', 'data-citation': citation.citation_id},
        el('h4', {}, `[${citation.citation_id}] `, el('a', {href: `#/knowledge/${citation.knowledge_id}`}, citation.title)),
        el('blockquote', {}, citation.quote), el('p', {className: 'muted'}, `笔记 v${citation.version} · ${citation.path || '等待 Markdown 路径'}`),
        ...(citation.sources || (citation.source ? [citation.source] : [])).map(source => el('p', {className: 'muted'}, '关联来源：', el('a', {href: `#/sources/${source.id || citation.source_id}`}, source.title || source.id)))))), {label: '本次回答引用分页', key: 'answer-citations'});
      answerResult.replaceChildren(el('article', {className: 'card stack', 'data-testid': 'ask-answer'},
        el('h2', {}, value.insufficient_evidence ? '知识库依据不足' : '知识库回答'),
        el('p', {className: 'muted'}, `本次问题：${submittedQuestion}`),
        value.index_incomplete && notice('当前索引不完整，回答仅使用本次可用片段。', 'warning'),
        value.insufficient_evidence ? el('p', {}, value.answer || '当前知识库没有足够依据回答这个问题。') : el('div', {className: 'answer-paragraphs'},
          ...(value.paragraphs || []).map(paragraph => el('p', {}, paragraph.text, ' ', ...(paragraph.citation_ids || []).map(id => el('a', {href: `#citation-${id}`, onClick: event => {event.preventDefault(); citationList.reveal(citations.findIndex(item => String(item.citation_id) === String(id))); answerResult.querySelector(`[data-citation="${CSS.escape(String(id))}"]`)?.scrollIntoView({behavior: 'smooth'});}, 'aria-label': `查看引用 ${id}`}, `[${id}]`))))),
        value.citations?.length > 0 && el('section', {className: 'stack'}, el('h3', {}, '引用与原文依据'),
          citationList),
        details('模型、模板与用量', jsonView({profile_id: value.profile_id, model: value.model, usage: value.usage, prompt_template: value.prompt_template}))));
    } catch (error) {
      if (!stopped) {showError(error, askErrors); askErrors.append(notice(error.status === 409 ? '生成期间引用笔记发生变化，本次回答未发布。请重新查看笔记后决定是否重新提问。' : '未自动重试。本页不保存问答历史；断连后请先检查服务状态，再决定是否发起新调用。'));}
    } finally {asking = false; if (!stopped) update();}
  }
  const searchPanel = el('section', {className: 'stack', role: 'tabpanel', id: 'semantic-panel'},
    el('div', {className: 'card stack'}, field('检索问题', keyword, '最多 2,000 字符'), searchButton, searchErrors), searchResult);
  const askPanel = el('section', {className: 'stack', role: 'tabpanel', id: 'answer-panel', hidden: true},
    el('div', {className: 'card stack'}, field('向知识库提问', question, '单轮问答，不使用通识补全，也不保存历史。'), field('生成模型', model), field('问答提示词模板', template.element),
      !ai.enabled && notice('AI 当前关闭，语义检索仍可独立使用。'), askButton, askErrors), answerResult);
  const searchTab = button('语义检索', () => switchTab(false), {role: 'tab', id: 'semantic-tab', tabIndex: 0, 'aria-controls': 'semantic-panel', 'aria-selected': 'true', className: 'btn active'});
  const askTab = button('引用问答', () => switchTab(true), {role: 'tab', id: 'answer-tab', tabIndex: -1, 'aria-controls': 'answer-panel', 'aria-selected': 'false'});
  searchPanel.setAttribute('aria-labelledby', 'semantic-tab'); askPanel.setAttribute('aria-labelledby', 'answer-tab');
  for (const tab of [searchTab, askTab]) tab.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault(); const isAsk = event.key === 'End' || (event.key !== 'Home' && tab === searchTab);
    switchTab(isAsk); (isAsk ? askTab : searchTab).focus();
  });
  function switchTab(isAsk) {
    searchPanel.hidden = isAsk; askPanel.hidden = !isAsk;
    searchTab.setAttribute('aria-selected', String(!isAsk)); askTab.setAttribute('aria-selected', String(isAsk));
    searchTab.tabIndex = isAsk ? -1 : 0; askTab.tabIndex = isAsk ? 0 : -1;
    searchTab.classList.toggle('active', !isAsk); askTab.classList.toggle('active', isAsk);
  }
  container.append(...[pageHeading('搜索与问答', '检索已提交的知识笔记，以可核验的引用连接答案与原文。'),
    !rag.enabled && notice('RAG 当前关闭。请到左上角设置按搭建引导配置 Embedding 与 Qdrant，启用后重启。'),
    ragResult.status === 'rejected' && notice(`索引状态读取失败：${ragResult.reason.message}`, 'error'),
    aiResult.status === 'rejected' && notice(`生成配置读取失败：${aiResult.reason.message}`, 'error'),
    el('div', {className: 'toolbar search-toolbar'}, el('div', {className: 'tabs', role: 'tablist', 'aria-label': '搜索方式'}, searchTab, askTab), retrievalLimit), searchPanel, askPanel].filter(Boolean));
  if (context.params.get('mode') === 'ask') switchTab(true);
  await template.ready; update(); return () => {stopped = true; controller.abort(); template.destroy();};
}
