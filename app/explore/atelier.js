import * as THREE from 'three';

// Presentation only. IDs, coordinates and geometry remain owned by the catalog/GLB.
// Window rhythm is illustrative, NOT surveyed facade or shop entrance evidence.
export const ATELIER_SAMPLES = Object.freeze({
  '499434918': {label:'新乐群', floors:4, height:13, wall:'#d6bd9c', roof:'#858390'},
  '499437078': {label:'学五片区西北体块', floors:2, height:8, wall:'#e1d7bc', roof:'#7b8790'},
  '499437130': {label:'学五片区西南体块', floors:2, height:8, wall:'#dbc7ad', roof:'#7b8790'},
  '681441380': {label:'学五片区连接体块', floors:2, height:8, wall:'#dfd5bb', roof:'#7b8790'},
});
export const ATELIER_TEXTURE = '/explore/art/atelier-plaster-v1.png';

const VARYINGS = 'varying vec3 vAtPosition;\nvarying vec3 vAtNormal;\n';
const FRAGMENT_HEADER = `${VARYINGS}
uniform sampler2D atPaper;
uniform float atReady;
uniform float atKind;
uniform float atFloors;
uniform float atHeight;
uniform vec3 atOrigin;
uniform vec3 atRoof;
float atRect(vec2 uv, vec2 halfSize) {
  vec2 d = abs(uv-.5)-halfSize;
  vec2 aa = max(fwidth(uv), vec2(.004));
  return (1.-smoothstep(-aa.x,aa.x,d.x))*(1.-smoothstep(-aa.y,aa.y,d.y));
}
`;
const FRAGMENT_SURFACE = `
vec3 an = abs(normalize(vAtNormal));
float roofFace = smoothstep(.65,.90,an.y);
float ap = sin(vAtPosition.x*.19+sin(vAtPosition.z*.14))*sin(vAtPosition.z*.23);
if (atKind < 1.5) {
  // Triplanar material coordinates in world metres: no stretched UVs or roof windows.
  vec3 weights = pow(an,vec3(5.)); weights /= max(dot(weights,vec3(1.)),.001);
  vec3 paper = texture2D(atPaper,vAtPosition.zy*.14).rgb*weights.x
             + texture2D(atPaper,vAtPosition.xz*.14).rgb*weights.y
             + texture2D(atPaper,vAtPosition.xy*.14).rgb*weights.z;
  diffuseColor.rgb *= mix(vec3(1.),mix(vec3(.88),paper, .27), atReady);
  diffuseColor.rgb = mix(diffuseColor.rgb,atRoof,roofFace*.88);
  float h = vAtPosition.y-atOrigin.y;
  diffuseColor.rgb *= mix(.79,1.,smoothstep(0.,1.7,h));
  if(atFloors > 0.) {
    float along = an.z>an.x ? vAtPosition.x-atOrigin.x : vAtPosition.z-atOrigin.z;
    float fh = atHeight/atFloors;
    vec2 cell = vec2(fract(along/3.2),fract(h/fh));
    float walls = (1.-roofFace)*step(.15,h)*(1.-step(atHeight-.2,h));
    float frame = atRect(cell,vec2(.34,.305))*walls;
    float glass = atRect(cell,vec2(.285,.25))*walls;
    float division = 1.-smoothstep(.012,.026,abs(cell.x-.5));
    vec3 glazing = mix(vec3(.10,.20,.24),vec3(.23,.36,.39),cell.y);
    glazing += vec3(.022)*sin(along*1.8);
    diffuseColor.rgb = mix(diffuseColor.rgb,vec3(.63,.65,.58),frame);
    diffuseColor.rgb = mix(diffuseColor.rgb,glazing,glass*(1.-division*.82));
    float sill = (1.-smoothstep(.012,.037,abs(cell.y-.17)))*walls;
    diffuseColor.rgb = mix(diffuseColor.rgb,vec3(.40,.41,.35),sill*.55);
  }
} else if(atKind < 2.5) {
  // Existing tree geometry only; no invented planting locations.
  diffuseColor.rgb *= .91+ap*.10+clamp(vAtPosition.y*.015,0.,.15);
} else if(atKind < 3.5) {
  diffuseColor.rgb *= .96+ap*.025;
}
`;

