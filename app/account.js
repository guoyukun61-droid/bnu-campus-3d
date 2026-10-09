import {request,setCSRF} from '/explore/api.js';
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
export function createAccountUI({onReset,onNotice}){
  let me=null,ready=false,dialog=null,timer=null,identityChanging=false;
  const channel=typeof BroadcastChannel!=='undefined'?new BroadcastChannel('bnu-account-session'):null;
  const reset=()=>{identityChanging=true;dialog?.close();dialog?.remove();onReset();location.reload();};
  if(channel)channel.onmessage=reset;
  window.addEventListener('account-expired',()=>{if(me?.user){me=null;setCSRF('');reset();}});
  const changed=()=>{channel?.postMessage('changed');reset();};
  const entry=el('button','登录 / 我的账号');entry.id='account-entry';entry.type='button';entry.onclick=()=>open();entry.hidden=true;
  document.querySelector('.header-actions').prepend(entry);
  const action=(text,fn)=>{const b=el('button',text);b.type='button';b.onclick=fn;return b;};
  const field=(form,label,type='text',value='')=>{const l=el('label',label),i=el('input');i.type=type;i.value=value;l.append(i);form.append(l);return i;};
  function shell(title,note){
    if(dialog){dialog.close();dialog.remove();}
    dialog=el('dialog');dialog.className='account-dialog';dialog.setAttribute('aria-label',title);
    const top=el('div');top.className='account-head';top.append(el('small','京师智行 / PERSONAL'),action('关闭',()=>dialog.close()));
    dialog.append(top,el('h2',title),el('p',note));document.body.append(dialog);dialog.showModal();return dialog;
  }
  function submit(form,label,run){
    const status=el('p');status.className='account-notice';status.setAttribute('role','status');
    const b=el('button',label);b.type='submit';b.className='account-primary';form.append(status,b);
    form.onsubmit=async e=>{e.preventDefault();b.disabled=true;status.textContent='正在保存…';try{await run(status);}catch(e){status.textContent=e.message||'暂未完成，请重试。';}finally{b.disabled=false;}};
  }
  async function refresh(){me=await request('/api/account/me');setCSRF(me.csrf);ready=true;entry.hidden=!me.enabled;document.body.dataset.accounts=String(!!me.enabled);entry.textContent=me.user?me.user+' · 账号':'登录';return me;}
  function open(){
    if(!ready){onNotice('账号状态尚未读取，请刷新页面后重试；地图仍可浏览。');return;}
    if(!me.enabled)return;
    if(!me.user){
      const d=shell('回到你的校园日常','五人内测 · 账号由管理员分配。地图无需登录；聊天按账号独立保存。');
      const f=el('form'),name=field(f,'账号'),pw=field(f,'密码','password');name.autocomplete='username';name.required=true;pw.autocomplete='current-password';pw.required=true;pw.maxLength=128;
      submit(f,'登录',async()=>{await request('/api/account/login',{name:name.value.trim(),password:pw.value});pw.value='';changed();});d.append(f);return;
    }
    if(me.must_change)return password(true);
    const d=shell(me.user+' 的个人空间','偏好只在你明确保存后生效。关闭后不再用于新请求；当前对话中明确提出的条件仍然保留。');
    const u=me.usage;d.append(el('p',`今日 ${u.used}/${u.limit} 轮 · 团队 ${u.team_used}/${u.team_limit} 轮（上海时间）`));
    const f=el('form'),pref=me.preferences,values=pref.values||{};
    const enabled=field(f,'启用我的长期偏好','checkbox');enabled.checked=!!pref.enabled;
    const budget=field(f,'默认预算上限（元，可留空）','number',values.budget??'');budget.min='1';budget.max='10000';budget.step='any';
    const taste=field(f,'口味（用逗号分隔）','text',(values.taste||[]).join('、'));
    const avoid=field(f,'忌口（用逗号分隔）','text',(values.avoid||[]).join('、'));
    taste.maxLength=410;avoid.maxLength=410;
    const list=s=>s.split(/[、,，]/).map(x=>x.trim()).filter(Boolean);
    submit(f,'保存个人偏好',async status=>{await request('/api/account/preferences',{version:pref.version,enabled:enabled.checked,values:{budget:budget.value?Number(budget.value):null,taste:list(taste.value),avoid:list(avoid.value)}});await refresh();status.textContent='已保存；本次问题里的要求优先于默认偏好。';open();});d.append(f);
    const row=el('div');row.className='account-actions';
    row.append(action('清空偏好',async()=>{if(!confirm('清空已保存的预算、口味和忌口？聊天记录不会删除。'))return;try{await request('/api/account/preferences',{version:me.preferences.version,enabled:false,values:{}});await refresh();open();}catch(e){onNotice(e.message);}}),action('修改密码',()=>password(false)),action('退出登录',async()=>{try{await request('/api/account/logout',{});changed();}catch(e){onNotice(e.message);}}));
    if(me.admin)row.append(action('管理账号',admin));d.append(row,el('small','对话保存在这台服务电脑。必要的近期消息与偏好会发送至配置的模型服务；请勿输入身份证、密码等敏感资料。'));
  }
  function password(first){
    const d=shell(first?'先设置自己的密码':'修改密码',first?'临时密码只用于首次登录。修改后，请用新密码重新登录。':'修改后，所有已登录设备都会失效。'),f=el('form');
    const old=field(f,first?'临时密码':'原密码','password'),pw=field(f,'新密码（12–128 字符）','password'),again=field(f,'再次输入新密码','password');
    old.autocomplete='current-password';pw.autocomplete=again.autocomplete='new-password';for(const p of [old,pw,again]){p.required=true;p.maxLength=128;}pw.minLength=again.minLength=12;
    submit(f,'修改并重新登录',async()=>{if(pw.value!==again.value)throw Error('两次输入的新密码不同。');await request('/api/account/password',{old:old.value,password:pw.value});changed();});d.append(f);
  }
  async function admin(){
    try{const data=await request('/api/account/admin/users');const d=shell('团队账号','这里只显示状态与用量，不提供他人的聊天或个人偏好。');for(const u of data.users){const row=el('div');row.className='account-user';row.append(el('strong',u.name),el('span',`${u.active?'启用':'停用'} · 今日 ${u.usage.used}/20`));if(u.name!=='g')row.append(action(u.active?'停用':'启用',async()=>{try{await request('/api/account/admin/status',{name:u.name,active:!u.active});admin();}catch(e){onNotice(e.message);}}));d.append(row);}d.append(el('p','忘记密码请在服务电脑运行 setup_accounts.py --reset 账号；不会删除原聊天。'));}catch(e){onNotice(e.message);}
  }
  return {
    get enabled(){return !ready||!!me?.enabled;},get user(){return me?.user;},
    async init(){try{await refresh();if(me?.enabled&&me?.user&&me.must_change)password(true);timer=setInterval(async()=>{try{const next=await request('/api/account/me');if(next.user!==me?.user){reset();return;}me=next;setCSRF(next.csrf);}catch{/* Offline is not logout. No history is overwritten. */}},30000);}catch{onNotice('账号状态未读取，个人对话暂不可用。请刷新重试；地图仍可用。');}window.addEventListener('pagehide',()=>{clearInterval(timer);channel?.close();},{once:true});},
    require(){if(!ready){open();return false;}if(!me.enabled)return true;if(!me.user||me.must_change){open();return false;}return true;},
    async history(){if(!me?.user||me.must_change||identityChanging)return [];const result=await request('/api/account/conversations');return identityChanging?[]:result.conversations;},
    async remove(id){await request('/api/account/conversations/delete',{id});},
    open
  };
}
