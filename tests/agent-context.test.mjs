import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import * as agentContext from '../app/explore/agent-context.js';
import {selectionIds} from '../app/explore/state.js';

const {entityReference,previousEntities,agentRequestContext,collectOutletRecords,loadedEntity,
  resolveMapAction,safeSourceUrl,evidencePresentation,relationPresentation,agentResponseExtras}=agentContext;
const rows=[{id:'poi-a',name:'测试餐饮集合',building_id:'building-a',location:{x:2,y:3}},
  {id:'poi-unknown',name:'无位置记录',location:null},
  {id:'poi-far',name:'模型外地点',location:{x:10000,y:10000}}];
const buildings=[{id:'building-a',name:'测试楼'}];
const cards=[{type:'food',id:'dish-a',name:'测试菜品',poi_id:'poi-a',outlet_id:'outlet-a',outlet_name:'甲窗口'},
  {type:'food',id:'dish-b',name:'另一菜品',poi_id:'poi-a',outlet_id:'outlet-b',outlet_name:'乙窗口'}];
const catalog={rows,buildings,outlets:collectOutletRecords(cards)};
const relation={mode:'same_type',anchor:{ref:{kind:'outlet',id:'outlet-a'},name:'甲窗口'},total:4,truncated:true,
  limitations:['不是导航路线。','同类不保证价格和当前营业。'],gaps:{semantic_matches_without_spatial_evidence:2},items:[{
    ref:{kind:'outlet',id:'outlet-b'},name:'乙窗口',poi_id:'poi-a',shared_concepts:[{name:'餐饮服务'}],
    path:{nodes:[{name:'甲窗口'},{name:'餐饮服务'},{name:'乙窗口'}],edges:[{id:'edge-a',type:'provides_service',status:'recorded',
      basis:{source:'公开名录'},limitations:['营业时间未知。']}]},
    spatial_evidence:{path:{nodes:[{name:'甲窗口'},{name:'测试楼'},{name:'乙窗口'}],edges:[{id:'edge-b',type:'same_building_member',
      status:'confirmed',source_links:[{title:'公开资料',url:'https://example.edu/evidence'}]}]},limitations:['同楼不保证室内连通。']},
    limitations:['当前在售未核验。']}]};
const main=await readFile(new URL('../app/explore/main.js',import.meta.url),'utf8');

test('request selection is only a validated reference, never current location or coordinates',()=>{
  assert.deepEqual(agentRequestContext({kind:'building',id:'building-a',name:'不要传',current_location:'poi-a',x:99}),{selected:{kind:'building',id:'building-a'}});
  for(const value of [undefined,null,{kind:'script',id:'a'},{kind:'poi',id:''},{kind:'poi',id:2},{kind:'poi',id:'bad\nref'}])assert.equal(entityReference(value),null);
  assert.deepEqual(agentRequestContext(null),{selected:null});
});

test('previous entities preserve independent windows and deduplicate dishes within a window',()=>{
  assert.deepEqual(previousEntities([...cards,cards[0],{...cards[0],ref:{kind:'poi',id:'poi-a'}},{type:'schedule',id:'course'},
    {type:'place',id:'mock',simulation:true},{type:'place',id:'mock-2',data_mode:'simulated'}]),
    [{kind:'outlet',id:'outlet-a'},{kind:'outlet',id:'outlet-b'}]);
  assert.deepEqual(previousEntities([{type:'place',id:'poi-a'}]),[{kind:'poi',id:'poi-a'}]);
  assert.equal(previousEntities(Array.from({length:30},(_,i)=>({type:'place',id:'p'+i}))).length,12);
});

test('outlet lookup uses returned identity records, not menu group IDs or arbitrary map commands',()=>{
  const found=collectOutletRecords([{type:'place',id:'poi-a',outlets:[{id:'outlet-a',name:'甲窗口'}],
    menu_groups:[{id:'group-only',name:'未确认菜单组'},{id:'group-b',outlet_id:'outlet-b',outlet_name:'乙窗口'}]}]);
  assert.equal(found.length,2);assert.ok(found.every(x=>x.poi_id==='poi-a'));
  assert.equal(loadedEntity({kind:'outlet',id:'group-only'},{...catalog,outlets:found}),null);
  assert.equal(collectOutletRecords([], [relation])[0].ref.id,'outlet-a');
});

