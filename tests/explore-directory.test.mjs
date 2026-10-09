import assert from 'node:assert/strict';
import {normalizePlace,filterPlaces,directorySelection,pagePlaces,markerGroups,areaGroups,positionNote,reduceState} from '../app/explore/state.js';

const source={id:'baidu-9d9d7030bb7bcc77e0110373',name:'蜜雪',category:'restaurant',display_category:'food'};
const corrected=normalizePlace(source);
assert.equal(corrected.display_category,'drinks');assert.equal(source.display_category,'food');
const rows=Array.from({length:165},(_,i)=>({id:'p'+i,name:'店'+i,display_category:i%2?'food':'drinks',location:null,spatial_sequence:i>=150?{group:'alley',label:'小吃街',order:i-150}:undefined}));
const west={id:'west',name:'乡村基',display_category:'food',map_reference:{building_id:9,x:1,y:2},spatial_sequence:{group:'west',label:'西侧',order:1}};
const missing={id:'orphan',name:'尚无类别',display_category:'other'};
rows.push(west,missing);
assert.equal(filterPlaces(rows,'eating').length,166);
assert.equal(filterPlaces(rows,'all').length,167);
assert.equal(filterPlaces(rows,'eating','乡村基')[0],west);
assert.equal(filterPlaces(rows,'all','小吃街').length,15);
const state={category:'all',area:'alley',kind:'',query:'',limit:40};
assert.equal(directorySelection(rows,state).length,15);
assert.equal(directorySelection(rows,state)[0].id,'p150');
assert.match(positionNote(rows[150]),/已知区域/);
const sorted=directorySelection(rows,{...state,area:''});
for(const limit of [40,80,120,160,200]){const page=pagePlaces(sorted,limit);assert.equal(page.items.length,Math.min(limit,167));assert.equal(page.items.length+page.remaining,167);}
assert.equal(pagePlaces(sorted,200).items.some(p=>p.id==='orphan'),true);
const buildings=[{id:'a',name:'分店',building_id:12,location:{x:1,y:2}},{id:'b',name:'分店',building_id:12,display_anchor:{x:3,y:4}},{id:'c',name:'分店',building_id:13,location:{x:1,y:2}},{id:'d',name:'缺点但确认楼栋',building_id:12},west];
const groups=markerGroups(buildings,new Set(buildings.map(p=>p.id)));
assert.equal(groups.length,2);assert.deepEqual(groups[0].ids,['a','b','d']);
assert.equal(groups.some(g=>g.ids.includes('west')),false);
assert.equal(markerGroups(buildings,null).length,0);
assert.equal(markerGroups(buildings,new Set(['b']))[0].row.id,'b');
assert.equal(areaGroups(rows).find(g=>g.id==='alley').rows.length,15);
const detail=reduceState(state,{type:'select',id:'p150'});
assert.equal(detail.area,'alley');assert.equal(detail.limit,40);
assert.equal(reduceState(detail,{type:'category',value:'eating'}).area,'');
assert.equal(rows[150].location,null);
const dining=[{id:'canteen-3',name:'学三食堂',display_category:'food',floor:'3'},
  {id:'canteen-4',name:'学四食堂',display_category:'food',floor:'4'},
  {id:'other-third',name:'科技楼三层服务点',display_category:'services',floor:'3'},
  {id:'other-fourth',name:'其他楼四层餐厅',display_category:'food',floor:'4'},
  {id:'known-alias',name:'正式名',display_category:'food',aliases:['已批准别名',7,null,{name:'不可检索'}]},
  {id:'bad-alias',name:'错误别名格式',display_category:'food',aliases:'不应隐式解释的字符串'}];
const before=JSON.stringify(dining);
for(const q of ['新三','学三','新乐群三层',' 新三 '])assert.deepEqual(filterPlaces(dining,'eating',q).map(p=>p.id),['canteen-3']);
for(const q of ['新四','学四','新乐群四层'])assert.deepEqual(filterPlaces(dining,'all',q).map(p=>p.id),['canteen-4']);
assert.equal(filterPlaces(dining,'services','新三').length,0,'Aliases must not bypass category selection');
assert.deepEqual(filterPlaces(dining,'food','已批准别名').map(p=>p.id),['known-alias']);
for(const q of ['不可检索','不应隐式解释的字符串'])assert.equal(filterPlaces(dining,'all',q).length,0);
assert.deepEqual(directorySelection(dining,{category:'eating',query:'新四',area:'',kind:'food',limit:40}).map(p=>p.id),['canteen-4']);
assert.equal(JSON.stringify(dining),before,'Search must not rename or mutate published records');
console.log('explore-directory: complete pagination, known aliases, missing positions, category, area and building aggregation passed');
