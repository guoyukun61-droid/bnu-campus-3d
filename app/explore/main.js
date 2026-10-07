import {GROUPS,filterPlaces,inModel,positionNote,reduceState,selectionIds,normalizePlace,matchesCategory,directorySelection,pagePlaces,areaGroups} from './state.js';
import {request,chatStream} from './api.js';
import {present,errorInfo} from '/presentation.js';
import {openHistory,saveConversation,listConversations} from '/history.js';
const $=id=>document.getElementById(id),node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const button=(text,fn,cls='')=>{const b=node('button',text,cls);b.type='button';b.onclick=fn;return b;};
const ICONS={building:'M3 21h18M5 21V5l7-3 7 3v16M9 7h1M14 7h1M9 11h1M14 11h1M10 21v-6h4v6',food:'M5 3v6M2 3v4c0 4 6 4 6 0V3M5 11v10M16 3c-3 3-4 7-1 9h3V3h-2M18 12v9',drinks:'M4 8h12v8a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8ZM16 9h2a3 3 0 0 1 0 6h-2M7 3v2M12 3v2',retail:'M4 7h16l-1 14H5L4 7ZM8 8V6a4 4 0 0 1 8 0v2',sports:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2v20M5 5l14 14M19 5 5 19',services:'m14 3-3 3 2 3 3-3c2 5-2 8-6 6l-6 7-3-3 7-6C6 6 9 2 14 3Z',campus:'m2 8 10-5 10 5-10 5L2 8ZM6 10v7c3 3 9 3 12 0v-7M22 8v8',all:'M3 3h6v6H3V3ZM15 3h6v6h-6V3ZM3 15h6v6H3v-6ZM15 15h6v6h-6v-6',clock:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 6v6l4 2',pin:'M12 22S4 14 4 9a8 8 0 1 1 16 0c0 5-8 13-8 13ZM12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6'};
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS(svg.namespaceURI,'path');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');path.setAttribute('d',ICONS[name]||ICONS.pin);svg.append(path);return svg;}
let state={category:'',panel:null,selected:null,query:'',area:'',kind:'',limit:40},rows=[],buildings=[],locations=[],map=null,db=null,history=[],active=null,detailsToken=0,art=true,textureReady=false;
const fresh=()=>({id:crypto.randomUUID(),title:'校园漫游',conditions:{},mode:'real',messages:[],updated_at:new Date().toISOString()});let conversation=fresh();
const sourceLabel=s=>s==='simulated'?'模拟数据':s==='menu_photo'?'菜单照片':s==='baidu_place_v2'?'百度地点资料':s==='user_reported'?'用户补充资料':'已发布资料';
const keyboard=()=>document.body.classList.contains('keyboard');
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');let panelMotion=null;
function cancelPanelMotion(){panelMotion?.cancel();panelMotion=null;}
reducedMotion.addEventListener('change',cancelPanelMotion);document.addEventListener('keydown',cancelPanelMotion);
document.addEventListener('keydown',e=>{document.body.classList.add('keyboard');map?.stopRoam();if(e.key==='Escape'){if($('settings').open){$('settings').open=false;$('settings').querySelector('summary').focus();}else closePanel();}});document.addEventListener('pointerdown',e=>{document.body.classList.remove('keyboard');if(!e.target.closest('#settings'))$('settings').open=false;if(!e.target.closest('#roam-toggle'))map?.stopRoam();});document.addEventListener('input',()=>map?.stopRoam());
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,4800);}
function hideIntro(){$('intro').dataset.hidden='true';}
function openPanel(title,kicker='校园导览'){const previous=$('panel').dataset.view,wasOpen=$('panel').dataset.open==='true';cancelPanelMotion();hideIntro();$('settings').open=false;$('panel').dataset.open='true';$('panel').dataset.view=state.panel||'list';$('panel').dataset.expanded='false';$('panel-size').setAttribute('aria-expanded','false');$('panel-size').textContent='展开';$('panel').inert=false;$('panel-title').textContent=title;$('panel-kicker').textContent=kicker;$('panel-body').scrollTop=0;document.body.dataset.panel='open';map?.setPanel(true);
  if(wasOpen&&previous!==state.panel&&['list','detail','building','cluster'].includes(previous)&&!keyboard()&&!reducedMotion.matches){const x=state.panel==='list'?-6:6;panelMotion=$('panel-body').animate([{opacity:.5,transform:`translateX(${x}px)`},{opacity:1,transform:'translateX(0)'}],{duration:160,easing:'cubic-bezier(.22,1,.36,1)'});}}
