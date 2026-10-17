// Local templates match the bundled provider example. Creating a profile never calls a provider.
export const protocols = [['openai_chat', 'OpenAI 兼容 · Chat Completions'], ['openai_responses', 'OpenAI · Responses'],
  ['anthropic_messages', 'Anthropic · Claude Messages'], ['gemini_generate_content', 'Google · Gemini']];
export const providerPresets = [
  ['compatible', '通用 OpenAI 兼容', {label: '通用兼容服务', protocol: 'openai_chat', base_url: 'http://127.0.0.1:11434/v1', api_key_ref: 'compatible'}],
  ['deepseek', 'DeepSeek', {label: 'DeepSeek', protocol: 'openai_chat', base_url: 'https://api.deepseek.com', model: 'deepseek-flash', api_key_ref: 'deepseek', response_format: 'json_object', extra_body: {thinking: {type: 'disabled'}}}],
  ['responses', 'OpenAI Responses', {label: 'OpenAI Responses', protocol: 'openai_responses', base_url: 'https://api.openai.com/v1', api_key_ref: 'openai'}],
  ['claude', 'Claude', {label: 'Anthropic Claude', protocol: 'anthropic_messages', base_url: 'https://api.anthropic.com/v1', api_key_ref: 'anthropic'}],
  ['gemini', 'Gemini', {label: 'Google Gemini', protocol: 'gemini_generate_content', base_url: 'https://generativelanguage.googleapis.com/v1beta', api_key_ref: 'gemini'}],
];
export function profileFromPreset(key, usedIds) {
  const [, , preset] = providerPresets.find(([id]) => id === key) || providerPresets[0];
  let id = key, suffix = 2;
  while (usedIds.includes(id)) id = `${key}-${suffix++}`;
  return {id, label: null, enabled: false, protocol: 'openai_chat', base_url: '', model: 'replace-with-your-model', api_key_ref: null,
    auth: 'auto', response_format: 'prompt', max_output_tokens: 4096, timeout_seconds: 90, token_limit_field: 'max_tokens',
    anthropic_version: '2023-06-01', extra_body: {}, ...structuredClone(preset)};
}
