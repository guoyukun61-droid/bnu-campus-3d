import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

// The pure helpers live beside renderPlace so old running servers do not need
// a new asset route. Execute exactly that implementation, not a test copy.
const source=await readFile(new URL('../app/explore/main.js',import.meta.url),'utf8');
const start=source.indexOf('// MENU_BROWSER_PURE_START'),end=source.indexOf('// MENU_BROWSER_PURE_END');
assert.ok(start>=0&&end>start);
const helperSource=source.slice(start,end);
const {groupKnownFloors,menuCursor,mergeMenuPage,menuBrowserGroups}=vm.runInNewContext(helperSource+'\n({groupKnownFloors,menuCursor,mergeMenuPage,menuBrowserGroups})');
const plain=value=>JSON.parse(JSON.stringify(value));
const makeCard=()=>({id:'floor-3',poi_id:'floor-3',floor:'3',hours:'06:00–22:00',menu_offset:0,menu_total:4,
  outlets:[{id:'w-a',poi_id:'floor-3',name:'六号窗口',floor:'3',hours_label:'尚未录入'},
    {id:'w-b',poi_id:'floor-3',name:'同名窗口',floor:'3',hours_label:'10:00–20:00'}],
  menu_groups:[{id:'g-a',name:'六号菜单',outlet_id:'w-a',floor:'3',identity_status:'confirmed',item_count:2},
    {id:'g-b',name:'同名窗口',outlet_id:'w-b',floor:'3',identity_status:'confirmed',item_count:1},
    {id:'g-unknown',name:'来源待核菜单',identity_status:'source_only',floor:'3',item_count:1}],
  menu:[{id:'a',name:'甲菜',group_id:'g-a',outlet_id:'w-a',price:12},
    {id:'u',name:'独立资料',group_id:'g-unknown',price:5}]});

test('floor navigation preserves all POIs and does not infer a floor from a name',()=>{
  const records=[{id:'a',floor:'10'},{id:'b',floor:'2'},{id:'c',name:'三层咖啡'},{id:'d',floor:'2'}];
  const grouped=plain(groupKnownFloors(records));
  assert.deepEqual(grouped.map(x=>x.key),['2','10','__unknown__']);
  assert.deepEqual(grouped.flatMap(x=>x.members.map(p=>p.id)).sort(),['a','b','c','d']);
  assert.equal(grouped.at(-1).label,'楼层尚未录入');
});

test('window identities retain own hours and declared unloaded groups',()=>{
  const groups=plain(menuBrowserGroups(makeCard()));
  assert.equal(groups.length,3);
  assert.equal(groups[0].name,'六号窗口');assert.equal(groups[0].hours,'尚未录入');
  assert.equal(groups[0].item_count,2);assert.equal(groups[0].items.length,1);
  assert.equal(groups[1].outlet_id,'w-b');assert.equal(groups[1].items.length,0);assert.equal(groups[1].hours,'10:00–20:00');
  assert.equal(groups[2].outlet_id,null);assert.equal(groups[2].name,'来源待核菜单');
  assert.ok(groups.every(g=>g.hours!=='06:00–22:00'));
});

test('same names do not merge identities, and multiple groups of one outlet do merge',()=>{
  const card=makeCard();card.outlets[0].name='同名窗口';
  card.menu_groups.push({...card.menu_groups[0],id:'g-a-extra',item_count:3});
  const groups=plain(menuBrowserGroups(card));assert.equal(groups.length,3);
  assert.equal(groups[0].item_count,5);assert.notEqual(groups[0].key,groups[1].key);
  assert.equal(groups[0].name,groups[1].name);
});

test('unknown, conflicting and foreign-parent records remain visible without wrong window binding',()=>{
  const card=makeCard();card.outlets.push({id:'foreign',poi_id:'other-floor',name:'异地窗口'});
  card.menu_groups.push({id:'g-foreign',name:'不确定资料',outlet_id:'foreign',outlet_name:'异地窗口',item_count:1});
  card.menu.push({id:'conflict',name:'冲突菜品',group_id:'g-a',outlet_id:'w-b'},
    {id:'foreign-item',name:'异地条目',group_id:'g-foreign',outlet_id:'foreign'},
    {id:'no-group',name:'无分组条目'});
  const groups=plain(menuBrowserGroups(card));
  assert.equal(groups.flatMap(g=>g.items).length,card.menu.length);
  for(const id of ['conflict','foreign-item','no-group'])assert.equal(groups.find(g=>g.items.some(i=>i.id===id)).outlet_id,null);
});

