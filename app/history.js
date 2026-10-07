// Storage is deliberately separate from UI and never holds API credentials.
export async function openHistory(){
  return new Promise((resolve,reject)=>{const request=indexedDB.open('bnu-companion-v1',1);request.onupgradeneeded=()=>request.result.createObjectStore('conversations',{keyPath:'id'});request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
}
export function saveConversation(db,conversation){return new Promise((resolve,reject)=>{const tx=db.transaction('conversations','readwrite');tx.objectStore('conversations').put(structuredClone(conversation));tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);});}
export function listConversations(db){return new Promise((resolve,reject)=>{const r=db.transaction('conversations').objectStore('conversations').getAll();r.onsuccess=()=>resolve(r.result.sort((a,b)=>b.updated_at.localeCompare(a.updated_at)));r.onerror=()=>reject(r.error);});}
