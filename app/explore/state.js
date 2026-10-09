export const GROUPS=[['','建筑','BUILDINGS'],['eating','吃喝','DINING'],['retail','购物','SHOPS'],['sports','运动','SPORT'],['services','服务','SERVICES'],['campus','校园','CAMPUS'],['all','全部','ALL']];
export function shouldRoam(requested,reduced,hidden,tweening){return requested&&!reduced&&!hidden&&!tweening;}
export function displayPoint(p){return p.display_anchor||p.location||null;}
export function inModel(p){const q=displayPoint(p);return !!q&&Number.isFinite(q.x)&&Number.isFinite(q.y)&&Math.abs(q.x)<=452&&Math.abs(q.y)<=601;}
// Exact, display-only correction. Never change the source category or location.
export function normalizePlace(p){return p.id==='baidu-9d9d7030bb7bcc77e0110373'?{...p,display_category:'drinks',category_label:'咖啡饮品',collection_label:'饮品'}:p;}
export function matchesCategory(p,category){return !category||category==='all'||(category==='eating'?['food','drinks'].includes(p.display_category):p.display_category===category);}
// These exact-ID aliases already belong to backend/life_relations.py's public
// identity projection. The older directory DTO omits aliases, so only search
// gains a compatibility lookup; source names, parents and coordinates stay put.
const DIRECTORY_ALIASES={'canteen-3':['新三','学三','新乐群三层'],'canteen-4':['新四','学四','新乐群四层']};
export function placeSearchText(p){const aliases=Array.isArray(p.aliases)?p.aliases.filter(value=>typeof value==='string'):[],known=Object.hasOwn(DIRECTORY_ALIASES,p.id)?DIRECTORY_ALIASES[p.id]:[];return [p.name,p.address,p.spatial_sequence?.label,...aliases,...known].filter(value=>typeof value==='string').join(' ').toLowerCase();}
export function filterPlaces(rows,category='',query=''){const q=query.trim().toLowerCase();return rows.filter(p=>matchesCategory(p,category)&&(!q||placeSearchText(p).includes(q)));}
export function positionNote(p){return p.display_anchor?'楼栋定位 · 入口待补':p.map_reference?'参照区域 · 具体楼栋待确认':!p.location?(p.spatial_sequence?'已知区域 · 具体位置待细化':'位置待补'):!inModel(p)?'模型范围外':'已有点位 · 入口未复测';}
export function reduceState(state,event){switch(event.type){case 'category':return {...state,category:event.value,panel:'list',query:'',area:'',kind:'',limit:40,selected:null};case 'panel':return {...state,panel:event.value};case 'select':return {...state,selected:event.id,panel:'detail'};case 'close':return {...state,panel:null};default:return state;}}
export function directorySelection(rows,state){return filterPlaces(rows,state.category,state.query).filter(p=>(!state.kind||p.display_category===state.kind)&&(!state.area||p.spatial_sequence?.group===state.area)).sort((a,b)=>state.area?(a.spatial_sequence?.order??999)-(b.spatial_sequence?.order??999):Number(!!b.spatial_sequence)-Number(!!a.spatial_sequence)||Number(inModel(b))-Number(inModel(a))||a.name.localeCompare(b.name,'zh-CN'));}
export function pagePlaces(rows,limit=40){return {items:rows.slice(0,Math.max(40,limit)),remaining:Math.max(0,rows.length-Math.max(40,limit))};}
export function areaGroups(rows){const groups=new Map();for(const row of rows){const s=row.spatial_sequence;if(!s)continue;if(!groups.has(s.group))groups.set(s.group,{id:s.group,label:s.label,rows:[]});groups.get(s.group).rows.push(row);}return [...groups.values()].map(g=>({...g,rows:g.rows.sort((a,b)=>(a.spatial_sequence.order??999)-(b.spatial_sequence.order??999))}));}
// Aggregate only confirmed building IDs, never a map_reference building ID.
export function markerGroups(rows,ids){if(!ids)return [];const groups=new Map();for(const row of rows.filter(r=>ids.has(r.id))){const key=row.building_id!=null?'building:'+row.building_id:'poi:'+row.id;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}return [...groups.values()].filter(rs=>rs.some(inModel)).map(rs=>({row:rs.find(inModel),ids:rs.map(r=>r.id)}));}
export function selectionIds(cards,rows){const valid=new Set(rows.map(r=>r.id));return [...new Set(cards.map(c=>c.poi_id||c.id).filter(id=>valid.has(id)))];}
export function easeCamera(t){return 1-Math.pow(1-Math.max(0,Math.min(1,t)),3);}

