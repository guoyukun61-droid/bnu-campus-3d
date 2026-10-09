import {GROUPS,filterPlaces,inModel,positionNote,reduceState,selectionIds,normalizePlace,matchesCategory,directorySelection,pagePlaces,areaGroups} from './state.js';
import {request,chatStream} from './api.js';
import {present,errorInfo} from '/presentation.js';
import {openHistory,saveConversation,listConversations} from '/history.js';
// The old running server may not know this optional static route yet. Only a
// verified 404 means legacy capability; transport or module errors stay visible.
async function loadAgentExtension(fetcher=fetch,importer=()=>import('./agent-context.js')){
  try{const response=await fetcher('/explore/agent-context.js',{credentials:'same-origin',signal:AbortSignal.timeout(10000)});
    if(response.status===404)return {status:'legacy',api:null,notice:'新对话功能需要重启本地服务，原地图与筛选仍可用。'};
    if(!response.ok)throw Error('Agent extension unavailable');
    const api=await importer();for(const name of ['entityReference','previousEntities','agentRequestContext','collectOutletRecords','loadedEntity','resolveMapAction','safeSourceUrl','agentResponseExtras'])if(typeof api[name]!=='function')throw Error('Invalid Agent extension');
    return {status:'ready',api,notice:''};
  }catch{return {status:'error',api:null,notice:'新对话功能加载失败，请刷新重试；原地图与筛选仍可用。'};}
}
const agentExtension=await loadAgentExtension();
const agentAPI=agentExtension.api;
const $=id=>document.getElementById(id),node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const button=(text,fn,cls='')=>{const b=node('button',text,cls);b.type='button';b.onclick=fn;return b;};
const ICONS={building:'M3 21h18M5 21V5l7-3 7 3v16M9 7h1M14 7h1M9 11h1M14 11h1M10 21v-6h4v6',food:'M5 3v6M2 3v4c0 4 6 4 6 0V3M5 11v10M16 3c-3 3-4 7-1 9h3V3h-2M18 12v9',drinks:'M4 8h12v8a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V8ZM16 9h2a3 3 0 0 1 0 6h-2M7 3v2M12 3v2',retail:'M4 7h16l-1 14H5L4 7ZM8 8V6a4 4 0 0 1 8 0v2',sports:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M2 12h20M12 2v20M5 5l14 14M19 5 5 19',services:'m14 3-3 3 2 3 3-3c2 5-2 8-6 6l-6 7-3-3 7-6C6 6 9 2 14 3Z',campus:'m2 8 10-5 10 5-10 5L2 8ZM6 10v7c3 3 9 3 12 0v-7M22 8v8',all:'M3 3h6v6H3V3ZM15 3h6v6h-6V3ZM3 15h6v6H3v-6ZM15 15h6v6h-6v-6',clock:'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 6v6l4 2',pin:'M12 22S4 14 4 9a8 8 0 1 1 16 0c0 5-8 13-8 13ZM12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6'};
function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg'),path=document.createElementNS(svg.namespaceURI,'path');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');path.setAttribute('d',ICONS[name]||ICONS.pin);svg.append(path);return svg;}
let state={category:'',panel:null,selected:null,query:'',area:'',kind:'',limit:40},rows=[],buildings=[],locations=[],map=null,db=null,history=[],active=null,detailsToken=0,art=new URLSearchParams(location.search).get('art')==='atelier'?'atelier':true,textureReady=false,atelierReady=false;
const fresh=()=>({id:crypto.randomUUID(),title:'校园漫游',conditions:{},mode:'real',messages:[],updated_at:new Date().toISOString()});let conversation=fresh();
let accountPatch={},identityEpoch=0;
// UI-only state never enters account history or changes geographic coordinates.
let chatView=null,chatScroll=0,chatFollow=true,chatUnread=false,placeReturn=null;
const composerHome=document.querySelector('.search-dock');
let selectedEntity=null,agentResponses=new WeakMap();
const knownOutlets=new Map(),selectionBar=node('div',undefined,'agent-selection');
selectionBar.hidden=true;selectionBar.setAttribute('aria-live','polite');composerHome.append(selectionBar);
const extensionNotice=node('p',agentExtension.notice,'agent-extension-notice');extensionNotice.hidden=!agentExtension.notice;extensionNotice.setAttribute('role','status');composerHome.append(extensionNotice);
document.body.dataset.composerNote=String(!!agentExtension.notice);
const agentCatalog=()=>({rows,buildings,outlets:[...knownOutlets.values()]});
function rememberAgentEntities(cards=[],relations=[],entities=[]){for(const record of agentAPI?.collectOutletRecords(cards,relations,entities)||[])knownOutlets.set(record.ref.id,record);}
function setAgentSelection(ref){selectedEntity=agentAPI?.loadedEntity(ref,agentCatalog())?.ref||null;renderAgentSelection();}
function renderAgentSelection(){
  const selected=agentAPI?.loadedEntity(selectedEntity,agentCatalog());selectionBar.hidden=!selected;document.body.dataset.composerNote=String(!!selected||!!agentExtension.notice);selectionBar.replaceChildren();if(!selected)return;
  const label=node('span','提问对象：'+selected.name);label.append(node('small','仅作提问上下文，不代表你的位置'));
  const clear=button('清除',()=>{selectedEntity=null;state.selected=null;markResultSelection(null);renderAgentSelection();$('ask-input').focus({preventScroll:true});},'text-button');clear.setAttribute('aria-label','清除提问对象');selectionBar.append(label,clear);
}
function dockComposer(chat){
  const host=chat?$('panel-composer'):composerHome,form=$('ask-form');
  const focused=document.activeElement===$('ask-input'),start=$('ask-input').selectionStart,end=$('ask-input').selectionEnd;
  if(form.parentElement!==host){host.append(form);if(focused){$('ask-input').focus({preventScroll:true});$('ask-input').setSelectionRange(start,end);}}
  host.append(selectionBar,extensionNotice);
  $('panel-composer').hidden=!chat;composerHome.hidden=chat;document.body.dataset.task=chat?'chat':'explore';
  $('ask-input').placeholder=chat?'继续问，或换一个条件…':'想吃什么，想去哪里？';
  $('chat-updates').hidden=!chat||!chatUnread||$('panel').dataset.peek==='true';
}
function resetChatView(){chatView=null;chatScroll=0;chatFollow=true;chatUnread=false;placeReturn=null;$('chat-updates').hidden=true;$('island-preview').textContent='';$('island-status').textContent='校园生活助手';}
function nearChatEnd(){const b=$('panel-body');return b.scrollHeight-b.clientHeight-b.scrollTop<64;}
$('panel-body').addEventListener('scroll',()=>{if(state.panel!=='chat'||$('panel').dataset.peek==='true')return;chatScroll=$('panel-body').scrollTop;chatFollow=nearChatEnd();if(chatFollow){chatUnread=false;$('chat-updates').hidden=true;}},{passive:true});
$('chat-updates').onclick=()=>{chatFollow=true;chatUnread=false;$('chat-updates').hidden=true;$('panel-body').scrollTop=$('panel-body').scrollHeight;chatScroll=$('panel-body').scrollTop;};
// Old running previews do not know the new asset route. Only an explicit 404 or
// disabled response permits legacy history; network/module failure stays closed.
let account={enabled:true,user:null,require(){if(this.enabled===false)return true;this.open();return false;},open(){toast('账号状态未就绪，请刷新后重试；地图仍可浏览。');},async history(){return [];},async init(){
  try{const response=await fetch('/api/account/me',{credentials:'same-origin',signal:AbortSignal.timeout(10000)});
    if(response.status===404){this.enabled=false;return;}
    if(!response.ok)throw Error('Account status unavailable');
    const status=await response.json();if(status.enabled===false){this.enabled=false;return;}if(status.enabled!==true)throw Error('Invalid account status');
    const {createAccountUI}=await import('/account.js');
    account=createAccountUI({onNotice:text=>toast(text),onReset:()=>{identityEpoch++;active?.controller.abort();active=null;conversation=fresh();history=[];accountPatch={};agentResponses=new WeakMap();knownOutlets.clear();setAgentSelection(null);resetChatView();$('ask-input').value='';$('ask-send').disabled=false;$('ask-stop').hidden=true;map?.filter(null);$('panel-body').replaceChildren();if(state.panel==='chat')renderChat();}});await account.init();
  }catch{toast('账号状态未读取，个人对话暂不可用；地图仍可使用。');}
}};
const sourceLabel=s=>s==='simulated'?'模拟数据':s==='menu_photo'?'菜单照片':s==='baidu_place_v2'?'百度地点资料':s==='user_reported'?'用户补充资料':'已发布资料';
const keyboard=()=>document.body.classList.contains('keyboard');
const reducedMotion=matchMedia('(prefers-reduced-motion: reduce)');let panelMotion=null,shellMotion=null,surfaceMotion=null;
function cancelShellMotion(){shellMotion?.cancel();surfaceMotion?.cancel();shellMotion=null;surfaceMotion=null;$('dialog-shell').hidden=true;}
function cancelPanelMotion(){panelMotion?.cancel();panelMotion=null;cancelShellMotion();}
// FLIP only the decorative shell. Text is independently translated, never scaled.
function chatBounds(){return (shellMotion&&!$('dialog-shell').hidden?$('dialog-shell'):$('panel').dataset.open==='true'&&state.panel==='chat'?$('panel'):composerHome).getBoundingClientRect?.();}
function morphChat(from,target=$('panel')){
  cancelShellMotion();if(!from||keyboard()||reducedMotion.matches||document.hidden||!target.animate)return;
  const to=target.getBoundingClientRect?.();if(!to?.width||!to.height||!from.width||!from.height)return;
  const shell=$('dialog-shell');Object.assign(shell.style,{left:`${to.left}px`,top:`${to.top}px`,width:`${to.width}px`,height:`${to.height}px`});shell.hidden=false;
  const dx=from.left-to.left,dy=from.top-to.top,sx=from.width/to.width,sy=from.height/to.height;
  const animation=shell.animate([{transform:`translate(${dx}px,${dy}px) scale(${sx},${sy})`,opacity:.9},{transform:'translate(0,0) scale(1,1)',opacity:0}],{duration:300,easing:'cubic-bezier(.22,1,.36,1)'});shellMotion=animation;
  const surface=target===composerHome?$('ask-form'):target;
  surfaceMotion=surface.animate([{opacity:0,transform:`translateY(${dy>0?14:-10}px)`},{opacity:1,transform:'translateY(0)'}],{duration:280,easing:'cubic-bezier(.16,1.08,.38,1)'});
  animation.finished.then(()=>{if(shellMotion===animation){shell.hidden=true;shellMotion=null;surfaceMotion=null;}},()=>{});
}
function renderIsland(){
  const island=$('chat-island'),compact=state.panel==='chat'&&$('panel').dataset.peek==='true';island.hidden=!compact;
  $('panel-body').inert=compact;
  const reply=[...conversation.messages].reverse().find(m=>m.role==='assistant');
  const pending=!!reply?.pending&&!reply?.error,error=!!reply?.error;
  island.dataset.state=pending?'pending':error?'error':reply?'ready':'idle';
  const status=pending?(reply.status||'正在查询校园资料'):error?'本次回答未完成':reply?'回答已就绪':'校园生活助手';
  if($('island-status').textContent!==status)$('island-status').textContent=status;
  const question=[...conversation.messages].reverse().find(m=>m.role==='user')?.content;
  const copy=pending?(question||'查询期间可以继续浏览地图。'):error?(reply.failure||errorInfo(reply)).message:reply?.content||'想去哪里？可以先从一餐饭、一杯咖啡开始。';
  const chars=Array.from(String(copy||''));$('island-preview').textContent=chars.slice(0,150).join('')+(chars.length>150?'…':'');
  $('island-expand').textContent=error?'查看原因与重试 ↗':pending?'查看查询过程 ↗':'展开完整对话 ↗';
}
function setChatPeek(peek,{animate=true}={}){
  const from=chatBounds();if(peek&&$('panel').dataset.peek!=='true')chatScroll=$('panel-body').scrollTop;
  $('panel').dataset.peek=String(peek);$('panel-size').setAttribute('aria-expanded',String(!peek));$('panel-size').textContent=peek?'继续对话':'看地图';
  $('chat-updates').hidden=peek||!chatUnread;renderIsland();if(!peek)$('panel-body').scrollTop=chatScroll;
  if(peek&&($('panel-body').contains(document.activeElement)||document.activeElement===$('panel-size')))$('island-expand').focus({preventScroll:true});
  if(animate)morphChat(from);map?.refreshLayout();
}
$('island-expand').onclick=()=>{setChatPeek(false);$('panel-size').focus({preventScroll:true});};
reducedMotion.addEventListener('change',cancelPanelMotion);document.addEventListener('keydown',cancelPanelMotion);
window.addEventListener('resize',cancelPanelMotion);
document.addEventListener('keydown',e=>{document.body.classList.add('keyboard');map?.stopRoam();if(e.key==='Escape'){if($('settings').open){$('settings').open=false;$('settings').querySelector('summary').focus();}else closePanel();}});document.addEventListener('pointerdown',e=>{document.body.classList.remove('keyboard');if(!e.target.closest('#settings'))$('settings').open=false;if(!e.target.closest('#roam-toggle'))map?.stopRoam();});document.addEventListener('input',()=>map?.stopRoam());
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').hidden=true,4800);}
function hideIntro(){$('intro').dataset.hidden='true';}
// Measure the settled layout, not a guessed left/right panel width. Transforms
// are entrance choreography only; offsetLeft/Top describe the final safe area.
function mapOcclusions(){
  const host=$('scene').getBoundingClientRect(),targets=[document.querySelector('.masthead'),$('categories'),composerHome,$('panel'),document.querySelector('.view-dock'),$('campus-tour')];
  return targets.filter(el=>el&&!el.hidden&&(el!==$('panel')||el.dataset.open==='true')&&getComputedStyle(el).display!=='none').map(el=>{
    const rect=el.getBoundingClientRect();
    if(el===$('panel'))return {left:el.offsetLeft-host.left,top:el.offsetTop-host.top,right:el.offsetLeft+el.offsetWidth-host.left,bottom:el.offsetTop+el.offsetHeight-host.top};
    return {left:rect.left-host.left,top:rect.top-host.top,right:rect.right-host.left,bottom:rect.bottom-host.top};
  });
}
let layoutObserver=null;
let tourIndex=-1,tourMoving=false;
const tourStops=()=>['前主楼','图书馆','新乐群','学五','科技楼'].map(name=>buildings.find(b=>b.name===name)||buildings.find(b=>b.name.includes(name))).filter((b,i,all)=>b&&all.findIndex(x=>x?.id===b.id)===i);
function renderTour(){const stops=tourStops(),active=tourIndex>=0&&stops.length>0;document.body.dataset.tour=active?'active':'idle';$('tour-start').hidden=active;$('tour-title').hidden=!active;for(const id of ['tour-prev','tour-next','tour-end'])$(id).hidden=!active;$('tour-step').textContent=active?`${String(tourIndex+1).padStart(2,'0')} / ${String(stops.length).padStart(2,'0')} · 校园镜头`:'精选镜头 / CAMPUS WALK';if(active)$('tour-title').textContent=stops[tourIndex].name;}
function endTour(){if(tourIndex<0)return;tourIndex=-1;renderTour();map?.cancelFocus();map?.refreshLayout();}
function visitTour(delta){const stops=tourStops();if(!stops.length)return toast('建筑资料尚未就绪，请稍后再试。');tourIndex=(tourIndex+delta+stops.length)%stops.length;hideIntro();map?.stopRoam();tourMoving=true;try{showBuilding(stops[tourIndex].id);}finally{tourMoving=false;}renderTour();map?.refreshLayout();}
$('tour-start').onclick=()=>{tourIndex=-1;visitTour(1);};$('tour-prev').onclick=()=>visitTour(-1);$('tour-next').onclick=()=>visitTour(1);$('tour-end').onclick=endTour;
document.addEventListener('visibilitychange',()=>{document.body.dataset.pageHidden=String(document.hidden);if(document.hidden)cancelPanelMotion();});
function openPanel(title,kicker='校园导览'){
  const previous=$('panel').dataset.view,wasOpen=$('panel').dataset.open==='true';
  if(wasOpen&&previous==='chat'&&$('panel').dataset.peek!=='true')chatScroll=$('panel-body').scrollTop;
  cancelPanelMotion();hideIntro();$('settings').open=false;$('panel').dataset.open='true';$('panel').dataset.view=state.panel||'list';
  if(!wasOpen||previous!==state.panel){$('panel').dataset.peek='false';$('panel').dataset.expanded='false';$('panel-size').setAttribute('aria-expanded',String(state.panel==='chat'));$('panel-size').textContent=state.panel==='chat'?'看地图':'展开';$('panel-body').scrollTop=0;}
  $('panel').inert=false;$('panel-title').textContent=title;$('panel-kicker').textContent=kicker;document.body.dataset.panel='open';dockComposer(state.panel==='chat');map?.setPanel(true);
  $('chat-island').hidden=state.panel!=='chat'||$('panel').dataset.peek!=='true';$('panel-body').inert=state.panel==='chat'&&$('panel').dataset.peek==='true';
  if(wasOpen&&previous!==state.panel&&!keyboard()&&!reducedMotion.matches){const x=['list','chat'].includes(state.panel)?-12:12;panelMotion=$('panel-body').animate([{opacity:.55,transform:`translateX(${x}px)`},{opacity:1,transform:'translateX(0)'}],{duration:220,easing:'cubic-bezier(.32,.72,0,1)'});}
}
function closePanel(){const wasChat=state.panel==='chat',from=wasChat?chatBounds():null;cancelPanelMotion();if(wasChat&&$('panel').dataset.peek!=='true')chatScroll=$('panel-body').scrollTop;const restoreFocus=$('panel').contains(document.activeElement);state=reduceState(state,{type:'close'});$('panel').dataset.open='false';$('panel').inert=true;dockComposer(false);document.body.dataset.panel='closed';map?.setPanel(false);detailsToken++;if(wasChat)morphChat(from,composerHome);if(restoreFocus)(wasChat?$('ask-input'):$('browse')).focus({preventScroll:true});}
$('close-panel').onclick=closePanel;
async function save(){conversation.updated_at=new Date().toISOString();if(account.enabled){if(account.user&&!active)try{history=await account.history();}catch{toast('服务端历史尚未刷新，未覆盖任何记录；请稍后打开“我的对话”。');}return;}if(!db)return;try{await saveConversation(db,conversation);history=await listConversations(db);}catch{toast('浏览器未能保存对话，离开前请保留需要的信息。');}}
function updateArtNote(){const trial=art==='atelier';document.body.dataset.art=trial?'atelier':'base';
  $('art-note').textContent=trial?(atelierReady?'手绘试验 · 学五 / 新乐群 · 窗位与材质为示意':'手绘试验 · 纹理未就绪，使用程序材质回退'):art?(textureReady?'示意上色 · 3栋纸感材质样例，非真实立面':'示意上色 · 材质未就绪，使用纯色回退'):'白模基准 · 标记高度不代表店铺楼层';
  $('atelier-toggle').textContent=trial?'返回基础上色':'手绘试验';$('atelier-toggle').setAttribute('aria-pressed',String(trial));
  $('trial-note').hidden=!trial;$('art-toggle').setAttribute('aria-pressed',String(!!art));
}
const scenePromise=import('./scene.js').then(({createScene})=>{map=createScene($('scene'),{
  getOcclusions:mapOcclusions,
  onSelect:(id,siblings)=>siblings?.length>1?showCluster(siblings):showPlace(id),onStatus:text=>$('scene-status').textContent=text,onInteraction:()=>{hideIntro();endTour();},
  onBuilding:id=>showBuilding(id),onRoam:active=>{$('roam-toggle').textContent=active?'暂停漫游':'继续漫游';$('roam-toggle').setAttribute('aria-pressed',String(active));},
  onBearing:angle=>$('compass').style.transform=`rotate(${angle}deg)`,
  onArtStatus:s=>{if(s.startsWith('atelier-'))atelierReady=s==='atelier-ready';else textureReady=s==='texture-ready';updateArtNote();}
});map.setArt(art);map.setPanel(!!state.panel);layoutObserver=new ResizeObserver(()=>map?.refreshLayout());for(const el of [$('panel'),$('categories'),composerHome,$('panel-composer')])layoutObserver.observe(el);$('panel').addEventListener('transitionend',()=>map?.refreshLayout());if(art==='atelier'){hideIntro();map.view('atelier',false);document.querySelectorAll('button[data-view]').forEach(b=>b.setAttribute('aria-pressed','false'));}if(rows.length){map.setRows(rows);if(state.category)map.filter(directorySelection(rows,state).map(p=>p.id));}return map;}).catch(()=>{$('scene-status').textContent='三维暂不可用；仍可通过分类清单查看地点与使用文字服务。';});
function setCategory(value){endTour();state=reduceState(state,{type:'category',value});setAgentSelection(null);$('pin-caption').hidden=true;for(const b of $('categories').children)b.setAttribute('aria-pressed',String(b.dataset.category===value));drawList();}
for(const [key,title] of GROUPS){const b=button('',()=>setCategory(key));b.append(icon(key==='eating'?'food':key||'building'),node('span',title));b.dataset.category=key;b.setAttribute('aria-pressed',String(!key));$('categories').append(b);}
$('start-food').onclick=()=>setCategory('eating');$('browse').onclick=()=>{state.panel='list';drawList();};
$('start-buildings').onclick=()=>setCategory('');
$('panel-size').onclick=()=>{
  if(state.panel==='chat'){
    setChatPeek($('panel').dataset.peek!=='true');return;
  }
  const expanded=$('panel').dataset.expanded!=='true';$('panel').dataset.expanded=String(expanded);$('panel-size').setAttribute('aria-expanded',String(expanded));$('panel-size').textContent=expanded?'缩小':'展开';
};
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
  if(!tourMoving)endTour();
  const b=buildings.find(b=>b.id===String(id));detailsToken++;state.panel='building';state.selected=null;
  setAgentSelection({kind:'building',id:String(id)});
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
  setAgentSelection({kind:'building',id:String(id)});
  openPanel(b?.name||'楼内服务',members.length+' 个地点 · '+(GROUPS.find(g=>g[0]===category)?.[1]||'楼内服务'));$('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',b?.name||'楼内服务'),node('small','楼内地点 · 请选择一家'));
  const body=$('panel-body'),floors=groupKnownFloors(members);body.replaceChildren(button('← 返回建筑',()=>showBuilding(id),'text-button'));
  const navigation=node('nav',undefined,'floor-tabs');navigation.setAttribute('aria-label','楼内楼层');const list=node('div',undefined,'building-floors');
  function fill(floor=''){for(const tab of navigation.children)tab.setAttribute('aria-pressed',String(tab.dataset.floor===floor));list.replaceChildren();for(const group of floors){if(floor&&group.key!==floor)continue;const section=node('section',undefined,'floor-section');section.append(node('h3',group.label),node('p',group.members.length+' 个已关联地点','meta'),...group.members.map((p,i)=>placeRow(p,i)));list.append(section);}}
  for(const [key,label] of [['','全部楼层'],...floors.map(f=>[f.key,f.label])]){const tab=button(label,()=>fill(key));tab.dataset.floor=key;navigation.append(tab);}body.append(navigation,list);fill();
}
// MENU_BROWSER_PURE_START — same logic is exercised without DOM or new asset routes.
function knownFloor(value){const floor=value==null?'':String(value).trim();return {key:floor||'__unknown__',label:floor?(/层|楼|阁楼/.test(floor)?floor:floor+'层'):'楼层尚未录入'};}
function groupKnownFloors(records){const groups=new Map();for(const record of records){const floor=knownFloor(record.floor);if(!groups.has(floor.key))groups.set(floor.key,{...floor,members:[]});groups.get(floor.key).members.push(record);}return [...groups.values()].sort((a,b)=>Number(a.key==='__unknown__')-Number(b.key==='__unknown__')||a.key.localeCompare(b.key,'zh-CN',{numeric:true}));}
function uniqueMenuRecords(records){const seen=new Set();return records.filter(record=>{if(!record||typeof record!=='object')return false;if(typeof record.id!=='string'||!record.id)return true;if(seen.has(record.id))return false;seen.add(record.id);return true;});}
function menuCursor(card){return Number.isInteger(card.menu_next_offset)?card.menu_next_offset:(Number.isInteger(card.menu_offset)?card.menu_offset:0)+(Array.isArray(card.menu)?card.menu.length:0);}
function mergeMenuPage(card,next){
  const id=card.poi_id||card.id,nextId=next?.poi_id||next?.id,cursor=menuCursor(card);
  if(!next||id!==nextId||!Array.isArray(next.menu)||next.menu_offset!==cursor)throw Error('菜单分页不一致，请重新打开地点后重试。');
  if(Number.isInteger(card.menu_total)&&Number.isInteger(next.menu_total)&&card.menu_total!==next.menu_total)throw Error('菜单资料已更新，请重新打开地点读取完整版本。');
  if(!next.menu.length&&cursor<(next.menu_total??card.menu_total??0))throw Error('本页菜单未完整返回，请重试；已加载资料保留。');
  return {...card,menu:uniqueMenuRecords([...(card.menu||[]),...next.menu]),menu_groups:uniqueMenuRecords([...(card.menu_groups||[]),...(next.menu_groups||[])]),outlets:uniqueMenuRecords([...(card.outlets||[]),...(next.outlets||[])]),menu_total:next.menu_total??card.menu_total,menu_next_offset:cursor+next.menu.length};
}
function menuBrowserGroups(card){
  const groups=new Map(),parent=card.poi_id||card.id,foreignOutlets=new Set((card.outlets||[]).filter(o=>o?.id&&o.poi_id&&o.poi_id!==parent).map(o=>o.id)),outlets=new Map((card.outlets||[]).filter(o=>o?.id&&(!o.poi_id||o.poi_id===parent)).map(o=>[o.id,o]));
  const invalid=new Set(['candidate','source_only','unassigned']);
  const create=(record,groupId=null)=>{
    const outlet=outlets.get(record.outlet_id),identity=record.outlet_id&&!foreignOutlets.has(record.outlet_id)&&!invalid.has(record.identity_status)&&(outlet||record.outlet_name)?record.outlet_id:null;
    const floor=knownFloor(record.floor??outlet?.floor??card.floor),key=identity?'outlet:'+identity+':'+floor.key:'group:'+(groupId||record.group_id||'unassigned');
    if(!groups.has(key))groups.set(key,{key,floor:floor.key,floor_label:floor.label,name:identity?(outlet?.name||record.outlet_name):record.name||'未分组资料',outlet_id:identity,identity_label:identity?(outlet?'独立窗口':'已录入店铺'):'菜单资料组',
      hours:identity?(outlet?.hours_label||record.outlet_hours_label||'尚未录入'):null,items:[],group_ids:[],item_count:0,count_known:true,simulated:record.data_mode==='simulated'});
    const section=groups.get(key);if(groupId&&!section.group_ids.includes(groupId)){section.group_ids.push(groupId);if(Number.isInteger(record.item_count)&&record.item_count>=0)section.item_count+=record.item_count;else section.count_known=false;}return section;
  };
  const byGroup=new Map();for(const record of uniqueMenuRecords(card.menu_groups||[])){const section=create(record,record.id);byGroup.set(record.id,{section,record});}
  for(const item of uniqueMenuRecords(card.menu||[])){
    const match=byGroup.get(item.group_id);let section;
    if(match&&(!item.outlet_id||item.outlet_id===match.record.outlet_id))section=match.section;
    else if(match){section=create({name:'归属待核资料',group_id:'conflict-'+item.group_id,floor:null});section.count_known=false;}
    else{section=create({outlet_id:item.outlet_id,outlet_name:item.outlet_name,outlet_hours_label:item.outlet_hours_label,identity_status:item.identity_status,data_mode:item.data_mode,floor:item.floor,name:'未分组资料',group_id:item.group_id});section.count_known=false;}
    section.items.push(item);if(item.data_mode==='simulated')section.simulated=true;
  }
  return [...groups.values()];
}
// MENU_BROWSER_PURE_END
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
  const filters=node('details',undefined,'directory-filters');filters.open=false;filters.append(node('summary',state.area||state.kind?'调整筛选 · 已筛选':'筛选类型与区域'),sub,areas,select);
  input.oninput=()=>{state.limit=40;fill();};select.onchange=()=>{state.limit=40;fill();};body.append(input,filters,summary,notice,list,pager);fill();}
