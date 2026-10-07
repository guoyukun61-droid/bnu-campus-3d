import * as THREE from 'three';
import {GLTFLoader} from '/map/GLTFLoader.js';
import {OrbitControls} from '/map/OrbitControls.js';
import {mapPosition,mountSpatialList} from '/map/locations.js';
// The embedded classic map remains available; direct visits use the full directory UI.
if(window.top===window.self)window.location.replace('/explore/');
const host=document.getElementById('canvas'),status=document.getElementById('status'),label=document.getElementById('label');
const scene=new THREE.Scene();scene.background=new THREE.Color('#eeece6');
const camera=new THREE.PerspectiveCamera(45,1,1,5000);
let renderer;
try{renderer=new THREE.WebGLRenderer({antialias:true});}catch(error){status.textContent='当前浏览器无法显示三维地图。请关闭地图，继续浏览地点或使用生活助手。';parent.postMessage({type:'map-error',message:status.textContent},location.origin);throw error;}
renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.append(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);controls.maxPolarAngle=Math.PI/2-.03;controls.minDistance=20;controls.maxDistance=2200;
scene.add(new THREE.HemisphereLight(0xffffff,0x827a68,2.4));const sun=new THREE.DirectionalLight(0xffffff,2);sun.position.set(250,700,300);scene.add(sun);
let model,rows=[],pins=[],pending=null,start=null,highlighted=[];const ray=new THREE.Raycaster(),down=new THREE.Raycaster();
const image=document.createElement('canvas');image.width=64;image.height=80;const ctx=image.getContext('2d');ctx.fillStyle='#ffffff';ctx.beginPath();ctx.moveTo(3,3);ctx.lineTo(61,3);ctx.lineTo(32,80);ctx.closePath();ctx.fill();const texture=new THREE.CanvasTexture(image);
function valid(hit){let o=hit.object;while(o){if(!o.visible||['Presentation_Base','GF2_NDVI_Trees'].includes(o.name))return false;o=o.parent;}return true;}
function send(data){parent.postMessage(data,location.origin);}
function buildPins(){if(!model||!rows.length)return;model.updateMatrixWorld(true);for(const p of rows){const pos=mapPosition(p);if(!pos||Math.abs(pos.x)>452||Math.abs(pos.y)>601)continue;down.set(new THREE.Vector3(pos.x,2000,-pos.y),new THREE.Vector3(0,-1,0));const hit=down.intersectObject(model,true).find(valid);if(!hit)continue;const pin=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,color:p.display_anchor?0x856399:0xc87945,depthTest:false,depthWrite:false}));pin.center.set(.5,0);pin.scale.set(10,13,1);pin.position.copy(hit.point);pin.renderOrder=90;pin.userData.row=p;scene.add(pin);pins.push(pin);}if(pending)focus(pending);status.textContent='选择地点查看详情 · '+pins.length+'个模型内标记（紫色为楼栋代表点）';}
function home(top=false){camera.position.set(top?0:680,top?1450:1000,top?1:850);controls.target.set(0,0,0);controls.update();}
function focus(id){pending=id;const pin=pins.find(p=>p.userData.row.id===id);for(const [mesh,mat] of highlighted){mesh.material.dispose();mesh.material=mat;}highlighted=[];
  for(const p of pins){p.material.color.setHex(p===pin?0xad421d:p.userData.row.display_anchor?0x856399:0xc87945);p.scale.set(p===pin?14:10,p===pin?18:13,1);}
  if(!pin){const row=rows.find(r=>r.id===id);if(row){label.hidden=false;label.textContent=row.name+(row.floor?' · '+row.floor+'层':'')+' · '+(row.address||'位置待补');const r=row.map_reference;if(r){controls.target.set(r.x,0,-r.y);camera.position.set(r.x+95,220,-r.y+175);controls.update();status.textContent='参照楼：'+r.label+'；店铺在其'+r.relation+'，未标注入口或绑定该楼';}else status.textContent='已保留分布顺序，具体入口尚未点选';send({type:'poi-selected',id});}return;}
  const p=pin.userData.row;if(p.building_id!=null)model.traverse(o=>{if(o.isMesh){let a=o,matched=false;while(a){if(new RegExp('^Building_'+p.building_id+'(?:_|$)').test(a.name)){matched=true;break;}a=a.parent;}if(matched&&!Array.isArray(o.material)){const old=o.material;o.material=old.clone();o.material.color.set('#e6ad77');highlighted.push([o,old]);}}});
  const v=pin.position;controls.target.copy(v);camera.position.set(v.x+115,v.y+220,v.z+185);controls.update();label.hidden=false;label.textContent=p.name+(p.floor?' · '+p.floor+'层':'')+(p.display_anchor?' · '+p.display_anchor.label:'');status.textContent=p.display_anchor?'紫色为楼栋定位，不是门店入口；楼层以文字为准':'原有点位；门店入口未重新测量';send({type:'poi-selected',id});}
home();document.getElementById('home').onclick=()=>home();document.getElementById('top').onclick=()=>home(true);document.getElementById('snack').onclick=()=>{camera.position.set(-140,160,535);controls.target.set(-300,8,373);controls.update();};
new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();}).observe(host);
fetch('/api/app/directory').then(r=>{if(!r.ok)throw Error();return r.json();}).then(d=>{rows=d.pois;mountSpatialList(rows,row=>focus(row.id),document.getElementById('tools'));buildPins();}).catch(()=>status.textContent='地点资料加载失败，可继续使用对话');
new GLTFLoader().load('/map/campus.glb',g=>{model=g.scene;scene.add(model);buildPins();send({type:'map-ready'});},p=>{if(p.total)status.textContent='正在加载白模 '+Math.round(p.loaded/p.total*100)+'%';},()=>{status.textContent='三维模型加载失败，地点列表与文字查询仍可使用。';const retry=document.createElement('button');retry.textContent='重新加载地图';retry.onclick=()=>location.reload();document.getElementById('tools').append(retry);send({type:'map-error',message:status.textContent});});
addEventListener('message',e=>{if(e.origin!==location.origin||e.source!==parent)return;if(e.data?.type==='focus-poi'&&typeof e.data.id==='string')focus(e.data.id);});
renderer.domElement.addEventListener('pointerdown',e=>{start={x:e.clientX,y:e.clientY};});renderer.domElement.addEventListener('pointercancel',()=>start=null);
renderer.domElement.addEventListener('pointerup',e=>{const s=start;start=null;if(!s||Math.hypot(s.x-e.clientX,s.y-e.clientY)>6||e.button!==0)return;const b=renderer.domElement.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-b.left)/b.width*2-1,-(e.clientY-b.top)/b.height*2+1),camera);const hit=ray.intersectObjects(pins)[0];if(hit)focus(hit.object.userData.row.id);});
renderer.setAnimationLoop(()=>{controls.update();renderer.render(scene,camera);});
