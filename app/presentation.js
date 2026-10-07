// Ordinary-user labels; keep this fallback for historical conversations.
export const categories = {
  food: ['餐饮','♨'], drinks: ['咖啡饮品','◒'], retail: ['便利购物','▣'],
  services: ['生活服务','◇'], sports: ['体育场馆','◎'], campus: ['校园公共设施','⌂'], other: ['其他地点','·']
};
const mapping={canteen:'food',restaurant:'food',snack:'food',coffee:'drinks',drink:'drinks',retail:'retail',supermarket:'retail',service:'services',finance:'services',sports:'sports',building:'campus',gate:'campus',library:'campus',dormitory:'campus'};
export function cleanAddress(value='') {
  return String(value).trim().replace(/^(?:百度|原始)地址[：:]\s*/,'').split(/[；;\n。]|\s+[|｜]\s+/).filter(s=>!/(BD[-–]?09|GCJ|WGS|EPSG|UTM|GF2|坐标|白模|模型|轮廓|匹配|投影|配准|关联|吸附|截图|实测|纠偏|核验|层高|楼高|待核|用户确认|用户补充|官方资料|来源|采集|几何|建筑说明|https?:\/\/|[A-Z]:[\\/])/i.test(s)).join('；').slice(0,240);
}
export function present(card, directory=[]) {
  const known=directory.find(p=>p.id===card.poi_id||p.id===card.id);
  const category=known?.display_category||card.display_category||mapping[card.category]||(card.type==='food'?'food':'other');
  const collection={food:'菜单',drinks:'饮品',retail:'商品'}[category];
  return {...card,display_category:category,category_label:categories[category]?.[0]||'其他地点',collection_label:collection,
    location:known?known.location:card.location,display_anchor:known?known.display_anchor:card.display_anchor,
    map_reference:known?known.map_reference:card.map_reference,floor:known?known.floor:card.floor,
    name:known&&card.type==='place'?known.name:card.name,
    hours_notes:String(card.hours_notes||'').split(/[；;。\n]/).filter(s=>!/用户.*(?:确认|补充|提供)|原ID|沿用|合并|快照|批次|字段|记录ID|审核|坐标|匹配|建筑关联/i.test(s)).join('；'),
    address:known?known.address:cleanAddress(card.address),hours_label:['sports','campus'].includes(category)?'开放时间':'营业时间',
    unknown:(card.unknown||[]).map(v=>['sports','campus'].includes(category)?v.replace('营业时间','开放时段'):v),
    menu:collection?card.menu:undefined};
}
export function messageText(message,directory=[]) {
  if(message.cards?.length&&message.cards.every(c=>c.type!=='schedule'&&!present(c,directory).collection_label)&&/^菜单为记录资料/.test(message.content||''))return '开放与服务信息以现场公告为准。';
  return message.content||'正在准备结果…';
}
export function errorInfo(error) {
  if(error?.code)return {message:error.message||error.text||'本轮服务暂时不可用。',code:error.code,retryable:error.retryable!==false};
  if(error?.name==='AbortError')return {message:'已停止等待，已有结果保留。',code:'CANCELLED',retryable:false};
  const raw=typeof error==='string'?error:error?.message||'';
  if(/Failed to fetch|NetworkError|Load failed|连接.*中断|fetch/i.test(raw))return {message:'连接中断，尚未确认本轮完成。请检查本地服务后重试；已有资料和对话仍保留。',code:'NETWORK',retryable:true};
  return {message:raw||'暂时无法完成请求，请稍后重试。',code:'SERVICE_ERROR',retryable:true};
}
