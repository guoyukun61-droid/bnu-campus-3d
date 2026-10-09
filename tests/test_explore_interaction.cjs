'use strict';
// Run the actual controller against a small, isolated DOM. This is an interaction
// regression, not a layout/WebGL test; browser screenshots remain a separate gate.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {pathToFileURL}=require('node:url');
const {webcrypto}=require('node:crypto');
const root=path.resolve(__dirname,'..');

class Element {
  constructor(tag,document){this.tagName=tag.toUpperCase();this.ownerDocument=document;this.children=[];this.parentElement=null;this.attributes={};this.dataset={};this.style={};this.className='';this.hidden=false;this.open=false;this.inert=false;this.value='';this._text='';this.listeners={};this.scrollTop=0;this.scrollHeight=1200;this.clientHeight=400;this.selectionStart=0;this.selectionEnd=0;this.replaceCount=0;this.animations=[];}
  get classList(){return {contains:n=>this.className.split(/\s+/).includes(n),add:n=>{if(!this.className.split(/\s+/).includes(n))this.className+=' '+n;},remove:n=>{this.className=this.className.split(/\s+/).filter(x=>x!==n).join(' ');},toggle:(n,on)=>{const value=on??!this.classList.contains(n);if(value)this.classList.add(n);else this.classList.remove(n);return value;}};}
  get textContent(){return this._text+this.children.map(c=>c.textContent).join('');}
  set textContent(value){this.replaceChildren();this._text=String(value??'');}
  get firstChild(){return this.children[0]||null;}
  get lastChild(){return this.children.at(-1)||null;}
  get childNodes(){return this.children;}
  get parentNode(){return this.parentElement;}
  get isConnected(){return this===this.ownerDocument.body||!!this.parentElement?.isConnected;}
  append(...values){for(let value of values){if(typeof value==='string')value=this.ownerDocument.createTextNode(value);value.remove();value.parentElement=this;this.children.push(value);}}
  appendChild(value){this.append(value);return value;}
  prepend(...values){for(const value of values.reverse()){value.remove();value.parentElement=this;this.children.unshift(value);}}
  replaceChildren(...values){this.replaceCount++;for(const child of this.children)child.parentElement=null;this.children=[];this._text='';this.append(...values);}
  remove(){if(this.parentElement){const siblings=this.parentElement.children;siblings.splice(siblings.indexOf(this),1);this.parentElement=null;}}
  contains(value){return value===this||this.children.some(c=>c.contains(value));}
  setAttribute(key,value){this.attributes[key]=String(value);if(key==='class')this.className=String(value);if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=String(value);}
  getAttribute(key){if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]??null;return this.attributes[key]??null;}
  removeAttribute(key){delete this.attributes[key];}
  addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
  removeEventListener(name,fn){this.listeners[name]=(this.listeners[name]||[]).filter(x=>x!==fn);}
  dispatchEvent(event){event.target??=this;for(const fn of this.listeners[event.type]||[])fn(event);return true;}
  matches(selector){if(selector.startsWith('#'))return this.id===selector.slice(1);if(selector.startsWith('.'))return selector.slice(1).split('.').every(n=>this.classList.contains(n));const m=selector.match(/^([\w-]+)?(?:\[([\w-]+)(?:="([^"]+)")?\])?$/);return !!m&&(!m[1]||this.tagName===m[1].toUpperCase())&&(!m[2]||(this.getAttribute(m[2])!==null&&(m[3]===undefined||this.getAttribute(m[2])===m[3])));}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(child.matches(selector)?[child]:[]),...child.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){return this.matches(selector)?this:this.parentElement?.closest(selector)||null;}
  focus(){this.ownerDocument.activeElement=this;}
  setSelectionRange(start,end){this.selectionStart=start;this.selectionEnd=end;}
  getBoundingClientRect(){return this.id==='panel'?{left:360,top:this.dataset.peek==='true'?450:160,width:560,height:this.dataset.peek==='true'?238:528}:{left:350,top:620,width:540,height:60};}
  animate(keyframes,options){const animation={keyframes,options,cancelled:false,cancel(){this.cancelled=true;},finished:Promise.resolve()};this.animations.push(animation);return animation;}
  add(value){this.append(value);}
  scrollTo(options){this.scrollTop=typeof options==='number'?options:options.top;}
}

function createDocument(html){
  const document={ids:new Map(),activeElement:null,listeners:{},createElement(tag){return new Element(tag,this);},createElementNS(namespace,tag){const el=this.createElement(tag);el.namespaceURI=namespace;return el;},createTextNode(text){const el=this.createElement('#text');el._text=text;return el;},getElementById(id){return this.ids.get(id)||null;},querySelector(selector){return this.body.querySelector(selector);},querySelectorAll(selector){return this.body.querySelectorAll(selector);},addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}};
  document.body=document.createElement('body');
  for(const match of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)){const el=document.createElement(match[1]);el.id=match[2];document.ids.set(el.id,el);document.body.append(el);if(/\bhidden\b/.test(match[0]))el.hidden=true;}
  const get=id=>document.getElementById(id),home=document.createElement('section');home.className='search-dock';document.body.append(home);home.append(get('ask-form'));
  get('ask-form').append(get('ask-input'),get('ask-send'),get('ask-stop'));
  get('panel').append(get('panel-title'),get('panel-kicker'),get('panel-body'),get('panel-composer'),get('chat-updates'),get('panel-size'),get('close-panel'));
  get('panel').dataset.open='false';get('panel-composer').hidden=true;get('chat-updates').hidden=true;
  get('settings').append(document.createElement('summary'));
  return document;
}

