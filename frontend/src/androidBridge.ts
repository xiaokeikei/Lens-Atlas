declare global {
  interface Window {
    LensAndroid?: {request:(id:number,action:string,payload:string)=>void};
    __lensReply?: (id:number,json:string)=>void;
    __lensBack?: ()=>boolean;
  }
}
let next=0;
const pending=new Map<number,{resolve:(value:any)=>void;reject:(error:Error)=>void;timer:ReturnType<typeof setTimeout>}>();
window.__lensReply=(id,json)=>{
  const promise=pending.get(id);if(!promise)return;
  pending.delete(id);clearTimeout(promise.timer);
  try{const reply=JSON.parse(json);if(reply.error)promise.reject(new Error(reply.error));else promise.resolve(reply.result);}catch{promise.reject(new Error('安卓接口响应无效'));}
};
export function native<T=any>(action:string,args:unknown={}):Promise<T>{
  return new Promise((resolve,reject)=>{
    if(!window.LensAndroid){reject(new Error('请在镜迹安卓 App 中打开'));return;}
    const id=++next;
    const timer=setTimeout(()=>{pending.delete(id);reject(new Error('请求超时，请重试'));},60000);
    pending.set(id,{resolve,reject,timer});
    try{window.LensAndroid.request(id,action,JSON.stringify(args));}catch(e){pending.delete(id);clearTimeout(timer);reject(e instanceof Error?e:new Error('安卓接口不可用'));}
  });
}