function closePanel(){cancelPanelMotion();state=reduceState(state,{type:'close'});$('panel').dataset.open='false';$('panel').inert=true;document.body.dataset.panel='closed';map?.setPanel(false);detailsToken++;if($('panel').contains(document.activeElement))$('browse').focus();}
$('close-panel').onclick=closePanel;
async function save(){conversation.updated_at=new Date().toISOString();if(!db)return;try{await saveConversation(db,conversation);history=await listConversations(db);}catch{toast('浏览器未能保存对话，离开前请保留需要的信息。');}}
function updateArtNote(){$('art-note').textContent=art?(textureReady?'示意上色 · 3栋纸感材质样例，非真实立面':'示意上色 · 材质未就绪，使用纯色回退'):'白模基准 · 标记高度不代表店铺楼层';}
const scenePromise=import('./scene.js').then(({createScene})=>{map=createScene($('scene'),{
  onSelect:(id,siblings)=>siblings?.length>1?showCluster(siblings):showPlace(id),onStatus:text=>$('scene-status').textContent=text,onInteraction:hideIntro,
  onBuilding:id=>showBuilding(id),onRoam:active=>{$('roam-toggle').textContent=active?'暂停漫游':'继续漫游';$('roam-toggle').setAttribute('aria-pressed',String(active));},
  onBearing:angle=>$('compass').style.transform=`rotate(${angle}deg)`,
  onArtStatus:s=>{textureReady=s==='texture-ready';updateArtNote();}
});map.setArt(art);map.setPanel(!!state.panel);if(rows.length){map.setRows(rows);if(state.category)map.filter(directorySelection(rows,state).map(p=>p.id));}return map;}).catch(()=>{$('scene-status').textContent='三维暂不可用；仍可通过分类清单查看地点与使用文字服务。';});
function setCategory(value){state=reduceState(state,{type:'category',value});$('pin-caption').hidden=true;for(const b of $('categories').children)b.setAttribute('aria-pressed',String(b.dataset.category===value));drawList();}
for(const [key,title] of GROUPS){const b=button('',()=>setCategory(key));b.append(icon(key==='eating'?'food':key||'building'),node('span',title));b.dataset.category=key;b.setAttribute('aria-pressed',String(!key));$('categories').append(b);}
$('start-food').onclick=()=>setCategory('eating');$('browse').onclick=()=>{state.panel='list';drawList();};
$('start-buildings').onclick=()=>setCategory('');
$('panel-size').onclick=()=>{const expanded=$('panel').dataset.expanded!=='true';$('panel').dataset.expanded=String(expanded);$('panel-size').setAttribute('aria-expanded',String(expanded));$('panel-size').textContent=expanded?'缩小':'展开';};
function drawBuildings(){
  state.panel='list';state.category='';map?.filter(null);$('pin-caption').hidden=true;
  for(const b of $('categories').children)b.setAttribute('aria-pressed',String(!b.dataset.category));
  openPanel('校园建筑');const body=$('panel-body');body.replaceChildren();
  const input=node('input');input.className='finder';input.placeholder='搜索建筑，例如科技楼、主楼';input.setAttribute('aria-label','搜索建筑');input.value=state.query;
  const list=node('div',undefined,'place-list');
  const fill=()=>{
    state.query=input.value;list.replaceChildren();
    const filtered=buildings.filter(b=>b.name.includes(input.value.trim())).sort((a,b)=>Number(a.name==='未命名建筑')-Number(b.name==='未命名建筑'));
    for(const b of filtered){const row=button('',()=>showBuilding(b.id),'place-row');row.append(node('strong',b.name),node('span',b.name==='未命名建筑'?'#'+b.id.slice(-6):'↗','arrow'));list.append(row);}
    if(!filtered.length)list.append(node('p','未找到建筑；店铺请切换到对应分类。','meta'));
  };
  input.oninput=fill;body.append(input,node('p','先认识一栋楼，再发现楼里的店。选“吃喝”等分类查看商户。','meta'),list);fill();
}
function showBuilding(id){
  const b=buildings.find(b=>b.id===String(id));detailsToken++;state.panel='building';state.selected=null;
  openPanel(b?.name||'未命名建筑','校园建筑');map?.focusBuilding(id,!keyboard());$('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',b?.name||'未命名建筑'),node('small','已选中建筑'));
  const body=$('panel-body');body.replaceChildren();
  const description=b?.description_status?.includes('待补')?'建筑介绍尚待补充。':b?.description||'建筑介绍尚待补充。';
  body.append(node('p',description,'detail-copy building-intro'));
  const section=node('section',undefined,'building-section');section.append(node('h3','发现楼内'));
  const groups=GROUPS.filter(g=>g[0]&&g[0]!=='all'&&rows.some(r=>String(r.building_id)===String(id)&&matchesCategory(r,g[0])));
  for(const [category,label] of groups){
    const count=rows.filter(r=>String(r.building_id)===String(id)&&matchesCategory(r,category)).length;
    const entry=button('',()=>showBuildingServices(id,category),'service-entry');entry.append(icon(category==='eating'?'food':category),node('strong',label),node('span',count+' 个地点 →'));section.append(entry);
  }
  if(!groups.length)section.append(node('p','暂未关联店铺与服务。','meta'));
  const actions=node('div',undefined,'action-row');actions.append(button('问问助手',()=>{$('ask-input').value='介绍一下'+(b?.name||'这栋建筑');chatPanel();$('ask-input').focus();},'action secondary'),button('建筑清单',drawBuildings,'text-button'));
  body.append(section,actions);
  const source=node('details',undefined,'source-details');source.append(node('summary','资料来源'),node('p',b?.source||'资料待补','meta'));body.append(source);
}
function showBuildingServices(id,category){
  const b=buildings.find(b=>b.id===String(id)),members=rows.filter(r=>String(r.building_id)===String(id)&&matchesCategory(r,category));
  state={...state,category,panel:'cluster',selected:null,query:'',area:'',kind:'',limit:40};detailsToken++;setCategoryButtons();map?.filter(members.map(p=>p.id));
  openPanel(b?.name||'楼内服务',members.length+' 个地点 · '+(GROUPS.find(g=>g[0]===category)?.[1]||'楼内服务'));$('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',b?.name||'楼内服务'),node('small','楼内地点 · 请选择一家'));
  const body=$('panel-body');body.replaceChildren(button('← 返回建筑',()=>showBuilding(id),'text-button'),...members.map((p,i)=>placeRow(p,i)));
}
function placeRow(p,index,select=()=>showPlace(p.id)){const b=button('',select,'place-row');b.dataset.poiId=p.id;b.dataset.category=p.display_category||'other';const symbol=node('span',undefined,'place-symbol');symbol.append(icon(p.display_category));const text=node('span',undefined,'place-copy'),name=node('strong');name.append(node('span',String(index+1).padStart(2,'0'),'index-mark'),document.createTextNode(' '+p.name));text.append(name,node('small',`${p.floor?p.floor+'层 · ':''}${positionNote(p)}`));if(p.hours)text.append(node('small',p.hours,'hours-preview'));b.append(symbol,text,node('span','↗','arrow'));return b;}
function drawList(){if(!state.category)return drawBuildings();state.panel='list';detailsToken++;$('pin-caption').hidden=true;openPanel(GROUPS.find(g=>g[0]===state.category)?.[1]||'校园地点','发现校园日常');const body=$('panel-body');body.replaceChildren();
  const input=node('input');input.className='finder';input.placeholder='搜索店铺、服务或区域';input.setAttribute('aria-label','搜索地点');input.value=state.query;
  const sub=node('nav',undefined,'subcategories');sub.setAttribute('aria-label','吃喝类型');if(state.category==='eating')for(const [key,label] of [['','全部吃喝'],['food','餐饮小吃'],['drinks','咖啡饮品']]){const b=button(label,()=>{state.kind=key;state.limit=40;drawList();});b.setAttribute('aria-pressed',String(state.kind===key));sub.append(b);}
  const select=node('select');select.className='finder area-select';select.setAttribute('aria-label','按分布组查看');select.add(new Option('全部区域（含周边）',''));for(const g of areaGroups(rows))select.add(new Option(`${g.label} · ${g.rows.length}`,g.id));select.value=state.area;
  const areas=node('div',undefined,'area-shortcuts');areas.setAttribute('aria-label','按区域发现');for(const [key,label] of [['snack-main','小吃街主排'],['northwest-west','西北食堂西侧']]){const count=rows.filter(r=>r.spatial_sequence?.group===key).length;if(!count)continue;const b=button('',()=>{state.area=key;state.kind='';state.query='';state.category='all';state.limit=40;setCategoryButtons();drawList();});b.append(node('span',label),node('strong',`${count} 家 →`));areas.append(b);}
  const summary=node('p','','list-summary'),notice=node('p','','area-note'),list=node('div',undefined,'place-list'),pager=node('div',undefined,'pager');summary.setAttribute('role','status');
  function fill(){state.query=input.value;state.area=select.value;const filtered=directorySelection(rows,state),page=pagePlaces(filtered,state.limit);$('panel').dataset.area=String(!!state.area);$('panel-title').textContent=areaGroups(rows).find(g=>g.id===state.area)?.label||GROUPS.find(g=>g[0]===state.category)?.[1]||'校园地点';summary.textContent=`${filtered.length} 个地点 · 已显示 ${page.items.length}`;notice.textContent=state.area==='northwest-west'?'乡村基等同楼商户待绑定楼栋；西北风味餐厅是独立参照记录。':state.area?'组内北→南排序，不代表间距；分店组除外。':'无精确点位也保留在列表，地图仅显示可定位部分。';map?.filter(filtered.map(p=>p.id));list.replaceChildren(...page.items.map((p,i)=>placeRow(p,i)));pager.replaceChildren();
    if(page.remaining){const more=button(`再显示 ${Math.min(40,page.remaining)} 个 · 还有 ${page.remaining} 个`,()=>{const first=list.children.length;state.limit+=40;fill();list.children[first]?.focus({preventScroll:true});},'action secondary load-more');pager.append(more);}else if(filtered.length)pager.append(node('p','已显示全部结果','meta'));
    if(!filtered.length)list.append(node('p','没有匹配地点。可清空搜索或切换区域。','notice'),button('清空筛选',()=>setCategory('all'),'text-button'));}
  const filters=node('details',undefined,'directory-filters');filters.open=!matchMedia('(max-width:800px)').matches;filters.append(node('summary','筛选类型与区域'),sub,areas,select);
  input.oninput=()=>{state.limit=40;fill();};select.onchange=()=>{state.limit=40;fill();};body.append(input,filters,summary,notice,list,pager);fill();}
