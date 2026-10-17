import {pageHeading} from '../ui.js';
import {promptSettings} from './prompt-settings.js';
export function mount(container, context) {
  const mountedHash = location.hash; let disposed = false;
  const prompts = promptSettings(context, {alive: () => !disposed && location.hash === mountedHash, onDirty: context.setDirty});
  container.append(pageHeading('提示词中心', '管理笔记解析与 RAG 问答的独立模板和版本。'), prompts.element);
  return () => {disposed = true; prompts.dispose();};
}
