import {useEffect,useState,useRef} from 'react';
import type {Row} from './types';

export function navigate(to:string){history.pushState({},'',to);window.dispatchEvent(new PopStateEvent('popstate'));window.scrollTo(0,0);}
export function useLocation(){const [url,set]=useState(location.pathname+location.search);useEffect(()=>{const update=()=>set(location.pathname+location.search);addEventListener('popstate',update);return()=>removeEventListener('popstate',update)},[]);return url;}
export function updateQuery(values:Record<string,string>){const url=new URL(location.href);for(const [k,v] of Object.entries(values)){if(v)url.searchParams.set(k,v);else url.searchParams.delete(k)}navigate(url.pathname+url.search);}
export function Link({to,children,...props}:React.AnchorHTMLAttributes<HTMLAnchorElement>&{to:string}){return <a href={to} {...props} onClick={e=>{if(!e.ctrlKey&&!e.metaKey&&!e.shiftKey&&e.button===0){e.preventDefault();navigate(to)}}}>{children}</a>}
export const taskUrl=(r:Row)=>`/tasks/${encodeURIComponent(r.session_id)}/${encodeURIComponent(r.id)}`;
export const query=(q:Row)=>new URLSearchParams(Object.fromEntries(Object.entries(q).filter(([,v])=>v!==''&&v!=null).map(([k,v])=>[k,String(v)]))).toString();
export function useApi<T=Row>(url:string|null,revision=0){
  const [state,set]=useState<{data:T|null;error:string|null;loading:boolean}>({data:null,error:null,loading:true});
  useEffect(()=>{if(!url){set({data:null,error:null,loading:false});return}const controller=new AbortController();
    set(s=>({...s,loading:!s.data,error:null}));
    fetch(url,{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error(r.status===404?'This record is unavailable.':'The local service could not complete this request.');return r.json()})
      .then(data=>set({data,error:null,loading:false})).catch(e=>{if(e.name!=='AbortError')set(s=>({...s,error:e.message,loading:false}))});
    return()=>controller.abort();
  },[url,revision]);return state;
}
export function useLive(){
  const [revision,set]=useState(0),[connected,connect]=useState(false);
  useEffect(()=>{const stream=new EventSource('/api/events');let pending:ReturnType<typeof setTimeout>|undefined;
    stream.onopen=()=>{connect(true);set(r=>r+1)};stream.onerror=()=>connect(false);
    stream.addEventListener('invalidate',()=>{clearTimeout(pending);pending=setTimeout(()=>set(r=>r+1),250)});
    const retry=setInterval(()=>set(r=>r+1),30000);
    return()=>{stream.close();clearTimeout(pending);clearInterval(retry)};
  },[]);return {revision,connected,refresh:()=>set(r=>r+1)};
}
export function usePreference<T>(key:string,fallback:T){const [value,set]=useState<T>(()=>{try{return JSON.parse(localStorage.getItem(key)||'null')??fallback}catch{return fallback}});useEffect(()=>{localStorage.setItem(key,JSON.stringify(value))},[key,value]);return [value,set] as const;}
export function useClock(){const [now,set]=useState(Date.now());useEffect(()=>{const timer=setInterval(()=>set(Date.now()),1000);return()=>clearInterval(timer)},[]);return now;}
export function useDebounce(value:string,ms=200){const [debounced,set]=useState(value);useEffect(()=>{const t=setTimeout(()=>set(value),ms);return()=>clearTimeout(t)},[value,ms]);return debounced;}
