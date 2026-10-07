/* External names and API values are always rendered as text, never HTML. */
(() => {
  'use strict';
  const panel=document.createElement('section');panel.className='life-panel';panel.setAttribute('aria-label','校园生活推荐');
  panel.innerHTML=[
    '<h2>今天中午吃什么？</h2><div class="life-caption">京师智行 · 1.2.0<br>用预算、口味与课表比较校园选择。来源逐项标注，排队仍为模拟。</div>',
    '<form id="life-form" class="life-form">',
    '<label>当前地点<select id="life-location"></select></label>',
    '<label>硬预算 / 元<input id="life-budget" type="number" min="0" max="10000" value="20" required></label>',
    '<label>口味<select id="life-taste"><option value="辣">想吃辣</option><option value="">不限</option><option value="清淡">清淡</option></select></label>',
    '<label>不想吃<select id="life-avoid"><option value="">不限</option><option value="米饭">米饭</option><option value="鸡肉">鸡肉</option><option value="牛肉">牛肉</option></select></label>',
    '<label>最多排队 / 分钟<input id="life-queue" type="number" min="0" max="180" value="10" required></label>',
    '<label>可用时间 / 分钟<input id="life-minutes" type="number" min="1" max="1440" value="105" required></label>',
    '<label>演示日期<input id="life-date" type="date" required></label>',
    '<label>当前时间<input id="life-time" type="time" value="11:45" required></label>',
    '<label>下一节课<input id="life-next-time" type="time" value="13:30" required></label>',
    '<label>下一课堂<select id="life-next-location"></select></label>',
    '<label>数据模式<select id="life-mode"><option value="demo">演示（含模拟数据）</option><option value="verified">仅已核验真实数据</option></select></label>',
    '<label>位置范围<select id="life-mapped"><option value="true">仅已有坐标的地点</option><option value="false">含位置待核（模拟步行）</option></select></label>',
    '<label>虚构用户<select id="life-user"><option value="demo-student-1">模拟学生 1</option><option value="demo-student-2">模拟学生 2</option></select></label>',
    '<button type="button" id="life-schedule">填入模拟课表</button><button class="primary" type="submit">推荐 Top 3</button></form>',
    '<p id="life-status" class="life-message" role="status" aria-live="polite"></p><div id="life-results"></div>',
    '<details open><summary>店铺名录与数据缺口</summary><input id="life-search" placeholder="搜索食堂、店铺或地址" aria-label="搜索生活店铺">',
    '<p id="life-coverage" class="life-message"></p><div id="life-directory" class="life-directory"></div></details>',
    '<details><summary>图书馆模拟预约</summary><p class="life-caption">仅在本机保存虚构预约，不会占用学校座位。日期与用户沿用上方表单。</p>',
    '<div class="life-form"><label>开始<input type="time" id="library-start" value="16:00"></label><label>结束<input type="time" id="library-end" value="17:00"></label>',
    '<button type="button" id="library-query" class="span-two">查询模拟座位</button></div><p id="library-status" class="life-message" role="status"></p>',
    '<div id="library-slots"></div><div id="library-reservations"></div></details>'
  ].join('');
  const model=document.getElementById('model');
  const layout=document.createElement('main');layout.className='life-layout';model.before(layout);layout.append(panel,model);
  document.title='京师智行 · 校园生活推荐';
  const $=id=>document.getElementById(id),iso=time=>$('life-date').value+'T'+time+':00+08:00';
  $('life-date').value=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  let pois=[],latest=[],libraryRequest=null;
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  function status(id,text,error=false){$(id).textContent=text;$(id).classList.toggle('error',error);}
  async function api(path,data){
    const response=await fetch('/api/life'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const body=await response.json();if(!response.ok)throw new Error(body.error||'HTTP '+response.status);return body;
  }
  function message(data){model.contentWindow.postMessage(data,location.origin);}
  function mapRecommendations(){message({type:'life-recommendations',records:latest.filter(r=>r.location&&r.building_id!=null&&r.zone!=='nearby')});}
  addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==model.contentWindow)return;
    if(event.data?.type==='campus-ready')mapRecommendations();
    if(event.data?.type==='campus-building-selected'){
      const card=[...$('life-results').children].find(c=>c.dataset.buildingId===String(event.data.building_id));
      if(card){card.scrollIntoView({block:'nearest'});card.focus({preventScroll:true});}
    }
  });
  function card(row){
    const box=el('article',undefined,'life-card');box.tabIndex=-1;box.dataset.buildingId=String(row.building_id);
    box.append(el('span',(row.sources.item==='simulated'?'演示商品':'真实来源商品')+' · '+(row.sources.queue==='simulated'?'模拟排队':'观测排队'),'badge'),el('h3',row.rank+'. '+row.poi),el('div',row.item,'dish'),
      el('span','餐品示意 · 暂无实物照片','placeholder'),
      el('div','¥'+row.price+'　步行约 '+row.walking_minutes+' 分钟　排队 '+row.queue_minutes+' 分钟','metrics'),
      el('div','总用时约 '+row.total_estimated_minutes+' 分钟 · '+row.shop,'metrics'));
    const reasons=el('ul');row.reason.forEach(reason=>reasons.append(el('li',reason)));box.append(reasons);
    box.append(el('small','价格：'+(row.sources.price==='simulated'?'模拟':'来源记录')+'；步行：'+(row.sources.walking==='simulated'?'模拟，位置待核':'距离估算')+'；营业时间：'+(row.sources.opening_hours==='simulated'?'模拟':'资料记录，当前状态待核')+'。'));
    const evidence=row.field_evidence?.item?.price;
    if(evidence)box.append(el('small','价格观察时间：'+evidence.observed_at+' · '+evidence.evidence));
    box.append(el('small','地址：'+(row.address||'待补')+' · 场所来源：'+row.sources.poi));
    if(row.building_id!=null&&row.location&&row.zone!=='nearby'){
      const button=el('button','在白模中查看');button.type='button';button.onclick=()=>message({type:'life-focus',building_id:row.building_id});box.append(button);
    }else box.append(el('small','独立地点 / 白模暂无可靠关联'));
    return box;
  }
  $('life-form').onsubmit=async event=>{
    event.preventDefault();const button=$('life-form').querySelector('[type=submit]');button.disabled=true;
    status('life-status','正在比较候选…');$('life-results').replaceChildren();latest=[];mapRecommendations();
    try{
      const data=await api('/recommendations',{current_location:$('life-location').value,current_time:iso($('life-time').value),
        budget:Number($('life-budget').value),max_queue_minutes:Number($('life-queue').value),available_minutes:Number($('life-minutes').value),
        taste:[$('life-taste').value].filter(Boolean),avoid:[$('life-avoid').value].filter(Boolean),mode:$('life-mode').value,mapped_only:$('life-mapped').value==='true',
        next_class:{time:iso($('life-next-time').value),location:$('life-next-location').value}});
      latest=data.recommendations;latest.forEach(row=>$('life-results').append(card(row)));mapRecommendations();
      const rejected=Object.entries(data.rejected).map(([reason,count])=>reason+' '+count+' 项').join('；');
      status('life-status',(latest.length?'找到 '+latest.length+' 个选择。':'没有符合全部条件的选择。')+data.notice+'\n筛除：'+(rejected||'无'));
    }catch(error){status('life-status',error.message,true);}finally{button.disabled=false;}
  };
  $('life-schedule').onclick=async()=>{
    try{
      const data=await api('/schedule?user_id='+encodeURIComponent($('life-user').value)+'&date='+$('life-date').value);
      const at=new Date(iso($('life-time').value)),next=data.records.find(r=>new Date(r.start)>at);
      if(!next){status('life-status','模拟课表当天没有下一节课，请手动填写。');return;}
      $('life-next-time').value=next.start.slice(11,16);$('life-next-location').value=next.location;
      $('life-minutes').value=Math.floor((new Date(next.start)-at)/60000);
      status('life-status','已填入模拟课表：'+next.name+'，'+next.start.slice(11,16)+'，'+next.location+'。');
    }catch(error){status('life-status',error.message,true);}
  };
  function directory(){
    $('life-directory').replaceChildren();const query=$('life-search').value.trim().toLowerCase();
    for(const p of pois.filter(p=>(p.name+' '+p.address).toLowerCase().includes(query))){
      const row=el('div',undefined,'life-row');row.append(el('strong',p.name),
        el('small',(p.address||'地址待补')+' · '+(p.status==='historical'?'历史记录':p.status==='archived'?'已归档':'当前营业待核')+' · '+(p.location?'位置有记录':'坐标待补')),
        el('small','来源：'+p.source));$('life-directory').append(row);
    }
  }
  $('life-search').oninput=directory;
  async function reservations(){
    const data=await api('/library/reservations?user_id='+$('life-user').value);
    $('library-reservations').replaceChildren(el('h3','我的模拟预约'));
    data.records.forEach(r=>{
      const row=el('div',r.seat_id+' · '+r.start.slice(0,16)+' — '+r.end.slice(11,16)+' · '+(r.status==='active'?'有效':'已取消'),'life-row');
      if(r.status==='active'){
        const button=el('button','取消模拟预约');button.type='button';
        button.onclick=async()=>{button.disabled=true;try{await api('/library/reservations/'+r.id+'/cancel',{user_id:$('life-user').value});await loadSlots();status('library-status','模拟预约已取消。');}catch(error){status('library-status',error.message,true);button.disabled=false;}};
        row.append(button);
      }$('library-reservations').append(row);
    });
  }
  async function loadSlots(){
    const start=iso($('library-start').value),end=iso($('library-end').value);
    const data=await api('/library/slots?start='+encodeURIComponent(start)+'&end='+encodeURIComponent(end));
    $('library-slots').replaceChildren();
    data.records.forEach(slot=>{
      const row=el('div',slot.id+' · '+(slot.available?'模拟可用':'模拟已占用')+' ','life-row');
      if(slot.available){
        const button=el('button','模拟预约');button.type='button';
        button.onclick=async()=>{
          button.disabled=true;const body={seat_id:slot.id,user_id:$('life-user').value,start,end},fingerprint=JSON.stringify(body);
          if(!libraryRequest||libraryRequest.fingerprint!==fingerprint)libraryRequest={fingerprint,id:crypto.randomUUID()};
          try{await api('/library/reservations',{...body,request_id:libraryRequest.id});libraryRequest=null;await loadSlots();status('library-status','本地模拟预约成功，未向学校系统提交。');}
          catch(error){status('library-status',error.message,true);button.disabled=false;}
        };row.append(button);
      }$('library-slots').append(row);
    });await reservations();
  }
  $('library-query').onclick=()=>loadSlots().catch(error=>status('library-status',error.message,true));
  $('life-user').onchange=()=>{libraryRequest=null;$('library-slots').replaceChildren();reservations().catch(error=>status('library-status',error.message,true));};
  for(const id of ['life-date','library-start','library-end']) $(id).addEventListener('change',()=>{$('library-slots').replaceChildren();libraryRequest=null;status('library-status','时段已变化，请重新查询模拟座位。');});
  async function initialize(){
    try{
      const [locations,catalog,coverage]=await Promise.all([api('/locations'),api('/pois'),api('/coverage')]);
      for(const id of ['life-location','life-next-location'])for(const p of locations.records){const option=el('option',p.name);option.value=p.id;$(id).append(option);}
      $('life-next-location').value='教九';pois=catalog.records;directory();
      status('life-coverage','名录 '+coverage.known_venues+' 条 · 模拟菜品 '+coverage.simulated_items+' 条。\n百度任务 '+coverage.completed_tasks+'/'+coverage.total_leaf_tasks+' 完成；'+(coverage.collection_status==='blocked_missing_key'?'缺少运行时密钥，尚未执行新采集':(coverage.collection_notice||coverage.collection_status))+'。\n'+coverage.missing_coordinates.length+' 条缺坐标，'+coverage.pending_duplicates.length+' 组疑似重复待核。现实全店覆盖尚未确认。');
      status('life-status','可先试：20元想吃辣、35分钟后上课、15元以内、不吃米饭。');
    }catch(error){status('life-status','数据服务不可用：'+error.message+'。请通过新版 campus_server.py 启动。',true);}
  }
  initialize();
})();
