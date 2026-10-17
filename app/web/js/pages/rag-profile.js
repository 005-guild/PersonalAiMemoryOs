import {el, button, field, select, notice} from '../ui.js';

export function ragProfile(profile, {keys = [], onRemove, onIdentityChange}) {
  const node = el('details', {className: 'settings-profile', 'data-testid': 'rag-profile'}), heading = el('strong'), grid = el('div', {className: 'form-grid'}), controls = {};
  function input(key, label, attrs = {}, help) {const control = el('input', {value: profile[key] ?? '', ...attrs, 'data-testid': `embedding-${key}`}); controls[key] = control; return field(label, control, help);}
  const enabled = el('input', {type: 'checkbox', checked: profile.enabled !== false});
  const auth = select([['auto','Bearer（默认）'],['bearer','Bearer'],['x_api_key','x-api-key'],['x_goog_api_key','x-goog-api-key'],['none','无需密钥']], profile.auth || 'auto');
  const secret = el('input', {type: 'password', autocomplete: 'new-password', spellcheck: false, 'data-testid': 'embedding-key'}), keyState = el('small', {className: 'muted'});
  grid.append(input('id','配置 ID',{required:true,pattern:'[a-z][a-z0-9_-]{0,63}',maxLength:64}),input('label','显示名称',{maxLength:200}),
    input('base_url','Embedding API 地址前缀',{type:'url',required:true,maxLength:2048},'系统追加 /embeddings；生成模型地址与向量模型可以不同。'),
    input('model','向量模型 ID',{required:true,maxLength:200}),input('dimension','实际向量维度',{type:'number',required:true,min:1,max:65536,step:1},'必须与服务实际输出一致。不要根据模型名称猜测。'),
    input('api_key_ref','密钥引用',{maxLength:64,pattern:'[a-zA-Z][a-zA-Z0-9_-]{0,63}'}),field('鉴权方式',auth),field('API 密钥',secret,'留空保留已有值；仅写入本机 .env，不回显。'),keyState,
    input('model_revision','模型 revision（可选）',{maxLength:200}),input('request_dimensions','请求降维（可选）',{type:'number',min:1,max:65536,step:1},'只有填写时才向服务发送 dimensions，需服务支持。'),
    input('timeout_seconds','调用超时（秒）',{type:'number',required:true,min:0.01,max:600,step:'any'}),input('batch_size','每批文本块数',{type:'number',required:true,min:1,max:8,step:1}));
  const extra = el('textarea',{className:'settings-extra mono',value:JSON.stringify(profile.extra_body || {},null,2),'data-testid':'embedding-extra'});
  node.append(el('summary',{},heading),el('div',{className:'settings-profile-content stack'},el('div',{className:'detail-header'},el('label',{className:'settings-check'},enabled,'启用此配置'),button('删除向量配置',onRemove,{className:'btn btn-danger'})),
    grid,el('details',{className:'settings-advanced'},el('summary',{},'高级扩展参数'),field('扩展请求参数（JSON 对象）',extra,'不可覆盖模型、输入、鉴权、向量格式等固定字段。'))));
  let previousId=controls.id.value;
  function refresh() {heading.textContent=`${controls.label.value || controls.id.value || '新建向量配置'} · ${controls.model.value || '未填模型'}`;onIdentityChange(previousId,controls.id.value);previousId=controls.id.value;
    const key=keys.find(item=>item.ref.toLowerCase()===controls.api_key_ref.value.trim().toLowerCase());secret.disabled=Boolean(key?.environment_managed);if(secret.disabled)secret.value='';
    keyState.textContent=key?.environment_managed?'密钥由运行环境管理。':key?.configured?'密钥已配置（不会回显）。':'尚未配置密钥。';}
  for(const input of [controls.id,controls.label,controls.model,controls.api_key_ref])input.addEventListener('input',refresh); refresh();
  return {node,id:()=>controls.id.value,label:()=>controls.label.value,clearSecret:()=>{secret.value='';},secret:()=>({ref:controls.api_key_ref.value.trim(),value:secret.disabled?'':secret.value}),
    collect() {let extras;try {extras=JSON.parse(extra.value);}catch {throw Error('向量扩展参数不是有效 JSON。');}if(!extras||Array.isArray(extras)||typeof extras!=='object')throw Error('向量扩展参数必须为 JSON 对象。');
      return {id:controls.id.value,label:controls.label.value||null,enabled:enabled.checked,protocol:'openai_embeddings',base_url:controls.base_url.value,model:controls.model.value,model_revision:controls.model_revision.value||null,
        dimension:controls.dimension.valueAsNumber,api_key_ref:controls.api_key_ref.value.trim()||null,auth:auth.value,request_dimensions:controls.request_dimensions.value?controls.request_dimensions.valueAsNumber:null,
        timeout_seconds:controls.timeout_seconds.valueAsNumber,batch_size:controls.batch_size.valueAsNumber,extra_body:extras};}};
}
