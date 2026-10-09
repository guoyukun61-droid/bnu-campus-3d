import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import * as THREE from '../vendor/three/three.module.min.js';
import {cameraSafeArea,cameraViewOffset,cameraFitDistance,stableCameraDirection} from '../app/explore/state.js';

const overlaps=(a,b)=>a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top;
const desktop=[{left:1000,top:90,right:1420,bottom:800},{left:300,top:20,right:900,bottom:80},{left:430,top:810,right:1010,bottom:878}];

test('no overlays retains centered padded framing',()=>{
  const safe=cameraSafeArea(1440,900);
  assert.equal(safe.centerX,720);assert.equal(safe.centerY,450);assert.equal(safe.available,true);
  assert.deepEqual(cameraViewOffset(1440,900,safe),{x:0,y:0});
});

test('right panel, top rail and bottom input yield a real free rectangle',()=>{
  const safe=cameraSafeArea(1440,900,desktop,8);
  assert.equal(safe.right,992);assert.equal(safe.top,88);assert.equal(safe.bottom,802);
  assert.ok(safe.width>900&&safe.height>700);
  for(const obstacle of desktop)assert.equal(overlaps(safe,obstacle),false);
  assert.ok(cameraViewOffset(1440,900,safe).x>0,'right panel shifts target left, not right');
});

test('mobile bottom sheet moves the target into the uncovered upper map',()=>{
  const obstacles=[{left:0,top:0,right:390,bottom:126},{left:0,top:420,right:390,bottom:844}];
  const safe=cameraSafeArea(390,844,obstacles,8);
  assert.equal(safe.top,134);assert.equal(safe.bottom,412);assert.equal(safe.centerX,195);
  assert.ok(cameraViewOffset(390,844,safe).y>0);
  for(const obstacle of obstacles)assert.equal(overlaps(safe,obstacle),false);
});

test('invalid, offscreen, nested and duplicate obstacles are safely bounded',()=>{
  const base={left:850,top:80,right:1300,bottom:720};
  const safe=cameraSafeArea(1200,800,[base,base,{left:900,top:100,right:1000,bottom:200},{left:NaN,top:0,right:4,bottom:2},{left:-200,top:0,right:-1,bottom:30}]);
  assert.ok(safe.left>=0&&safe.top>=0&&safe.right<=1200&&safe.bottom<=800);
  assert.equal(overlaps(safe,base),false);
  assert.deepEqual(safe,cameraSafeArea(1200,800,[base]));
});

test('full occlusion and zero-size mounts explicitly report unavailable or bounded area',()=>{
  const covered=cameraSafeArea(390,844,[{left:0,top:0,right:390,bottom:844}]);
  assert.equal(covered.available,false);
  assert.deepEqual(cameraViewOffset(390,844,covered),{x:0,y:0});
  const tiny=cameraSafeArea(0,0);assert.ok(tiny.width>0&&tiny.height>0);
});

test('measured panel changes are recomputed rather than tied to a boolean offset',()=>{
  const small=cameraSafeArea(1440,900,[{left:1150,top:10,right:1440,bottom:900}]);
  const large=cameraSafeArea(1440,900,[{left:900,top:10,right:1440,bottom:900}]);
  assert.ok(large.centerX<small.centerX);assert.ok(large.width<small.width);
  assert.deepEqual(cameraSafeArea(1440,900,desktop),cameraSafeArea(1440,900,[...desktop].reverse()));
});

test('fit distance respects building bounds and reduced visible dimensions',()=>{
  const full=cameraSafeArea(1440,900),small=cameraSafeArea(1440,900,[{left:0,top:350,right:1440,bottom:900}]);
  const size={x:160,y:30,z:90};
  assert.ok(cameraFitDistance(size,42,1440,900,small)>cameraFitDistance(size,42,1440,900,full));
  assert.ok(cameraFitDistance({x:320,y:60,z:180},42,1440,900,full)>cameraFitDistance(size,42,1440,900,full));
  assert.equal(cameraFitDistance({x:0,y:0,z:0},42,1440,900,full),90);
  assert.equal(cameraFitDistance({x:1e9,y:1e9,z:1e9},42,1440,900,full),1900);
});

test('stable heading is unit length and clamps overhead and ground-level views',()=>{
  const fallback={x:-1,y:1,z:1};
  for(const d of [{x:0,y:1200,z:.0001},{x:10,y:0,z:-4},{x:NaN,y:1,z:1},{x:0,y:0,z:0}]){
    const result=stableCameraDirection(d,fallback);
    assert.ok(Math.abs(Math.hypot(result.x,result.y,result.z)-1)<1e-12);
    assert.ok(result.y>=Math.sin(32*Math.PI/180)-1e-12&&result.y<=Math.sin(62*Math.PI/180)+1e-12);
  }
  const overhead=stableCameraDirection({x:0,y:1200,z:.0001},fallback);
  assert.ok(overhead.x<0&&overhead.z>0,'near vertical view retains the previous reliable azimuth');
});

