export const compact = n => n == null ? '—' : Intl.NumberFormat('en',{notation:'compact',maximumFractionDigits:n>=1e6?2:1}).format(n);
export const exact = n => n == null ? '—' : Intl.NumberFormat('en',{maximumFractionDigits:1}).format(n);
export const percent = n => n == null ? '—' : `${(n*100).toFixed(1)}%`;
export function displayDate(value,kind='datetime'){
  if(!value)return 'Unknown';
  let utc=false;try{utc=JSON.parse(localStorage.getItem('observatory.time')||'"local"')==='utc'}catch{}
  const options=kind==='time'?{hour:'2-digit',minute:'2-digit',hour12:false}:kind==='date'?{month:'short',day:'numeric'}:{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false};
  return new Intl.DateTimeFormat('en',{...options,...(utc?{timeZone:'UTC'}:{})}).format(new Date(value))+(utc&&kind!=='date'?' UTC':'');
}
export const turnLabel = row => `Turn · ${displayDate(row.started_at||row.first_response,'time')}`;
export function duration(seconds){
  if(seconds==null || !Number.isFinite(seconds))return '—';
  seconds=Math.max(0,Math.floor(seconds));
  if(seconds>=3600)return `${Math.floor(seconds/3600)}h ${Math.floor(seconds%3600/60)}m`;
  return `${Math.floor(seconds/60)}m ${seconds%60}s`;
}
export function dateRange(range, customStart='', customEnd='', now=new Date()){
  if(range==='all')return {};
  if(range==='custom'){
    const start=new Date(`${customStart}T00:00:00`),end=new Date(`${customEnd}T00:00:00`);
    end.setDate(end.getDate()+1);
    return Number.isFinite(+start)&&Number.isFinite(+end)&&end>start ? {start:start.toISOString(),end:end.toISOString()} : {invalid:true};
  }
  const start=new Date(now);start.setHours(0,0,0,0);start.setDate(start.getDate()-(range==='today'?0:Number(range)-1));
  return {start:start.toISOString(),end:now.toISOString()};
}
export function warning(task, settings, baseline, elapsed){
  if(!task || !settings)return {level:'Normal',reasons:[]};
  const reasons=[];
  for(const [value,limit,label] of [[task.total_tokens,settings.threshold_tokens,'Token threshold'],[task.request_count,settings.threshold_requests,'Request threshold'],[elapsed/60,settings.threshold_minutes,'Duration threshold'],[baseline?task.total_tokens/baseline:0,settings.threshold_multiple,'Median comparison']]){
    if(limit>0&&value>=limit)reasons.push({label,ratio:value/limit});
  }
  const max=Math.max(0,...reasons.map(r=>r.ratio));
  return {level:max>=3?'Critical':max>=2?'High':max>=1?'Elevated':'Normal',reasons:reasons.sort((a,b)=>b.ratio-a.ratio)};
}
