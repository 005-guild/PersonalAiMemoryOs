import {api} from '../api.js';
import {el, button, field, notice, badge, select, confirmAction, showError} from '../ui.js';
import {keyValues} from './workflow-utils.js';
import {ragProfile} from './rag-profile.js';
import {localPagination} from './list-pagination.js';
import {offerRestart} from './settings-restart.js';

export function ragSettings({alive, onDirty, hasDirty}) {
  const element = el('section', {className: 'stack', 'data-testid': 'rag-settings'}), messages = el('div'), body = el('div');
  let snapshot, profiles = [], busy = false, confirming = false, disposed = false, pagination, fields, form, pendingKeys;
  const active = () => !disposed && alive();
  async function settle() {while(!disposed&&!alive())await new Promise(resolve=>setTimeout(resolve,25));return active();}
  const clearSecrets = () => {for (const profile of profiles) profile.clearSecret(); if (pendingKeys) for (const key of pendingKeys) key.value = ''; pendingKeys = null;};
  element.append(el('section', {className: 'card stack'}, el('h2', {}, 'RAG 搭建引导'),
    el('ol', {}, el('li', {}, '先保存知识笔记。资料库原文和未采纳草稿不会进入索引。'),
      el('li', {}, '配置独立的 Embedding 接口、模型及实际维度。DeepSeek 等生成模型与向量模型分别配置。'),
      el('li', {}, '启动或连接 Qdrant。桌面程序不内置向量数据库；项目可单独启动 Compose 的 qdrant 服务。'),
      el('li', {}, '保存后主动测试连接；Embedding 测试明确确认一次调用。准备好后开启 RAG 并重启。'),
      el('li', {}, '到“同步与系统”检查索引进度，先测试语义搜索，再用已开启的生成 AI 进行引用问答。')),
    notice('RAG 默认关闭。保存配置不调用模型、不启动索引；重启使“开启 RAG”生效后会自动索引笔记，可能产生向量调用费用。模型、维度或分块语义变更需要重建索引。'),
    el('p', {}, el('code', {}, 'docker compose --profile rag up -d qdrant')), el('a', {href: '#/system'}, '查看同步与索引状态 →')), messages, body);
  async function reload() {
    if (busy || !active()) return;
    busy=true;if(fields)fields.disabled=true;clearSecrets();
    try {const value = await api('/api/v1/settings/rag'); if (await settle()) {render(value); onDirty(false);}}
    catch (error) {if (await settle()) showError(error, messages);}
    finally{busy=false;if(active()&&fields)fields.disabled=false;}
  }
  function render(value) {
    snapshot = value; profiles = [];
    const enabled = el('input', {type: 'checkbox', checked: value.enabled, 'data-testid': 'rag-enabled'});
    const url = el('input', {type: 'url', required: true, value: value.qdrant_url, 'data-testid': 'rag-qdrant-url'}), defaultProfile = select([], value.default_profile || '');
    defaultProfile.dataset.testid = 'rag-default-profile'; defaultProfile.setAttribute('aria-label', '默认向量配置');
    let defaultId = value.default_profile || '';
    function defaults(before,after) {if(before&&defaultId===before)defaultId=after;defaultProfile.replaceChildren(el('option', {value: ''}, '未指定'), ...profiles.map(item => el('option', {value: item.id()}, item.label() || item.id() || '未命名')));defaultProfile.value = profiles.some(item => item.id() === defaultId) ? defaultId : '';}
    defaultProfile.addEventListener('change', () => defaultId = defaultProfile.value);
    const profileList = el('div'), errors = el('div'), save = el('button', {type: 'submit', className: 'btn btn-primary', 'data-testid': 'rag-settings-save'}, '保存 RAG 设置');
    function redraw() {pagination = localPagination(profiles, rows => el('div', {className: 'stack'}, ...rows.map(item => item.node)), {label: '向量配置分页', key: 'rag-settings-profiles'}); profileList.replaceChildren(pagination);}
    function add(profile) {
      let editor; editor = ragProfile(profile, {keys: value.keys, onIdentityChange: defaults, onRemove: async () => {
        if (busy || confirming) return;confirming=true;const accepted=await confirmAction('删除此向量配置？密钥和现有索引保留，后续需明确选择模型或重建。', {title: '删除配置', confirmLabel: '删除'});confirming=false;
        if(!accepted||!active())return;const index=profiles.indexOf(editor);if(index<0)return;
        if (editor.id() === defaultId) defaultId = ''; editor.clearSecret(); profiles.splice(index, 1); defaults(); redraw(); onDirty(true);
      }}); profiles.push(editor); defaults();
    }
    for (const profile of value.profiles) add(profile); redraw(); defaults();
    fields = el('fieldset', {className: 'settings-fields'});
    fields.append(el('section', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, '向量检索配置'), badge(value.active?.enabled ? '当前 RAG 已开启' : '当前 RAG 已关闭')),
      value.restart_required && notice('已保存配置与当前运行配置不同，需要重启。', 'warning'),
      !value.editable && notice('本配置由运行环境管理或不可写，请在本机文件中修改。', 'warning'),
      el('label', {className: 'settings-check'}, enabled, '开启 RAG（重启后自动索引知识笔记）'),field('Qdrant 地址', url),field('默认向量配置', defaultProfile),
      el('p', {className: 'muted'}, `本地配置检查：${value.preflight?.ready ? '就绪' : '未就绪'}。尚未测试远程连接。`),
      value.preflight?.issues?.length && notice(`需处理：${value.preflight.issues.join('、')}`, 'warning'),
      value.preflight?.rebuild_required && notice('向量模型或维度配置变化：重启后请到系统页明确重建索引。', 'warning'),
      value.environment_overrides?.length && notice(`环境覆盖项：${value.environment_overrides.join('、')}`)),
      el('section', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, 'Embedding 模型'), button('＋ 新建向量配置', () => {
        if (profiles.length >= 100) {errors.replaceChildren(notice('最多保留 100 套配置。', 'warning'));return;}
        let index=profiles.length+1;while(profiles.some(profile=>profile.id()===`embedding_${index}`))index++;
        add({id:`embedding_${index}`,enabled:true,base_url:'',model:'',dimension:'',auth:'bearer',timeout_seconds:60,batch_size:8});redraw();pagination.reveal(profiles.length-1);onDirty(true);
      }, {'data-testid': 'rag-add-profile'})), profileList), errors, el('div', {className: 'page-actions'}, save));
    form = el('form', {className: 'settings-form', autocomplete: 'off'}, fields);
    if (!value.editable) {
      for (const node of form.querySelectorAll('input,select,textarea,button')) if (!node.closest('nav')) node.disabled = true;
      for (const profile of profiles) for (const node of profile.node.querySelectorAll('input,select,textarea,button')) node.disabled = true;
    }
    form.addEventListener('input',()=>onDirty(true));form.addEventListener('change',()=>onDirty(true));
    form.addEventListener('submit',event=>{event.preventDefault();saveSettings(enabled,url,defaultProfile,errors);});
    body.replaceChildren(form,el('section',{className:'card stack'},el('h2',{},'连接测试（主动操作）'),
      notice('测试使用已保存的配置。未保存输入不参与测试；不会开启索引，不自动重试。'),
      el('div',{className:'page-actions'},button('检查 Qdrant 连接',()=>probe('qdrant'),{'data-testid':'rag-test-qdrant'}),button('测试默认 Embedding（1 次调用）',()=>probe('embedding'),{'data-testid':'rag-test-embedding'})),
      keyValues([['配置文件',value.locations?.embedding_config_file],['密钥配置',value.locations?.env_file]])));
  }
  async function saveSettings(enabled, url, defaultProfile, errors) {
    if (busy || confirming || !snapshot?.editable || !active()) return;
    for(let index=0;index<profiles.length;index++)for(const node of profiles[index].node.querySelectorAll('input,select,textarea'))if(!node.checkValidity()){pagination.reveal(index);profiles[index].node.open=true;node.reportValidity();return;}
    if(!form.reportValidity())return;
    if(enabled.checked&&!snapshot.enabled){confirming=true;const accepted=await confirmAction('开启后，重启会自动为知识笔记调用 Embedding，可能产生费用。确认开启 RAG？',{title:'开启自动索引',confirmLabel:'确认开启'});confirming=false;if(!accepted)return;}
    if(!active())return;
    let values;
    try {const rows=profiles.map(item=>item.collect()), refs=new Map();if(new Set(rows.map(item=>item.id)).size!==rows.length)throw Error('向量配置 ID 不能重复。');
      for(const profile of profiles){const key=profile.secret();if(!key.value)continue;if(!key.ref)throw Error('填写密钥时需同时填写引用。');const ref=key.ref.toLowerCase();if(refs.has(ref)&&refs.get(ref).value!==key.value)throw Error('同一引用的新密钥不一致。');refs.set(ref,key);}
      pendingKeys=[...refs.values()];values={expected_revision:snapshot.revision,enabled:enabled.checked,qdrant_url:url.value,default_profile:defaultProfile.value||null,profiles:rows,key_updates:pendingKeys};
    }catch(error){errors.replaceChildren(notice(error.message,'warning'));return;}
    busy=true;fields.disabled=true;messages.replaceChildren();
    try {const saved=await api('/api/v1/settings/rag',{method:'PUT',headers:{'X-Configuration-Token':snapshot.csrf_token},body:values});clearSecrets();values=null;if(!await settle())return;render(saved);fields.disabled=true;onDirty(false);
      messages.replaceChildren(notice('RAG 配置已保存，没有调用模型或启动索引。','success'));await offerRestart(saved,'rag',messages,active,hasDirty);
    }catch(error){if(await settle()){showError(error,messages);messages.append(button('重新读取 RAG 配置',async()=>{if(await confirmAction('重新读取会丢弃未保存的 RAG 输入，是否继续？'))reload();}));}}
    finally{clearSecrets();values=null;busy=false;if(active())fields.disabled=false;}
  }
  async function probe(target) {
    if(busy||confirming||!active())return;
    if(target==='embedding'){confirming=true;const accepted=await confirmAction('将用已保存的默认向量配置发送一段固定短文本，最多一次 Embedding 调用，可能收费；不写索引。是否测试？',{title:'确认向量测试',confirmLabel:'调用一次'});confirming=false;if(!accepted)return;}
    if(!active())return;busy=true;
    try{const result=await api('/api/v1/settings/rag/test',{method:'POST',headers:{'X-Configuration-Token':snapshot.csrf_token},body:{expected_revision:snapshot.revision,target,confirm_embedding:target==='embedding',...(target==='embedding'&&snapshot.default_profile?{profile_id:snapshot.default_profile}:{})}});
      if(await settle())messages.replaceChildren(notice(target==='qdrant'?'Qdrant 只读连接检查通过。':`Embedding 测试通过：${result.dimension} 维，调用 ${result.calls} 次。`,'success'));
    }catch(error){if(await settle()){showError(error,messages);messages.append(notice('未自动重试测试。'));}}finally{busy=false;}
  }
  reload();return{element,clearSecrets,dispose(){disposed=true;clearSecrets();}};
}