function setCategoryButtons(){for(const b of $('categories').children)b.setAttribute('aria-pressed',String(b.dataset.category===state.category));}
function showCluster(ids){detailsToken++;state.panel='cluster';const members=rows.filter(p=>ids.includes(p.id));const id=members[0]?.building_id,b=buildings.find(b=>b.id===String(id));setAgentSelection(b?{kind:'building',id:b.id}:null);openPanel(b?.name||'同栋建筑内的地点',`${members.length} 个地点 · 选择一家查看`);const body=$('panel-body');body.replaceChildren(button('← 返回地点清单',drawList,'text-button'),node('p','这些店铺共用楼栋标记，标记不是各店入口。','meta'),...members.map((p,i)=>placeRow(p,i)));if(members.length)map?.focus(members[0].id,!keyboard());}
function returnFromPlace(){
  if(placeReturn?.view==='chat'&&placeReturn.conversationId===conversation.id){chatPanel({restore:true});return;}
  const top=placeReturn?.scroll||0;state.panel='list';drawList();$('panel-body').scrollTop=top;
}
async function showPlace(id,{siblings=null,move=true}={}){const p=rows.find(r=>r.id===id);if(!p)return;endTour();
  if(state.panel!=='detail')placeReturn={view:state.panel,conversationId:conversation.id,scroll:$('panel-body').scrollTop};
  state=reduceState(state,{type:'select',id});setAgentSelection({kind:'poi',id});openPanel(p.name,p.category_label||'校园地点');if(move)map?.focus(id,!keyboard());
  $('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',p.name),node('small',(p.floor?p.floor+'层 · ':'')+positionNote(p)));
  const token=++detailsToken,body=$('panel-body');body.replaceChildren();body.append(button(placeReturn?.view==='chat'?'← 返回这次回答':'← 返回地点清单',returnFromPlace,'text-button detail-back'));
  const content=node('div');body.append(content);renderPlace(p,content);
  const same=siblings||rows.filter(r=>p.building_id!=null&&String(r.building_id)===String(p.building_id)).map(r=>r.id);
  if(same.length>1){const group=node('details');group.append(node('summary','同楼还有 '+(same.length-1)+' 个地点'));for(const ident of same.filter(x=>x!==id)){const row=rows.find(r=>r.id===ident);if(row)group.append(button(row.name,()=>showPlace(ident),'history-row'));}body.append(group);}
  try{const detail=await request('/api/app/place?id='+encodeURIComponent(id));if(token!==detailsToken||state.panel!=='detail'||state.selected!==id)return;renderPlace(detail.cards[0],content);if(detail.cards[0].menu?.length)$('pin-caption').append(node('small','已录入样例：'+detail.cards[0].menu.slice(0,2).map(m=>m.name).join(' · ')));}catch(e){if(token===detailsToken&&state.panel==='detail'){content.append(node('p',errorInfo(e).message+' 已保留基础资料。','notice'),button('重试加载详情',()=>showPlace(id,{move:false}),'action secondary'));}}
}
function renderPlace(raw,host,menuState={query:'',floor:'',open:new Set()}){rememberAgentEntities([raw]);const p=present(raw,rows);host.replaceChildren(node('p',p.address||'具体地址尚待补充','detail-copy'));
  if(p.menu?.length){const samples=node('div',undefined,'sample-strip');samples.append(node('small','已录入样例 · 非热销排行'));for(const m of p.menu.slice(0,3))samples.append(node('span',m.name+(m.price==null?'':' ¥'+m.price),'pill'));host.append(samples);}
  for(const [label,value] of [[p.hours_label||'开放时间',p.hours||'尚未记录，请以现场公告为准'],['楼层与位置',(p.floor?p.floor+'层 · ':'')+positionNote(p)]]){const line=node('div',undefined,'info-line');line.append(node('small',label),node('span',value));host.append(line);}
  if(p.hours_notes)host.append(node('p',p.hours_notes,'meta'));if(p.simulation)host.append(node('p','模拟资料，仅用于演示。','notice'));
  if(p.service_info?.summary){
    const info=p.service_info;host.append(node('h3','服务说明'),node('p',info.summary,'detail-copy'));
    try{const source=new URL(info.source_url);if(source.protocol==='https:'&&source.hostname==='news.bnu.edu.cn'){
      const link=node('a','查看学校报道'+(info.published_at?' · '+info.published_at:''),'text-button');
      link.href=source.href;link.target='_blank';link.rel='noopener noreferrer';host.append(link);
    }}catch{/* Invalid source URLs remain plain text and are not opened. */}
  }
  const actions=node('div',undefined,'action-row'),known=rows.find(r=>r.id===(p.id||p.poi_id))||p;if(inModel(known)||p.map_reference)actions.append(button(p.map_reference?'查看参照区域':'定位到地图',()=>{hideIntro();map?.focus(p.id||p.poi_id,!keyboard());},'action'));else if(known.spatial_sequence)actions.append(button('查看所在区域名录',()=>{state.category='all';state.area=known.spatial_sequence.group;state.query='';state.kind='';state.limit=40;setCategoryButtons();drawList();},'action'));actions.append(button('问问助手',()=>{$('ask-input').value='介绍一下'+p.name+'，有什么需要注意的？';chatPanel({restore:true});$('ask-input').focus();},'action secondary'));host.append(actions);
  if(p.collection_label){const menu=node('section',undefined,'menu menu-browser');menu.append(node('h3',p.collection_label+'与规格'),node('p','按店铺与窗口整理；记录价格不代表实时在售。','meta'));
    if(p.menu===undefined)menu.append(node('p','正在读取已录入资料…','meta'));
    else if(!p.menu.length)menu.append(node('p','暂无已录入'+p.collection_label+'，不使用模拟内容填充。','notice'));
    else {
      const sections=menuBrowserGroups(p),finder=node('input'),list=node('div',undefined,'outlet-list'),floors=[...new Map(sections.map(s=>[s.floor,s.floor_label]))];finder.className='finder menu-finder';finder.placeholder='搜索窗口或已加载菜品';finder.setAttribute('aria-label','搜索窗口或菜品');finder.value=menuState.query;
      const tabs=node('nav',undefined,'floor-tabs');tabs.setAttribute('aria-label','菜单楼层');if(!floors.some(([key])=>key===menuState.floor))menuState.floor='';
      const progress=node('p',Number.isInteger(p.menu_total)?`已加载 ${p.menu.length} / ${p.menu_total} 条商品记录`:`已加载 ${p.menu.length} 条商品记录；总数未提供`,'menu-progress');progress.setAttribute('role','status');
      function fill(){menuState.query=finder.value;const query=menuState.query.trim().toLocaleLowerCase();list.replaceChildren();for(const tab of tabs.children)tab.setAttribute('aria-pressed',String(tab.dataset.floor===menuState.floor));let shown=0;
        for(const section of sections){if(menuState.floor&&section.floor!==menuState.floor)continue;const matchedName=section.name.toLocaleLowerCase().includes(query),items=section.items.filter(item=>!query||matchedName||[item.name,item.specification].filter(Boolean).join(' ').toLocaleLowerCase().includes(query));if(query&&!matchedName&&!items.length)continue;shown++;
          const disclosure=node('details',undefined,'outlet-disclosure');disclosure.dataset.outletId=section.outlet_id||'';disclosure.dataset.menuGroup=section.key;disclosure.open=!!query||menuState.open.has(section.key);disclosure.ontoggle=()=>{if(disclosure.open)menuState.open.add(section.key);else menuState.open.delete(section.key);};
          const summary=node('summary'),heading=node('span',undefined,'outlet-heading');heading.append(node('strong',section.name),node('small',section.floor_label+' · '+section.identity_label+(section.simulated?' · 含模拟资料':'')));summary.append(heading,node('span',section.count_known?`${section.items.length} / ${section.item_count} 条`:`${section.items.length} 条已加载`,'outlet-count'));disclosure.append(summary);
          if(section.outlet_id){const window=section.identity_label==='独立窗口';disclosure.append(node('p',(window?'窗口':'店铺')+'营业时间：'+section.hours,'outlet-hours'));const ref={kind:'outlet',id:section.outlet_id};if(!section.simulated&&agentAPI?.loadedEntity(ref,agentCatalog()))disclosure.append(button(window?'问这个窗口':'问这家店',()=>{setAgentSelection(ref);$('ask-input').value='介绍一下'+section.name+'，有哪些已录入'+p.collection_label+'？';chatPanel({restore:true});$('ask-input').focus({preventScroll:true});},'text-button outlet-ask'));}
          else disclosure.append(node('p','此组仅整理菜品资料，不视为已确认的独立窗口。','meta'));
          for(const item of items){const row=node('div',undefined,'menu-row'),name=node('span',item.name);name.append(node('small',(item.specification||'规格未注明')+(item.data_mode==='simulated'?' · 模拟资料':'')));row.append(name,node('b',item.price==null?'待询价':'¥'+item.price));disclosure.append(row);}
          if(!section.items.length)disclosure.append(node('p','该窗口或分组的商品尚未加载到当前页，可继续加载下方资料。','meta'));else if(query&&!items.length)disclosure.append(node('p','当前已加载商品无匹配项。','meta'));list.append(disclosure);
        }if(!shown)list.append(node('p','当前已加载资料没有匹配结果；可清空筛选，或继续加载更多商品。','notice'));
      }
      for(const [key,label] of [['','全部楼层'],...floors]){const tab=button(label,()=>{menuState.floor=key;fill();});tab.dataset.floor=key;tabs.append(tab);}finder.oninput=fill;menu.append(progress,finder);if(floors.length>1)menu.append(tabs);menu.append(list);fill();
      if(Number.isInteger(p.menu_total)&&menuCursor(p)<p.menu_total){const more=button('继续加载'+p.collection_label,async()=>{more.disabled=true;try{const next=await request('/api/app/place?id='+encodeURIComponent(p.poi_id||p.id)+'&offset='+menuCursor(p));if(!host.isConnected)return;const merged=mergeMenuPage(p,next.cards?.[0]);renderPlace(merged,host,menuState);}catch(e){if(host.isConnected){more.disabled=false;toast(errorInfo(e).message);}}},'action secondary menu-load-more');menu.append(more);}
    }
    host.append(menu);}
  host.append(node('p','资料来源：'+sourceLabel(p.source)+'；营业与商品以现场信息为准。','meta'));
}
function markResultSelection(id){if(!chatView)return;for(const card of chatView.root.querySelectorAll('.chat-result')){const selected=card.dataset.poiId===id;card.dataset.selected=String(selected);card.querySelector('[data-locate]')?.setAttribute('aria-pressed',String(selected));}}
function locateResult(id,ref=null){const p=rows.find(r=>r.id===id);if(!p)return;state.selected=id;setAgentSelection(ref||{kind:'poi',id});hideIntro();map?.stopRoam();map?.focus(id,!keyboard());markResultSelection(id);$('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',p.name),node('small',(p.floor?p.floor+'层 · ':'')+positionNote(p)));}
function renderResult(raw){rememberAgentEntities([raw]);const c=present(raw,rows),box=node('div',undefined,'chat-result'),heading=node('div',undefined,'result-heading');if(raw.outlet_id&&raw.type==='place')c.name=raw.outlet_name||raw.name;heading.append(node('h3',c.name));if(c.price!=null){const price=node('span',undefined,'result-price');price.append(node('strong','¥'+c.price),node('small','记录价'));heading.append(price);}box.append(node('span',c.simulation?'模拟样例':c.category_label||'候选','result-category'),heading);
  if(c.shop)box.append(node('p',c.shop+(c.floor?' · '+c.floor+'层':'')));if(c.address)box.append(node('p',c.address));if(c.reasons?.length)box.append(node('p',c.reasons.join('；')));if(c.unknown?.length)box.append(node('p','待确认：'+c.unknown.join('；'),'notice'));
  if(c.type==='schedule')box.append(node('p',c.start+' — '+c.end+' · '+c.location_name+'（模拟课表）'));
  if(c.total_minutes!=null)box.append(node('p','估算用时 '+c.total_minutes+' 分钟，包含估计或模拟值，不保证按时。'));
  const id=c.poi_id||c.id,known=rows.find(r=>r.id===id);box.dataset.poiId=id||'';
  if(known){const actions=node('div',undefined,'result-actions'),ref=agentAPI?.entityReference(c.outlet_id?{kind:'outlet',id:c.outlet_id}:{kind:'poi',id});if(inModel(known)||known.map_reference){const locate=button(known.map_reference?'查看参照区域':'在地图看',()=>locateResult(id,ref),'action secondary');locate.dataset.locate=id;locate.setAttribute('aria-pressed',String(state.selected===id));actions.append(locate);}else actions.append(node('span',positionNote(known),'meta'));
    if(c.outlet_id&&agentAPI?.loadedEntity(ref,agentCatalog()))actions.append(button('问这个窗口',()=>{setAgentSelection(ref);$('ask-input').focus({preventScroll:true});},'text-button'));
    actions.append(button('地点详情 →',()=>showPlace(id,{move:false}),'text-button'));box.append(actions);}
  return box;
}
function appendSources(host,sources){
  for(const source of [...new Set(sources)]){
    const url=agentAPI?.safeSourceUrl(source);if(url){const link=node('a','查看来源','text-button');link.href=url;link.target='_blank';link.rel='noopener noreferrer';host.append(link);}
    else host.append(node('p','来源：'+(['simulated','menu_photo','baidu_place_v2','user_reported'].includes(source)?sourceLabel(source):source),'meta'));
  }
}
function focusAgentEntity(action){
  const target=agentAPI?.resolveMapAction(action,agentCatalog());if(!target)return toast('该对象尚无可核对的地图位置。');
  setAgentSelection(target.ref);hideIntro();map?.stopRoam();
  if(target.target==='poi'){locateResult(target.target_id,target.ref);if(target.ref.kind==='outlet')$('pin-caption').replaceChildren(node('span',target.name),node('small','窗口所在地点的参照定位 · 非窗口入口'));}
  else{state.selected=null;map?.focusBuilding(target.target_id,!keyboard());markResultSelection(null);$('pin-caption').hidden=false;$('pin-caption').replaceChildren(node('span',target.name),node('small',target.ref.kind==='building'?'已选中建筑':'所在建筑的参照定位 · 非店铺入口'));}
}
function renderAgentExtras(data){
  const root=node('div',undefined,'agent-extras');if(!data)return root;
  for(const relation of data.relations){
    const section=node('section',undefined,'agent-relations');section.setAttribute('aria-label',relation.title);
    section.append(node('h3',relation.title+(relation.anchor?' · '+relation.anchor:'')),node('p',`已展示 ${relation.items.length} / ${relation.total} 条关联记录${relation.truncated?'；结果有界，未展示全部':''}。关系解释不是导航路线。`,'meta'));
    if(!relation.items.length)section.append(node('p','本次范围内未查到关系，不代表现实中没有服务。','notice'));
    for(const item of relation.items){
      const row=node('article',undefined,'relation-item');row.append(node('small',item.kind,'meta'),node('strong',item.name));
      if(item.path.length)row.append(node('p',item.path.join(' → '),'relation-path'));
      if(item.concepts.length)row.append(node('p','共同资料：'+item.concepts.join('、'),'meta'));
      if(item.ref&&agentAPI?.loadedEntity(item.ref,agentCatalog()))row.append(button('选为提问对象',()=>{setAgentSelection(item.ref);$('ask-input').focus({preventScroll:true});},'text-button'));
      const details=node('details',undefined,'source-details');details.append(node('summary','关系依据与待确认'));
      if(item.spatialPath.length)details.append(node('p','空间依据：'+item.spatialPath.join(' → '),'meta'));
      for(const edge of item.edges){details.append(node('p',edge.label+' · '+edge.status,'meta'));if(edge.distance)details.append(node('p',edge.distance,'meta'));appendSources(details,edge.source);for(const limitation of edge.limitations)details.append(node('p',limitation,'notice'));}
      for(const limitation of item.limitations)details.append(node('p',limitation,'notice'));
      row.append(details);section.append(row);
    }
    const limits=node('details',undefined,'source-details');limits.append(node('summary','本次关系查询的范围与限制'));for(const limitation of relation.limitations)limits.append(node('p',limitation,'notice'));if(relation.gap)limits.append(node('p',relation.gap,'notice'));section.append(limits);root.append(section);
  }
  if(data.evidence.length){
    const sources=node('details',undefined,'source-details agent-evidence');sources.append(node('summary',`回答依据与待确认（${data.evidence.length} 条）`));
    for(const item of data.evidence){const line=node('div',undefined,'evidence-item');line.append(node('p',(item.simulated?'模拟资料 · ':'')+(item.kind==='limitation'?'待确认：':'已查资料：')+item.text,item.kind==='limitation'?'notice':'meta'));appendSources(line,item.source);sources.append(line);}root.append(sources);
  }
  const actions=node('div',undefined,'agent-map-actions'),seen=new Set();
  for(const action of data.map_actions){const target=agentAPI?.resolveMapAction(action,agentCatalog());if(!target)continue;const key=target.ref.kind+':'+target.ref.id;if(seen.has(key))continue;seen.add(key);actions.append(button((target.ref.kind==='outlet'?'查看窗口所在地点：':'在地图看：')+target.name,()=>focusAgentEntity(action),'action secondary'));}
  if(actions.children.length)root.append(actions);
  for(const notice of data.notices)root.append(node('p',notice,'notice'));
  return root;
}
function chatPanel({restore=true,latest=false,compact=false}={}){const from=chatBounds(),wasChat=state.panel==='chat';detailsToken++;state.panel='chat';openPanel('校园生活助手',active?'正在查询校园资料':'查地点 · 找吃喝');if(latest||compact)setChatPeek(compact,{animate:false});renderChat({restore,latest});if(!wasChat||compact)morphChat(from);}
function createChatView(){
  const root=node('div',undefined,'chat-view'),toolbar=node('div'),messages=node('div',undefined,'chat-messages'),empty=node('section',undefined,'chat-empty');toolbar.id='chat-toolbar';toolbar.setAttribute('aria-label','对话操作');
  toolbar.append(button('新对话',()=>{if(active)return toast('请先停止当前请求');conversation=fresh();accountPatch={};setAgentSelection(null);resetChatView();map?.filter(null);$('pin-caption').hidden=true;renderChat();},'text-button'),button('历史记录',historyPanel,'text-button'));
  if(account.enabled)toolbar.append(button('我的偏好',()=>account.open(),'text-button'));
  empty.append(node('h3','今天，想去哪里？','detail-title'),node('p','找一餐饭、一杯咖啡，或校园里的一栋楼。','detail-copy'));
  for(const text of ['20元以内想吃辣，不吃米饭','新乐群三层有什么？','瑞幸咖啡在哪里？'])empty.append(button(text,()=>{$('ask-input').value=text;$('ask-input').focus();},'history-row'));
  empty.append(button('也可以按条件查找 →',conditionPanel,'text-button'));
  const storage=node('details',undefined,'chat-storage');storage.append(node('summary','关于资料与对话'),node('p',account.enabled?'AI 对话按账号保存。条件筛选结果仅本次可见，不写入聊天历史。':db?'对话保存在本机浏览器，未写入校园数据库。':'对话仅在当前页面保留，本机历史暂不可用。','meta'),node('p','回答依据已发布资料；价格、营业与入口未知时会明确提示。','meta'));
  root.append(toolbar,empty,messages,storage);return {root,messages,empty,id:conversation.id,entries:new Map()};
}
function renderChat({restore=false,latest=false}={}){
  if(state.panel!=='chat')return;const body=$('panel-body');
  renderIsland();
  $('ask-input').placeholder=conversation.messages.length?'继续问，或换一个条件…':'想吃什么，想去哪里？';
  if(!chatView||chatView.id!==conversation.id){chatView=createChatView();chatScroll=0;chatFollow=true;chatUnread=false;}
  const peek=$('panel').dataset.peek==='true',attached=chatView.root.parentElement===body,previousScroll=restore||!attached||peek?chatScroll:body.scrollTop,follow=chatFollow;let changed=false;
  if(!attached)body.replaceChildren(chatView.root);
  chatView.empty.hidden=conversation.messages.length>0;
  for(const m of conversation.messages){
    let entry=chatView.entries.get(m);
    if(!entry){const box=node('article',undefined,'chat-msg '+m.role),copy=node('div',undefined,'message-copy'),cards=node('div',undefined,'message-cards'),extras=node('div',undefined,'message-extras'),feedback=node('div',undefined,'message-feedback');box.setAttribute('aria-label',m.role==='user'?'你的问题':'助手回答');box.append(copy,cards,extras,feedback);chatView.messages.append(box);entry={box,copy,cards,extras,feedback,cardKey:null,extraKey:null,errorKey:null};chatView.entries.set(m,entry);changed=true;}
    const text=m.error?errorInfo(m.failure||m.content).message:m.pending?m.status||'正在查询校园资料…':m.content||'';
    if(entry.copy.textContent!==text){entry.copy.textContent=text;changed=true;}
    entry.box.dataset.pending=String(!!m.pending);entry.copy.setAttribute('role',m.pending?'status':'group');
    const cardKey=JSON.stringify(m.cards||[]);if(cardKey!==entry.cardKey){entry.cards.replaceChildren(...(m.cards||[]).map(renderResult));entry.cardKey=cardKey;changed=true;}
    const extraData=agentResponses.get(m),extraKey=JSON.stringify(extraData||null);if(extraKey!==entry.extraKey){entry.extras.replaceChildren();if(extraData)entry.extras.append(renderAgentExtras(extraData));entry.extraKey=extraKey;changed=true;}
    const errorKey=m.error?JSON.stringify(m.failure||m.content):'';
    if(errorKey!==entry.errorKey){entry.feedback.replaceChildren();if(m.error){entry.feedback.append(node('p','仍可浏览地图和地点，或直接按条件找一餐。','meta'));if(m.request&&errorInfo(m.failure).retryable)entry.feedback.append(button('重试这次请求',()=>send(m.request.message,m),'action secondary'));entry.feedback.append(button('打开条件推荐',conditionPanel,'text-button'));}entry.errorKey=errorKey;changed=true;}
  }
  markResultSelection(state.selected);$('panel-kicker').textContent=active?'正在查询校园资料':'查地点 · 找吃喝';
  if(peek){chatUnread=chatUnread||changed;$('panel-size').textContent=chatUnread?'继续对话 · 有更新':'继续对话';$('chat-updates').hidden=true;return;}
  if(latest){body.scrollTop=body.scrollHeight;chatFollow=true;chatUnread=false;}
  else if(!attached||restore)body.scrollTop=previousScroll;
  else if(changed&&follow){body.scrollTop=body.scrollHeight;chatUnread=false;}
  else if(changed){body.scrollTop=previousScroll;chatUnread=true;}
  chatScroll=body.scrollTop;$('chat-updates').hidden=!chatUnread;
}
async function historyPanel(){if(active)return toast('请先停止当前请求');if(!account.require())return;if(account.enabled)try{history=await account.history();}catch(e){toast(e.message);return;}state.panel='history';openPanel('我的对话',account.enabled?'仅当前账号可读取 · 服务端保存':'仅保存在这台设备');const body=$('panel-body');body.replaceChildren();for(const item of history){body.append(button(item.title,()=>{conversation=structuredClone(item);accountPatch={};for(const m of conversation.messages)if(m.pending){m.pending=false;m.error=true;m.content='上次请求未完成，请重新发送。';}chatPanel();},'history-row'));if(account.enabled)body.append(button('删除这段对话',async()=>{if(!confirm('删除“'+item.title+'”及其聊天内容？此操作不可撤回。'))return;try{await account.remove(item.id);if(conversation.id===item.id)conversation=fresh();historyPanel();}catch(e){toast(e.message);}},'text-button'));}if(!history.length)body.append(node('p','还没有保存的对话。','meta'));}
$('chat').onclick=chatPanel;
$('header-chat').onclick=historyPanel;
$('settings-history').onclick=historyPanel;
async function send(text,retry=null){text=text.trim();if(!text||active||!account.require())return;const previousCards=conversation.messages.filter(m=>m.role==='assistant'&&!m.error&&!m.pending).at(-1)?.cards||[];const payload=retry?structuredClone(retry.request):{request_id:crypto.randomUUID(),conversation_id:conversation.id,message:text,conditions:structuredClone(account.enabled?accountPatch:conversation.conditions),mode:conversation.mode,...(agentAPI?{context:agentAPI.agentRequestContext(selectedEntity)}:{}),...(account.enabled?{}:{history:conversation.messages.filter(m=>!m.error&&!m.pending).slice(-12).map(m=>({role:m.role,content:m.content})),previous_poi_ids:selectionIds(previousCards,rows),...(agentAPI?{previous_entities:agentAPI.previousEntities(previousCards)}:{})})};
  if(!agentAPI){delete payload.context;delete payload.previous_entities;}
  if(retry&&!['NETWORK','REQUEST_ACTIVE'].includes(retry.failure?.code))payload.request_id=crypto.randomUUID();
  const reply=retry||{role:'assistant',cards:[],time:new Date().toISOString()};if(!retry){conversation.messages.push({role:'user',content:text},reply);if(conversation.messages.length===2)conversation.title=text.slice(0,24);}Object.assign(reply,{content:'',pending:true,error:false,failure:null,request:payload});
  agentResponses.delete(reply);
  const compact=state.panel!=='chat'||$('panel').dataset.peek==='true';
  const controller=new AbortController(),epoch=identityEpoch;active={controller,id:payload.request_id};$('ask-input').value='';$('ask-send').disabled=true;$('ask-stop').hidden=false;chatPanel({latest:true,compact});await save();
  try{await chatStream(payload,controller.signal,e=>{if(epoch!==identityEpoch)return;if(e.type==='status')reply.status=e.text;if(e.type==='cards'){reply.cards=Array.isArray(e.cards)?e.cards:[];rememberAgentEntities(reply.cards);conversation.conditions=e.conditions||conversation.conditions;map?.filter(selectionIds(reply.cards,rows));}if(e.type==='result'){reply.content=e.data.answer;reply.cards=Array.isArray(e.data.cards)?e.data.cards:[];rememberAgentEntities(reply.cards,e.data.relations,e.data.entities);if(agentAPI)agentResponses.set(reply,agentAPI.agentResponseExtras(e.data));reply.pending=false;conversation.conditions=e.data.conditions||conversation.conditions;map?.filter(reply.cards.length?selectionIds(reply.cards,rows):null);}if(e.type==='error'){reply.error=true;reply.failure=errorInfo(e);reply.content=reply.failure.message;reply.pending=false;}renderChat();});}
  catch(e){reply.error=true;reply.failure=errorInfo(e);reply.content=reply.failure.message;}finally{if(epoch===identityEpoch){reply.pending=false;active=null;if(!reply.error)accountPatch={};$('ask-send').disabled=false;$('ask-stop').hidden=true;renderChat();await save();updateModel();}}}
