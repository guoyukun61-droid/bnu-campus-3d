const $=id=>document.getElementById(id),frame=$('campus');let records=[];
document.querySelector('label[for="building_id"]').textContent='关联建筑 ID（OSM / 本地补建，可空）';
const gateOption=document.createElement('option');gateOption.value='gate';gateOption.textContent='校门 / 出入口';$('category').append(gateOption);
const fields=['name','category','x','y','building_id','floor','unit','source','status','notes','hours','price','tags'];
const locationFields=document.createElement('div');locationFields.className='pair';
for(const [id,title] of [['floor','所在楼层（未知留空）'],['unit','门牌 / 档口（未知留空）']]){const wrap=document.createElement('div'),label=document.createElement('label'),input=document.createElement('input');label.htmlFor=id;label.textContent=title;input.id=id;input.maxLength=id==='floor'?80:100;wrap.append(label,input);locationFields.append(wrap);}
$('building_id').after(locationFields);
const sibling=document.createElement('button');sibling.type='button';sibling.className='secondary';sibling.textContent='在同一栋楼新增店铺';$('new').after(sibling);
sibling.onclick=()=>{const bid=$('building_id').value,x=$('x').value,y=$('y').value;if(!bid){tell('请先选定关联建筑，再新增楼内店铺。');return;}reset();$('building_id').value=bid;$('x').value=x;$('y').value=y;$('category').value='shop';tell('已保留建筑关联，请填写另一家店的名称、楼层和来源。');$('name').focus();};
const statusNames={unverified:'待核实',verified:'已核实',historical:'历史记录',archived:'归档'};
function tell(text){$('message').textContent=text;}
function send(message){frame.contentWindow.postMessage(message,location.origin);}
function marks(){send({type:'campus-pois',records});}
async function load(){
 try{const response=await fetch('/api/places');if(!response.ok)throw Error('HTTP '+response.status);const data=await response.json();if(!Array.isArray(data.records))throw Error('接口格式错误');records=data.records;render();marks();$('save').disabled=false;tell(`已连接本机数据库 · ${records.length} 条记录`);}
 catch(e){$('save').disabled=true;tell('数据服务未启动：请运行“打开校园信息工作台.cmd”，使用 8786 端口；当前不会假装保存。');}
}
function render(){const q=$('filter').value.toLowerCase();$('records').replaceChildren();for(const r of records.filter(r=>(r.name+' '+(r.notes||'')).toLowerCase().includes(q))){const b=document.createElement('button');b.className='record';b.type='button';b.textContent=r.name;const small=document.createElement('small');small.textContent=`${statusNames[r.status]} · ${r.category} · v${r.revision}`;b.append(small);b.onclick=()=>edit(r);$('records').append(b);}if(!records.length)$('records').textContent='尚无记录。可先在三维图中选点，再填写名称与来源。';}
function edit(r){$('recordId').value=r.id;$('revision').value=r.revision;for(const k of fields)$(k).value=k==='tags'?(r[k]||[]).join(', '):(r[k]??'');send({type:'campus-focus',x:r.x,y:r.y});tell('正在编辑 '+r.name+'；保存将保留上一版本。');}
function reset(){$('editor').reset();$('recordId').value='';$('revision').value='';tell('新建记录：请选点或输入本地坐标。');}
$('new').onclick=reset;$('filter').oninput=render;
$('southwest').onclick=()=>send({type:'reference-view',view:'southwest'});$('overview').onclick=()=>send({type:'reference-view',view:'reference'});
$('pick').onclick=()=>{send({type:'campus-pick-enable'});tell('下一次单击三维模型确定位置；选择建筑时会自动关联 ID。');};
addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==frame.contentWindow)return;const d=e.data;if(d?.type==='campus-ready')marks();if(d?.type==='campus-point'&&Number.isFinite(d.x)&&Number.isFinite(d.y)){$('x').value=d.x.toFixed(2);$('y').value=d.y.toFixed(2);$('building_id').value=d.building_id||'';tell('位置已选定；请补充名称、来源后保存。');}if(d?.type==='campus-poi-selected'){const r=records.find(r=>r.id===d.id);if(r)edit(r);}});
$('editor').onsubmit=async e=>{e.preventDefault();const d={};for(const k of fields)d[k]=$(k).value.trim();d.x=Number(d.x);d.y=Number(d.y);d.building_id=d.building_id?Number(d.building_id):null;d.tags=d.tags?d.tags.split(/[,，]/).map(x=>x.trim()).filter(Boolean):[];const id=$('recordId').value;if(id)d.revision=Number($('revision').value);$('save').disabled=true;try{const r=await fetch('/api/places'+(id?'/'+encodeURIComponent(id):''),{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});const result=await r.json();if(!r.ok)throw Error(result.error||r.status);await load();edit(result);tell('已保存到本机数据库 · 版本 '+result.revision);}catch(e){tell('保存失败：'+e.message);}finally{$('save').disabled=false;}};
load();
