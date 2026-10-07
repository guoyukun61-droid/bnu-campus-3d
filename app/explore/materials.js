import * as THREE from 'three';
export const SAMPLE_BUILDINGS=new Set(['499434918','499437078','172257586']);
export function buildingId(object){let o=object;while(o){const m=o.name?.match(/^Building_(\d+)(?:_|$)/);if(m)return m[1];o=o.parent;}return null;}
export function createArtLayer(model,notice){
  const entries=[];let illustration=false,texture=null,disposed=false;
  model.traverse(mesh=>{if(!mesh.isMesh)return;const originals=Array.isArray(mesh.material)?mesh.material:[mesh.material];
    const copies=originals.map(original=>{const m=original.clone();m.roughness=.94;return m;});
    entries.push({mesh,originals,copies,array:Array.isArray(mesh.material),id:buildingId(mesh)});
  });
  const installTexture=m=>{m.onBeforeCompile=shader=>{shader.uniforms.paperMap={value:texture};shader.uniforms.paperAmount={value:illustration?0.32:0};m.userData.paperShader=shader;
    shader.vertexShader='varying vec3 vPaperPosition;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <project_vertex>','#include <project_vertex>\nvPaperPosition = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader='uniform sampler2D paperMap;\nuniform float paperAmount;\nvarying vec3 vPaperPosition;\n'+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>','#include <map_fragment>\nvec2 paperUV = vec2(vPaperPosition.x + vPaperPosition.z, vPaperPosition.y + vPaperPosition.x * 0.13) * 0.11;\ndiffuseColor.rgb *= mix(vec3(1.0), texture2D(paperMap, paperUV).rgb, paperAmount);');};m.customProgramCacheKey=()=> 'campus-illustrative-paper-v1';m.needsUpdate=true;};
  const loader=new THREE.TextureLoader();loader.load('/explore/art/paper-plaster-v1.png',t=>{if(disposed){t.dispose();return;}texture=t;t.wrapS=t.wrapT=THREE.RepeatWrapping;t.colorSpace=THREE.SRGBColorSpace;t.anisotropy=2;
    for(const e of entries)if(SAMPLE_BUILDINGS.has(e.id))for(const m of e.copies)installTexture(m);notice('texture-ready');
  },undefined,()=>notice('texture-unavailable'));
  function refresh(highlights=new Set(),selected=null){for(const e of entries){e.copies.forEach((m,i)=>{
    const original=e.originals[i];m.color.copy(original.color);m.emissive?.copy(original.emissive||new THREE.Color(0));
    if(m.userData.paperShader)m.userData.paperShader.uniforms.paperAmount.value=illustration?0.32:0;
    if(illustration){const n=original.name||'';
      if(e.id)m.color.set(SAMPLE_BUILDINGS.has(e.id)?e.id==='499434918'?'#ccb591':e.id==='172257586'?'#b8c6b7':'#d5c4a1':'#dfdacc');
      else if(n.includes('Tree'))m.color.set('#527866');else if(n.includes('Ground'))m.color.set('#b6c4aa');else if(n.includes('Road'))m.color.copy(original.color);else if(n.includes('Turf'))m.color.set('#849e7c');else if(n.includes('Track'))m.color.set('#b98067');
    }
    const highlighted=e.id&&(e.id===selected||highlights.has(e.id));if(highlighted){m.color.lerp(new THREE.Color(e.id===selected?'#b58157':'#86a799'),e.id===selected ? 0.55 : 0.35);if(m.emissive)m.emissive.set(e.id===selected?'#1d1006':'#07130e');}
    // Use untouched original material when base mode is not highlighted.
  });e.mesh.material=(!illustration&&!highlights.has(e.id)&&e.id!==selected)?(e.array?e.originals:e.originals[0]):(e.array?e.copies:e.copies[0]);}}
  return {refresh,setMode(value,highlights,selected){illustration=value;refresh(highlights,selected);},dispose(){disposed=true;for(const e of entries){e.mesh.material=e.array?e.originals:e.originals[0];e.copies.forEach(m=>m.dispose());}texture?.dispose();}};
}