function setCategoryButtons(){for(const b of $('categories').children)b.setAttribute('aria-pressed',String(b.dataset.category===state.category));}
function showCluster(ids){detailsToken++;state.panel='cluster';const members=rows.filter(p=>ids.includes(p.id));const id=members[0]?.building_id,b=buildings.find(b=>b.id===String(id));openPanel(b?.name||'同栋建筑内的地点',`${members.length} 个地点 · 选择一家查看`);const body=$('panel-body');body.replaceChildren(button('← 返回地点清单',drawList,'text-button'),node('p','这些店铺共用楼栋标记，标记不是各店入口。','meta'),...members.map((p,i)=>placeRow(p,i)));if(members.length)map?.focus(members[0].id,!keyboard());}
async function showPlace(id,{siblings=null,move=true}={}){const p=rows.find(r=>r.id===id);if(!p)return;state=reduceState(state,{type:'select',id});openPanel(p.name,p.category_label||'校园地点');if(move)map?.focus(id,!keyboard());
  $('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',p.name),node('small',(p.floor?p.floor+'层 · ':'')+positionNote(p)));
  const token=++detailsToken,body=$('panel-body');body.replaceChildren();body.append(button('← 返回地点清单',()=>{state.panel='list';drawList();},'text-button'));
  const content=node('div');body.append(content);renderPlace(p,content);
  const same=siblings||rows.filter(r=>p.building_id!=null&&String(r.building_id)===String(p.building_id)).map(r=>r.id);
  if(same.length>1){const group=node('details');group.append(node('summary','同楼还有 '+(same.length-1)+' 个地点'));for(const ident of same.filter(x=>x!==id)){const row=rows.find(r=>r.id===ident);if(row)group.append(button(row.name,()=>showPlace(ident),'history-row'));}body.append(group);}
  try{const detail=await request('/api/app/place?id='+encodeURIComponent(id));if(token!==detailsToken||state.panel!=='detail'||state.selected!==id)return;renderPlace(detail.cards[0],content);if(detail.cards[0].menu?.length)$('pin-caption').append(node('small','已录入样例：'+detail.cards[0].menu.slice(0,2).map(m=>m.name).join(' · ')));}catch(e){if(token===detailsToken&&state.panel==='detail'){content.append(node('p',errorInfo(e).message+' 已保留基础资料。','notice'),button('重试加载详情',()=>showPlace(id,{move:false}),'action secondary'));}}
}
function renderPlace(raw,host){const p=present(raw,rows);host.replaceChildren(node('p',p.address||'具体地址尚待补充','detail-copy'));
  if(p.menu?.length){const samples=node('div',undefined,'sample-strip');samples.append(node('small','已录入样例 · 非热销排行'));for(const m of p.menu.slice(0,3))samples.append(node('span',m.name+(m.price==null?'':' ¥'+m.price),'pill'));host.append(samples);}
  for(const [label,value] of [[p.hours_label||'开放时间',p.hours||'尚未记录，请以现场公告为准'],['楼层与位置',(p.floor?p.floor+'层 · ':'')+positionNote(p)]]){const line=node('div',undefined,'info-line');line.append(node('small',label),node('span',value));host.append(line);}
  if(p.hours_notes)host.append(node('p',p.hours_notes,'meta'));if(p.simulation)host.append(node('p','模拟资料，仅用于演示。','notice'));
  const actions=node('div',undefined,'action-row'),known=rows.find(r=>r.id===(p.id||p.poi_id))||p;if(inModel(known)||p.map_reference)actions.append(button(p.map_reference?'查看参照区域':'定位到地图',()=>{hideIntro();map?.focus(p.id||p.poi_id,!keyboard());},'action'));else if(known.spatial_sequence)actions.append(button('查看所在区域名录',()=>{state.category='all';state.area=known.spatial_sequence.group;state.query='';state.kind='';state.limit=40;setCategoryButtons();drawList();},'action'));actions.append(button('问问助手',()=>{$('ask-input').value='介绍一下'+p.name+'，有什么需要注意的？';$('ask-input').focus();},'action secondary'));host.append(actions);
  if(p.collection_label){const menu=node('section',undefined,'menu');menu.append(node('h3',p.collection_label+'与规格'),node('p','已有资料样例，不代表热销排行或实时在售。','meta'));
    if(p.menu===undefined)menu.append(node('p','正在读取已录入资料…','meta'));
    else if(!p.menu.length)menu.append(node('p','暂无已录入'+p.collection_label+'，不使用模拟内容填充。','notice'));
    else {for(const item of p.menu){const r=node('div',undefined,'menu-row'),name=node('span',item.name);name.append(node('small',item.specification||'规格未注明'));r.append(name,node('b',item.price==null?'待询价':'¥'+item.price));menu.append(r);}
      if(p.menu.length+(p.menu_offset||0)<p.menu_total){const more=button('继续查看'+p.collection_label,async()=>{more.disabled=true;try{const next=await request('/api/app/place?id='+encodeURIComponent(p.poi_id||p.id)+'&offset='+((p.menu_offset||0)+p.menu.length));p.menu.push(...next.cards[0].menu);renderPlace(p,host);}catch(e){more.disabled=false;toast(errorInfo(e).message);}},'action secondary');menu.append(more);}}
    host.append(menu);}
  host.append(node('p','资料来源：'+sourceLabel(p.source)+'；营业与商品以现场信息为准。','meta'));
}
function renderResult(raw){const c=present(raw,rows),box=node('div',undefined,'chat-result');box.append(node('span',c.simulation?'模拟样例':c.category_label||'候选','pill'),node('h3',c.name));if(c.price!=null)box.append(node('strong','¥'+c.price+' / 记录价'));
  if(c.shop)box.append(node('p',c.shop+(c.floor?' · '+c.floor+'层':'')));if(c.address)box.append(node('p',c.address));if(c.reasons?.length)box.append(node('p',c.reasons.join('；')));if(c.unknown?.length)box.append(node('p','待确认：'+c.unknown.join('；'),'notice'));
  if(c.type==='schedule')box.append(node('p',c.start+' — '+c.end+' · '+c.location_name+'（模拟课表）'));
  if(c.total_minutes!=null)box.append(node('p','估算用时 '+c.total_minutes+' 分钟，包含估计或模拟值，不保证按时。'));
  const id=c.poi_id||c.id;if(rows.some(r=>r.id===id))box.append(button('查看地点与位置 ↗',()=>showPlace(id),'text-button'));return box;}