test('candidate groups cannot become confirmed windows and simulated records keep a label',()=>{
  const card={id:'p',menu_groups:[{id:'g',name:'待核',outlet_id:'candidate',outlet_name:'疑似窗口',identity_status:'candidate',data_mode:'simulated',item_count:1}],menu:[{id:'x',group_id:'g',name:'模拟菜',data_mode:'simulated'}]};
  const [group]=menuBrowserGroups(card);assert.equal(group.outlet_id,null);assert.equal(group.simulated,true);
});

test('raw page cursor advances even if stable IDs overlap; metadata and original inputs survive',()=>{
  const card=makeCard(),original=JSON.stringify(card);
  const next={id:'floor-3',menu_offset:2,menu_total:4,menu:[{id:'a',name:'甲菜'},{id:'b',name:'乙菜',group_id:'g-b',outlet_id:'w-b'}],menu_groups:[{id:'g-new',name:'新组',item_count:1}],outlets:[{id:'w-new',name:'新窗口'}]};
  const result=mergeMenuPage(card,next);assert.equal(result.menu.length,3);assert.equal(menuCursor(result),4);assert.equal(result.menu_total,4);
  assert.equal(result.menu_groups.length,4);assert.equal(result.outlets.length,3);assert.equal(result.menu_offset,0);
  assert.equal(JSON.stringify(card),original);assert.equal(next.menu.length,2);
});

test('paging rejects cross-place, wrong-offset, changing-total and truncated empty pages',()=>{
  const card=makeCard(),next={id:'floor-3',menu_offset:2,menu_total:4,menu:[{id:'b'}]};
  for(const patch of [{id:'other'},{menu_offset:60},{menu_total:5},{menu:[]}])assert.throws(()=>mergeMenuPage(card,{...next,...patch}));
  assert.equal(mergeMenuPage(card,next).menu.length,3);
});

test('missing total remains unknown instead of inventing completeness',()=>{
  const result=mergeMenuPage({id:'p',menu:[{id:'a'}]}, {id:'p',menu_offset:1,menu:[{id:'b'}]});
  assert.equal(result.menu_total,undefined);assert.equal(menuCursor(result),2);
  assert.equal(menuBrowserGroups(result)[0].count_known,false);
});

test('ordinary store membership is not relabeled as a separately confirmed dining window',()=>{
  const [group]=menuBrowserGroups({id:'p',menu_groups:[{id:'g',name:'店铺菜单',outlet_id:'shop-a',outlet_name:'便利店',outlet_hours_label:'08:00–22:00',identity_status:'existing_shop',item_count:1}],menu:[{id:'i',name:'矿泉水',group_id:'g',outlet_id:'shop-a'}]});
  assert.equal(group.identity_label,'已录入店铺');assert.equal(group.outlet_id,'shop-a');assert.equal(group.hours,'08:00–22:00');
});

test('three 60-row pages preserve all item identities, and a repeated request cannot append twice',()=>{
  const items=Array.from({length:150},(_,i)=>({id:'item-'+i,name:'商品'+i,group_id:'g'}));
  let card={id:'p',menu_offset:0,menu_total:150,menu:items.slice(0,60),menu_groups:[{id:'g',name:'资料',item_count:150}]};
  const page={id:'p',menu_offset:60,menu_total:150,menu:items.slice(60,120)};card=mergeMenuPage(card,page);
  assert.throws(()=>mergeMenuPage(card,page));
  card=mergeMenuPage(card,{id:'p',menu_offset:120,menu_total:150,menu:items.slice(120)});
  assert.equal(menuCursor(card),150);assert.equal(card.menu.length,150);assert.equal(menuBrowserGroups(card)[0].items.length,150);
});

