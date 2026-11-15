// Legacy routes retain their identifiers; navigation groups describe ownership.
export const primary = [['reading','阅读书架','▧'],['search','搜索问答','⌕'],['workbench','整理工作台','▥'],['settings','设置','⚙']];
export const routes = [
  ['reading','阅读书架','reading','reading'],['search','搜索问答','search','search'],
  ['workbench','整理工作台','workbench','workbench'],['settings','设置','settings','settings'],
  ['sources','资料库','content','workbench'],['knowledge','笔记管理','content','workbench'],
  ['imports','资料导入','imports','workbench'],['organization','收藏整理','organization','workbench'],
  ['processing','AI 分析','processing','workbench'],['drafts','草稿箱','drafts','workbench'],
  ['prompts','提示词中心','prompts','settings'],['system','系统维护','system','settings'],
];
export const sublabels = {ai:'AI 模型',rag:'向量检索',zhihu:'知乎同步',storage:'存储与关于',
  config:'整理规则与预算',records:'处理记录',review:'样本审核',jobs:'任务记录',
  sync:'文件同步',index:'知识索引',conflicts:'同步冲突',history:'分析历史',browse:'全部笔记',topics:'全部主题'};
