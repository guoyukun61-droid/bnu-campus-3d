import * as THREE from 'three';
import {GLTFLoader} from '/map/GLTFLoader.js';
import {OrbitControls} from '/map/OrbitControls.js';
import {displayPoint,inModel,easeCamera,shouldRoam,markerGroups} from './state.js';
import {createArtLayer,buildingId} from './materials.js';

export function createScene(host,{onSelect,onBuilding=()=>{},onRoam=()=>{},onStatus,onInteraction,onArtStatus,onBearing=()=>{}}){
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false});renderer.setPixelRatio(Math.min(devicePixelRatio,1.75));renderer.setClearColor('#e9e9df');host.append(renderer.domElement);
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,1,5000);
  const controls=new OrbitControls(camera,renderer.domElement);controls.maxPolarAngle=Math.PI/2-.06;controls.minDistance=35;controls.maxDistance=2000;controls.enableDamping=true;controls.dampingFactor=.09;
  scene.add(new THREE.HemisphereLight(0xf4f8ff,0x839789,1.8));const sun=new THREE.DirectionalLight(0xfffdf5,2.0);sun.position.set(-220,700,250);scene.add(sun);
  const ray=new THREE.Raycaster(),down=new THREE.Raycaster();let model=null,rows=[],pins=[],visibleIds=null,art=null,artMode=true,selected=null,selectedBuilding=null,tween=null,pendingFocus=null,start=null,dead=false;let highlights=new Set();
  let panelOpen=false;
  function projectLayout(){const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;camera.aspect=w/h;
    // Frame the selected building in the unobscured map area, without changing XY.
    if(panelOpen&&w<=800)camera.setViewOffset(w,h,0,h*.22,w,h);
    else if(panelOpen&&w>800)camera.setViewOffset(w,h,-Math.min(180,w*.15),0,w,h);
    else camera.clearViewOffset();camera.updateProjectionMatrix();}
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let roaming=!reduced.matches,lastFrame=performance.now();controls.autoRotateSpeed=1/3;
  function stopRoam(){roaming=false;controls.autoRotate=false;onRoam(false);}
  function resumeRoam(){roaming=!reduced.matches;onRoam(roaming);}
  const motionChange=()=>{if(reduced.matches)stopRoam();};reduced.addEventListener('change',motionChange);onRoam(roaming);
  // Local +Y is north; the scene maps it to -Z. Project a northward vector
  // so the compass remains meaningful when the user rotates the camera.
  const northOrigin=new THREE.Vector3(),northTip=new THREE.Vector3();
  controls.addEventListener('change',()=>{camera.updateMatrixWorld();northOrigin.copy(controls.target).project(camera);northTip.copy(controls.target).add(new THREE.Vector3(0,0,-40)).project(camera);onBearing(Math.atan2((northTip.x-northOrigin.x)*camera.aspect,northTip.y-northOrigin.y)*180/Math.PI);});
  const pinImage=document.createElement('canvas');pinImage.width=64;pinImage.height=80;const c=pinImage.getContext('2d');c.fillStyle='#fff';c.beginPath();c.moveTo(8,5);c.lineTo(56,5);c.lineTo(32,78);c.closePath();c.fill();const pinTexture=new THREE.CanvasTexture(pinImage);
  const clusterTextures=new Map();
  function markerTexture(count){if(count<2)return pinTexture;if(clusterTextures.has(count))return clusterTextures.get(count);const canvas=document.createElement('canvas');canvas.width=80;canvas.height=96;const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.beginPath();ctx.roundRect(3,3,74,65,18);ctx.fill();ctx.beginPath();ctx.moveTo(28,64);ctx.lineTo(52,64);ctx.lineTo(40,94);ctx.fill();ctx.fillStyle='#18261d';ctx.font='bold 34px sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(String(count),40,37);const texture=new THREE.CanvasTexture(canvas);clusterTextures.set(count,texture);return texture;}
  function surface(hit){for(let o=hit.object;o;o=o.parent)if(!o.visible||['Presentation_Base','GF2_NDVI_Trees'].includes(o.name))return false;return true;}
  function go(position,target,animate=true){controls.enableDamping=false;controls.update();controls.enableDamping=true;
    if(reduced.matches||!animate){camera.position.copy(position);controls.target.copy(target);tween=null;controls.update();return;}
    tween={from:camera.position.clone(),to:position,startTarget:controls.target.clone(),target,start:performance.now(),duration:720};}
  function view(name,animate=true){const spec={home:[[590,697,787],[0,0,-45]],snack:[[-150,190,555],[-300,6,375]],top:[[0,1200,1],[0,0,0]]}[name];if(spec)go(new THREE.Vector3(...spec[0]),new THREE.Vector3(...spec[1]),animate);}
  view('home',false);
  function applyFilter(){highlights=new Set(rows.filter(r=>(visibleIds&&visibleIds.has(r.id))&&r.building_id!=null).map(r=>String(r.building_id)));
    const ids=visibleIds?new Set([...visibleIds,...(selected?[selected]:[])]):null,groups=markerGroups(rows,ids);
    for(const p of pins){const row=p.userData.row,group=groups.find(g=>g.row.id===row.id);p.visible=!!visibleIds&&!!group;p.userData.ids=group?.ids||[];const picked=p.userData.ids.includes(selected);p.material.color.set(picked?'#dbefa1':'#f7f4df');p.material.map=markerTexture(p.userData.ids.length);if(p.userData.ids.length<2)p.material.color.set(picked?'#304935':row.display_anchor?'#826b84':'#61774e');}
    const row=rows.find(r=>r.id===selected);art?.setMode(artMode,highlights,selectedBuilding||(row?.building_id!=null?String(row.building_id):null));
    const count=pins.filter(p=>p.visible).length;onStatus(visibleIds?`${visibleIds.size} 个地点 · ${count} 个楼栋/点位标记`:'建筑视图 · 点击楼栋查看名称与介绍');}
  function buildPins(){if(!model||!rows.length||pins.length)return;model.updateMatrixWorld(true);for(const row of rows){if(!inModel(row))continue;const p=displayPoint(row);down.set(new THREE.Vector3(p.x,2000,-p.y),new THREE.Vector3(0,-1,0));const hit=down.intersectObject(model,true).find(surface);if(!hit)continue;
      const pin=new THREE.Sprite(new THREE.SpriteMaterial({map:pinTexture,color:0x788856,depthTest:false,depthWrite:false}));pin.position.copy(hit.point);pin.center.set(.5,0);pin.renderOrder=90;pin.userData.row=row;scene.add(pin);pins.push(pin);}
    applyFilter();if(pendingFocus){const p=pendingFocus;pendingFocus=null;if(p.building)focusBuilding(p.building,p.animate);else focus(p.id,p.animate);}}
  function focus(id,animate=true){stopRoam();selected=id;selectedBuilding=null;if(!visibleIds)visibleIds=new Set([id]);const row=rows.find(r=>r.id===id);applyFilter();if(!row)return false;if(!model){pendingFocus={id,animate};return false;}
    const pin=pins.find(p=>p.visible&&p.userData.ids.includes(id));const ref=row.map_reference;
    if(pin){const v=pin.position,k=host.clientWidth<=800?1.45:1;go(new THREE.Vector3(v.x+110*k,v.y+205*k,v.z+205*k),v.clone(),animate);return true;}
    if(ref){go(new THREE.Vector3(ref.x+95,200,-ref.y+210),new THREE.Vector3(ref.x,0,-ref.y),animate);onStatus('参照区域：'+ref.label+' '+ref.relation+' · 尚无店门位置');return true;}
    onStatus(row.location?'地点在模型范围外，保留列表与地址':'该地点入口待点选，保留文字资料');return false;}
  function focusBuilding(id,animate=true){stopRoam();selected=null;selectedBuilding=String(id);applyFilter();if(!model){pendingFocus={building:id,animate};return false;}const object=model.getObjectByName('Building_'+id);if(!object)return false;const bounds=new THREE.Box3().setFromObject(object),center=bounds.getCenter(new THREE.Vector3()),size=bounds.getSize(new THREE.Vector3());const distance=Math.max(140,Math.max(size.x,size.z)*1.8)*(host.clientWidth<=800?1.45:1);go(center.clone().add(new THREE.Vector3(distance*.6,distance,distance)),center,animate);return true;}
  controls.addEventListener('start',()=>{tween=null;stopRoam();onInteraction();});
  renderer.domElement.addEventListener('pointerdown',e=>{start={x:e.clientX,y:e.clientY,id:e.pointerId};});
  renderer.domElement.addEventListener('pointercancel',()=>start=null);
  renderer.domElement.addEventListener('pointerup',e=>{const s=start;start=null;if(!s||e.pointerId!==s.id||e.button!==0||Math.hypot(e.clientX-s.x,e.clientY-s.y)>6)return;
    const b=renderer.domElement.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-b.left)/b.width*2-1,-(e.clientY-b.top)/b.height*2+1),camera);
    const pin=ray.intersectObjects(pins.filter(p=>p.visible))[0];if(pin){onSelect(pin.object.userData.row.id,pin.object.userData.ids);return;}
    if(model){const hit=ray.intersectObject(model,true).find(surface);const id=hit?buildingId(hit.object):null;if(id){if(!visibleIds){onBuilding(id);return;}const matches=rows.filter(r=>String(r.building_id)===id&&visibleIds.has(r.id));if(matches.length)onSelect(matches[0].id,matches.map(r=>r.id));else onBuilding(id);}}
  });
  const resize=new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight;if(w&&h){renderer.setSize(w,h);projectLayout();}});resize.observe(host);
  new GLTFLoader().load('/map/campus.glb',g=>{if(dead)return;model=g.scene;scene.add(model);art=createArtLayer(model,onArtStatus);applyFilter();buildPins();if(pendingFocus?.building){const p=pendingFocus;pendingFocus=null;focusBuilding(p.building,p.animate);}},p=>{if(p.total)onStatus('正在加载三维校园 '+Math.round(p.loaded/p.total*100)+'%');},()=>onStatus('地图加载失败；地点清单和文字服务仍可使用。可刷新重试。'));
  renderer.setAnimationLoop(now=>{const dt=Math.min(.05,(now-lastFrame)/1000);lastFrame=now;if(document.hidden)return;controls.autoRotate=shouldRoam(roaming,reduced.matches,document.hidden,!!tween);if(tween){const t=Math.min(1,(now-tween.start)/tween.duration),a=easeCamera(t);camera.position.lerpVectors(tween.from,tween.to,a);controls.target.lerpVectors(tween.startTarget,tween.target,a);if(t===1)tween=null;}controls.update(dt);for(const pin of pins){if(!pin.visible)continue;const pixels=pin.userData.ids.length>1?36:pin.userData.ids.includes(selected)?28:20;const height=camera.position.distanceTo(pin.position)*2*Math.tan(THREE.MathUtils.degToRad(camera.fov/2))/Math.max(1,host.clientHeight)*pixels;pin.scale.set(height*.8,height,1);}renderer.render(scene,camera);});
  return {stopRoam,resumeRoam,focusBuilding,setPanel(value){panelOpen=value;projectLayout();},setRows(value){rows=value;buildPins();},filter(ids){visibleIds=ids?new Set(ids):null;selected=null;selectedBuilding=null;pendingFocus=null;applyFilter();},focus,view,setArt(value){artMode=value;applyFilter();},dispose(){dead=true;reduced.removeEventListener('change',motionChange);renderer.setAnimationLoop(null);resize.disconnect();controls.dispose();art?.dispose();pinTexture.dispose();clusterTextures.forEach(t=>t.dispose());pins.forEach(p=>p.material.dispose());renderer.dispose();}};
}