// Screen-space layout only. No world coordinate or building geometry is changed.
export function cameraSafeArea(width,height,occlusions=[],padding=12){
  const w=Number.isFinite(width)&&width>0?width:1,h=Number.isFinite(height)&&height>0?height:1;
  const gap=Number.isFinite(padding)?Math.max(0,Math.min(padding,w/4,h/4)):12;
  const frame={left:gap,top:gap,right:w-gap,bottom:h-gap};
  const blocked=(Array.isArray(occlusions)?occlusions:[]).filter(r=>r&&['left','top','right','bottom'].every(k=>Number.isFinite(r[k]))&&r.right>r.left&&r.bottom>r.top).map(r=>({
    left:Math.max(frame.left,r.left-gap),right:Math.min(frame.right,r.right+gap),
    top:Math.max(frame.top,r.top-gap),bottom:Math.min(frame.bottom,r.bottom+gap)
  })).filter(r=>r.left<r.right&&r.top<r.bottom);
  const xs=[...new Set([frame.left,frame.right,...blocked.flatMap(r=>[r.left,r.right])])].sort((a,b)=>a-b);
  let best=null,bestArea=-1,bestCenter=Infinity;
  function consider(left,right,top,bottom){
    if(right<=left||bottom<=top)return;
    const area=(right-left)*(bottom-top),center=Math.hypot((left+right-w)/2,(top+bottom-h)/2);
    if(area>bestArea||(area===bestArea&&center<bestCenter)){best={left,top,right,bottom};bestArea=area;bestCenter=center;}
  }
  // For each pair of X boundaries, merge occupied Y intervals. The largest
  // empty rectangle must end at a viewport or obstacle edge.
  for(let i=0;i<xs.length-1;i++)for(let j=i+1;j<xs.length;j++){
    const left=xs[i],right=xs[j],ys=blocked.filter(r=>r.left<right&&r.right>left).sort((a,b)=>a.top-b.top);
    let top=frame.top;
    for(const r of ys){consider(left,right,top,r.top);top=Math.max(top,r.bottom);}
    consider(left,right,top,frame.bottom);
  }
  const available=!!best,rect=best||frame;
  return {...rect,width:rect.right-rect.left,height:rect.bottom-rect.top,centerX:(rect.left+rect.right)/2,centerY:(rect.top+rect.bottom)/2,available};
}

export function cameraViewOffset(width,height,safe){
  return {x:width/2-safe.centerX,y:height/2-safe.centerY};
}

export function cameraFitDistance(size,fov,width,height,safe,{padding=1.16,min=90,max=1900}={}){
  const radius=Math.hypot(...['x','y','z'].map(k=>Math.max(0,Number.isFinite(size?.[k])?size[k]:0)))/2;
  const fullHeight=Math.max(1,height),fullWidth=Math.max(1,width),vertical=Math.tan(Math.max(1,Math.min(120,fov))*Math.PI/360);
  const usableWidth=safe?.available?Math.max(1,Math.min(fullWidth,safe.width)):fullWidth;
  const usableHeight=safe?.available?Math.max(1,Math.min(fullHeight,safe.height)):fullHeight;
  const angle=Math.min(Math.atan(vertical*usableHeight/fullHeight),Math.atan(vertical*usableWidth/fullHeight));
  return Math.max(min,Math.min(max,radius*Math.max(1,padding)/Math.sin(angle)));
}

// Keep a stable azimuth when coming from a nearly vertical overview. Looking
// directly down gives no reliable heading and can otherwise flip the camera.
export function stableCameraDirection(delta,fallback={x:.6,y:1,z:1}){
  const valid=v=>v&&['x','y','z'].every(k=>Number.isFinite(v[k]));
  const safeFallback=valid(fallback)&&Math.hypot(fallback.x,fallback.z)>1e-6?fallback:{x:.6,y:1,z:1};
  const d=valid(delta)?delta:safeFallback,horizontal=Math.hypot(d.x,d.z),length=Math.hypot(horizontal,d.y);
  const bearing=horizontal>length*.04&&horizontal>1e-6?d:safeFallback;
  const bearingLength=Math.hypot(bearing.x,bearing.z);
  const angle=Math.max(Math.PI*32/180,Math.min(Math.PI*62/180,Math.atan2(Math.max(0,d.y),horizontal)));
  return {x:bearing.x/bearingLength*Math.cos(angle),y:Math.sin(angle),z:bearing.z/bearingLength*Math.cos(angle)};
}