$('ask-form').onsubmit=e=>{e.preventDefault();send($('ask-input').value);};$('ask-stop').onclick=()=>{if(!active)return;const {controller,id}=active;request('/api/agent/cancel',{request_id:id}).catch(()=>toast('已停止本机等待；服务端停止请求未确认。'));controller.abort();};
function conditionPanel(){state.panel='conditions';openPanel('找到适合的一餐','按你的条件，查已知资料');const body=$('panel-body');body.replaceChildren(node('p','直接筛选已录入资料，无需大模型。未知耗时不会被当成时间保证。','meta'));const form=node('form');form.className='condition-form';
  const fields={};for(const [key,label,type,placeholder] of [['budget','预算上限（元）','number','例如20'],['taste','偏好口味','text','例如辣'],['avoid','不吃什么','text','例如米饭'],['available_minutes','可用时间（分钟）','number','不知道可留空']]){const l=node('label',label),input=node('input');input.type=type;input.placeholder=placeholder;input.name=key;if(type==='number'){input.min='1';input.max='10000';input.step='any';}input.value=Array.isArray(conversation.conditions[key])?conversation.conditions[key].join('、'):conversation.conditions[key]??'';l.append(input);form.append(l);fields[key]=input;}
  const l=node('label','当前位置'),select=node('select');select.add(new Option('选择地点（时间筛选需要）',''));const seen=new Set();for(const p of [...locations,...rows.filter(r=>r.location)])if(!seen.has(p.id)){select.add(new Option(p.name,p.id));seen.add(p.id);}select.value=conversation.conditions.current_location||'';l.append(select);form.append(l);
  const submit=node('button','按条件查看候选','action');submit.type='submit';form.append(submit);form.onsubmit=async e=>{e.preventDefault();if(active)return toast('请先停止当前助手请求');submit.disabled=true;const conditions={...conversation.conditions};for(const k of ['budget','available_minutes']){if(fields[k].value)conditions[k]=Number(fields[k].value);else delete conditions[k];}for(const k of ['taste','avoid'])conditions[k]=fields[k].value.split(/[、,，]/).map(x=>x.trim()).filter(Boolean);if(select.value)conditions.current_location=select.value;else delete conditions.current_location;
    try{const result=await request('/api/app/candidates',{conditions,mode:'real'});conversation.conditions=conditions;accountPatch={...conditions,budget:conditions.budget??null,available_minutes:conditions.available_minutes??null,current_location:conditions.current_location??null};conversation.messages.push({role:'assistant',content:result.clarification||((result.cards.length?'按已知条件找到这些候选。':'没有符合条件的候选。')+' '+(result.notice||'')+' '+Object.keys(result.rejected||{}).join('、')),cards:result.cards,time:new Date().toISOString()});map?.filter(selectionIds(result.cards,rows));chatPanel();await save();}catch(e){toast(errorInfo(e).message);}finally{submit.disabled=false;}};body.append(form);}