function chatPanel(){state.panel='chat';openPanel('校园生活助手','问一问');renderChat();}
function renderChat(){if(state.panel!=='chat')return;const body=$('panel-body');body.replaceChildren();const tools=node('div',undefined,'action-row');tools.append(button('新对话',()=>{if(active)return toast('请先停止当前请求');conversation=fresh();renderChat();},'action secondary'),button('历史对话',historyPanel,'text-button'));body.append(tools);
  if(!conversation.messages.length){body.append(node('h3','把日常，交给一句话。','detail-title'),node('p','我会查询已发布的校园资料。位置、价格或时间未知时，会明确告诉你。','detail-copy'));for(const text of ['20元以内想吃辣，不吃米饭','新乐群三层有什么？','瑞幸咖啡在哪里？'])body.append(button(text,()=>{$('ask-input').value=text;$('ask-input').focus();},'history-row'));}
  for(const m of conversation.messages){const box=node('article',undefined,'chat-msg '+m.role);if(m.role==='assistant')box.append(node('small','JINGSHI / 京师智行'));box.append(node('div',m.pending?m.status||'正在查询校园资料…':m.error?errorInfo(m.failure||m.content).message:m.content));
    if(m.cards)for(const c of m.cards)box.append(renderResult(c));if(m.error){box.append(node('p','仍可浏览地点，或使用无需模型的条件推荐。','meta'));if(m.request&&errorInfo(m.failure).retryable)box.append(button('重试这次请求',()=>send(m.request.message,m),'action secondary'));box.append(button('打开条件推荐',conditionPanel,'text-button'));}body.append(box);}
  body.append(node('p',db?'对话保存在本机浏览器，未写入校园数据库。':'对话仅在当前页面保留；本机历史存储尚不可用。','meta'));if(active)body.scrollTop=body.scrollHeight;}
