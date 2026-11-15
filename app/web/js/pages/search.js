import {api} from '../api.js';
import {el, button, field, notice, badge, empty, pageHeading, showError} from '../ui.js';
import {select, profilePicker, profileReady, jsonView, details} from './workflow-utils.js';
import {promptPicker} from './prompt-picker.js';
import {mountList} from './reading-list.js';
import {localPagination} from './list-pagination.js';

const views=new Map(); // In-memory current views only; no persisted question history.

export async function mount(container, context) {
  container.append(el('nav',{className:'subnav','aria-label':'搜索方式'},...[
    ['keyword','关键词'],['search','语义搜索'],['answer','引用问答']].map(([mode,label])=>el('a',{href:'#/search?mode='+mode,className:(context.params.get('mode')||'keyword')===mode?'active':''},label))));
  if(!context.params.get('mode')||context.params.get('mode')==='keyword'){
    let disposed=false,cleanup;const controller=new AbortController();const root=el('div',{className:'reading-root'});container.append(root);
    api('/api/v1/reading/overview?scope=all',{signal:controller.signal}).then(data=>{if(!disposed)cleanup=mountList(root,data,context.params,()=>!disposed,'#/search?mode=keyword');}).catch(error=>{if(!disposed)showError(error,root);});
    return()=>{disposed=true;controller.abort();cleanup?.();};
  }
  const view=views.get(context.params.get('mode'))||{};
  const mountedHash = location.hash, controller = new AbortController(); let stopped = false, searching = false, asking = false;
  const alive = () => !stopped && location.hash === mountedHash;
  const [ragResult, aiResult] = await Promise.allSettled([
    api('/api/v1/rag/index/status?summary_only=true', {signal: controller.signal}), api('/api/v1/ai/profiles', {signal: controller.signal})]);
  const rag = ragResult.status === 'fulfilled' ? ragResult.value : {enabled: false};
  const ai = aiResult.status === 'fulfilled' ? aiResult.value : {enabled: false, items: []};
  const keyword = el('textarea', {rows: 3, maxLength: 2000, placeholder: '例如：如何减少并发编辑导致的数据覆盖？', 'data-testid': 'search-query'});
  const question = el('textarea', {rows: 3, maxLength: 2000, placeholder: '向你的知识库提问，回答只依据当前可用笔记。', 'data-testid': 'ask-question'});
  const scope=select([['all','全部笔记'],['collection','知乎收藏'],['other','普通笔记']],'all'),category=el('input',{placeholder:'精确分类'}),tag=el('input',{placeholder:'精确标签'});
  const topK = select(Array.from({length: 10}, (_, index) => [String(index + 1), `${index + 1} 篇笔记`]), '5');
  topK.setAttribute('data-testid', 'retrieval-limit');
  const retrievalLimit = field('最多参考笔记', topK);
  retrievalLimit.classList.add('search-limit-field');
  const model = profilePicker(ai);
  const template = promptPicker({purpose: 'rag_qa', alive, onChange: () => update()});
  template.element.dataset.testid = 'ask-template';
  const searchErrors = el('div'), askErrors = el('div');
  const searchResult = el('div', {}, empty('查找相关知识笔记', '同一笔记合并展示。搜索不调用生成模型。'));
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
      const value = await api('/api/v1/rag/retrieve', {method: 'POST', body: {query: submittedQuery, max_notes: Number(topK.value),scope:scope.value,category:category.value.trim(),tag:tag.value.trim()}});
      if (!alive()) return;
      view.search={value,query:submittedQuery};renderSearch(value,submittedQuery);
    } catch (error) {if (!stopped) {searchResult.replaceChildren(); showError(error, searchErrors); searchErrors.append(notice('未自动重试搜索或向量调用。请确认索引和向量服务状态后手动操作。'));}}
    finally {searching = false; if (!stopped) update();}
  }
  function renderSearch(value,submittedQuery){
      searchResult.replaceChildren(...[el('p', {className: 'muted'}, `本次检索：${submittedQuery}`), value.index_incomplete && notice('索引尚未完整。以下仅展示当前已发布并核验的片段。', 'warning'),
        localPagination(value.notes, rows => el('div', {className: 'stack'}, ...rows.map(hit => el('article', {className: 'card stack', 'data-testid': 'retrieved-note'},
          el('div', {className: 'detail-header'}, el('h2', {}, el('a', {href: `#/reading/${hit.knowledge_id}?${new URLSearchParams({from:location.hash})}`}, hit.title)), badge(hit.scope === 'full' ? '阅读全文' : '阅读部分章节')),
          el('p', {className: 'muted'}, `v${hit.version} · ${hit.path || '等待 Markdown 路径'}${hit.source?.title ? ` · 来源：${hit.source.title}` : ''}`),
          el('p', {className: 'muted'}, `正文 ${hit.body_chars} 字符 · 本次读取 ${hit.read_chars} 字符 · 排序分数 ${Number(hit.score).toFixed(4)}（不是可信度）`),
          details(`命中位置（${hit.matches.length} 处）`, ...hit.matches.map(match => el('pre', {className: 'text-excerpt'}, match.text))),
          details('本次阅读内容', el('pre', {className: 'text-excerpt'}, value.contexts.find(item => item.context_id === hit.context_id)?.text || ''))))), {label: '本次检索笔记分页', key: 'search-results'}),
        !value.notes.length && empty('没有可用笔记', '知识库依据不足。可以新增笔记，或在系统页面查看索引状态。')].filter(Boolean));
  }
  async function ask() {
    if (stopped || askButton.disabled) return;
    const submittedQuestion = question.value.trim();
    asking = true; update(); askErrors.replaceChildren(notice('正在检索并生成回答，请等待。不会自动重新调用模型。')); answerResult.replaceChildren();
    try {
      const selected = template.value();
      const payload = {question: submittedQuestion, max_notes: Number(topK.value), prompt_template_id: selected.id, prompt_template_version: selected.version}; if (model.value) payload.profile_id = model.value;
      const value = await api('/api/v1/rag/answer', {method: 'POST', body: payload});
      if (!alive()) return;
      askErrors.replaceChildren();
      view.answer={value,query:submittedQuestion};renderAnswer(value,submittedQuestion);
    } catch (error) {
      if (!stopped) {showError(error, askErrors); askErrors.append(notice(error.status === 409 ? '生成期间引用笔记发生变化，本次回答未发布。请重新查看笔记后决定是否重新提问。' : '未自动重试。本页不保存问答历史；断连后请先检查服务状态，再决定是否发起新调用。'));}
    } finally {asking = false; if (!stopped) update();}
  }
  function renderAnswer(value,submittedQuestion){
      const citations = value.citations || [];
      const citationList = localPagination(citations, rows => el('div', {className: 'stack'}, ...rows.map(citation => el('article', {className: 'citation', 'data-citation': citation.citation_id},
        el('h4', {}, `[${citation.citation_id}] `, el('a', {href: `#/reading/${citation.knowledge_id}?${new URLSearchParams({from:location.hash})}`}, citation.title)),
        el('blockquote', {}, citation.quote), el('p', {className: 'muted'}, `笔记 v${citation.version} · ${citation.scope === 'full' ? '阅读全文' : '阅读部分章节'} · ${citation.path || '等待 Markdown 路径'}`),
        ...(citation.sources || (citation.source ? [citation.source] : [])).map(source => el('p', {className: 'muted'}, '关联来源：', el('a', {href: `#/sources/${source.id || citation.source_id}`}, source.title || source.id)))))), {label: '本次回答引用分页', key: 'answer-citations'});
      answerResult.replaceChildren(el('article', {className: 'card stack', 'data-testid': 'ask-answer'},
        el('h2', {}, value.insufficient_evidence ? '知识库依据不足' : '知识库回答'),
        el('p', {className: 'muted'}, `本次问题：${submittedQuestion}`),
        value.index_incomplete && notice('当前索引不完整，回答仅使用本次可用片段。', 'warning'),
        value.insufficient_evidence ? el('p', {}, value.answer || '当前知识库没有足够依据回答这个问题。') : el('div', {className: 'answer-paragraphs'},
          ...(value.paragraphs || []).map(paragraph => el('p', {}, paragraph.text, ' ', ...(paragraph.citation_ids || []).map(id => el('a', {href: `#citation-${id}`, onClick: event => {event.preventDefault(); citationList.reveal(citations.findIndex(item => String(item.citation_id) === String(id))); answerResult.querySelector(`[data-citation="${CSS.escape(String(id))}"]`)?.scrollIntoView({behavior: 'smooth'});}, 'aria-label': `查看引用 ${id}`}, `[${id}]`))))),
        value.citations?.length > 0 && el('section', {className: 'stack'}, el('h3', {}, '引用与原文依据'),
          citationList),
        details('本次阅读范围', ...(value.notes || []).map(note => el('p', {}, el('a', {href: `#/reading/${note.knowledge_id}`}, note.title), `：${note.scope === 'full' ? '全文' : '部分章节'}（${note.read_chars}/${note.body_chars} 字符）`))),
        details('模型、模板与用量', jsonView({profile_id: value.profile_id, model: value.model, usage: value.usage, prompt_template: value.prompt_template, rerank: value.rerank}))));
  }
  const searchPanel = el('section', {className: 'stack', role: 'region', id: 'semantic-panel'},
    el('div', {className: 'card stack'}, field('检索问题', keyword, '最多 2,000 字符'),el('details',{},el('summary',{},'检索范围'),field('来源',scope),field('分类',category),field('标签',tag)), searchButton, searchErrors), searchResult);
  const askPanel = el('section', {className: 'stack', role: 'region', id: 'answer-panel', hidden: true},
    el('div', {className: 'card stack'}, field('向知识库提问', question, '单轮问答，不使用通识补全，也不保存历史。'), el('p',{className:'muted'},'问答范围：全部已索引知识笔记。'),el('details',{},el('summary',{},'模型与模板'),field('生成模型',model),field('问答提示词模板',template.element)),
      !ai.enabled && notice('AI 当前关闭，语义检索仍可独立使用。'), askButton, askErrors), answerResult);
  searchPanel.setAttribute('aria-label','语义搜索结果');askPanel.setAttribute('aria-label','引用问答结果');
  function switchTab(isAsk){searchPanel.hidden=isAsk;askPanel.hidden=!isAsk;}
  container.append(...[pageHeading('搜索与问答', '检索已提交的知识笔记，以可核验的引用连接答案与原文。'),
    !rag.enabled && notice('RAG 当前关闭。请到设置的向量检索页面配置 Embedding 与 Qdrant，启用后重启。'),
    ragResult.status === 'rejected' && notice(`索引状态读取失败：${ragResult.reason.message}`, 'error'),
    aiResult.status === 'rejected' && notice(`生成配置读取失败：${aiResult.reason.message}`, 'error'),
    el('div', {className: 'toolbar search-toolbar'}, el('span',{},context.params.get('mode')==='search'?'语义搜索':'引用问答'), retrievalLimit), searchPanel, askPanel].filter(Boolean));
  switchTab(context.params.get('mode') !== 'search');
  await template.ready;
  if(view.template)await template.choose(view.template,false);
  if(view.form){const f=view.form;keyword.value=f.keyword;question.value=f.question;scope.value=f.scope;category.value=f.category;tag.value=f.tag;topK.value=f.topK;model.value=f.model;}
  if(view.search)renderSearch(view.search.value,view.search.query);
  if(view.answer)renderAnswer(view.answer.value,view.answer.query);
  requestAnimationFrame(()=>{if(alive())window.scrollTo(0,view.scroll||0);});
  update();return()=>{view.template=template.value();view.form={keyword:keyword.value,question:question.value,scope:scope.value,category:category.value,tag:tag.value,topK:topK.value,model:model.value};view.scroll=window.scrollY;views.set(context.params.get('mode'),view);stopped=true;controller.abort();template.destroy();};
}
