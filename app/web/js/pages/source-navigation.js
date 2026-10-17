export function positivePage(value, fallback = 1) {
  return /^[1-9]\d*$/.test(String(value)) && Number.isSafeInteger(Number(value)) ? Number(value) : fallback;
}
export function sourceState(value) {return ['active','deleted','all'].includes(value) ? value : 'active';}
export function pageSize(value, choices, fallback) {const size = Number(value); return choices.includes(size) ? size : fallback;}
export function sourceHash(path, values) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value !== '' && value !== null && value !== undefined) params.set(key, String(value));
  return `#/sources${path ? '/' + path : ''}${params.size ? '?' + params : ''}`;
}
export function sourceReturn(value, fallback = '#/sources', allowGroup = true) {
  if (typeof value !== 'string' || !value.startsWith('#/') || value.length > 16000) return fallback;
  try {
    const url = new URL(value.slice(1), location.origin);
    return url.origin === location.origin && (url.pathname === '/sources' || (allowGroup && url.pathname === '/sources/group')) ? value : fallback;
  } catch {return fallback;}
}
export function sourceKind(source) {
  try {
    const url = new URL(source.url);
    const mainHost = ['zhihu.com', 'www.zhihu.com'].includes(url.hostname);
    if (mainHost && /\/answer\/\d+\/?$/.test(url.pathname)) return '回答';
    if (url.hostname === 'zhuanlan.zhihu.com' && /^\/p\/\d+\/?$/.test(url.pathname)) return '文章';
    if (mainHost && /\/pin\/\d+\/?$/.test(url.pathname)) return '想法';
  } catch {}
  return source.source_type === 'manual' ? '手动资料' : source.source_type || '资料';
}