function historyPanel(){if(active)return toast('请先停止当前请求');state.panel='history';openPanel('我的对话','仅保存在这台设备');const body=$('panel-body');body.replaceChildren();for(const item of history.slice(0,25))body.append(button(item.title,()=>{conversation=structuredClone(item);for(const m of conversation.messages)if(m.pending){m.pending=false;m.error=true;m.content='上次请求未完成，请重新发送。';}chatPanel();},'history-row'));if(!history.length)body.append(node('p','还没有本机历史对话。','meta'));}
$('chat').onclick=chatPanel;
$('header-chat').onclick=historyPanel;
$('settings-history').onclick=historyPanel;
async function send(text,retry=null){text=text.trim();if(!text||active)return;const payload=retry?structuredClone(retry.request):{request_id:crypto.randomUUID(),conversation_id:conversation.id,message:text,conditions:structuredClone(conversation.conditions),mode:conversation.mode,history:conversation.messages.filter(m=>!m.error&&!m.pending).slice(-12).map(m=>({role:m.role,content:m.content})),previous_poi_ids:selectionIds(conversation.messages.filter(m=>m.role==='assistant').at(-1)?.cards||[],rows)};
  if(retry&&!['NETWORK','REQUEST_ACTIVE'].includes(retry.failure?.code))payload.request_id=crypto.randomUUID();
  const reply=retry||{role:'assistant',cards:[],time:new Date().toISOString()};if(!retry){conversation.messages.push({role:'user',content:text},reply);if(conversation.messages.length===2)conversation.title=text.slice(0,24);}Object.assign(reply,{content:'',pending:true,error:false,failure:null,request:payload});
  const controller=new AbortController();active={controller,id:payload.request_id};$('ask-input').value='';$('ask-send').disabled=true;$('ask-stop').hidden=false;chatPanel();await save();
  try{await chatStream(payload,controller.signal,e=>{if(e.type==='status')reply.status=e.text;if(e.type==='cards'){reply.cards=e.cards;conversation.conditions=e.conditions||conversation.conditions;map?.filter(selectionIds(e.cards,rows));}if(e.type==='result'){reply.content=e.data.answer;reply.cards=e.data.cards;reply.pending=false;conversation.conditions=e.data.conditions||conversation.conditions;map?.filter(selectionIds(reply.cards,rows));}if(e.type==='error'){reply.error=true;reply.failure=errorInfo(e);reply.content=reply.failure.message;reply.pending=false;}renderChat();});}
  catch(e){reply.error=true;reply.failure=errorInfo(e);reply.content=reply.failure.message;}finally{reply.pending=false;active=null;$('ask-send').disabled=false;$('ask-stop').hidden=true;renderChat();await save();updateModel();}}
