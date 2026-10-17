import {api} from '../api.js';
import {el, button, badge, notice, pageHeading, confirmAction} from '../ui.js';
import {keyValues} from './workflow-utils.js';
import {settingsEditor} from './settings-editor.js';
import {promptSettings} from './prompt-settings.js';

export function mount(container, context) {
  const mountedHash = location.hash, controller = new AbortController();
  let disposed = false, saving = false, snapshot, editor, pendingKeys;
  const clearPendingKeys = () => {if (pendingKeys) {for (const key of pendingKeys) key.value = ''; pendingKeys.length = 0; pendingKeys = null;}};
  const alive = () => !disposed && location.hash === mountedHash;
  const dirtySections=new Set();
  function dirty(section,value){if(value)dirtySections.add(section);else dirtySections.delete(section);context.setDirty(dirtySections.size>0);}
  async function resultIsCurrent() {
    // The router temporarily changes hash while asking about unsaved edits.
    // Wait for that choice so cancelling navigation cannot strand a busy form.
    while (!disposed && location.hash !== mountedHash) await new Promise(resolve => setTimeout(resolve, 25));
    return alive();
  }
  const messages = el('div', {className: 'stack'}), status = el('div'), body = el('div', {}, el('div', {className: 'loading'}, '正在读取本机设置…'));
  const prompts = promptSettings(context, {alive, onDirty: value => dirty('prompts', value)});
  container.append(pageHeading('设置', '管理模型、提示词模板和本机配置；业务数据目录保持独立。'), messages, status, body, prompts.element);
  function errorMessage(error) {
    if (error.status === 409) return '配置已在其他位置修改。你的输入仍保留，请确认后重新读取配置。';
    if (error.status === 403) return '本次保存验证已失效或当前访问方式不允许修改，请重新读取设置后再操作。';
    if (error.status === 422 || error.status === 400) return '配置参数未通过校验。请检查模型配置、协议、高级参数及密钥引用后手动保存。';
    if (error.status === 503) return '当前配置暂不可写或服务不可用。输入仍保留，请检查本机配置和日志。';
    return '保存未确认成功，未自动重试。请重新读取配置核对后再决定是否保存。';
  }
  function render(value) {
    editor?.clearSecrets(); snapshot = value;
    const locations = value.locations || {}, active = value.active || {};
    const readOnlyReason = ({configuration_read_only: '当前配置由启动环境或宿主机管理，请在本机配置文件中修改并重启。',
      configuration_not_writable: '配置目录不可写，请检查目录权限后重新打开设置。'})[value.read_only_reason] || '当前运行方式不允许修改本机配置，设置仅供查看。';
    status.replaceChildren(el('section', {className: 'card stack'}, el('h2', {}, '当前状态'),
      el('div', {className: 'page-actions'}, badge(active.enabled ? '当前 AI 已开启' : '当前 AI 已关闭', active.enabled ? 'success' : ''),
        badge(value.restart_required ? '配置已保存 · 等待重启' : '启动配置已加载', value.restart_required ? 'warning' : 'info')),
      el('p', {className: 'muted'}, `当前默认配置：${active.default_profile || '未指定'}。配置就绪不代表接口连通性或生成质量已经验收。`),
      !value.editable && notice(readOnlyReason, 'warning'),
      value.environment_overrides?.length > 0 && el('div', {}, notice('部分设置受启动环境覆盖，请在对应环境中修改并重启。', 'warning'),
        el('details', {className: 'settings-advanced'}, el('summary', {}, '查看环境覆盖项'), el('p', {className: 'mono muted'}, value.environment_overrides.join('、'))))));
    editor = settingsEditor(value, {onSave: save, onDirty: () => {if (alive()) dirty('ai',true);}, alive});
    body.replaceChildren(editor.node, el('section', {className: 'card stack settings-locations'}, el('h2', {}, '本机存储位置（只读）'),
      keyValues([['运行目录', locations.runtime_root || '未提供'], ['数据目录', locations.data_directory || '未提供'],
        ['数据库文件', locations.database_file || '未提供'], ['知识目录', locations.knowledge_directory || '未提供'], ['配置目录', locations.config_directory || '未提供'],
        ['模型配置', locations.ai_config_file || '未提供'], ['密钥配置', locations.env_file || '未提供']]),
      notice('便携 EXE 使用 EXE 所在目录，和项目或其他便携目录的数据相互独立。备份时请保留完整便携目录。'),
      el('p', {className: 'muted'}, 'Embedding / RAG 继续通过本机配置文件管理，本页不修改它们的开关或参数。')));
  }
  async function reload() {
    if (saving || !alive()) return;
    try {const value = await api('/api/v1/settings/ai', {signal: controller.signal}); if (alive()) {render(value); dirty('ai',false); messages.replaceChildren();}}
    catch (error) {if (alive() && error.name !== 'AbortError') messages.replaceChildren(notice('无法读取本机设置，请检查服务和配置文件后手动重试。', 'error'), button('重试读取', reload));}
  }
  async function save() {
    if (!alive() || saving || !snapshot?.editable || !editor.valid()) return;
    let values;
    try {values = editor.collect();} catch (error) {editor.showLocalError(error.message); return;}
    pendingKeys = values.key_updates;
    saving = true; editor.busy(true); messages.replaceChildren();
    try {
      const value = await api('/api/v1/settings/ai', {method: 'PUT', headers: {'X-Configuration-Token': snapshot.csrf_token}, body: {expected_revision: snapshot.revision, ...values}});
      clearPendingKeys(); values = null;
      if (!await resultIsCurrent()) return;
      editor.clearSecrets(); render(value); dirty('ai',false);
      messages.replaceChildren(notice('设置已保存。完全退出应用并重新打开后，新的 AI 设置才会生效。没有发起模型调用。', 'success'));
      if (value.restart_required) {
        if (value.desktop?.restart_supported) {
          const restart = await confirmAction('新的 AI 配置需要重启应用。现在重启会等待在途任务完成；选择稍后则保留当前运行状态，配置将在下次启动生效。', {title: '设置已保存', confirmLabel: '现在重启', cancelLabel: '稍后'});
          if (restart && alive()) {
            if (dirtySections.has('prompts')) messages.append(notice('提示词模板还有未保存修改，请先保存或取消这些修改，再退出重启。', 'warning'));
            else try {
              await api('/api/v1/desktop/restart', {method: 'POST', headers: {'X-Configuration-Token': value.csrf_token}, body: {expected_revision: value.revision}});
              if (alive()) messages.append(notice('正在等待任务结束并重启应用…'));
            } catch {if (alive()) messages.append(notice('未确认重启成功，请完全退出应用后手动重新打开。没有自动重试。', 'error'));}
          }
        } else messages.append(notice('当前运行方式不支持网页重启。请停止并重新启动本机或 Docker 服务。'));
      }
    } catch (error) {
      clearPendingKeys(); values = null;
      if (!await resultIsCurrent()) return;
      messages.replaceChildren(notice(errorMessage(error), 'error'));
      if (error.status === 409 || error.status === 403) messages.append(button('重新读取配置', async () => {
        if (!alive() || saving || !await confirmAction('重新读取将丢弃本页未保存的修改和输入的新密钥。是否继续？', {title: '重新读取设置', confirmLabel: '重新读取'}) || !alive()) return;
        editor.clearSecrets(); await reload();
      }, {'data-testid': 'ai-settings-reload'}));
    } finally {saving = false; if (alive()) editor.busy(false); clearPendingKeys(); values = null;}
  }
  reload();
  return () => {disposed = true; controller.abort(); prompts.dispose(); editor?.clearSecrets(); clearPendingKeys();};
}
