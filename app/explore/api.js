import {errorInfo} from '/presentation.js';
export async function request(path,body,signal){try{const r=await fetch(path,{...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-BNU-Client':'1'},body:JSON.stringify(body)}),signal});const value=await r.json();if(!r.ok)throw Object.assign(Error(value.error||'服务暂不可用'),value);return value;}catch(e){throw Object.assign(Error(errorInfo(e).message),errorInfo(e));}}
export async function chatStream(payload,signal,onEvent){
  const response=await fetch('/api/agent/chat',{method:'POST',headers:{'Content-Type':'application/json','X-BNU-Client':'1'},body:JSON.stringify(payload),signal});
  if(!response.ok){const e=await response.json();throw Object.assign(Error(e.error||'请求失败'),e);}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',final=false;
  const consume=line=>{if(!line.trim())return;const e=JSON.parse(line);if(e.type==='error'||e.type==='result')final=true;onEvent(e);};
  try{while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let i;while((i=buffer.indexOf('\n'))>=0){consume(buffer.slice(0,i));buffer=buffer.slice(i+1);}if(done)break;}if(buffer.trim())consume(buffer);if(!final)throw Error('连接已中断，未收到完成结果；请重试。');}finally{reader.releaseLock();}
}
