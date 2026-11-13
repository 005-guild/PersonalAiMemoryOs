import {api} from '../api.js';
import {el, button, field, notice, formatDate} from '../ui.js';

const endpoint = '/api/v1/settings/zhihu-sync';
const errors = {
  login_required: '请点击“登录知乎”，在独立窗口完成登录。',
  verification_required: '知乎要求验证，已暂停。请在登录窗口手动完成验证后重试。',
  browser_unavailable: '同步浏览器未就绪，请检查完整安装包及浏览器组件。',
  rate_limited: '知乎暂时限制访问，本轮已停止，下一轮再试。',
  state_invalid: '同步记录损坏，已停止写入。请保留 .sync 目录并检查备份。',
  state_missing: '同步记录缺失，已停止写入。请恢复 .sync 中的记录。',
  legacy_inventory_mismatch: '旧导出记录与本地文件不一致，已停止首次接管。',
  existing_file_invalid: '已有 Markdown 无法识别，请检查文件元数据。',
  page_structure_changed: '知乎页面结构未能识别，本轮已停止。',
  collection_changed_or_incomplete: '分页数量与收藏夹总数不一致；请稍后重试，未把不完整扫描视为成功。',
  pagination_stalled: '收藏夹翻页未推进，本轮已停止。',
  source_invalid: '正文或元数据未通过校验，该篇未计为完成。',
  sync_busy: '已有同步任务正在运行。',
  configuration_changed: '配置已变化，请重新读取后保存。',
  configuration_invalid: '请检查收藏夹链接、绝对保存目录和同步间隔。',
  configuration_incomplete: '请先保存收藏夹链接和目录。',
  target_protected: '不能将原始收藏保存到应用数据库、知识库或配置目录。',
  target_busy: '另一个程序正在向该目录同步。',
  output_conflict: '目标文件已存在且内容不同，未覆盖。',
  network_error: '网络访问未完成，请稍后重试。',
  cancelled: '本轮已停止；已完成的文件保留。',
  operation_failed: '同步未完成，请检查网络、目录权限和登录状态。',
};

export function zhihuSettings({alive, onDirty}) {
  let disposed = false, dirty = false, busy = false, snapshot, timer;
  const element = el('section', {className:'card stack', 'data-testid':'zhihu-sync-settings'});
  const messages = el('div'), status = el('div'), actions = el('div', {className:'page-actions'});
  const changed = () => {dirty = true; onDirty(true);};
  const enabled = el('input', {type:'checkbox', onChange:changed});
  const url = el('input', {type:'url', placeholder:'https://www.zhihu.com/collection/…', onInput:changed});
  const path = el('input', {type:'text', placeholder:'本机 articles 文件夹的绝对路径', onInput:changed});
  const interval = el('input', {type:'number', min:15, max:1440, value:60, onInput:changed});
  const controls = [];
  const active = () => !disposed && alive();
  function show(value, fill = false) {
    if (!dirty || fill) snapshot = value;
    if (fill) {
      enabled.checked = value.enabled; url.value = value.collection_url;
      path.value = value.target_dir; interval.value = value.interval_seconds / 60;
      dirty = false; onDirty(false);
    }
    const s = value.status, r = s.report;
    status.replaceChildren(el('p', {}, `状态：${({idle:'待运行',queued:'等待执行',running:'正在运行',finished:'已完成',failed:'未完成',cancelled:'已停止'})[s.state] || s.state}${value.paused ? ' · 自动同步已暂停' : ''}；最近结束：${formatDate(s.last_finished)}`));
    if (r) status.append(el('p', {}, `收藏夹总数 ${r.total}；新增 ${r.created}；跳过 ${r.skipped}；预计新增 ${r.would_create}；失败 ${r.failed}；不支持 ${r.unsupported || 0}；站点未返回 ${r.unlisted || 0}`));
    if (r?.unlisted) status.append(notice('已核对完整分页，但知乎未返回部分条目。这些条目未记为已同步，下次仍会检查。', 'warning'));
    if (s.last_error) status.append(notice(errors[s.last_error] || `任务未完成：${s.last_error}`, 'warning'));
    if (r?.errors?.length) status.append(el('details', {}, el('summary', {}, '查看未完成条目'),
      ...r.errors.map(item => el('p', {}, `${item.key}：${errors[item.code] || item.code}`))));
    for (const input of [enabled,url,path,interval]) input.disabled = busy || !value.editable;
    for (const control of controls) control.disabled = busy || !value.editable;
  }
  async function read(fill = false) {
    try {const value = await api(endpoint); if (active()) show(value,fill);}
    catch (error) {if (active()) messages.replaceChildren(notice(errors[error.detail?.code] || '无法读取知乎同步设置。', 'error'));}
  }
  async function perform(action) {
    if (!active() || busy || !snapshot) return;
    if (dirty && action !== 'save' && action !== 'stop') {
      messages.replaceChildren(notice('请先保存设置，再登录或运行。', 'warning')); return;
    }
    if (action === 'save' && (![url,path,interval].every(input=>input.reportValidity()))) return;
    busy = true; show(snapshot); messages.replaceChildren();
    try {
      const value = await api(action === 'save' ? endpoint : `${endpoint}/${action}`, {
        method:action === 'save' ? 'PUT' : 'POST', headers:{'X-Configuration-Token':snapshot.csrf_token},
        body:action === 'save' ? {enabled:enabled.checked,collection_url:url.value.trim(),target_dir:path.value.trim(),
          interval_seconds:Number(interval.value)*60,expected_revision:snapshot.revision} : {},
      });
      if (active()) {show(value,action === 'save'); messages.replaceChildren(notice(action === 'save' ? '设置已保存并生效。' : '操作已提交，进度会自动刷新。'));}
    } catch (error) {
      if (active()) messages.replaceChildren(notice(errors[error.detail?.code] || '操作未确认成功，请检查状态后重试。','error'));
    } finally {busy=false; if (active() && snapshot) show(snapshot);}
  }
  for (const [action,label] of [['save','保存同步设置'],['login','登录知乎'],['preview','预演'],['run','立即同步'],['stop','停止本轮']]) {
    const control=button(label,()=>perform(action)); controls.push(control); actions.append(control);
  }
  element.append(el('h2', {}, '知乎收藏同步'),
    notice('仅在软件运行时检查新收藏。已同步内容永久跳过，删除本地文件也不会重新下载。首次请保存目录、登录并预演，再开启自动同步。'),
    el('label',{className:'settings-check'},enabled,'启用自动同步'),field('收藏夹链接',url),field('保存目录',path),field('间隔（分钟）',interval),
    actions,messages,status);
  read(true);
  async function poll() {if (!active()) return; if (!busy) await read(false); timer=setTimeout(poll,2000);}
  timer=setTimeout(poll,2000);
  return {element,dispose(){disposed=true;clearTimeout(timer);}};
}
