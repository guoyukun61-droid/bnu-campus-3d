// Shared by public map and authenticated review map; no private evidence.
export const mapPosition = row => row.display_anchor || row.location;
export function mountSpatialList(rows, select, toolbar) {
  const css=document.createElement('link');css.rel='stylesheet';css.href='/map/locations.css';document.head.append(css);
  const node=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
  const panel=document.createElement('aside');panel.id='spatial-list';panel.setAttribute('aria-label','已确认店铺分布');
  const title=node('h2','店铺分布');const close=node('button','收起');close.setAttribute('aria-label','收起店铺分布');
  close.onclick=()=>panel.hidden=true;title.append(close);panel.append(title);
  panel.append(node('p','北 → 南为各组内部顺序，不代表门店间距。紫色标记仅定位已确认楼栋；楼层见文字。'));
  const groups=new Map();for(const row of rows){const s=row.spatial_sequence;if(!s)continue;if(!groups.has(s.group))groups.set(s.group,[]);groups.get(s.group).push(row);}
  for(const group of ['luckin-branches','snack-main','north-services','south-second','xuewu-side','northwest-west','tmall-services']){
    const items=groups.get(group);if(!items)continue;
    items.sort((a,b)=>(a.spatial_sequence.order??999)-(b.spatial_sequence.order??999));
    const details=document.createElement('details');details.open=['luckin-branches','snack-main'].includes(group);
    details.append(node('summary',items[0].spatial_sequence.label+' · '+items.length));
    for(const row of items){const order=row.spatial_sequence.order;const b=node('button',
      `${row.spatial_sequence.direction==='north_to_south'&&order!=null?order+'. ':''}${row.name}${row.floor?' · '+row.floor+'层':''}`);
      const hint=row.display_anchor?'定位楼栋（非入口）':row.map_reference?'查看参照楼 · 店铺在其西侧':row.location?'原有点位 · 顺序已记录':'顺序已记录 · 入口待点选';
      b.append(node('small',hint));b.onclick=()=>{panel.querySelectorAll('[aria-pressed]').forEach(x=>x.setAttribute('aria-pressed','false'));b.setAttribute('aria-pressed','true');select(row);};b.setAttribute('aria-pressed','false');details.append(b);
    }panel.append(details);
  }
  const toggle=node('button','店铺分布 · 北→南');toggle.onclick=()=>panel.hidden=!panel.hidden;toolbar.append(toggle);document.body.append(panel);
  if(innerWidth<640)panel.hidden=true;
  return panel;
}
