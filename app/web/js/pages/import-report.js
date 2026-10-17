import {el, button, notice, badge} from '../ui.js';
import {labelStatus, dataTable} from './workflow-utils.js';

// Keep downloads independent of input files, even if an unexpected server field contains content.
export function publicImportReport(value) {
  const output = {};
  for (const key of ['dry_run','total','processed','created','skipped','invalid','would_create','failed']) {
    if (value[key] !== undefined) output[key] = value[key];
  }
  output.items = (value.items || []).map(item => {
    const row = {};
    for (const key of ['index','status','reason','resource_type','external_id','source_id','version',
      'relative_path','title','author','url','differing_fields','matched_source_ids','warnings']) {
      if (item[key] !== undefined) row[key] = item[key];
    }
    row.errors = (item.errors || []).map(error => ({field: error.field, message: error.message}));
    return row;
  });
  return output;
}

export function showImportReport(target, value, {markdown = false, download}) {
  let offset = 0;
  const entries = value.items || [], table = el('div'), paging = el('div');
  function render() {
    const rows = entries.slice(offset, offset + 50).map(item => {
      const itemLabel = markdown ? el('div', {}, el('div', {className: 'record-title'}, item.relative_path || '未知文件'), el('small', {className: 'muted'}, `#${item.index + 1}`)) : `#${item.index + 1}`;
      const details = el('div', {}, el('div', {}, item.reason),
        item.differing_fields?.length ? el('p', {className: 'muted'}, `差异字段：${item.differing_fields.join('、')}`) : null,
        ...(item.errors || []).map(error => el('div', {}, `${error.field}：${error.message}`)),
        ...(item.warnings || []).map(warning => el('div', {className: 'muted'}, `提示：${warning}`)),
        item.matched_source_ids?.length > 1 && el('p', {}, `匹配到 ${item.matched_source_ids.length} 条已有资料，请人工确认。`));
      return el('tr', {}, el('td', {}, itemLabel), ...(markdown ? [
        el('td', {}, el('div', {className: 'record-title'}, item.title || '—'), el('small', {className: 'muted'}, item.author || '未知作者'),
          item.url && el('details', {}, el('summary', {}, '原文链接'), el('code', {}, item.url))),
        el('td', {}, ({answer: '回答', article: '文章', pin: '想法'})[item.resource_type] || '—')
      ] : []), el('td', {}, badge(labelStatus(item.status))), el('td', {}, details),
      el('td', {}, item.source_id ? el('a', {href: `#/sources/${item.source_id}`}, `查看资料 · v${item.version}`) : '—'));
    });
    table.replaceChildren(dataTable(markdown ? ['文件', '标题 / 作者', '类型', '结果', '说明 / 差异', '资料'] : ['条目', '结果', '说明 / 差异', '资料'], rows));
    paging.replaceChildren();
    if (entries.length > 50) paging.append(el('div', {className: 'pagination'},
      el('span', {}, `报告共 ${entries.length} 条 · 第 ${Math.floor(offset / 50) + 1} 页`),
      el('div', {className: 'pagination-controls'}, button('报告上一页', () => {offset -= 50; render();}, {disabled: offset === 0}),
        button('报告下一页', () => {offset += 50; render();}, {disabled: offset + 50 >= entries.length}))));
  }
  target.replaceChildren(el('div', {className: 'card stack'},
    el('div', {className: 'detail-header'}, el('h2', {}, value.dry_run ? '预演结果' : '导入报告'), button('下载报告', download)),
    el('div', {className: 'page-actions'}, ...[['总数', value.total], ['预计创建', value.would_create], ['已创建', value.created], ['跳过', value.skipped], ['无效', value.invalid], ['失败', value.failed]].map(([key, count]) => badge(`${key} ${count || 0}`))),
    value.local_read_failed > 0 && notice(`本报告的计数仅包含已上传文件；另有 ${value.local_read_failed} 个文件本地读取失败，未上传。`, 'warning'),
    value.processed < value.total && notice(`已处理 ${value.processed}/${value.total} 条。服务中断后的未处理项尚未提交。`, 'warning'), table, paging));
  render();
}
