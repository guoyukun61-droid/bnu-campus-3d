import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../vendor/three/three.module.min.js';
const source=await readFile(new URL('../app/explore/atelier.js',import.meta.url),'utf8');
const vendor=new URL('../vendor/three/three.module.min.js',import.meta.url).href;
const {createAtelierLayer,ATELIER_SAMPLES}=await import('data:text/javascript;base64,'+Buffer.from(source.replace("from 'three'",`from '${vendor}'`)).toString('base64'));
const originalLoad=THREE.TextureLoader.prototype.load;let loaded,failed;
THREE.TextureLoader.prototype.load=function(url,ok,progress,error){loaded=ok;failed=error;};
try {
  const root=new THREE.Group(),geo=new THREE.BoxGeometry(20,13,20),base=new THREE.MeshStandardMaterial({color:'#ffffff'});
  const building=new THREE.Mesh(geo,base);building.name='Building_499434918';root.add(building);
  const multi=new THREE.Mesh(geo,[base,base]);root.add(multi);
  const vertices=geo.attributes.position.array.slice(),originalMatrix=building.matrix.clone();
  const notices=[],layer=createAtelierLayer(root,o=>o===building?'499434918':null,s=>notices.push(s));
  layer.apply(true);const first=building.material;
  assert.notEqual(first,base);assert.equal(building.geometry,geo);assert.equal(building.castShadow,true);
  const shader={uniforms:{},vertexShader:'#include <project_vertex>',fragmentShader:'#include <map_fragment>'};first.onBeforeCompile(shader);
  assert.equal(shader.uniforms.atFloors.value,4);assert.equal(shader.uniforms.atHeight.value,13);assert.equal(shader.uniforms.atReady.value,0);
  assert.match(shader.fragmentShader,/1\.-roofFace/,'Windows excluded from roofs');
  assert.match(shader.fragmentShader,/step\(atHeight-\.2,h\)/,'Window rhythm bounded by known illustrative height');
  failed();assert.deepEqual(notices,['atelier-fallback']);assert.equal(layer.ready,false);
  loaded(new THREE.Texture());assert.equal(layer.ready,true);assert.equal(shader.uniforms.atReady.value,1);
  layer.apply(true,new Set(['499434918']));assert.notEqual(first.color.getHex(),new THREE.Color(ATELIER_SAMPLES['499434918'].wall).getHex());
  layer.apply(true);assert.equal(first.color.getHex(),new THREE.Color(ATELIER_SAMPLES['499434918'].wall).getHex());
  // The baseline layer owns off-mode material assignment. Shadow flags must restore.
  building.material=base;layer.apply(false);assert.equal(building.material,base);assert.equal(building.castShadow,false);
  layer.apply(true);layer.dispose();assert.equal(building.material,base);assert.deepEqual(multi.material,[base,base]);
  assert.deepEqual(geo.attributes.position.array,vertices);assert.deepEqual(building.matrix,originalMatrix);assert.equal(base.color.getHex(),0xffffff);
  const late=createAtelierLayer(root,()=>null,()=>assert.fail('Disposed layer emitted status'));late.dispose();
  const texture=new THREE.Texture();let cleaned=false;texture.addEventListener('dispose',()=>cleaned=true);loaded(texture);assert.equal(cleaned,true);
  const patch=JSON.parse(await readFile(new URL('../assets/snack_blocks_v6.json',import.meta.url),'utf8'));
  for(const [id,spec] of Object.entries(ATELIER_SAMPLES)){const record=[...patch.changes,...patch.retained].find(b=>String(b.osm_id)===id);assert.equal(spec.floors,record.floors);assert.equal(spec.height,record.height);}
  geo.dispose();base.dispose();
  console.log('atelier: geometry preservation, bounded facade shader, known floor counts, load fallback, highlighting and restoration passed');
} finally {THREE.TextureLoader.prototype.load=originalLoad;}