test('map action verifies loaded IDs and ignores coordinates or executable extras',()=>{
  const target=resolveMapAction({type:'focus_entity',entity:{kind:'poi',id:'poi-a'},location:{x:999,y:999},javascript:'alert(1)'},catalog);
  assert.equal(target.target_id,'poi-a');assert.equal(target.target,'poi');assert.equal(target.location,undefined);
  assert.equal(resolveMapAction({type:'eval',entity:{kind:'poi',id:'poi-a'}},catalog),null);
  assert.equal(resolveMapAction({type:'focus_entity',entity:{kind:'poi',id:'forged'},poi_id:'poi-a'},catalog),null);
  assert.equal(resolveMapAction({type:'focus_entity',entity:{kind:'outlet',id:'forged'},poi_id:'poi-a'},catalog),null);
  assert.equal(resolveMapAction({type:'focus_entity',entity:{kind:'building',id:'building-a'}},catalog).target_id,'building-a');
});

test('window positioning uses a known parent and rejects mismatched target hints',()=>{
  const action={type:'focus_entity',entity:{kind:'outlet',id:'outlet-a'},poi_id:'poi-a',building_id:'building-a'};
  const target=resolveMapAction(action,catalog);assert.equal(target.target_id,'poi-a');assert.equal(target.ref.kind,'outlet');
  assert.equal(resolveMapAction({...action,poi_id:'poi-unknown'},catalog),null);
  assert.equal(resolveMapAction({...action,building_id:'building-other'},catalog),null);
  for(const id of ['poi-unknown','poi-far'])assert.equal(resolveMapAction({type:'focus_entity',entity:{kind:'poi',id}},catalog),null);
  assert.equal(resolveMapAction(action,{...catalog,rows:rows.map(p=>({...p,location:null}))}).target,'building');
});

test('source links are HTTPS-only and credentials or executable schemes cannot become links',()=>{
  assert.equal(safeSourceUrl('https://example.edu/source'),'https://example.edu/source');
  for(const value of ['javascript:alert(1)','data:text/html,test','file:///data/private','http://example.edu','https://user:password@example.edu'])assert.equal(safeSourceUrl(value),null);
});

test('evidence keeps unknowns explicit and renders plain text rather than model HTML',()=>{
  const output=evidencePresentation([{id:'F1',kind:'fact',text:'已录入窗口',source:{title:'公开资料',url:'https://example.edu'}},
    {id:'L1',kind:'limitation',text:'营业时间未知。'},{id:'X',kind:'script',text:'ignore'},
    {id:'F2',kind:'fact',text:'<img src=x onerror=alert(1)>',data_mode:'simulated'}]);
  assert.equal(output.length,3);assert.equal(output[1].kind,'limitation');assert.equal(output[1].text,'营业时间未知。');
  assert.match(output[2].text,/<img/);assert.equal(output[2].simulated,true);
});

test('relations preserve explanation chains, spatial evidence, sources, limits and bounded-result notices',()=>{
  const output=relationPresentation(relation);assert.equal(output.title,'同类比较');assert.equal(output.total,4);assert.equal(output.truncated,true);
  assert.deepEqual(output.items[0].path,['甲窗口','餐饮服务','乙窗口']);assert.deepEqual(output.items[0].spatialPath,['甲窗口','测试楼','乙窗口']);
  assert.equal(output.items[0].kind,'窗口');assert.equal(output.items[0].edges.length,2);assert.equal(output.items[0].edges[1].status,'已确认');
  assert.ok(output.items[0].edges[1].source.includes('https://example.edu/evidence'));
  assert.ok(output.items[0].limitations.includes('当前在售未核验。'));assert.match(output.gap,/2 个.*缺少空间依据/);
  assert.deepEqual(agentResponseExtras({answer:'旧历史',cards:[]}),{relations:[],evidence:[],map_actions:[],notices:[]});
});