function assertProjectedFit(width,height,obstacles){
  const safe=cameraSafeArea(width,height,obstacles),size={x:170,y:42,z:75};
  const distance=cameraFitDistance(size,42,width,height,safe),direction=stableCameraDirection({x:1,y:1,z:1});
  const camera=new THREE.PerspectiveCamera(42,width/height,1,5000),center=new THREE.Vector3(10,25,-35);
  camera.position.copy(center).add(new THREE.Vector3(direction.x,direction.y,direction.z).multiplyScalar(distance));
  camera.lookAt(center);const offset=cameraViewOffset(width,height,safe);camera.setViewOffset(width,height,offset.x,offset.y,width,height);camera.updateMatrixWorld(true);
  const projected=center.clone().project(camera),screen={x:(projected.x+1)*width/2,y:(1-projected.y)*height/2};
  assert.ok(Math.abs(screen.x-safe.centerX)<1e-8&&Math.abs(screen.y-safe.centerY)<1e-8);
  for(const x of [-.5,.5])for(const y of [-.5,.5])for(const z of [-.5,.5]){
    const p=center.clone().add(new THREE.Vector3(x*size.x,y*size.y,z*size.z)).project(camera),sx=(p.x+1)*width/2,sy=(1-p.y)*height/2;
    assert.ok(sx>=safe.left&&sx<=safe.right&&sy>=safe.top&&sy<=safe.bottom,`corner ${sx},${sy} must remain visible`);
  }
}

test('actual Three.js projection keeps desktop target and all bounds corners in the free rectangle',()=>assertProjectedFit(1440,900,desktop));
test('actual Three.js projection keeps mobile building clear of the bottom sheet',()=>assertProjectedFit(390,844,[{left:0,top:0,right:390,bottom:126},{left:0,top:420,right:390,bottom:844}]));

test('scene wires measurements, resize, motion interruption and cleanup without new runtime imports',async()=>{
  const scene=await readFile(new URL('../app/explore/scene.js',import.meta.url),'utf8');
  assert.match(scene,/getOcclusions=\(\)=>\[\]/);assert.match(scene,/cameraSafeArea\(w,h,getOcclusions\(\)\)/);
  assert.match(scene,/setPanel\(\)\{return refreshLayout\(\);\}/);
  assert.match(scene,/controls.addEventListener\('start',\(\)=>\{tween=null;framedTarget=null;pendingFocus=null;stopRoam/);
  assert.match(scene,/if\(tween\)tween.start\+=performance.now\(\)-hiddenAt/);
  assert.match(scene,/document.removeEventListener\('keydown',keyboardInput\)/);
  assert.doesNotMatch(scene,/camera-layout\.js|h\*\.22|Math.min\(180,w\*\.15\)/);
});

async function focusHarness(){
  const source=await readFile(new URL('../app/explore/scene.js',import.meta.url),'utf8');
  const cancel=source.slice(source.indexOf('  function cancelFocus('),source.indexOf('  const reduced='));
  const focus=source.slice(source.indexOf('  function focus(id'),source.indexOf("  controls.addEventListener('start'"));
  const refresh=source.slice(source.indexOf('  function refreshLayout('),source.indexOf('  function cancelFocus('));
  const start=source.match(/controls\.addEventListener\('start',\(\)=>\{([^]*?)\}\);/)[1];
  const context=vm.createContext({THREE,tween:{old:true},pendingFocus:{building:'previous'},framedTarget:{old:true},selected:null,selectedBuilding:null,visibleIds:null,
    rows:[{id:'unknown-location'}],model:{getObjectByName:()=>null},pins:[],statuses:[],stopRoam(){},applyFilter(){},
    framePoint(){throw Error('Unknown positions must not frame a new world point');},onStatus(text){this.statuses.push(text);},
    projectLayout:()=>({available:true}),fittedPosition(){throw Error('Manual control must not reframe an old target');},
    camera:{position:{copy(){throw Error('Manual control must not replace camera position');}}},controls:{},onInteraction(){}});
  // Use the real scene functions with rendering dependencies isolated. These
  // tests exercise interruption, not a text-only assertion about implementation.
  context.onStatus=text=>context.statuses.push(text);
  vm.runInContext(cancel+refresh+focus+`\nfunction manualStart(){${start}}`,context);
  return context;
}

test('selecting a location-less POI cancels a previous camera flight without inventing a point',async()=>{
  const ctx=await focusHarness();assert.equal(vm.runInContext("focus('unknown-location')",ctx),false);
  assert.equal(ctx.tween,null);assert.equal(ctx.pendingFocus,null);assert.equal(ctx.framedTarget,null);
  assert.match(ctx.statuses[0],/入口待点选/);
});

test('an unavailable building cancels the old flight and does not reuse its target',async()=>{
  const ctx=await focusHarness();assert.equal(vm.runInContext("focusBuilding('missing-model-object')",ctx),false);
  assert.equal(ctx.tween,null);assert.equal(ctx.pendingFocus,null);assert.equal(ctx.framedTarget,null);
});

test('manual drag cancels deferred loading focus and layout refresh never pulls back the camera',async()=>{
  const ctx=await focusHarness();ctx.model=null;
  vm.runInContext("focusBuilding('loading-building')",ctx);assert.equal(ctx.pendingFocus.building,'loading-building');
  vm.runInContext('manualStart();refreshLayout()',ctx);
  assert.equal(ctx.pendingFocus,null);assert.equal(ctx.tween,null);assert.equal(ctx.framedTarget,null);
});

test('public cancelFocus cancels pending and animated targets without moving the camera',async()=>{
  const ctx=await focusHarness();vm.runInContext('cancelFocus();refreshLayout()',ctx);
  assert.equal(ctx.pendingFocus,null);assert.equal(ctx.tween,null);assert.equal(ctx.framedTarget,null);
  const source=await readFile(new URL('../app/explore/scene.js',import.meta.url),'utf8');
  assert.match(source,/return \{stopRoam,resumeRoam,focusBuilding,refreshLayout,cancelFocus,/);
});
