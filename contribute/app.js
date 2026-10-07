'use strict';
const $ = id => document.getElementById(id);
document.querySelector('.eyebrow').textContent='BNU / FIELD NOTES · 1.4.2';
let auth, catalog, tasks, records = [], editing = null, uploaded = [], pending = null;
let mapPoint=null,mapReady=false,mapPreview=null;
const mapPanel=element('section');mapPanel.id='map-panel';mapPanel.hidden=true;
mapPanel.append(element('h2','三维地图 · 定位与核对'),element('p','先选“地点 / 店铺基本信息”，再开始选点。缺失建筑也可点地面。选点不自动提交，不改变模型。模型外地点请用文字或经纬度描述。'));
const mapFrame=document.createElement('iframe');mapFrame.title='校园三维地图选点';mapFrame.id='map-frame';mapFrame.width='100%';mapFrame.height='500';mapPanel.append(mapFrame);
mapPanel.append(button('收起地图',()=>{mapPanel.hidden=true;}));$('workspace').insertBefore(mapPanel,$('tasks'));
const mapHelp=element('div');mapHelp.dataset.field='pois';mapHelp.append(button('打开三维地图选位置',()=>openMap(mapPoint)),button('清除本次选点',()=>{mapPoint=null;showMapPoint();}));
const mapSummary=element('p','尚未选择地图位置');mapSummary.id='map-selection';mapHelp.append(mapSummary);$('entry-form').prepend(mapHelp);
for(const [id,title] of [['location_description','具体位置 / 缺楼、轮廓或入口问题'],['building_floors','建筑总层数（不是店铺所在楼层）']]){
  const label=element('label',title);label.dataset.field='pois';const input=element('input');input.id=id;
  if(id==='building_floors'){input.type='number';input.min='1';input.max='100';input.step='1';}label.append(input);$('entry-form').querySelector('.grid').append(label);
}
const floorLabel=element('label','层数依据（未知则不填总层数）');floorLabel.dataset.field='pois';const floorEvidence=element('select');floorEvidence.id='floor_evidence';floorEvidence.append(new Option('未知 / 不修改',''),new Option('现场确认','observed'),new Option('目测估计','estimated'));floorLabel.append(floorEvidence);$('entry-form').querySelector('.grid').append(floorLabel);
$('category').append(new Option('建筑 / 缺失建筑','building'));
function openMap(point){mapPanel.hidden=false;mapPreview=point;if(!mapFrame.getAttribute('src'))mapFrame.src='/map/';if(mapReady&&point)mapFrame.contentWindow.postMessage({type:'contribution-map-show',point},location.origin);mapPanel.scrollIntoView({behavior:'smooth',block:'start'});}
function showMapPoint(){mapSummary.textContent=mapPoint?`候选选点：${mapPoint.x}, ${mapPoint.y}（white_v4 本地米坐标）；${mapPoint.building_id==null?'独立位置 / 缺失建筑待核':'关联建筑 '+mapPoint.building_id}。提交后须审核。`:'尚未选择地图位置；可保留原位置或文字填报。';}
addEventListener('message',e=>{
  if(e.origin!==location.origin||e.source!==mapFrame.contentWindow)return;
  if(e.data?.type==='contribution-map-ready'){mapReady=true;if(mapPreview)openMap(mapPreview);return;}
  if(e.data?.type!=='contribution-map-point')return;
  if($('form').hidden||$('kind').value!=='pois'){message('地图当前仅供核对。请进入填写信息并选择地点类型后选点。');return;}
  const p=e.data.point;if(!p||!Number.isFinite(p.x)||!Number.isFinite(p.y)||Math.abs(p.x)>452||Math.abs(p.y)>601||p.model!=='white_v4'||p.crs!=='local EPSG:32650')return;
  mapPoint=p;showMapPoint();formGroups.position.open=true;message('位置已放入表单，尚未提交。只补必要描述；仅在修改总层数时需要层数依据。若已填经纬度，请清空其中一种定位方式。');mapSummary.scrollIntoView({behavior:'smooth',block:'center'});
});
const labels = {draft:'草稿',submitted:'待审核',approved:'已批准',rejected:'已拒绝',needs_info:'待补充'};
for(const [id,title,type] of [['lng','经度（不确定留空）','number'],['lat','纬度（不确定留空）','number'],['crs','坐标系：仅 WGS84 或 BD09','text'],['observation','现场备注：排队时段、耗时、疑似重复关联ID等','text']]){
  const label=document.createElement('label');label.dataset.field='pois';label.textContent=title;
  const input=document.createElement('input');input.id=id;input.type=type;if(type==='number')input.step='any';label.append(input);$('entry-form').querySelector('.grid').append(label);
}
function message(text) { $('notice').textContent = text; }
// Compact difference entry: existing data is displayed, never copied into a patch.
const fieldNames={name:'名称',category:'类别',address:'地址 / 入口',floor:'楼层 / 窗口',hours:'营业时段',price:'价格（元）',specification:'规格',sales_channel:'销售渠道',tags:'口味标签',serving_minutes:'出餐分钟',available:'是否在售',location_description:'具体位置 / 特殊情况',building_floors:'建筑总层数',floor_evidence:'层数依据',lng:'经度',lat:'纬度',crs:'坐标系',observation:'现场备注'};
const baseline=element('details');baseline.id='existing-info';baseline.open=true;
baseline.append(element('summary','已有资料 · 未填写的项继续沿用'),element('div',undefined,'baseline-values'));
const entryGrid=$('entry-form').querySelector('.grid');entryGrid.after(baseline);
const formGroups={};
let groupAfter=baseline;
for(const [key,title,ids] of [
  ['position','位置与楼层 · 仅位置不准或有特殊情况时填写',['address','floor','location_description','building_floors','floor_evidence']],
  ['hours','营业时间 · 仅有补充或变更时填写',['hours']],
  ['menu','菜品与价格 · 只填这次核实的内容',['price','specification','sales_channel','tags','serving_minutes','available']],
  ['basic','名称与类别 · 仅新增或纠错时填写',['name','category']],
  ['advanced','其他情况与经纬度 · 可跳过',['observation','lng','lat','crs']]
]){
  const details=element('details');details.className='optional-group';details.append(element('summary',title));
  const grid=element('div',undefined,'grid');details.append(grid);
  for(const id of ids)grid.append($(id).closest('label'));
  if(key==='position')grid.prepend(mapHelp);
  groupAfter.after(details);groupAfter=details;formGroups[key]=details;
}
const timeLabel=$('observed').closest('label');timeLabel.firstChild.textContent='观察时间（已预填当前时间；非当下观察请修改）';groupAfter.after(timeLabel);
const sourceActions=element('div',undefined,'source-actions');sourceActions.append(element('p','本次修改依据（可点选后补充；不要选择未使用的来源）'));
for(const [title,explanation] of [['现场观察','我已现场核对本次修改字段，具体内容见本次填写项。'],['门店公告','我已查看该店公告并核对本次修改字段，具体内容见本次填写项。'],['店内价目表','我已查看该店价目表并核对本次修改字段，价格及规格以本次填写项为准。']]){
  sourceActions.append(button(title,()=>{if($('evidence').value.trim()&&!confirm('替换当前来源说明？'))return;$('evidence').value=explanation;}));
}
$('evidence').closest('label').before(sourceActions);
$('evidence').rows=2;$('evidence').placeholder='可点击上方真实使用的依据；官网补充请写具体链接，特殊情况再加说明。';
$('form').querySelector('h2').textContent='只补需要改的，不必重新填一遍';
$('form').querySelector('p').textContent='先选已有对象，再展开需要补充的分组；只填一项也可以。空白保持旧值和原来源，已有官网资料无需重复提交，未知信息仍保持未知。';
$('entry-form').querySelector('p.muted').textContent='不用逐项填写，也不用重复录入官网资料。仅保留一条本次依据及观察时间；照片选填。无修改可直接返回任务页。';
const patchPreview=element('p','仅提交本次填写且发生变化的字段，其余保留原资料。','muted');patchPreview.id='patch-preview';$('entry-form').querySelector('.actions').before(patchPreview);
function displayValue(id,value){
  if(value==null||value==='')return '暂无资料，留空仍为未知';
  if(id==='available')return value?'在售':'停售';
  if(id==='category')return [...$('category').options].find(o=>o.value===value)?.textContent||String(value);
  if(id==='floor_evidence')return value==='observed'?'现场确认':value==='estimated'?'目测估计':String(value);
  if(id==='hours')return value.map(v=>v.join('-')).join('，');
  if(Array.isArray(value))return value.join('，');
  return typeof value==='object'?JSON.stringify(value):String(value);
}
function renderExisting(){
  const current=catalog[$('kind').value].find(r=>r.id===$('entity').value);
  const values=baseline.querySelector('div');values.replaceChildren();
  for(const id of Object.keys(fieldNames))if(['INPUT','TEXTAREA'].includes($(id).tagName))$(id).placeholder='选填 · 未知可留空';
  if(current){
    values.append(element('p',current.name+' · 原来源：'+(current.source||'待核')));
    for(const [key,title] of [['opening_hours_text','营业时间原文'],['hours_notes','时段说明'],['dining_type','供餐类型'],['menu_section','照片菜单分组'],['availability_note','在售说明']]){
      if(current[key])values.append(element('p',title+'：'+current[key]));
    }
    for(const [id,title] of Object.entries(fieldNames)){
      const label=$(id).closest('label');if(label.hidden)continue;
      const value=current[id==='hours'?'opening_hours':id];
      if(value==null||value==='')continue;
      const row=element('p');row.append(element('strong',title+'：'),element('span',displayValue(id,value)));values.append(row);
      if(['INPUT','TEXTAREA'].includes($(id).tagName)&&!['lng','lat','crs'].includes(id))$(id).placeholder=value==null?'选填 · 未知可留空':'保留：'+displayValue(id,value);
    }
    values.append(element('p','仅展示已有值；未收录的项仍未知，无需为了填满而补写。原资料不代表本次现场核验，未修改字段不会刷新来源或观察时间。','muted'));
  }else values.append(element('p','新增对象：名称必填；窗口 / 商品还需选择真实所属对象。其他信息按实际掌握情况填写。'));
  $('name').required=!current;$('parent').required=!current&&$('kind').value!=='pois';
  $('parent-label').hidden=!!current||$('kind').value==='pois';
  for(const [key,details] of Object.entries(formGroups)){
    details.hidden=![...details.querySelectorAll('label')].some(n=>!n.hidden);
    details.open=(!current&&key==='basic')||[...details.querySelectorAll('input,select')].some(n=>!n.closest('label').hidden&&n.value!=='')||(key==='position'&&!!mapPoint);
  }
}
function onlyChanged(patch,base){
  if(!base)return patch;
  const result={};for(const [key,value] of Object.entries(patch))if(JSON.stringify(value)!==JSON.stringify(base[key]))result[key]=value;
  if('building_floors' in result)result.floor_evidence=patch.floor_evidence;
  return result;
}
async function api(path, data, mime) {
  const options = {credentials:'same-origin',headers:{}};
  if (data !== undefined) {
    options.method = 'POST'; options.headers['X-CSRF-Token'] = auth?.csrf || '';
    options.headers['Content-Type'] = mime || 'application/json'; options.body = mime ? data : JSON.stringify(data);
  }
  let response;
  try { response = await fetch('/api/contribute/' + path, options); }
  catch { throw Error('网络中断，未确认保存成功。请保留表单，稍后重试。'); }
  const result = await response.json();
  if (!response.ok) throw Error(result.error || '请求失败');
  return result;
}
function element(tag, text, className) { const n = document.createElement(tag); if(text!==undefined)n.textContent=text;if(className)n.className=className;return n; }
function button(text, fn) { const b=element('button',text);b.type='button';b.onclick=()=>run(fn);return b; }
async function run(fn) { try { await fn(); } catch(e) { message(e.message); } }
function page(name) { for(const id of ['tasks','form','mine','review'])$(id).hidden=id!==name; }
function options(select, rows, placeholder) { select.replaceChildren(new Option(placeholder,''),...rows.map(r=>new Option(r.name+' · '+r.id,r.id))); }
function newForm() {
  $('entry-form').reset(); editing=null;uploaded=[];pending=null;
  mapPoint=null;showMapPoint();
  $('observed').value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
  populate();
}
function populate() {
  const kind=$('kind').value;
  options($('entity'),catalog[kind],'新增（先确认名录中没有）');
  $('parent-label').hidden=kind==='pois';
  options($('parent'),kind==='shops'?catalog.pois:catalog.shops,'请选择所属对象');
  document.querySelectorAll('[data-field]').forEach(n=>n.hidden=!n.dataset.field.split(' ').includes(kind));
  $('uploaded').textContent=uploaded.length?'已附 '+uploaded.length+' 张图片':'';
  renderExisting();
}
function selectEntity() {
  mapPoint=null;showMapPoint();
  const current=catalog[$('kind').value].find(r=>r.id===$('entity').value);
  if(current){$('parent').value=current.poi_id||current.shop_id||'';}
  renderExisting();
  message(current?'当前填写的是候选修改；未填字段保持原值。':'新增地点批准后仍需范围核验，暂不推荐。');
}
function renderTasks() {
  const q=$('search').value.trim().toLowerCase();
  $('counts').textContent=`名录 ${catalog.pois.length} 条 · 缺坐标 ${tasks.missing_coordinates.length} 条 · 缺营业时间 ${tasks.missing_hours.length} 条 · 疑似重复 ${tasks.duplicates.length} 组 · 候选更新 ${tasks.updates.length} 条`;
  const target=$('task-list');target.replaceChildren();
  for(const row of catalog.pois.filter(r=>[r.name,r.address,r.floor].join(' ').toLowerCase().includes(q)).slice(0,60)){
    const c=element('article',undefined,'card');c.append(element('h3',row.name),element('p',row.address||'地址待补'),element('small',(row.zone||'范围未知')+' / '+(row.floor||'楼层未知')));
    const claim=tasks.claims[row.id];if(claim&&Date.parse(claim.expires_at)>Date.now())c.append(element('p',`${claim.name} 正在核对（不锁定）`,'badge'));
    c.append(button('领取并补充',async()=>{await api('claim',{entity_id:row.id});newForm();$('entity').value=row.id;selectEntity();page('form');}));target.append(c);
  }
  if(!target.children.length)target.append(element('p','没有找到。可在“填写信息”申请新增，先核对同名分店。'));
  const details=element('details');details.append(element('summary','查看疑似重复与候选更新（仅供核对，不自动合并）'),element('pre',JSON.stringify({疑似重复:tasks.duplicates,候选更新:tasks.updates},null,2)));target.append(details);
}
function renderRecords() {
  $('my-list').replaceChildren();$('review-list').replaceChildren();
  for(const r of records){
    const card=element('article',undefined,'card');
    card.append(element('h3',r.patch.name||r.base?.name||r.id),element('span',labels[r.status],'badge'),element('p',`${r.author} · ${r.observed_at}`),element('p',r.evidence));
    if(r.review_note)card.append(element('p','审核意见：'+r.review_note));
    const changes={};for(const [k,v] of Object.entries(r.patch))changes[k]={旧值:r.base?.[k]??'未知/新增',新值:v};
    card.append(element('pre',JSON.stringify(changes,null,2)));
    if(r.patch.map_point)card.append(button('在三维地图核对位置',()=>openMap(r.patch.map_point)));
    for(const id of r.attachments){const a=element('a','查看证据图片');a.href='/api/contribute/attachments/'+id;a.target='_blank';a.rel='noopener';card.append(a,element('br'));}
    if(r.author_id===auth.user.id&&['draft','needs_info'].includes(r.status))card.append(button('继续填写',()=>editRecord(r)));
    if(auth.user.role==='admin'&&r.author_id===auth.user.id){
      const own=element('article',undefined,'card');own.append(element('h3',r.patch.name||r.base?.name||r.id),element('p',labels[r.status]));
      if(['draft','needs_info'].includes(r.status))own.append(button('继续填写',()=>editRecord(r)));
      if(r.patch.map_point)own.append(button('在三维地图核对位置',()=>openMap(r.patch.map_point)));
      $('my-list').append(own);
    }
    if(auth.user.role==='admin'&&r.status==='submitted'){
      const note=element('textarea');note.placeholder='审核意见（退回/拒绝必填）';note.setAttribute('aria-label','审核意见');
      const distinct=document.createElement('input');distinct.type='checkbox';const label=element('label','已核对为同名不同分店（仅用于新增重名对象）');label.append(distinct);card.append(note,label);
      for(const [action,text] of [['approved','批准'],['needs_info','退回补充'],['rejected','拒绝']])card.append(button(text,async()=>{await api('review',{id:r.id,revision:r.revision,action,note:note.value,allow_distinct:distinct.checked});await refresh();message('审核已保存。');}));
      $('review-list').append(card);
    }else if(auth.user.role==='admin'){
      const history=element('details');history.append(element('summary',labels[r.status]+' · '+(r.patch.name||r.base?.name||r.id)),card);$('review-list').append(history);
    }else if(r.author_id===auth.user.id)$('my-list').append(card);
  }
  if(!$('my-list').children.length)$('my-list').append(element('p','暂无可显示的个人提交。'));
  if(!$('review-list').children.length)$('review-list').append(element('p','没有待审核提交。'));
}
function editRecord(r){
  newForm();editing=r;$('kind').value=r.kind;populate();$('entity').value=r.entity_id||'';
  for(const [key,value] of Object.entries(r.patch)){
    if(key==='map_point'){mapPoint=value;showMapPoint();}
    else if(key==='coordinates'){for(const k of ['lng','lat','crs'])$(k).value=value[k];}
    else if(key==='opening_hours')$('hours').value=(value||[]).map(v=>v.join('-')).join(',');
    else if(key==='poi_id'||key==='shop_id')$('parent').value=value;
    else if($(key))$(key).value=Array.isArray(value)?value.join(','):value===null?'':String(value);
  }
  $('evidence').value=r.evidence;
  $('observed').value=new Date(Date.parse(r.observed_at)-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
  uploaded=[...r.attachments];$('uploaded').textContent='已附 '+uploaded.length+' 张图片';renderExisting();page('form');
}
async function submit(draft){
  // Open collapsed groups containing invalid fields before native validation.
  for(const details of Object.values(formGroups))if([...details.querySelectorAll('input,select')].some(n=>!n.checkValidity()))details.open=true;
  if(!$('entry-form').reportValidity())return;
  $('submit-entry').disabled=true;$('save-draft').disabled=true;
  try{
    const kind=$('kind').value, entity=catalog[kind].find(r=>r.id===$('entity').value);
    const fields={pois:['name','category','address','floor'],shops:['name','floor'],items:['name','price','specification','sales_channel','tags','serving_minutes','available']}[kind];
    const patch={};for(const field of fields){const value=$(field).value.trim();if(!value)continue;patch[field]=['price','serving_minutes'].includes(field)?Number(value):field==='available'?value==='true':field==='tags'?value.split(/[,，]/).map(s=>s.trim()).filter(Boolean):value;}
    if(kind==='pois'){
      if(mapPoint)patch.map_point=mapPoint;
      if($('location_description').value.trim())patch.location_description=$('location_description').value.trim();
      if($('building_floors').value){if(!floorEvidence.value)throw Error('请注明建筑总层数是现场确认还是目测估计');patch.building_floors=Number($('building_floors').value);patch.floor_evidence=floorEvidence.value;}
      if($('observation').value.trim())patch.observation=$('observation').value.trim();
      if($('lng').value||$('lat').value||$('crs').value){
        if(mapPoint)throw Error('地图选点与经纬度只能保留一种，请清除选点或清空经纬度。');
        if(!$('lng').value||!$('lat').value||!['WGS84','BD09'].includes($('crs').value.trim()))throw Error('坐标需同时填写经度、纬度与 WGS84/BD09；不确定请全部留空。');
        patch.coordinates={lng:Number($('lng').value),lat:Number($('lat').value),crs:$('crs').value.trim()};
      }
    }
    if(kind!=='items'&&$('hours').value.trim())patch.opening_hours=$('hours').value.split(/[,，]/).map(s=>s.trim().split('-'));
    if(kind!=='pois'&&!entity)patch[kind==='shops'?'poi_id':'shop_id']=$('parent').value;
    const changes=onlyChanged(patch,entity);
    if(!Object.keys(changes).length)throw Error('没有需要更新的内容，已有资料继续保留；无需重复提交。可返回采集任务。');
    const files=[...$('photos').files];if(files.length+uploaded.length>5)throw Error('最多5张图片');
    for(const file of files){if(file.size>3*1024*1024||!['image/png','image/jpeg'].includes(file.type))throw Error('仅支持3MB以内PNG/JPEG');}
    // Remove each confirmed upload from the input; failed retries won't re-upload it.
    for(let i=0;i<files.length;i++){const file=files[i];const result=await api('attachments',file,file.type);uploaded.push(result.id);const remaining=new DataTransfer();files.slice(i+1).forEach(f=>remaining.items.add(f));$('photos').files=remaining.files;}
    $('photos').value='';$('uploaded').textContent='已附 '+uploaded.length+' 张图片';
    const data={kind,entity_id:entity?.id||null,base_revision:editing?editing.base_revision:entity?.revision||null,patch:changes,evidence:$('evidence').value,observed_at:new Date($('observed').value).toISOString(),attachments:uploaded,draft};
    if(editing){data.submission_id=editing.id;data.revision=editing.revision;}
    const signature=JSON.stringify(data);if(!pending||pending.signature!==signature)pending={signature,key:crypto.randomUUID()};
    data.request_id=pending.key;
    await api('submissions',data);await refresh();newForm();page('mine');message(draft?'草稿已保存到服务器。':'已提交，等待管理员审核。');
  }finally{$('submit-entry').disabled=false;$('save-draft').disabled=false;}
}
async function refresh(){[catalog,tasks,records]=await Promise.all([api('catalog'),api('tasks'),api('submissions')]);renderTasks();renderRecords();}
async function enter(result){auth=result;$('login').hidden=true;$('workspace').hidden=false;$('review-tab').hidden=auth.user.role!=='admin';$('identity').textContent=auth.user.name+' · '+(auth.user.role==='admin'?'管理员':'采集队员');if(auth.user.role==='admin'&&!document.getElementById('audit-link')){const link=document.createElement('a');link.id='audit-link';link.href='/audit/';link.textContent='建筑与证据审查';$('review-tab').after(link);}await refresh();newForm();}
$('login-form').onsubmit=e=>{e.preventDefault();run(async()=>{await enter(await api('login',{name:$('member-name').value}));message('已进入资料台。署名仅作填写标记。');});};
$('entry-form').onsubmit=e=>{e.preventDefault();run(()=>submit(false));};
$('save-draft').onclick=()=>run(()=>submit(true));
let selection={kind:'pois',entity:''};
function rememberSelection(){selection={kind:$('kind').value,entity:$('entity').value};}
function switchSelection(kindChanged){
  const next={kind:$('kind').value,entity:$('entity').value};
  const dirty=editing||uploaded.length||$('photos').files.length||mapPoint||$('evidence').value.trim()||Object.keys(fieldNames).some(id=>$(id).value!=='');
  if(dirty&&!confirm('切换对象会清空本次尚未保存的修改。需要保留请取消并先保存草稿。继续切换？')){$('kind').value=selection.kind;$('entity').value=selection.entity;return;}
  newForm();$('kind').value=next.kind;populate();if(!kindChanged)$('entity').value=next.entity;selectEntity();rememberSelection();
}
$('kind').onchange=()=>switchSelection(true);$('entity').onchange=()=>switchSelection(false);$('search').oninput=renderTasks;
$('entry-form').addEventListener('focusin',rememberSelection);
document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>page(b.dataset.page));
$('refresh').onclick=()=>run(refresh);
$('logout').onclick=()=>run(async()=>{await api('logout',{});location.reload();});
$('export').onclick=()=>run(async()=>{const data=await api('export');const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download='contributions-backup.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('已导出记录清单；完整备份还需保留管理员电脑上的附件目录。');});
api('me').then(enter).catch(()=>{});
