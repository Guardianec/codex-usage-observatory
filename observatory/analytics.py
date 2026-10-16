"""Read models for the UI. All token metrics pass through domain.Usage."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from statistics import median, mean
from .domain import Usage, timestamp, estimate_cost

SUMS = ','.join(f'coalesce(sum(r.{k}),0) AS {k}' for k in
               ('input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens'))
JOIN = ' FROM responses r JOIN sessions s ON s.id=r.session_id JOIN tasks t ON t.session_id=r.session_id AND t.id=r.task_id '
FILTERS = {'start','end','model','effort','project_id','session_id','task_id','status','search','root_session_id'}


def where(q):
    if set(q)-FILTERS:
        raise ValueError('unknown filter')
    parts, params = [], []
    for k,col in [('model','r.model'),('effort','r.effort'),('project_id','s.project_id'),
                  ('session_id','r.session_id'),('task_id','r.task_id'),('status','t.status'),
                  ('root_session_id','r.root_session_id')]:
        if q.get(k):
            if k=='model' and q[k]=='__unknown__':
                parts.append('r.model IS NULL');continue
            if k=='project_id' and q[k]=='unknown':
                parts.append('s.project_id IS NULL');continue
            parts.append(col+'=?');params.append(q[k])
    for k,op in [('start','>='),('end','<')]:
        if q.get(k):
            parts.append('r.timestamp'+op+'?');params.append(timestamp(q[k]))
    if q.get('start') and q.get('end') and timestamp(q['start'])>=timestamp(q['end']):
        raise ValueError('invalid range')
    if q.get('search'):
        parts.append("(instr(lower(t.id),lower(?))>0 OR instr(lower(coalesce(p.name,'')),lower(?))>0 OR instr(lower(coalesce(r.model,'')),lower(?))>0 OR instr(lower(t.session_id),lower(?))>0)")
        params += [q['search']]*4
    return (' WHERE '+' AND '.join(parts) if parts else ''), params


def metrics(row):
    return Usage(*(int(row[k] or 0) for k in ('input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens'))).metrics()


def duration(start,end):
    if not start or not end:return None
    return max(0,(datetime.fromisoformat(end.replace('Z','+00:00'))-datetime.fromisoformat(start.replace('Z','+00:00'))).total_seconds())


def query_rows(db,sql,args=()):
    return [dict(r) for r in db.execute(sql,args)]


def response_groups(db,q,group,extra=''):
    clause,args=where(q)
    sql=f'SELECT {group} AS key,{SUMS},count(*) AS request_count {extra}'+JOIN+' LEFT JOIN projects p ON p.id=s.project_id'+clause+f' GROUP BY {group}'
    return [{**r,**metrics(r)} for r in query_rows(db,sql,args)]


def task_rows(db,q):
    clause,args=where(q)
    sql='SELECT t.*,s.project_id,s.agent_kind,p.name AS project,'+SUMS+",count(*) AS request_count,min(r.timestamp) AS first_response,max(r.timestamp) AS last_response,group_concat(DISTINCT r.model) AS models,group_concat(DISTINCT r.effort) AS efforts"+JOIN+' LEFT JOIN projects p ON p.id=s.project_id'+clause+' GROUP BY r.session_id,r.task_id'
    result=[]
    for row in query_rows(db,sql,args):
        row.update(metrics(row));row['duration_seconds']=duration(row['started_at'],row['ended_at'])
        row['label']='Turn · '+(row['started_at'] or row['first_response'])[11:16]
        result.append(row)
    # Include genuinely unknown/zero-usage turns; never imply their accounting is complete.
    parts=['NOT EXISTS(SELECT 1 FROM responses r WHERE r.session_id=t.session_id AND r.task_id=t.id)']; params=[]
    for key,col in [('session_id','t.session_id'),('task_id','t.id'),('project_id','s.project_id'),('model','t.model'),('effort','t.effort'),('status','t.status'),('root_session_id','s.root_session_id')]:
        if q.get(key):
            if (key=='model' and q[key]=='__unknown__') or (key=='project_id' and q[key]=='unknown'):
                parts.append(col+' IS NULL')
            else:parts.append(col+'=?');params.append(q[key])
    for key,op in [('start','>='),('end','<')]:
        if q.get(key):parts.append('t.started_at'+op+'?');params.append(timestamp(q[key]))
    if q.get('search'):
        parts.append("(instr(lower(t.id),lower(?))>0 OR instr(lower(coalesce(p.name,'')),lower(?))>0 OR instr(lower(coalesce(t.model,'')),lower(?))>0 OR instr(lower(t.session_id),lower(?))>0)");params += [q['search']]*4
    unknown=query_rows(db,'SELECT t.*,s.project_id,s.agent_kind,p.name AS project FROM tasks t JOIN sessions s ON s.id=t.session_id LEFT JOIN projects p ON p.id=s.project_id WHERE '+' AND '.join(parts),params)
    for row in unknown:
        row.update(Usage(0,0,0,0).metrics());row.update(request_count=0,models=row['model'],efforts=row['effort'],first_response=None,last_response=None,
            duration_seconds=duration(row['started_at'],row['ended_at']),label='Turn · '+(row['started_at'] or '???????????unknown')[11:16])
        result.append(row)
    return result


def task_statistics(items):
    known=[r for r in items if r['request_count']]
    completed=[r['duration_seconds'] for r in known if r.get('duration_seconds') is not None]
    return {'task_count':len(items),'measured_tasks':len(known),
        'median_tokens':median([r['total_tokens'] for r in known]) if known else None,
        'average_tokens':mean([r['total_tokens'] for r in known]) if known else None,
        'median_duration_seconds':median(completed) if completed else None,
        'average_duration_seconds':mean(completed) if completed else None,
        'completed_turn_seconds':sum(completed)}


def costs(db,q,prices):
    groups=response_groups(db,q,"coalesce(r.model,'')||'|'||substr(r.timestamp,1,10)",',r.model,substr(r.timestamp,1,10) AS date')
    amount=Decimal(0);covered=0;requests=0
    for g in groups:
        requests+=g['request_count']
        cost=estimate_cost(Usage(g['input_tokens'],g['cached_input_tokens'],g['output_tokens'],g['reasoning_output_tokens']),g['model'],g['date']+'T00:00:00Z',prices)
        if cost:amount+=Decimal(cost['amount']);covered+=g['request_count']
    return {'amount':str(amount) if covered else None,'currency':'USD','basis':'api-equivalent','covered_requests':covered,'total_requests':requests,'complete':covered==requests and requests>0}


def snapshot(db,q,prices=()):
    clause,args=where(q)
    raw=db.execute('SELECT '+SUMS+',count(*) AS request_count'+JOIN+' LEFT JOIN projects p ON p.id=s.project_id'+clause,args).fetchone()
    tasks=task_rows(db,q);stats=task_statistics(tasks)
    projects=response_groups(db,q,"coalesce(s.project_id,'unknown')",",p.name AS name,count(DISTINCT r.session_id) AS session_count,max(r.timestamp) AS last_seen")
    models=response_groups(db,q,"coalesce(r.model,'Unknown model')")
    for collection,field in [(projects,'project_id'),(models,'model')]:
        for item in collection:
            subset=[t for t in tasks if (t.get(field)==item['key'] or (field=='model' and (item['key'] in (t.get('models') or '').split(',') or item['key']=='Unknown model' and not t.get('models'))))]
            if field=='model':
                # Model statistics use this model's contribution to each turn; duration stays whole-turn.
                modelparts=response_groups(db,{**q,'model':item['key'] if item['key']!='Unknown model' else '__unknown__'},"r.session_id||char(31)||r.task_id")
                contribution={g['key']:g['total_tokens'] for g in modelparts}
                subset=[{**t,'total_tokens':contribution[t['session_id']+'\x1f'+t['id']]} for t in tasks if t['session_id']+'\x1f'+t['id'] in contribution]
            item.update(task_statistics(subset))
            item['cache_ratio']=item['cached_input_tokens']/item['input_tokens'] if item['input_tokens'] else None
            item['top_model']=max(response_groups(db,{**q,'project_id':item['key']},"coalesce(r.model,'Unknown model')"),key=lambda x:x['total_tokens'],default={}).get('key') if field=='project_id' and item['key']!='unknown' else None
            if field=='model':
                item['cost']=costs(db,{**q,'model':item['key'] if item['key']!='Unknown model' else '__unknown__'},prices)
                completed=[r for r in subset if r['duration_seconds'] is not None and r['duration_seconds']>0]
                recorded_minutes=sum(r['duration_seconds'] for r in completed)/60
                item['tokens_per_turn_minute']=sum(r['total_tokens'] for r in completed)/recorded_minutes if recorded_minutes else None
    daily=response_groups(db,q,'substr(r.timestamp,1,10)');daily_truncated=False
    for day in daily:day['date']=day.pop('key')
    daily.sort(key=lambda x:x['date'])
    if daily:
        first=datetime.fromisoformat(q['start'].replace('Z','+00:00')).date() if q.get('start') else datetime.fromisoformat(daily[0]['date']).date()
        last=(datetime.fromisoformat(q['end'].replace('Z','+00:00'))-timedelta(milliseconds=1)).date() if q.get('end') else datetime.fromisoformat(daily[-1]['date']).date()
        daily_truncated=(last-first).days>=730
        first=max(first,last-timedelta(days=729));indexed={r['date']:r for r in daily};filled=[]
        while first<=last:
            key=first.isoformat();filled.append(indexed.get(key,{'date':key,**Usage(0,0,0,0).metrics(),'request_count':0}));first+=timedelta(days=1)
        daily=filled
    recent=sorted(tasks,key=lambda t:t.get('started_at') or t.get('first_response') or '',reverse=True)
    top=sorted(tasks,key=lambda t:t['total_tokens'],reverse=True)[:5]
    active=sorted((t for t in task_rows(db,{}) if t['status']=='running'),key=lambda t:t.get('started_at') or '',reverse=True)[:8]
    return {'summary':{**metrics(raw),'request_count':raw['request_count'],**stats,
                        'cache_ratio':raw['cached_input_tokens']/raw['input_tokens'] if raw['input_tokens'] else None},
            'daily':daily[-730:],'daily_truncated':daily_truncated,
            'projects':sorted(projects,key=lambda r:r['total_tokens'],reverse=True),
            'models':sorted(models,key=lambda r:r['total_tokens'],reverse=True),
            'efforts':[r[0] for r in db.execute('SELECT DISTINCT effort FROM responses WHERE effort IS NOT NULL ORDER BY effort')],
            'recent':recent[:5],'expensive':top,'active':active,'latest':recent[0] if recent else None,
            'cost':costs(db,q,prices),'coverage':'recorded_responses_only',
            'range_semantics':'Response timestamps in range; turn comparisons use recorded contribution in range.'}


def page_tasks(db,q,sort='started_at',direction='desc',page=1,limit=25):
    items=task_rows(db,q)
    if sort not in {'started_at','total_tokens','input_tokens','cached_input_tokens','output_tokens','request_count','duration_seconds','model','project'}:raise ValueError('invalid sort')
    if direction not in {'asc','desc'} or page<1 or not 1<=limit<=100:raise ValueError('invalid page')
    items.sort(key=lambda t:(t.get(sort) is not None,t.get(sort) or (0 if sort not in {'started_at','model','project'} else '')),reverse=direction=='desc')
    start=(page-1)*limit
    return {'items':items[start:start+limit],'total':len(items),'page':page,'limit':limit}


def requests(db,q,page=1,limit=50):
    if page<1 or not 1<=limit<=100:raise ValueError('invalid page')
    clause,args=where(q)
    total=db.execute('SELECT count(*)'+JOIN+' LEFT JOIN projects p ON p.id=s.project_id'+clause,args).fetchone()[0]
    items=query_rows(db,'SELECT r.*'+JOIN+' LEFT JOIN projects p ON p.id=s.project_id'+clause+' ORDER BY r.timestamp DESC,r.id DESC LIMIT ? OFFSET ?',args+[limit,(page-1)*limit])
    return {'items':[{**r,**metrics(r)} for r in items],'total':total,'page':page,'limit':limit}


def timeline(db,q):
    clause,args=where(q)
    span=db.execute("SELECT min(unixepoch(r.timestamp)),max(unixepoch(r.timestamp))"+JOIN+' LEFT JOIN projects p ON p.id=s.project_id'+clause,args).fetchone()
    if span[0] is None:return {'items':[],'bucket_seconds':60}
    step=max(60,((span[1]-span[0])//120//60+1)*60)
    groups=response_groups(db,q,f'cast(unixepoch(r.timestamp)/{step} AS INTEGER)*{step}')
    indexed={g['key']:g for g in groups}
    first=min(indexed);last=max(indexed)
    groups=[indexed.get(key,{'key':key,**Usage(0,0,0,0).metrics(),'request_count':0}) for key in range(first,last+step,step)]
    total=0
    for g in sorted(groups,key=lambda x:x['key']):
        total+=g['total_tokens'];g['cumulative_tokens']=total;g['tokens_per_minute']=g['total_tokens']/(step/60)
        g['timestamp']=datetime.fromtimestamp(g.pop('key'),timezone.utc).isoformat().replace('+00:00','Z')
    return {'items':sorted(groups,key=lambda x:x['timestamp']),'bucket_seconds':step}


def session_rows(db,q):
    tasks=task_rows(db,q);usage=response_groups(db,q,'r.session_id')
    byid={r['key']:r for r in usage};result=[]
    clause=''
    for s in query_rows(db,'SELECT s.*,p.name AS project FROM sessions s LEFT JOIN projects p ON p.id=s.project_id'):
        own=[t for t in tasks if t['session_id']==s['id']]
        if not own:continue
        u=byid.get(s['id'],{**Usage(0,0,0,0).metrics(),'request_count':0})
        result.append({**s,**u,**task_statistics(own),'models':sorted({m for t in own for m in (t['models'] or '').split(',') if m})})
    return sorted(result,key=lambda r:r['started_at'] or '',reverse=True)