$('conditions').onclick=conditionPanel;
$('settings-conditions').onclick=conditionPanel;
document.querySelectorAll('button[data-view]').forEach(b=>b.onclick=()=>{hideIntro();map?.stopRoam();map?.view(b.dataset.view,!keyboard());for(const other of document.querySelectorAll('button[data-view]'))other.setAttribute('aria-pressed',String(other===b));});
$('roam-toggle').onclick=()=>{if($('roam-toggle').getAttribute('aria-pressed')==='true')map?.stopRoam();else map?.resumeRoam();};
$('art-toggle').onclick=()=>{art=!art;$('art-toggle').setAttribute('aria-pressed',String(art));map?.setArt(art);updateArtNote();toast(art?'已开启示意上色；3栋纸感样例不代表真实立面。':'已恢复白模基准。');};
$('atelier-toggle').onclick=()=>{art=art==='atelier'?true:'atelier';map?.setArt(art);hideIntro();updateArtNote();if(art==='atelier'){map?.stopRoam();map?.view('atelier',!keyboard());document.querySelectorAll('button[data-view]').forEach(b=>b.setAttribute('aria-pressed','false'));}const url=new URL(location.href);if(art==='atelier')url.searchParams.set('art','atelier');else url.searchParams.delete('art');window.history.replaceState(null,'',url);};
async function updateModel(){try{const s=await request('/api/agent/status');$('model-status').textContent=s.connection_status==='connected'?'● 助手已连接':s.configured?'○ 助手待连接':'○ 助手未启用';}catch{$('model-status').textContent='○ 本地服务未连接';}}
await account.init();
if(!account.enabled)try{db=await openHistory();history=await listConversations(db);}catch{toast('本机历史不可用，本次仍可使用地图和查询。');}
try{const d=await request('/api/app/directory');rows=d.pois.map(normalizePlace);locations=d.locations;map?.setRows(rows);if(state.panel==='list')drawList();}catch(e){toast(errorInfo(e).message);$('scene-status').textContent='地点加载失败，请确认本地服务后刷新重试。';}
try{buildings=(await request('/api/app/buildings')).buildings;if(state.panel==='list'&&!state.category)drawBuildings();}catch{toast('建筑资料暂未读取；仍可查看地图和店铺分类，请刷新重试。');}
updateArtNote();
updateModel();
window.addEventListener('pagehide',()=>{cancelPanelMotion();layoutObserver?.disconnect();reducedMotion.removeEventListener('change',cancelPanelMotion);map?.dispose();},{once:true});
