import assert from 'node:assert/strict';
import {cleanAddress,present,errorInfo,messageText} from '../app/presentation.js';
const directory=[{id:'gym',display_category:'sports',address:'立身路'}];
const old={id:'gym',poi_id:'gym',type:'place',name:'邱季端体育场',menu:[],menu_total:0,address:'BD-09 轮廓匹配',unknown:['营业时间待确认']};
const card=present(old,directory);
assert.equal(card.collection_label,undefined);
assert.equal(card.menu,undefined);
assert.equal(card.address,'立身路');
assert.deepEqual(card.unknown,['开放时段待确认']);
assert.equal(messageText({content:'菜单为记录资料，当前在售情况需向店铺确认。',cards:[old]},directory),'开放与服务信息以现场公告为准。');
assert.equal(old.menu_total,0); // historical data is not mutated
assert.equal(present({category:'retail',menu:[]}).collection_label,'商品');
assert.equal(present({category:'coffee',menu:[]}).collection_label,'饮品');
assert.equal(cleanAddress('百度地址：立身路19号。关联建筑；BD-09；GF2截图'),'立身路19号');
assert.equal(errorInfo('Failed to fetch').code,'NETWORK');
assert.equal(errorInfo({code:'MODEL_AUTH',message:'服务不可用',retryable:false}).retryable,false);
assert.equal(errorInfo({name:'AbortError'}).retryable,false);
console.log('presentation: 12 assertions passed');
