import {el, button, select, field, notice, confirmAction} from '../ui.js';
import {profileEditor} from './settings-profile.js';
import {providerPresets, profileFromPreset} from './settings-presets.js';
import {localPagination} from './list-pagination.js';

export function settingsEditor(document, {onSave, onDirty, alive}) {
  const form = el('form', {className: 'settings-form', autocomplete: 'off'}), controls = el('fieldset', {className: 'settings-fields'});
  const enabled = el('input', {type: 'checkbox', checked: document.enabled, 'data-testid': 'ai-enabled'});
  const defaultProfile = select([], ''), profiles = [], list = el('div', {className: 'stack'});
  defaultProfile.setAttribute('data-testid', 'ai-default-profile'); defaultProfile.setAttribute('aria-label', '默认模型配置');
  const preset = select(providerPresets.map(([id, label]) => [id, label]), 'compatible'); preset.setAttribute('aria-label', '新配置模板');
  const errors = el('div');
  let defaultId = document.default_profile || '';
  let pagination;
  function redraw() {pagination = localPagination(profiles, rows => el('div', {className:'stack'}, ...rows.map(profile=>profile.node)), {label:'生成模型配置分页',key:'settings-ai-profiles'});list.replaceChildren(pagination);}
  defaultProfile.addEventListener('change', () => {defaultId = defaultProfile.value;});
  function refreshDefault(before, after) {
    if (before && defaultId === before) defaultId = after;
    defaultProfile.replaceChildren(el('option', {value: ''}, '不指定默认配置'), ...profiles.map(profile => el('option', {value: profile.id()}, profile.label() || profile.id() || '未命名配置')));
    defaultProfile.value = profiles.some(profile => profile.id() === defaultId) ? defaultId : '';
  }
  function add(profile, open = false) {
    let editor;
    editor = profileEditor(profile, {keys: document.keys, open,
      onIdentityChange: refreshDefault,
      onRemove: async () => {
        if (!await confirmAction('删除这套模型配置？已有处理记录和笔记不会删除，已有密钥仍保留在本机。', {title: '删除模型配置', confirmLabel: '删除配置'}) || !alive()) return;
        const index = profiles.indexOf(editor); if (index < 0) return;
        if (defaultId === editor.id()) defaultId = '';
        editor.clearSecret(); profiles.splice(index, 1); editor.node.remove(); refreshDefault(); redraw(); onDirty();
      }});
    profiles.push(editor); refreshDefault();
  }
  const addButton = button('＋ 新建模型配置', () => {
    if (profiles.length >= 100) {errors.replaceChildren(notice('最多保留 100 套模型配置。', 'warning')); return;}
    add(profileFromPreset(preset.value, profiles.map(profile => profile.id())), true); redraw(); pagination.reveal(profiles.length-1); onDirty();
  }, {'data-testid': 'ai-add-profile'});
  const save = el('button', {type: 'submit', className: 'btn btn-primary', 'data-testid': 'ai-settings-save'}, '保存设置');
  controls.append(el('section', {className: 'card stack'}, el('h2', {}, '文本生成 AI'),
    el('label', {className: 'settings-check'}, enabled, '开启文本生成 AI（保存并重启后生效）'),
    field('默认模型配置', defaultProfile), notice('保存只更新本机配置，不调用模型。请完全退出应用后重新打开；本页不会开启 RAG。')),
    el('section', {className: 'card stack'}, el('div', {className: 'detail-header'}, el('h2', {}, '模型配置'),
      el('div', {className: 'page-actions'}, preset, addButton)),
      el('p', {className: 'muted'}, '可为同一服务配置多个模型。模板来自应用内置示例，模型 ID 请按服务商账户填写。'), list),
    errors, el('div', {className: 'page-actions'}, save));
  form.append(controls);
  for (const profile of document.profiles) add(profile);
  redraw();
  refreshDefault();
  form.addEventListener('input', onDirty); form.addEventListener('change', onDirty);
  form.addEventListener('submit', event => {event.preventDefault(); onSave();});
  // Read-only deployments still allow paging through every configuration.
  controls.disabled = false;
  if (!document.editable) {
    for (const node of form.querySelectorAll('input,select,textarea,button')) if (!node.closest('nav')) node.disabled = true;
    for (const profile of profiles) for (const node of profile.node.querySelectorAll('input,select,textarea,button')) node.disabled = true;
  }
  return {node: form, valid: () => {
    for (let index=0;index<profiles.length;index++) for (const control of profiles[index].node.querySelectorAll('input,select,textarea')) if (!control.checkValidity()) {
      pagination.reveal(index); profiles[index].node.open=true;let ancestor=control.parentElement;
      while(ancestor&&ancestor!==form){if(ancestor.tagName==='DETAILS')ancestor.open=true;ancestor=ancestor.parentElement;}
      control.reportValidity();return false;
    }
    for (const control of form.querySelectorAll('input,select,textarea')) if (!control.checkValidity()) {
      let ancestor = control.parentElement;
      while (ancestor && ancestor !== form) {if (ancestor.tagName === 'DETAILS') ancestor.open = true; ancestor = ancestor.parentElement;}
    }
    return form.reportValidity();
  },
    busy: value => {controls.disabled = value; save.textContent = value ? '正在保存…' : '保存设置';},
    clearSecrets: () => profiles.forEach(profile => profile.clearSecret()),
    collect: () => {
      errors.replaceChildren();
      const values = profiles.map(profile => profile.collect()), ids = values.map(profile => profile.id);
      if (new Set(ids).size !== ids.length) throw new Error('配置 ID 不能重复，请为每套配置填写不同 ID。');
      if (enabled.checked && !defaultProfile.value) throw new Error('开启 AI 前，请选择默认模型配置。');
      const updates = new Map();
      for (const profile of profiles) {
        const {ref, value} = profile.secret(); if (!value) continue;
        if (!ref) throw new Error('填写 API 密钥时，请同时填写密钥引用。');
        const identity = ref.toLowerCase();
        if (updates.has(identity) && updates.get(identity).value !== value) throw new Error('同一密钥引用填写了不同新值，请保持一致。');
        updates.set(identity, {ref, value});
      }
      return {enabled: enabled.checked, default_profile: defaultProfile.value || null, profiles: values, key_updates: [...updates.values()]};
    }, showLocalError: message => errors.replaceChildren(notice(message, 'warning'))};
}
