import * as THREE from 'three';
import {GLTFLoader} from '/map/GLTFLoader.js';
import {OrbitControls} from '/map/OrbitControls.js';
import {mapPosition,mountSpatialList} from '/map/locations.js';
const host=document.getElementById('canvas'),status=document.getElementById('status'),pick=document.getElementById('pick');
let model,armed=false,start=null,dragged=false,buildingInfo=new Map();
const scene=new THREE.Scene();scene.background=new THREE.Color('#e7eef5');
const camera=new THREE.PerspectiveCamera(45,1,1,5000);
const renderer=new THREE.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.maxDistance=2200;controls.minDistance=15;controls.maxPolarAngle=Math.PI/2-.03;
scene.add(new THREE.HemisphereLight(0xffffff,0x667788,2));const sun=new THREE.DirectionalLight(0xffffff,2.5);sun.position.set(250,700,300);scene.add(sun);
// Sprite bottom centre is the triangle tip: its world position is the surface hit.
const pinCanvas=document.createElement('canvas');pinCanvas.width=64;pinCanvas.height=80;
const pinContext=pinCanvas.getContext('2d');pinContext.fillStyle='white';
pinContext.beginPath();pinContext.moveTo(3,4);pinContext.lineTo(61,4);pinContext.lineTo(32,80);pinContext.closePath();pinContext.fill();
const pinTexture=new THREE.CanvasTexture(pinCanvas);
function makePin(color){const pin=new THREE.Sprite(new THREE.SpriteMaterial({map:pinTexture,color,depthTest:false,depthWrite:false}));pin.center.set(.5,0);pin.scale.set(12,15,1);pin.visible=false;pin.renderOrder=90;return pin;}
const marker=makePin(0xff4b28);marker.scale.set(15,19,1);marker.renderOrder=99;scene.add(marker);
const surfaceRay=new THREE.Raycaster();let pendingPreview=null;
function validSurface(hit){let o=hit.object;while(o){if(!o.visible||['Presentation_Base','GF2_NDVI_Trees'].includes(o.name))return false;o=o.parent;}return true;}
function surfaceAt(p){
  if(!model)return null;
  surfaceRay.set(new THREE.Vector3(p.x,2000,-p.y),new THREE.Vector3(0,-1,0));
  return surfaceRay.intersectObject(model,true).find(validSurface)||null;
}
function anchorPin(pin,p){const hit=surfaceAt(p);pin.userData.anchored=Boolean(hit);pin.visible=Boolean(hit);if(hit)pin.position.copy(hit.point);return hit;}
function anchorPois(){if(!model)return;model.updateMatrixWorld(true);poiMeshes.forEach(pin=>anchorPin(pin,mapPosition(pin.userData.row)));drawList();if(pendingPreview)anchorPin(marker,pendingPreview);}
const ray=new THREE.Raycaster(),pointer=new THREE.Vector2();
const style=document.createElement('link');style.rel='stylesheet';style.href='/map/review.css';document.head.append(style);
const poiGroup=new THREE.Group();scene.add(poiGroup);
let reviewRows=[],poiMeshes=[];
const review=document.createElement('aside');review.id='poi-review';
const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
const totals=node('p','正在读取已发布名录…');
const search=document.createElement('input');search.placeholder='搜索店名、地址或问题';search.setAttribute('aria-label','搜索POI');
const filter=document.createElement('select');filter.setAttribute('aria-label','筛选问题');
for(const [value,label] of [['all','全部地点'],['issues','有待核问题'],['missing','缺坐标'],['campus','校内'],['price','缺价格']])filter.add(new Option(label,value));
const list=document.createElement('div');list.id='poi-list';
const info=document.createElement('div');info.id='poi-info';
review.append(node('h2','POI · 人工核对'),totals,search,filter,list,info);document.body.append(review);
const toggle=node('button','POI / 审核清单');toggle.onclick=()=>{review.hidden=!review.hidden;};document.getElementById('toolbar').append(toggle);
function showPoi(row){
  info.replaceChildren(node('h3',row.name),node('p',`${row.address||'地址未知'} · 楼层 ${row.floor||'未注明'}`),node('p',`营业：${row.opening_hours_text||'未知'} ${row.hours_notes}`),node('p',`来源：${row.source||'未知'}；位置依据：${row.location_source}`));
  info.append(node('p',row.issues.join('；')||'当前自动检查未发现缺失项，仍不代表全部现场核实'));
  marker.visible=false;pendingPreview=null;
  if(row.display_anchor||(row.location&&row.on_map)){const p=mapPosition(row);pendingPreview=p;const hit=anchorPin(marker,p);const h=hit?.point.y||0;controls.target.set(p.x,h,-p.y);camera.position.set(p.x+95,h+210,-p.y+175);controls.update();if(row.display_anchor)info.append(node('p','楼栋代表点，不是入口坐标：'+row.display_anchor.label));if(!hit)info.append(node('p','尚未命中模型表面，暂不显示标记；请核对位置或等待模型加载。'));}
  else if(row.map_reference){const p=row.map_reference;controls.target.set(p.x,0,-p.y);camera.position.set(p.x+95,210,-p.y+175);controls.update();info.append(node('p','参照楼：'+p.label+'；店铺在其'+p.relation+'，具体建筑和入口待点选，不将参照楼作为商户所属楼。'));}
  else info.append(node('p','没有可展示的模型内位置，请从原填写表单补充。'));
  if(row.shops.length)info.append(node('p','关联店铺/集合：'+row.shops.map(s=>s.name).join('、')));
  const menus=document.createElement('details');menus.append(node('summary',`真实菜单 / 规格 ${row.items.length} 条（展开查看）`));
  row.items.forEach(i=>menus.append(node('p',`${i.name} · ${i.specification||'规格未知'} · ${i.price==null?'价格待核':i.price+'元'} · ${i.source}`)));info.append(menus);
}
function drawList(){
  const q=search.value.trim().toLowerCase();
  const rows=reviewRows.filter(r=>(!q||[r.name,r.address,...r.issues].join(' ').toLowerCase().includes(q))&&(filter.value!=='issues'||r.issues.length)&&(filter.value!=='missing'||!r.location)&&(filter.value!=='campus'||r.zone==='campus')&&(filter.value!=='price'||r.issues.some(i=>i.includes('缺价格'))));
  list.replaceChildren();const ids=new Set(rows.map(r=>r.id));poiMeshes.forEach(m=>m.visible=Boolean(m.userData.anchored)&&ids.has(m.userData.row.id));
  for(const r of rows){const b=node('button',`${r.issues.length?'●':'○'} ${r.name}${r.floor?' · '+r.floor+'层':''}${!r.location?' [缺坐标]':!r.on_map?' [范围外]':''}`);b.onclick=()=>showPoi(r);list.append(b);}
}
search.oninput=drawList;filter.onchange=drawList;
fetch('/api/contribute/map-review').then(r=>{if(!r.ok)throw Error('请先在填报首页登录，再打开地图');return r.json();}).then(data=>{
  reviewRows=data.rows;const c=data.counts;
  totals.textContent=`${c.pois} 条真实名录 · ${c.on_map} 个模型内点位 · ${c.missing_coordinates} 条缺坐标。橙色：有待核字段；蓝色：检查项齐全。疑似重复 ${c.duplicate_candidates} 组、原始更新候选 ${c.update_candidates} 条需比对。重叠点用列表选择；点高仅为显示，不代表楼层。`;
  totals.textContent=totals.textContent.replace('点高仅为显示，不代表楼层。','倒三角尖端贴合该XY处建筑或地面，不表示店铺楼层。');
  const spatialPanel=mountSpatialList(reviewRows,row=>{review.hidden=false;spatialPanel.hidden=true;showPoi(row);},document.getElementById('toolbar'));spatialPanel.hidden=true;
  totals.append(node('span',' 紫色为已确认楼栋代表点，仍计入缺入口坐标。'));
  for(const row of reviewRows){if(!row.on_map&&!row.display_anchor)continue;const m=makePin(row.display_anchor?0x856399:row.issues.length?0xe48b20:0x1673cc);m.userData.row=row;poiGroup.add(m);poiMeshes.push(m);}
  anchorPois();drawList();
}).catch(e=>{totals.textContent='名录加载失败：'+e.message;});
function send(data){parent.postMessage(data,location.origin);}
function home(top=false){camera.position.set(top?0:680,top?1450:1000,top?1:850);controls.target.set(0,0,0);controls.update();}
home();document.getElementById('home').onclick=()=>home();document.getElementById('top').onclick=()=>home(true);
const detail=document.getElementById('building-detail');
const views={snack:[-140,160,535],reverse:[-445,140,200],plan:[-300,290,373.1]};
document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>{camera.position.set(...views[button.dataset.view]);controls.target.set(-300,8,373);controls.update();status.textContent='小吃街逐栋核对：新乐群保留四层，北侧补建低楼层数待核';});
new ResizeObserver(()=>{host.style.top=document.getElementById('toolbar').offsetHeight+'px';}).observe(document.getElementById('toolbar'));
pick.disabled=true;pick.onclick=()=>{armed=!armed;pick.textContent=armed?'取消选点':'开始选点';status.textContent=armed?'轻点建筑或地面标记位置':'可旋转或平移地图';};
new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe(host);
fetch('/map/buildings.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{buildingInfo=new Map(d.buildings.map(b=>[String(b.osm_id),b]));}).catch(()=>{status.textContent='建筑名称暂不可用，仍可记录位置';});
new GLTFLoader().load('/map/campus.glb',g=>{model=g.scene;scene.add(model);anchorPois();pick.disabled=false;status.textContent='white_v6 已加载；倒三角尖端贴合建筑或地面，点击“开始选点”可修改位置';send({type:'contribution-map-ready'});},p=>{if(p.total)status.textContent=`白模加载 ${Math.round(p.loaded/p.total*100)}%`;},()=>{status.textContent='地图加载失败，请刷新或继续文字填报；需要有效登录会话。';});
renderer.domElement.addEventListener('pointerdown',e=>{if(start){dragged=true;return;}start={x:e.clientX,y:e.clientY,id:e.pointerId};dragged=false;});
renderer.domElement.addEventListener('pointermove',e=>{if(start&&Math.hypot(e.clientX-start.x,e.clientY-start.y)>6)dragged=true;});
renderer.domElement.addEventListener('pointercancel',()=>{start=null;dragged=true;});
renderer.domElement.addEventListener('pointerup',e=>{
  if(!start||e.pointerId!==start.id)return;const moved=dragged;start=null;
  if(moved||!model||e.button!==0)return;
  const box=renderer.domElement.getBoundingClientRect();pointer.set((e.clientX-box.left)/box.width*2-1,-(e.clientY-box.top)/box.height*2+1);ray.setFromCamera(pointer,camera);
  if(!armed){const poi=ray.intersectObjects(poiMeshes.filter(m=>m.visible))[0];if(poi)showPoi(poi.object.userData.row);return;}
  const hit=ray.intersectObject(model,true).find(h=>{let o=h.object;while(o){if(!o.visible||['Presentation_Base','GF2_NDVI_Trees'].includes(o.name))return false;o=o.parent;}return true;});
  if(!hit){status.textContent='未点中模型，请点建筑或地面';return;}
  const x=+hit.point.x.toFixed(2),y=+(-hit.point.z).toFixed(2);
  if(Math.abs(x)>452||Math.abs(y)>601){status.textContent='超出当前选点范围，请用文字或经纬度填写';return;}
  let obj=hit.object;while(obj&&!obj.name.startsWith('Building_'))obj=obj.parent;
  const raw=obj?.name.match(/^Building_(\d+)/)?.[1],b=raw?buildingInfo.get(raw):null;
  const point={x,y,building_id:b?b.osm_id:null,model:'white_v4',crs:'local EPSG:32650'};
  marker.position.copy(hit.point);marker.visible=true;pendingPreview=null;armed=false;pick.textContent='重新选点';
  const label=b?.audit_label||b?.name||'独立位置';
  detail.hidden=!b;detail.textContent=b?`${label} · 建筑ID ${b.osm_id} · ${b.floors??'未知'}层 · 表现高度 ${b.height??'未知'} m（非实测）。${b.correction_note||'旧模型参数，尚未逐栋核实；不要照抄为现场数据。'}`:'';
  status.textContent=`已选 ${label} · 本地坐标 ${x}, ${y}`;send({type:'contribution-map-point',point,name:label});
});
addEventListener('message',e=>{
  if(e.origin!==location.origin||e.source!==parent||e.data?.type!=='contribution-map-show')return;
  const p=e.data.point;if(!p||!Number.isFinite(p.x)||!Number.isFinite(p.y)||Math.abs(p.x)>452||Math.abs(p.y)>601){status.textContent='此地点在模型范围外，保留列表与文字填报';return;}
  pendingPreview=p;const hit=anchorPin(marker,p);const h=hit?.point.y||0;controls.target.set(p.x,h,-p.y);camera.position.set(p.x+100,h+220,-p.y+180);controls.update();status.textContent=hit?'已回显位置；倒三角尖端贴合模型表面':'模型表面尚不可用，暂不显示标记';
});
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});
