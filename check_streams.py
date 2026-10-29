#!/usr/bin/env python3
"""Build a deduplicated catalog and conservatively probe public stream URLs."""
import json, os, re, time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT=os.path.join(ROOT,'data'); SRC=os.path.join(ROOT,'sources.json')
CAT=os.path.join(OUT,'channels.json'); STATE=os.path.join(OUT,'health-state.json')
NOW=datetime.now(timezone.utc).isoformat(timespec='seconds'); UA='SuprioTVHealthCheck/1.0 (GitHub Actions)'
def read(path,default):
 try:
  with open(path,encoding='utf-8') as f:return json.load(f)
 except (OSError,ValueError):return default
def norm(s):
 s=(s or '').lower();s=re.sub(r'\b(hd|fhd|uhd|4k|sd|live)\b',' ',s);return re.sub(r'[^a-z0-9]+',' ',s).strip()
def attr(line,key):
 m=re.search(r'(?:^|\s)'+re.escape(key)+r'="([^"]*)"',line,re.I);return m.group(1).strip() if m else ''
def fetch(url,timeout=12,limit=1000000):
 req=Request(url,headers={'User-Agent':UA,'Accept':'*/*','Range':'bytes=0-999999'})
 with urlopen(req,timeout=timeout) as r:return r.status,r.headers.get('Content-Type',''),r.read(limit),r.geturl()
def parse(text,source):
 out=[];item=None
 for raw in text.splitlines():
  line=raw.strip()
  if not line:continue
  if line.startswith('#EXTINF:'):
   comma=line.rfind(',');name=line[comma+1:].strip() if comma>=0 else ''
   item={'name':name or attr(line,'tvg-name') or 'Unnamed channel','id':attr(line,'tvg-id'),'logo':attr(line,'tvg-logo'),'country':attr(line,'tvg-country'),'language':attr(line,'tvg-language'),'group':attr(line,'group-title') or 'Other','source':source,'url':''}
  elif not line.startswith('#') and item:
   item['url']=urljoin(source,line)
   if urlparse(item['url']).scheme in ('http','https'):out.append(item)
   item=None
 return out
def key(c):
 country=norm(c.get('country'))
 return ('id:'+norm(c['id']) if c.get('id') else 'name:'+norm(c.get('name')))+'|country:'+country
def probe(url,timeout):
 try:
  status,ctype,body,final=fetch(url,timeout)
  if not 200<=status<400:return False,'HTTP '+str(status)
  if urlparse(final).path.lower().endswith('.m3u8') or b'#EXTM3U' in body[:300]:
   text=body.decode('utf-8','replace')
   if '#EXTM3U' not in text:return False,'Invalid HLS manifest'
   child=next((x.strip() for x in text.splitlines() if x.strip() and not x.strip().startswith('#')),None)
   if child:
    _,_,b2,u2=fetch(urljoin(final,child),timeout,200000)
    t2=b2.decode('utf-8','replace')
    if '#EXTM3U' in t2:
     segment=next((x.strip() for x in t2.splitlines() if x.strip() and not x.strip().startswith('#')),None)
     if segment:fetch(urljoin(u2,segment),timeout,64000)
   return True,'HLS manifest and available child checked'
  return (bool(body),'HTTP response received' if body else 'Empty response')
 except HTTPError as e:return False,'HTTP '+str(e.code)
 except Exception as e:return False,(type(e).__name__+': '+str(e))[:160]
def main():
 cfg=read(SRC,{});settings=cfg.get('settings',{});urls=list(dict.fromkeys(x.strip() for x in cfg.get('playlists',[]) if isinstance(x,str) and x.strip()))
 timeout=int(settings.get('request_timeout_seconds',12));retries=max(1,int(settings.get('retry_attempts_per_stream',2)));threshold=max(2,int(settings.get('maintenance_after_consecutive_failed_runs',3)));limit=int(settings.get('max_channels',5000))
 os.makedirs(OUT,exist_ok=True);old=read(CAT,{'channels':[]});state=read(STATE,{});oldmap={c.get('key'):c for c in old.get('channels',[]) if c.get('key')};items=[];results=[]
 for u in urls:
  try:
   _,_,body,final=fetch(u,timeout,20000000);parsed=parse(body.decode('utf-8','replace'),final);items+=parsed;results.append({'url':u,'ok':True,'entries':len(parsed),'checked_at':NOW});print('Loaded',len(parsed),'entries from',u)
  except Exception as e:results.append({'url':u,'ok':False,'error':str(e)[:160],'checked_at':NOW});print('Playlist load failed:',u,str(e)[:160])
 merged={}
 for it in items:
  if not it.get('url'):continue
  k=key(it)
  if k not in merged:merged[k]={'key':k,'name':it['name'],'id':it['id'],'logo':it['logo'],'country':it['country'],'language':it['language'],'group':it['group'],'streams':[],'sources':[]}
  c=merged[k]
  for field in ('logo','id','country','language'):
   if not c[field] and it[field]:c[field]=it[field]
  if c['group']=='Other' and it['group']:c['group']=it['group']
  if it['url'] not in c['streams']:c['streams'].append(it['url'])
  if it['source'] not in c['sources']:c['sources'].append(it['source'])
 output=[];any_playlist_ok=any(x['ok'] for x in results)
 for i,(k,c) in enumerate(sorted(merged.items(),key=lambda kv:kv[1]['name'].casefold())):
  if i>=limit:break
  previous=oldmap.get(k,{});st=state.get(k,{});ok=False;errs=[]
  # Probe all backup URLs; a single healthy backup means the channel is Working.
  for u in c['streams']:
   this_ok=False;why=''
   for n in range(retries):
    this_ok,why=probe(u,timeout)
    if this_ok:break
    if n+1<retries:time.sleep(1)
   if this_ok:ok=True
   else:errs.append(why)
  if ok:
   failures=0;status='Working';reason='At least one stream passed server-side check';state[k]={'failures':0,'last_success':NOW,'status':status,'reason':reason}
  elif not any_playlist_ok:
   # Playlist-fetch failure is not evidence that individual channels failed.
   failures=int(st.get('failures',0));status=previous.get('status','Unverified');reason='Playlist sources unavailable; previous channel status retained'
   state[k]=st or {'failures':0,'status':'Unverified','reason':reason}
  else:
   failures=int(st.get('failures',0))+1;reason='; '.join(errs[:3]) or 'No stream passed check';status='Maintenance' if failures>=threshold else 'Unverified'
   state[k]={'failures':failures,'last_success':st.get('last_success'),'status':status,'reason':reason}
  output.append({**c,'status':status,'checked_at':NOW,'consecutive_failures':failures,'health_reason':reason,'last_success':state.get(k,{}).get('last_success')})
 # If all playlist fetches failed, preserve old catalog rather than erasing it.
 if urls and not any_playlist_ok:
  present={c['key'] for c in output}
  for c in old.get('channels',[]):
   if c.get('key') not in present:output.append(c)
 payload={'generated_at':NOW,'playlist_count':len(urls),'playlist_results':results,'channels':output}
 with open(CAT,'w',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2)
 with open(STATE,'w',encoding='utf-8') as f:json.dump(state,f,ensure_ascii=False,indent=2)
 print('Wrote',len(output),'unique channels; maintenance after',threshold,'consecutive failed runs.')
if __name__=='__main__':main()
