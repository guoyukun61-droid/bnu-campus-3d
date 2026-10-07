import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../vendor/three/three.module.min.js';

// Use actual Three.js materials and geometry, with only image I/O stubbed.
const source=await readFile(new URL('../app/explore/materials.js',import.meta.url),'utf8');
const moduleUrl=new URL('../vendor/three/three.module.min.js',import.meta.url).href;
const {createArtLayer,buildingId}=await import('data:text/javascript;base64,'+Buffer.from(source.replace("from 'three'",`from '${moduleUrl}'`)).toString('base64'));
let loaded;
const originalLoad=THREE.TextureLoader.prototype.load;
THREE.TextureLoader.prototype.load=function(url,onLoad){loaded=onLoad;};
try {
  const root=new THREE.Group(),building=new THREE.Group();building.name='Building_499434918';root.add(building);
  const roadMaterial=new THREE.MeshStandardMaterial({color:0x70767b});roadMaterial.name='V3_Road_Graphite';const road=new THREE.Mesh(new THREE.PlaneGeometry(),roadMaterial);root.add(road);
  const material=new THREE.MeshStandardMaterial({color:0xffffff}),geometry=new THREE.BoxGeometry(10,20,30),mesh=new THREE.Mesh(geometry,material);building.add(mesh);
  const second=new THREE.Mesh(geometry,[material,material]);building.add(second);const originalArray=second.material;
  const vertices=geometry.attributes.position.array.slice(),matrix=mesh.matrix.clone();
  assert.equal(buildingId(mesh),'499434918');
  const notices=[],art=createArtLayer(root,s=>notices.push(s));
  loaded(new THREE.Texture());assert.deepEqual(notices,['texture-ready']);
  art.setMode(true,new Set(),null);assert.notEqual(mesh.material,material);assert.equal(mesh.geometry,geometry);
  assert.equal(road.material.color.getHex(),roadMaterial.color.getHex());
  assert.deepEqual(geometry.attributes.position.array,vertices);assert.deepEqual(mesh.matrix,matrix);
  const shader={uniforms:{},vertexShader:'#include <project_vertex>',fragmentShader:'#include <map_fragment>'};
  mesh.material.onBeforeCompile(shader);assert.equal(shader.uniforms.paperAmount.value,.32);
  art.setMode(false,new Set(['499434918']),null);assert.equal(shader.uniforms.paperAmount.value,0);
  assert.equal(material.color.getHex(),0xffffff);
  art.setMode(false,new Set(),null);assert.equal(mesh.material,material);
  assert.deepEqual(second.material,originalArray);assert.equal(second.material[0],material);
  art.setMode(true,new Set(),'499434918');art.dispose();assert.equal(mesh.material,material);
  const late=createArtLayer(root,()=>assert.fail('Disposed layer must not emit ready'));
  const texture=new THREE.Texture();let disposed=false;texture.addEventListener('dispose',()=>disposed=true);
  late.dispose();loaded(texture);assert.equal(disposed,true);
  geometry.dispose();material.dispose();
  console.log('explore-materials: material restoration, geometry preservation and road color passed');
} finally {THREE.TextureLoader.prototype.load=originalLoad;}
