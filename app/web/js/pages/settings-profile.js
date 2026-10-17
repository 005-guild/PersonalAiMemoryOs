import {el, button, field, select, badge} from '../ui.js';
import {protocols} from './settings-presets.js';

export function profileEditor(profile, {keys = [], onRemove, onIdentityChange, open = false}) {
  const inputs = {}, heading = el('strong'), metadata = el('span', {className: 'muted'});
  const enabledState = badge('', '');
  const node = el('details', {className: 'settings-profile', open, 'data-testid': 'ai-profile'});
  const content = el('div', {className: 'settings-profile-content'}), grid = el('div', {className: 'form-grid'});
  function input(name, label, attrs = {}, help) {
    const control = el('input', {value: profile[name] ?? '', ...attrs, 'data-testid': `profile-${name}`});
    inputs[name] = control; return field(label, control, help);
  }
  function choice(name, label, options, help) {
    const control = select(options, profile[name]); control.setAttribute('data-testid', `profile-${name}`);
    inputs[name] = control; return field(label, control, help);
  }
  const enabled = el('input', {type: 'checkbox', checked: profile.enabled, 'data-testid': 'profile-enabled'}); inputs.enabled = enabled;
  node.append(el('summary', {}, el('div', {}, heading, metadata, ' ', enabledState)), content);
  content.append(el('div', {className: 'detail-header'}, el('label', {className: 'settings-check'}, enabled, '启用此配置（重启后生效）'),
    button('删除配置', onRemove, {className: 'btn btn-danger', 'data-testid': 'profile-delete'})), grid);
  grid.append(input('id', '配置 ID', {required: true, maxLength: 64, pattern: '[a-z][a-z0-9_-]{0,63}'}, '小写字母开头，可使用数字、短横线和下划线。'),
    input('label', '显示名称', {maxLength: 200}), choice('protocol', '接口协议', protocols),
    input('base_url', 'API 地址前缀', {type: 'url', required: true, maxLength: 2048}, '填写 API 前缀，系统按协议追加具体接口；不填写密钥或查询参数。'),
    input('model', '模型 ID', {required: true, maxLength: 200}),
    input('api_key_ref', '密钥引用', {maxLength: 64, pattern: '[a-zA-Z][a-zA-Z0-9_-]{0,63}'}, '同一引用可供多套模型配置共用。'));
  const secret = el('input', {type: 'password', autocomplete: 'new-password', spellcheck: false, value: '', 'data-testid': 'profile-key'});
  const keyState = el('small', {className: 'muted', 'data-testid': 'profile-key-state'});
  const keyField = field('API 密钥', secret, '留空保留已有密钥；保存到本机 .env，不回显。同一引用的新密钥会用于所有共用此引用的配置。'); keyField.append(keyState);
  grid.append(keyField, choice('auth', '鉴权方式', [['auto', '按协议自动选择'], ['bearer', 'Bearer'], ['x_api_key', 'x-api-key'], ['x_goog_api_key', 'x-goog-api-key'], ['none', '无需密钥']]),
    input('max_output_tokens', '输出 Token 上限', {type: 'number', required: true, min: 1, max: 131072, step: 1}),
    input('timeout_seconds', '调用超时（秒）', {type: 'number', required: true, min: 0.01, max: 600, step: 'any'}));
  const response = choice('response_format', '结构化输出模式', [['prompt', '提示词约束 JSON'], ['json_object', 'JSON Object（仅 Chat）']]);
  const tokenLimit = choice('token_limit_field', 'Chat 输出限额字段', [['max_tokens', 'max_tokens'], ['max_completion_tokens', 'max_completion_tokens']]);
  const version = input('anthropic_version', 'Anthropic API 版本', {required: true, pattern: '\\d{4}-\\d{2}-\\d{2}'});
  const extra = el('textarea', {value: JSON.stringify(profile.extra_body ?? {}, null, 2), className: 'settings-extra mono', 'data-testid': 'profile-extra_body', spellcheck: false});
  inputs.extra_body = extra;
  content.append(el('details', {className: 'settings-advanced'}, el('summary', {}, '高级参数'),
    el('div', {className: 'form-grid'}, response, tokenLimit, version),
    field('扩展请求参数（JSON 对象）', extra, '保留供应商特有参数，例如 thinking；不能覆盖消息、模型、鉴权或输出限额。')));
  let previousId = inputs.id.value;
  function refreshHeader() {
    heading.textContent = inputs.label.value || inputs.id.value || '未命名配置'; metadata.textContent = ` ${inputs.id.value} · ${inputs.model.value}`;
    enabledState.textContent = enabled.checked ? '已启用' : '已停用'; enabledState.className = `badge ${enabled.checked ? 'success' : ''}`;
  }
  function refreshKey() {
    const key = keys.find(item => item.ref.toLowerCase() === inputs.api_key_ref.value.trim().toLowerCase());
    secret.disabled = Boolean(key?.environment_managed);
    if (key?.environment_managed) secret.value = '';
    keyState.textContent = key?.environment_managed ? '由系统环境变量管理，请在运行环境中修改。' : key?.configured ? '已配置（不会显示原值）' : '尚未配置';
  }
  function refreshProtocol(changed = false) {
    const chat = inputs.protocol.value === 'openai_chat';
    inputs.response_format.querySelector('option[value="json_object"]').disabled = !chat;
    tokenLimit.hidden = !chat; version.hidden = inputs.protocol.value !== 'anthropic_messages';
    if (changed && !chat) {inputs.response_format.value = 'prompt'; inputs.token_limit_field.value = 'max_tokens';}
  }
  inputs.id.addEventListener('input', () => {onIdentityChange(previousId, inputs.id.value); previousId = inputs.id.value; refreshHeader();});
  inputs.label.addEventListener('input', () => {onIdentityChange(previousId, inputs.id.value); refreshHeader();});
  inputs.model.addEventListener('input', refreshHeader);
  enabled.addEventListener('change', refreshHeader);
  inputs.api_key_ref.addEventListener('input', refreshKey);
  inputs.protocol.addEventListener('change', () => refreshProtocol(true));
  refreshHeader(); refreshKey(); refreshProtocol();
  return {node, id: () => inputs.id.value, label: () => inputs.label.value,
    clearSecret: () => {secret.value = '';},
    collect: () => {
      let extraBody;
      try {extraBody = JSON.parse(extra.value);} catch {throw new Error('扩展请求参数必须是有效的 JSON 对象。');}
      if (!extraBody || Array.isArray(extraBody) || typeof extraBody !== 'object') throw new Error('扩展请求参数必须是 JSON 对象。');
      return {id: inputs.id.value, label: inputs.label.value || null, enabled: enabled.checked, protocol: inputs.protocol.value,
        base_url: inputs.base_url.value, model: inputs.model.value, api_key_ref: inputs.api_key_ref.value.trim() || null,
        auth: inputs.auth.value, response_format: inputs.response_format.value, max_output_tokens: inputs.max_output_tokens.valueAsNumber,
        timeout_seconds: inputs.timeout_seconds.valueAsNumber, token_limit_field: inputs.token_limit_field.value,
        anthropic_version: inputs.anthropic_version.value, extra_body: extraBody};
    },
    secret: () => ({ref: inputs.api_key_ref.value.trim(), value: secret.disabled ? '' : secret.value})};
}
