// Read only explicitly selected Markdown files. Paths are display metadata, never server paths.
export const MAX_IMPORT_BYTES = 10 * 1024 * 1024;
export const MAX_MARKDOWN_FILES = 1000;

export function markdownSelection(files) {
  const all = Array.from(files), markdown = [], skipped = {readme: 0, other: 0};
  for (const file of all) {
    const path = file.webkitRelativePath || file.name;
    const name = path.split(/[\\/]/).at(-1);
    if (!/\.md$/i.test(name)) skipped.other++;
    else if (/^readme\.md$/i.test(name)) skipped.readme++;
    else markdown.push({file, relative_path: path});
  }
  const size = markdown.reduce((total, {file}) => total + file.size, 0);
  if (markdown.length > MAX_MARKDOWN_FILES) throw new Error('Markdown 文件超过 1,000 个，请分次选择。');
  if (size > MAX_IMPORT_BYTES) throw new Error('Markdown 原始文件总大小超过 10 MiB，请分次选择。');
  if (!markdown.length) throw new Error('没有可导入的 Markdown 文件（README.md 和非 Markdown 文件会跳过）。');
  return {markdown, size, skipped, selected: all.length};
}

export async function readMarkdownSelection(selection, {isCurrent, onProgress = () => {}}) {
  const files = [], errors = [];
  for (let index = 0; index < selection.markdown.length; index++) {
    if (!isCurrent()) return null;
    const {file, relative_path} = selection.markdown[index];
    try {
      const raw = await file.arrayBuffer();
      if (!isCurrent()) return null;
      const content = new TextDecoder('utf-8', {fatal: true}).decode(raw);
      files.push({relative_path, content});
    } catch (error) {
      if (!isCurrent()) return null;
      errors.push({relative_path, message: error?.name === 'TypeError' ? '不是有效 UTF-8 文本。' : '无法读取此文件，请检查文件是否仍可访问。'});
    }
    onProgress(index + 1, selection.markdown.length);
  }
  if (!isCurrent()) return null;
  if (!files.length) return {bytes: null, files: 0, errors};
  const bytes = new TextEncoder().encode(JSON.stringify({files}));
  if (bytes.byteLength > MAX_IMPORT_BYTES) throw new Error('序列化后的请求超过 10 MiB，请减少文件后重新选择；没有截断或提交正文。');
  return {bytes, files: files.length, errors};
}