export function createAtelierLayer(model, identify, notice=()=>{}) {
  let disposed=false, ready=false;
  // Complete neutral fallback is valid before the asynchronous image arrives.
  let texture=new THREE.DataTexture(new Uint8Array([255,255,255,255]),1,1);
  texture.needsUpdate=true;
  const entries=[];
  model.updateMatrixWorld(true);
  const sampleBounds=new Map();
  for(const id of Object.keys(ATELIER_SAMPLES)) {
    const object=model.getObjectByName('Building_'+id);
    if(object)sampleBounds.set(id,new THREE.Box3().setFromObject(object));
  }
  model.traverse(mesh=>{
    if(!mesh.isMesh)return;
    const id=identify(mesh),sample=ATELIER_SAMPLES[id];
    const original=mesh.material, originals=Array.isArray(original)?original:[original];
    const uniforms=[];
    const copies=originals.map(source=>{
      const m=source.clone(),name=source.name||'';
      const kind=id?1:name.includes('Tree')?2:3;
      const base=id?(sample?.wall||'#d4d0bf'):name.includes('Tree')?'#557b53':name.includes('Ground')?'#aaba8e':name.includes('Road')?'#69747a':name.includes('Turf')?'#85985e':name.includes('Track')?'#b98165':null;
      if(base)m.color.set(base);
      m.roughness=.93;m.metalness=0;
      const u={atPaper:{value:texture},atReady:{value:0},atKind:{value:kind},
        atFloors:{value:sample?.floors||0},atHeight:{value:sample?.height||1},
        atOrigin:{value:sampleBounds.get(id)?.min.clone()||new THREE.Vector3()},
        atRoof:{value:new THREE.Color(sample?.roof||'#abaeaa')}};
      uniforms.push(u);
      m.onBeforeCompile=shader=>{
        Object.assign(shader.uniforms,u);
        shader.vertexShader=VARYINGS+shader.vertexShader;
        shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>',
          '#include <project_vertex>\nvAtPosition = (modelMatrix * vec4(transformed,1.)).xyz;\nvAtNormal = normalize(mat3(modelMatrix) * normal);');
        shader.fragmentShader=FRAGMENT_HEADER+shader.fragmentShader;
        shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>','#include <map_fragment>\n'+FRAGMENT_SURFACE);
      };
      m.customProgramCacheKey=()=> 'campus-atelier-v1';
      return {material:m,base:m.color.clone()};
    });
    entries.push({mesh,id,original,copies,uniforms,cast:mesh.castShadow,receive:mesh.receiveShadow});
  });
  new THREE.TextureLoader().load(ATELIER_TEXTURE,loaded=>{
    if(disposed){loaded.dispose();return;}
    texture.dispose();texture=loaded;texture.wrapS=texture.wrapT=THREE.RepeatWrapping;
    texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=4;ready=true;
    for(const e of entries)for(const u of e.uniforms){u.atPaper.value=texture;u.atReady.value=1;}
    notice('atelier-ready');
  },undefined,()=>{if(!disposed)notice('atelier-fallback');});
  return {
    get ready(){return ready;},
    apply(enabled,highlights=new Set(),selected=null){
      for(const e of entries){
        e.mesh.castShadow=enabled?!!e.id:e.cast;
        e.mesh.receiveShadow=enabled?true:e.receive;
        if(!enabled)continue; // Caller has already reapplied baseline/white materials.
        for(const c of e.copies){c.material.color.copy(c.base);
          if(e.id&&(e.id===selected||highlights.has(e.id)))c.material.color.lerp(new THREE.Color(e.id===selected?'#cf9c60':'#b5c793'),.38);
        }
        e.mesh.material=Array.isArray(e.original)?e.copies.map(c=>c.material):e.copies[0].material;
      }
    },
    dispose(){disposed=true;for(const e of entries){
      const active=Array.isArray(e.mesh.material)?e.mesh.material:[e.mesh.material];
      if(active.some(m=>e.copies.some(c=>c.material===m)))e.mesh.material=e.original;
      e.mesh.castShadow=e.cast;e.mesh.receiveShadow=e.receive;e.copies.forEach(c=>c.material.dispose());
    }texture.dispose();}
  };
}