// Read the project's existing isolated DOM harness; no browser, HTTP, model,
// account or private production data is touched by these rendering tests.
const harness=await readFile(new URL('./test_explore_interaction.cjs',import.meta.url),'utf8');
const html=await readFile(new URL('../app/explore/index.html',import.meta.url),'utf8');
const domSource=harness.slice(harness.indexOf('class Element'),harness.indexOf('(async()=>{'));
function renderFixture(card,{agent=null,request=async()=>{throw Error('Unexpected request');}}={}){
  const context=vm.createContext({card,request,agentAPI:agent,html});
  const renderSource=source.slice(source.indexOf('function renderPlace('),source.indexOf('function markResultSelection('));
  vm.runInContext(domSource+helperSource+`
    const document=createDocument(html);
    const host=document.createElement('div');document.body.append(host);
    const $=id=>document.getElementById(id),node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
    const button=(text,fn,cls='')=>{const n=node('button',text,cls);n.onclick=fn;return n;};
    const rows=[],remembered=[],selected=[];let state={};
    const present=x=>({...x,collection_label:'菜单'}),rememberAgentEntities=x=>remembered.push(x),positionNote=()=>'',inModel=()=>false,sourceLabel=()=> '公开样例',agentCatalog=()=>({});
    const setAgentSelection=ref=>selected.push(ref),chatPanel=()=>{},toast=x=>selected.push(x),errorInfo=e=>({message:e.message});
    const hideIntro=()=>{},keyboard=()=>false,setCategoryButtons=()=>{},drawList=()=>{};
  `+renderSource+`\nrenderPlace(card,host);globalThis.fixture={host,document,remembered,selected};`,context);
  return context.fixture;
}

test('rendering uses collapsed per-window disclosures, preserves missing hours, and shows unloaded group',()=>{
  const fixture=renderFixture(makeCard());
  const details=fixture.host.querySelectorAll('.outlet-disclosure');assert.equal(details.length,3);assert.ok(details.every(d=>!d.open));
  assert.match(details[0].textContent,/窗口营业时间：尚未录入/);
  assert.match(details[1].textContent,/尚未加载到当前页/);
  assert.ok(details[2].textContent.includes('不视为已确认的独立窗口'));
  assert.equal(fixture.host.querySelectorAll('.outlet-ask').length,0);
});

test('window search only filters loaded content and clearing it restores every group',()=>{
  const fixture=renderFixture(makeCard()),input=fixture.host.querySelector('.menu-finder');
  input.value='甲菜';input.oninput();assert.equal(fixture.host.querySelectorAll('.outlet-disclosure').length,1);
  input.value='不存在';input.oninput();assert.match(fixture.host.textContent,/当前已加载资料没有匹配结果/);
  input.value='';input.oninput();assert.equal(fixture.host.querySelectorAll('.outlet-disclosure').length,3);
});

test('only loaded window identities can become a question context',()=>{
  const fixture=renderFixture(makeCard(),{agent:{loadedEntity:ref=>ref.id==='w-a'?{ref}:null}});
  const actions=fixture.host.querySelectorAll('.outlet-ask');assert.equal(actions.length,1);actions[0].onclick();
  assert.deepEqual(plain(fixture.selected),[{kind:'outlet',id:'w-a'}]);
});

test('load more preserves window grouping and filter state rather than flattening the next page',async()=>{
  const calls=[];const fixture=renderFixture(makeCard(),{request:async url=>{calls.push(url);return {cards:[{id:'floor-3',menu_offset:2,menu_total:4,menu:[{id:'b',name:'乙菜',group_id:'g-b',outlet_id:'w-b'},{id:'a2',name:'甲菜二',group_id:'g-a',outlet_id:'w-a'}]}]};}});
  const input=fixture.host.querySelector('.menu-finder');input.value='六号';input.oninput();
  await fixture.host.querySelector('.menu-load-more').onclick();
  assert.deepEqual(calls,['/api/app/place?id=floor-3&offset=2']);
  assert.equal(fixture.host.querySelector('.menu-finder').value,'六号');assert.equal(fixture.host.querySelectorAll('.outlet-disclosure').length,1);
  assert.match(fixture.host.textContent,/甲菜二/);assert.equal(fixture.host.querySelector('.menu-load-more'),null);
  const finder=fixture.host.querySelector('.menu-finder');finder.value='';finder.oninput();assert.equal(fixture.host.querySelectorAll('.outlet-disclosure').length,3);
});