$('ask-form').onsubmit=e=>{e.preventDefault();send($('ask-input').value);};$('ask-stop').onclick=()=>{if(!active)return;const {controller,id}=active;request('/api/agent/cancel',{request_id:id}).catch(()=>toast('已停止本机等待；服务端停止请求未确认。'));controller.abort();};
function conditionPanel(){state.panel='conditions';openPanel('找到适合的一餐','按你的条件，查已知资料');const body=$('panel-body');body.replaceChildren(node('p','直接筛选已录入资料，无需大模型。未知耗时不会被当成时间保证。','meta'));const form=node('form');form.className='condition-form';
  const fields={};for(const [key,label,type,placeholder] of [['budget','预算上限（元）','number','例如20'],['taste','偏好口味','text','例如辣'],['avoid','不吃什么','text','例如米饭'],['available_minutes','可用时间（分钟）','number','不知道可留空']]){const l=node('label',label),input=node('input');input.type=type;input.placeholder=placeholder;input.name=key;if(type==='number'){input.min='1';input.max='10000';input.step='any';}input.value=Array.isArray(conversation.conditions[key])?conversation.conditions[key].join('、'):conversation.conditions[key]??'';l.append(input);form.append(l);fields[key]=input;}
  const l=node('label','当前位置'),select=node('select');select.add(new Option('选择地点（时间筛选需要）',''));const seen=new Set();for(const p of [...locations,...rows.filter(r=>r.location)])if(!seen.has(p.id)){select.add(new Option(p.name,p.id));seen.add(p.id);}select.value=conversation.conditions.current_location||'';l.append(select);form.append(l);
  const submit=node('button','按条件查看候选','action');submit.type='submit';form.append(submit);form.onsubmit=async e=>{e.preventDefault();if(active)return toast('请先停止当前助手请求');submit.disabled=true;const conditions={...conversation.conditions};for(const k of ['budget','available_minutes']){if(fields[k].value)conditions[k]=Number(fields[k].value);else delete conditions[k];}for(const k of ['taste','avoid'])conditions[k]=fields[k].value.split(/[、,，]/).map(x=>x.trim()).filter(Boolean);if(select.value)conditions.current_location=select.value;else delete conditions.current_location;
    try{const result=await request('/api/app/candidates',{conditions,mode:'real'});conversation.conditions=conditions;conversation.messages.push({role:'assistant',content:result.clarification||((result.cards.length?'按已知条件找到这些候选。':'没有符合条件的候选。')+' '+(result.notice||'')+' '+Object.keys(result.rejected||{}).join('、')),cards:result.cards,time:new Date().toISOString()});map?.filter(selectionIds(result.cards,rows));chatPanel();await save();}catch(e){toast(errorInfo(e).message);}finally{submit.disabled=false;}};body.append(form);}