function element(tag,text=''){
  return {tag,text,children:[],attributes:{},hidden:false,append(...children){this.children.push(...children);},
    replaceChildren(...children){this.children=children;},setAttribute(key,value){this.attributes[key]=value;},
    get textContent(){return this.text+this.children.map(x=>x.textContent??x).join('');}};
}
const descendants=node=>[node,...node.children.flatMap(x=>typeof x==='object'?descendants(x):[])];
const styledElement=(tag,text='',className='')=>Object.assign(element(tag,text),{className});

test('relation UI has separate records, collapsed evidence and no automatic camera movement',()=>{
  const calls=[],controls=new Map();let selected;
  const context=vm.createContext({agentAPI:agentContext,Set,String,document:{},agentCatalog:()=>catalog,
    node:styledElement,button:(text,onclick,cls='')=>Object.assign(styledElement('button',text,cls),{onclick}),
    sourceLabel:value=>value,toast:text=>calls.push(['toast',text]),setAgentSelection:ref=>{selected=ref;},hideIntro(){},
    map:{stopRoam(){},focusBuilding:id=>calls.push(['building',id])},keyboard:()=>false,markResultSelection(){},state:{},
    locateResult:(id,ref)=>{calls.push(['poi',id]);selected=ref;},$:id=>{if(!controls.has(id))controls.set(id,{...element('div'),focus(){}});return controls.get(id);}});
  const source=main.slice(main.indexOf('function appendSources('),main.indexOf('function chatPanel('));
  vm.runInContext(source,context);
  const extra=agentResponseExtras({relations:[relation],evidence:[{id:'L',kind:'limitation',text:'入口未知。'}],
    map_actions:[{type:'focus_entity',entity:{kind:'outlet',id:'outlet-b'},poi_id:'poi-a'},
      {type:'focus_entity',entity:{kind:'poi',id:'forged'},location:{x:2,y:3}}]});
  const view=context.renderAgentExtras(extra),nodes=descendants(view);
  assert.equal(calls.length,0,'Receiving and rendering a result must never focus the map');
  assert.ok(nodes.some(n=>n.className==='relation-item'));assert.ok(!nodes.some(n=>n.className==='chat-result'));
  assert.match(view.textContent,/同楼不保证室内连通/);assert.match(view.textContent,/入口未知/);
  assert.ok(nodes.filter(n=>n.tag==='details').every(n=>!n.open));
  const actions=nodes.filter(n=>n.tag==='button'&&n.text.startsWith('查看窗口所在地点'));
  assert.equal(actions.length,1);actions[0].onclick();assert.deepEqual(calls,[['poi','poi-a']]);assert.equal(selected.id,'outlet-b');
});

async function runSend(accountEnabled,extensionEnabled=true,panel=null,peek=false){
  const payloads=[],saved=[],calls=[],controls=new Map();
  const conversation={id:'conversation-fixture',conditions:{budget:20},mode:'real',messages:[{role:'assistant',content:'上一轮',cards}],updated_at:''};
  const final={answer:'已查资料：测试窗口。未知项：入口未核验。',cards,conditions:{budget:20},relations:[relation],
    evidence:[{id:'F1',kind:'fact',text:'测试窗口。'},{id:'L1',kind:'limitation',text:'入口未核验。'}],
    map_actions:[{type:'focus_entity',entity:{kind:'outlet',id:'outlet-a'},poi_id:'poi-a'}],context:{notices:['所选对象不是当前位置。']}};
  const context=vm.createContext({agentAPI:extensionEnabled?agentContext:null,crypto:webcrypto,structuredClone,AbortController,Array,WeakMap,
    selectedEntity:{kind:'building',id:'building-a'},account:{enabled:accountEnabled,require:()=>true},accountPatch:{},
    active:null,identityEpoch:0,conversation,rows,agentResponses:new WeakMap(),selectionIds,state:{panel},
    $:id=>{if(!controls.has(id))controls.set(id,{dataset:{peek:String(peek)}});return controls.get(id);},
    chatPanel:options=>calls.push(['chatPanel',options]),renderChat(){},updateModel(){},rememberAgentEntities(){},
    map:{filter:ids=>calls.push(['filter',ids]),focus:()=>calls.push(['focus'])},
    save:async()=>saved.push(structuredClone(conversation)),errorInfo:e=>({message:e.message}),
    chatStream:async(payload,signal,onEvent)=>{payloads.push(payload);onEvent({type:'status',text:'测试查询'});onEvent({type:'result',data:final});}});
  const source=main.slice(main.indexOf('async function send('),main.indexOf("$('ask-form').onsubmit"));
  vm.runInContext(source,context);await context.send('换个窗口');
  return {payload:payloads[0],saved,calls,conversation,extras:context.agentResponses.get(conversation.messages.at(-1))};
}

