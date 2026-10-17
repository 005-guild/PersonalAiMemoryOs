import {api} from '../api.js';
import {notice, confirmAction} from '../ui.js';

export async function offerRestart(value, scope, messages, alive, hasDirty = () => false) {
  if (!value.restart_required || !alive()) return;
  if (!value.desktop?.restart_supported) {messages.append(notice('当前为 Python／Docker 运行方式，请停止并重新启动服务使配置生效；刷新网页不会重启后端。')); return;}
  const accepted = await confirmAction('已保存配置需要重启应用。现在重启会等待在途任务收尾；选择稍后则保持当前运行状态。', {title: '设置已保存', confirmLabel: '现在重启', cancelLabel: '稍后'});
  if (!accepted || !alive()) return;
  if (hasDirty()) {messages.append(notice('还有未保存修改，请先保存或取消这些修改，再退出重启。', 'warning')); return;}
  try {await api('/api/v1/desktop/restart', {method: 'POST', headers: {'X-Configuration-Token': value.csrf_token}, body: {expected_revision: value.revision, scope}});
    if (alive()) messages.append(notice('正在等待任务结束并重启应用…'));
  } catch {if (alive()) messages.append(notice('未确认重启成功，请检查服务后手动退出重开；没有自动重试。', 'error'));}
}