$('conditions').onclick=conditionPanel;
$('settings-conditions').onclick=conditionPanel;
document.querySelectorAll('button[data-view]').forEach(b=>b.onclick=()=>{hideIntro();map?.stopRoam();map?.view(b.dataset.view,!keyboard());for(const other of document.querySelectorAll('button[data-view]'))other.setAttribute('aria-pressed',String(other===b));});
$('roam-toggle').onclick=()=>{if($('roam-toggle').getAttribute('aria-pressed')==='true')map?.stopRoam();else map?.resumeRoam();};
$('art-toggle').onclick=()=>{art=!art;$('art-toggle').setAttribute('aria-pressed',String(art));map?.setArt(art);updateArtNote();toast(art?'已开启示意上色；3栋纸感样例不代表真实立面。':'已恢复白模基准。');};
async function updateModel(){try{const s=await request('/api/agent/status');$('model-status').textContent=s.connection_status==='connected'?'● 助手已连接':s.configured?'○ 助手待连接':'○ 助手未启用';}catch{$('model-status').textContent='○ 本地服务未连接';}}
try{db=await openHistory();history=await listConversations(db);}catch{toast('本机历史不可用，本次仍可使用地图和查询。');}
try{const d=await request('/api/app/directory');rows=d.pois.map(normalizePlace);locations=d.locations;map?.setRows(rows);if(state.panel==='list')drawList();}catch(e){toast(errorInfo(e).message);$('scene-status').textContent='地点加载失败，请确认本地服务后刷新重试。';}
try{buildings=(await request('/api/app/buildings')).buildings;if(state.panel==='list'&&!state.category)drawBuildings();}catch{toast('建筑资料暂未读取；仍可查看地图和店铺分类，请刷新重试。');}
updateArtNote();
updateModel();
window.addEventListener('pagehide',()=>{cancelPanelMotion();reducedMotion.removeEventListener('change',cancelPanelMotion);map?.dispose();},{once:true});