(async()=>{
  const stateModule=await import(pathToFileURL(path.join(root,'app/explore/state.js')));
  const agentContext=await import(pathToFileURL(path.join(root,'app/explore/agent-context.js')));
  const presentation=await import(pathToFileURL(path.join(root,'app/presentation.js')));
  const html=fs.readFileSync(path.join(root,'app/explore/index.html'),'utf8');
  const document=createDocument(html),get=id=>document.getElementById(id);
  const rows=[{id:'fixture-food',name:'隔离测试餐厅',display_category:'food',address:'测试建筑一层',floor:'1',building_id:'fixture-building',location:{x:1,y:1},hours:'09:00–20:00',menu:[],menu_total:0},{id:'fixture-unknown',name:'隔离测试待定位店',display_category:'food',location:null},{id:'fixture-sibling',name:'隔离测试同楼咖啡',display_category:'drinks',building_id:'fixture-building',location:{x:1,y:1},menu:[],menu_total:0}];
  const mapCalls=[];
  const fixtureMap=new Proxy({},{get:(_,key)=>(...args)=>mapCalls.push({key,args})});
  const transport=[];let detailFailure=false,delayedDetail=null;
  const request=async(url)=>{transport.push(url);if(url==='/api/app/directory')return {pois:rows,locations:[]};if(url==='/api/app/buildings')return {buildings:[]};if(url==='/api/agent/status')return {configured:false};if(url.startsWith('/api/app/place?id=')){if(detailFailure)throw Error('Failed to fetch');const result={cards:[{...rows.find(x=>x.id===decodeURIComponent(url.split('=')[1])),menu:[],menu_total:0}]};if(delayedDetail){const save=delayedDetail;delayedDetail=null;return new Promise(resolve=>save(()=>resolve(result)));}return result;}throw Error('Unexpected fixture request '+url);};
  let source=fs.readFileSync(path.join(root,'app/explore/main.js'),'utf8').replace(/^import .*;\r?\n/gm,'');
  source=source.replace('const agentExtension=await loadAgentExtension();',"const agentExtension={status:'ready',api:agentContext,notice:''};");
  const sceneStart=source.indexOf("const scenePromise=import('./scene.js')"),sceneEnd=source.indexOf('function setCategory(',sceneStart);
  assert.ok(sceneStart>=0&&sceneEnd>sceneStart,'Scene isolation anchor must match the controller');
  source=source.slice(0,sceneStart)+'map=fixtureMap;\n'+source.slice(sceneEnd);
  const motion={matches:false,addEventListener(){},removeEventListener(){}};
  const context=vm.createContext({document,fixtureMap,request,...stateModule,agentContext,...presentation,crypto:webcrypto,URL,URLSearchParams,location:{search:'',href:'http://fixture.invalid/explore/'},window:{addEventListener(){},history:{replaceState(){}}},matchMedia:()=>motion,Option:function(text,value){const n=document.createElement('option');n.textContent=text;n.value=value;return n;},fetch:async url=>{assert.equal(url,'/api/account/me');return {ok:true,status:200,json:async()=>({enabled:false})};},AbortSignal,AbortController,structuredClone,openHistory:async()=>null,listConversations:async()=>[],saveConversation:async()=>{},chatStream:async()=>{throw Error('Real or mock AI is not part of this UI regression');},setTimeout:()=>0,clearTimeout(){},requestAnimationFrame:fn=>{fn();return 1;},cancelAnimationFrame(){},confirm:()=>false,console});
  const app=await vm.runInContext('(async()=>{'+source+'\nreturn {chatPanel,closePanel,renderChat,renderResult,showPlace,returnFromPlace,setCategory,drawList,resetChatView,getState:()=>state,getConversation:()=>conversation,getAccount:()=>account,setActive:value=>active=value};})()',context,{filename:'explore-controller-fixture.js'});
  const body=get('panel-body'),form=get('ask-form'),input=get('ask-input'),home=document.querySelector('.search-dock');
  let passed=0;
  const check=(name,fn)=>{fn();passed++;console.log('PASS '+name);};

  input.value='尚未发送的输入';input.focus();input.setSelectionRange(2,5);app.chatPanel();
  check('single composer moves into chat without losing draft, focus or selection',()=>{assert.equal(form.parentElement,get('panel-composer'));assert.equal(document.querySelectorAll('#ask-form').length,1);assert.equal(input.value,'尚未发送的输入');assert.equal(document.activeElement,input);assert.equal(input.selectionStart,2);assert.equal(input.selectionEnd,5);assert.equal(home.hidden,true);});
  app.closePanel();
  check('closing chat returns the same form to exploration',()=>{assert.equal(form.parentElement,home);assert.equal(get('panel-composer').hidden,true);assert.equal(input.value,'尚未发送的输入');});
  app.setCategory('eating');
  check('advanced directory filters default collapsed while result rows remain visible',()=>{assert.equal(body.querySelector('.directory-filters')?.open,false);assert.ok(body.querySelectorAll('.place-row').length>=2);});

  const conversation=app.getConversation();
  conversation.messages.push({role:'user',content:'找测试餐厅'},{role:'assistant',content:'测试已知资料',cards:[{type:'place',poi_id:'fixture-food',name:'隔离测试餐厅',unknown:['等待时间未知']}]});
  app.chatPanel();body.scrollTop=180;body.dispatchEvent({type:'scroll'});
  const firstMessage=body.querySelector('.chat-msg'),chatChildren=[...body.children];
  const card=body.querySelector('.chat-result');
  const locate=card.querySelectorAll('button').find(x=>/在地图看/.test(x.textContent));
  assert.ok(locate,'Recommendation needs a separate map-only action');
  locate.onclick();
  check('map-only recommendation action preserves chat DOM and reading position',()=>{assert.equal(app.getState().panel,'chat');assert.equal(body.scrollTop,180);assert.equal(body.querySelector('.chat-msg'),firstMessage);assert.deepEqual(body.children,chatChildren);assert.ok(mapCalls.some(c=>c.key==='focus'&&c.args[0]==='fixture-food'));assert.equal(card.dataset.selected,'true');assert.equal(locate.getAttribute('aria-pressed'),'true');});
  const detail=card.querySelectorAll('button').find(x=>/详情/.test(x.textContent));assert.ok(detail,'Recommendation needs an explicit details action');
  const focusCallsBeforeDetails=mapCalls.filter(c=>c.key==='focus').length;
  await detail.onclick();
  check('details has a return-to-answer action without moving the map again',()=>{assert.equal(app.getState().panel,'detail');assert.ok(body.querySelectorAll('button').some(x=>/返回这次回答/.test(x.textContent)));assert.equal(mapCalls.filter(c=>c.key==='focus').length,focusCallsBeforeDetails);});
  await body.querySelectorAll('button').find(x=>x.textContent==='隔离测试同楼咖啡').onclick();
  check('same-building details keep the original answer return context',()=>{assert.equal(app.getState().selected,'fixture-sibling');assert.ok(body.querySelectorAll('button').some(x=>/返回这次回答/.test(x.textContent)));});
  app.returnFromPlace();
  check('return from details restores answer and previous reading offset',()=>{assert.equal(app.getState().panel,'chat');assert.equal(body.scrollTop,180);assert.equal(body.querySelector('.chat-msg'),firstMessage);});

  const reply=conversation.messages[1];reply.pending=true;reply.status='正在核对测试资料';app.setActive({});app.renderChat();
  const preservedMessage=body.querySelector('.chat-msg'),preservedCard=body.querySelector('.chat-result');
  body.scrollTop=100;body.dispatchEvent({type:'scroll'});reply.status='正在整理测试资料';app.renderChat();
  check('stream update changes only the current message and does not steal scroll',()=>{assert.equal(body.querySelector('.chat-msg'),preservedMessage);assert.equal(body.querySelector('.chat-result'),preservedCard);assert.equal(body.scrollTop,100);assert.equal(get('chat-updates').hidden,false);assert.match(body.textContent,/正在整理测试资料/);});
  const rootReplaceCount=body.replaceCount;
  reply.cards=[{...reply.cards[0],unknown:['等待时间未知','单品价格未知']}];app.renderChat();
  check('changed result cards refresh without replacing unchanged messages or panel root',()=>{assert.equal(body.querySelector('.chat-msg'),preservedMessage);assert.notEqual(body.querySelector('.chat-result'),preservedCard);assert.equal(body.replaceCount,rootReplaceCount);assert.equal(body.scrollTop,100);assert.match(body.textContent,/单品价格未知/);});
  get('chat-updates').onclick();reply.status='完成前的最后一次整理';app.renderChat();
  check('explicit new-answer action resumes following the stream',()=>{assert.equal(get('chat-updates').hidden,true);assert.ok(body.scrollTop>=body.scrollHeight-body.clientHeight);});
  reply.pending=false;reply.content='完整回答已经就绪';app.setActive(null);app.renderChat();
  check('stream completion replaces pending status with final content',()=>{const answer=body.querySelectorAll('.chat-msg').find(x=>x.classList.contains('assistant'));assert.equal(answer.dataset.pending,'false');assert.match(answer.textContent,/完整回答已经就绪/);assert.doesNotMatch(answer.textContent,/完成前的最后一次整理/);});
  body.scrollTop=135;body.dispatchEvent({type:'scroll'});detailFailure=true;await app.showPlace('fixture-food',{move:false});
  check('detail failure exposes a retry and preserves the published base data',()=>{assert.match(body.textContent,/已保留基础资料/);assert.match(body.textContent,/测试建筑一层/);assert.doesNotMatch(body.textContent,/Failed to fetch/);});
  detailFailure=false;await body.querySelectorAll('button').find(x=>/重试加载详情/.test(x.textContent)).onclick();app.returnFromPlace();
  check('detail retry keeps the original answer and scroll return context',()=>{assert.equal(app.getState().panel,'chat');assert.equal(body.scrollTop,135);assert.match(body.textContent,/完整回答已经就绪/);});
  let releaseDetail;delayedDetail=resolve=>{releaseDetail=resolve;};const obsolete=app.showPlace('fixture-food',{move:false});app.chatPanel();releaseDetail();await obsolete;
  check('late detail response cannot replace a reopened chat',()=>{assert.equal(app.getState().panel,'chat');assert.match(body.textContent,/完整回答已经就绪/);assert.equal(form.parentElement,get('panel-composer'));});
  app.closePanel();app.renderChat();
  check('background stream does not reopen closed chat',()=>{assert.equal(app.getState().panel,null);assert.equal(get('panel').dataset.open,'false');});
  const absent=app.renderResult({type:'place',poi_id:'fixture-unknown',name:'隔离测试待定位店',unknown:['位置未核验']});
  check('unknown-location card never offers a false map guarantee',()=>{assert.match(absent.textContent,/位置未核验/);assert.equal(absent.querySelectorAll('button').some(x=>/在地图看/.test(x.textContent)),false);});
  const account=app.getAccount();
  check('explicitly disabled account mode permits legacy use but unknown mode fails closed',()=>{assert.equal(account.enabled,false);assert.equal(account.require(),true);account.enabled=true;assert.equal(account.require(),false);account.enabled=false;});
  account.enabled=true;context.fetch=async()=>({status:404});await account.init();
  check('explicit account endpoint 404 retains supported legacy access',()=>{assert.equal(account.enabled,false);assert.equal(account.require(),true);});
  account.enabled=true;context.fetch=async()=>{throw Error('isolated network failure');};await account.init();
  check('account status network failure never opens anonymous access',()=>{assert.equal(account.enabled,true);assert.equal(account.require(),false);});
  account.enabled=false;
  app.setCategory('eating');document.body.classList.add('keyboard');const keyboardAnimations=body.animations.length;app.chatPanel();
  check('keyboard navigation disables panel animation and map tweening',()=>{assert.equal(body.animations.length,keyboardAnimations);const currentCard=body.querySelector('.chat-result');currentCard.querySelectorAll('button').find(x=>/在地图看/.test(x.textContent)).onclick();assert.equal(mapCalls.filter(c=>c.key==='focus').at(-1).args[1],false);});
  document.body.classList.remove('keyboard');app.setCategory('eating');motion.matches=true;const reducedAnimations=body.animations.length;app.chatPanel();
  check('reduced-motion setting disables panel animations',()=>{assert.equal(body.animations.length,reducedAnimations);});
  motion.matches=false;app.setCategory('eating');const pointerAnimations=body.animations.length;app.chatPanel();
  check('pointer transition uses one bounded transform-opacity animation',()=>{assert.equal(body.animations.length,pointerAnimations+1);const a=body.animations.at(-1);assert.ok(a.options.duration<=300);assert.deepEqual(Object.keys(a.keyframes[0]).sort(),['opacity','transform']);});
  body.scrollTop=111;body.dispatchEvent({type:'scroll'});app.closePanel();app.chatPanel();
  check('closing ordinary chat and reopening preserves its reading offset',()=>{assert.equal(body.scrollTop,111);});
  body.scrollTop=222;body.dispatchEvent({type:'scroll'});const beforePeekRoot=body.firstChild;get('panel-size').onclick();
  check('chat peek retains its mounted content and exposes a continue action',()=>{assert.equal(get('panel').dataset.peek,'true');assert.equal(get('panel-size').getAttribute('aria-expanded'),'false');assert.equal(get('panel-size').textContent,'继续对话');assert.equal(body.firstChild,beforePeekRoot);assert.equal(form.parentElement,get('panel-composer'));});
  // display:none can reset the browser's scroll box; its resulting scroll event
  // must not overwrite the saved reading position while the panel is peeking.
  body.scrollTop=0;body.dispatchEvent({type:'scroll'});reply.pending=true;reply.status='收起面板期间的测试更新';app.setActive({});app.renderChat();
  check('updates while peeking only flag new content and never reopen the panel',()=>{assert.equal(get('panel').dataset.peek,'true');assert.equal(get('panel-size').textContent,'继续对话 · 有更新');assert.equal(get('chat-updates').hidden,true);assert.equal(body.firstChild,beforePeekRoot);});
  get('panel-size').onclick();
  check('expanding peek restores the saved scroll offset and unread affordance',()=>{assert.equal(get('panel').dataset.peek,'false');assert.equal(get('panel-size').getAttribute('aria-expanded'),'true');assert.equal(body.scrollTop,222);assert.equal(get('chat-updates').hidden,false);});
  get('panel-size').onclick();body.scrollTop=0;body.dispatchEvent({type:'scroll'});app.closePanel();app.chatPanel();
  check('closing from peek and reopening restores the original reading position',()=>{assert.equal(get('panel').dataset.peek,'false');assert.equal(body.scrollTop,222);assert.equal(body.firstChild,beforePeekRoot);});
  get('panel-size').onclick();body.scrollTop=0;app.chatPanel({latest:true});
  check('latest-send intent expands peek and follows the latest message',()=>{assert.equal(get('panel').dataset.peek,'false');assert.equal(get('panel-size').getAttribute('aria-expanded'),'true');assert.equal(get('panel-size').textContent,'看地图');assert.ok(body.scrollTop>=body.scrollHeight-body.clientHeight);assert.equal(get('chat-updates').hidden,true);});
  app.closePanel();reply.pending=true;reply.error=false;reply.status='正在检查已发布资料';app.chatPanel({latest:true,compact:true});
  check('compact map question exposes real status and retains exactly one composer',()=>{assert.equal(get('panel').dataset.peek,'true');assert.equal(get('chat-island').hidden,false);assert.equal(get('island-status').textContent,reply.status);assert.match(get('island-preview').textContent,/找测试餐厅/);assert.equal(body.inert,true);assert.equal(document.querySelectorAll('#ask-form').length,1);});
  reply.pending=false;reply.content='答案正文'.repeat(80);app.setActive(null);app.renderChat();
  check('completed answer stays compact with a bounded preview and explicit expansion',()=>{assert.equal(get('panel').dataset.peek,'true');assert.equal(get('island-status').textContent,'回答已就绪');assert.ok(Array.from(get('island-preview').textContent).length<=151);assert.equal(get('island-expand').textContent,'展开完整对话 ↗');});
  const preservedRoot=body.firstChild;input.value='还没发送的追问';get('island-expand').onclick();
  check('island expansion preserves history and draft and unhides reading controls',()=>{assert.equal(get('panel').dataset.peek,'false');assert.equal(get('chat-island').hidden,true);assert.equal(body.inert,false);assert.equal(body.firstChild,preservedRoot);assert.equal(input.value,'还没发送的追问');assert.equal(document.activeElement,get('panel-size'));});
  const shell=get('dialog-shell'),previousAnimation=shell.animations.at(-1);get('panel-size').onclick();
  check('rapid direction reversal cancels the old shell without scaling text',()=>{assert.equal(previousAnimation.cancelled,true);assert.equal(get('panel').dataset.peek,'true');for(const frame of get('panel').animations.at(-1).keyframes)assert.doesNotMatch(frame.transform,/scale/);for(const frame of shell.animations.at(-1).keyframes)assert.deepEqual(Object.keys(frame).sort(),['opacity','transform']);});
  reply.error=true;reply.failure={message:'连接中断，可以重试；地图仍可使用。',retryable:true};app.renderChat();
  check('failed request shows recovery wording, not a success state or raw error',()=>{assert.equal(get('island-status').textContent,'本次回答未完成');assert.match(get('island-preview').textContent,/可以重试/);assert.equal(get('island-expand').textContent,'查看原因与重试 ↗');});
  document.hidden=true;for(const fn of document.listeners.visibilitychange||[])fn();
  check('backgrounding cleans up the morph overlay immediately',()=>{assert.equal(shell.hidden,true);assert.equal(shell.animations.at(-1).cancelled,true);});document.hidden=false;
  const shellCount=shell.animations.length;motion.matches=true;get('island-expand').onclick();
  check('reduced motion changes layout directly without a morph shell',()=>{assert.equal(shell.animations.length,shellCount);assert.equal(get('panel').dataset.peek,'false');assert.equal(body.inert,false);});motion.matches=false;
  get('panel-size').onclick();app.setCategory('eating');
  check('switching to places removes compact chat from accessibility and restores place controls',()=>{assert.equal(get('chat-island').hidden,true);assert.equal(body.inert,false);assert.ok(body.querySelector('.place-row'));assert.equal(shell.hidden,true);});
  app.resetChatView();
  check('identity/conversation reset removes stale summary text',()=>{assert.equal(get('island-preview').textContent,'');assert.equal(get('island-status').textContent,'校园生活助手');});
  check('no model/chat/account-data endpoints are accessed by the regression',()=>{assert.ok(transport.every(x=>x.startsWith('/api/app/')||x==='/api/agent/status'));});
  console.log(`explore-interaction: ${passed} behavioral scenarios passed (isolated DOM; no WebGL or real AI).`);
})().catch(error=>{console.error(error);process.exitCode=1;});
