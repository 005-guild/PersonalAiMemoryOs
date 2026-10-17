import {confirmAction, el} from './ui.js';

// No privileged JavaScript bridge and no eval: native code dispatches an event,
// then reads the Boolean response through WebView2's ExecuteScriptAsync.
export function installDesktopLifecycle(isDirty, clearDirty) {
  let asking = false;
  Object.defineProperty(window, 'memoryOsHasUnsavedChanges', {value: isDirty});
  window.memoryOsDesktopCloseResult = null;
  window.memoryOsDesktopClosePending = false;
  window.addEventListener('memory-os-desktop-request-close', async () => {
    if (asking) return;
    asking = true;
    window.memoryOsDesktopClosePending = true;
    try {
      const allowed = !isDirty() || await confirmAction('有未保存的修改。退出后将丢失这些修改，是否继续？',
        {title: '退出应用', confirmLabel: '退出'});
      if (allowed) clearDirty();
      window.memoryOsDesktopCloseResult = allowed;
    } finally {asking = false; window.memoryOsDesktopClosePending = false;}
  });
  let overlay;
  window.addEventListener('memory-os-desktop-stopping', () => {
    clearDirty();
    if (overlay) return;
    document.querySelectorAll('.sidebar,.workspace').forEach(node => {node.inert = true;});
    overlay = el('div', {className: 'desktop-shutdown', role: 'status'}, el('div', {className: 'card'},
      el('h2', {}, '正在安全退出'), el('p', {}, '正在等待当前请求与同步完成，请稍候。')));
    document.body.append(overlay);
  });
  window.addEventListener('memory-os-desktop-long-shutdown', () => {
    if (overlay) overlay.querySelector('p').textContent = '任务仍在收尾，程序会继续等待完成，不会强制终止。可查看 logs/memory-os.log。';
  });
}