test('anonymous send uses top-level window references, preserves conditions and keeps relation extras out of history',async()=>{
  const result=await runSend(false),payload=JSON.parse(JSON.stringify(result.payload));
  assert.deepEqual(payload.context,{selected:{kind:'building',id:'building-a'}});
  assert.deepEqual(payload.previous_entities,[{kind:'outlet',id:'outlet-a'},{kind:'outlet',id:'outlet-b'}]);
  assert.equal(payload.conditions.budget,20);assert.equal(payload.conditions.current_location,undefined);
  assert.ok(result.extras.relations.length);assert.ok(result.extras.evidence.some(x=>x.kind==='limitation'));
  assert.ok(result.saved.every(snapshot=>snapshot.messages.every(m=>!('relations'in m)&&!('evidence'in m)&&!('map_actions'in m))));
  assert.ok(!result.calls.some(x=>x[0]==='focus'));
});

test('account send omits client prior history and references for server identity isolation',async()=>{
  const {payload}=await runSend(true);
  assert.equal(payload.previous_entities,undefined);assert.equal(payload.previous_poi_ids,undefined);assert.equal(payload.history,undefined);
  assert.equal(payload.context.selected.id,'building-a');
});

test('legacy capability never transmits extension context or adds extra result controls',async()=>{
  const {payload,extras,conversation}=await runSend(false,false);
  assert.equal(payload.context,undefined);assert.equal(payload.previous_entities,undefined);assert.equal(extras,undefined);
  assert.equal(conversation.messages.at(-1).cards.length,2);assert.match(conversation.messages.at(-1).content,/已查资料/);
});

test('send respects compact map context without collapsing an expanded conversation',async()=>{
  for(const [panel,peek,expected] of [[null,false,true],['chat',false,false],['chat',true,true]]){
    const result=await runSend(false,true,panel,peek);
    assert.equal(result.calls.find(c=>c[0]==='chatPanel')[1].compact,expected);
  }
});

test('extension loader distinguishes explicit 404 from network, HTTP and module failures',async()=>{
  const context=vm.createContext({AbortSignal,Error});
  vm.runInContext(main.slice(main.indexOf('async function loadAgentExtension('),main.indexOf('const agentExtension=await loadAgentExtension();')),context);
  let imports=0;const importer=async()=>{imports++;return agentContext;};
  const legacy=await context.loadAgentExtension(async()=>({status:404,ok:false}),importer);
  assert.equal(legacy.status,'legacy');assert.equal(imports,0);assert.match(legacy.notice,/需要重启本地服务/);
  for(const fetcher of [async()=>{throw Error('Network failed');},async()=>({status:500,ok:false})]){
    const failed=await context.loadAgentExtension(fetcher,importer);assert.equal(failed.status,'error');assert.match(failed.notice,/加载失败/);assert.equal(failed.api,null);
  }
  const syntax=await context.loadAgentExtension(async()=>({status:200,ok:true}),async()=>{throw SyntaxError('bad module');});
  assert.equal(syntax.status,'error');assert.match(syntax.notice,/加载失败/);
  const incomplete=await context.loadAgentExtension(async()=>({status:200,ok:true}),async()=>({}));assert.equal(incomplete.status,'error');
  const ready=await context.loadAgentExtension(async()=>({status:200,ok:true}),importer);assert.equal(ready.status,'ready');assert.equal(ready.api,agentContext);
});
