import { parentPort, workerData } from 'node:worker_threads';
import * as fs from 'node:fs';
import path from 'node:path';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
import http from 'node:http';
import type { Config, Draft } from './types.js';

const cfg: Config = workerData;
const endpoint = new URL(cfg.endpoint);
if (endpoint.protocol !== 'http:' || endpoint.hostname !== '127.0.0.1' || endpoint.username || endpoint.password || endpoint.pathname !== '/' || endpoint.search || endpoint.hash) throw Error('INVALID_ENDPOINT');
if (!path.isAbsolute(cfg.tokenFile) || !path.isAbsolute(cfg.dataDir)) throw Error('ABSOLUTE_PATH_REQUIRED');
fs.mkdirSync(cfg.dataDir, {recursive:true, mode:0o700});
const file = (s:string) => path.join(cfg.dataDir,s);
const hash = (s:string) => createHash('sha256').update(s).digest('hex');
function writeAtomic(name:string, value:unknown) {
  const body = JSON.stringify(value), text = JSON.stringify({body, sha256:hash(body)});
  const tmp = file(name+'.tmp'), fd = fs.openSync(tmp,'w',0o600);
  try { fs.writeFileSync(fd,text); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  if (fs.existsSync(file(name))) fs.copyFileSync(file(name), file(name+'.previous'));
  fs.renameSync(tmp, file(name));
}
function readMeta() {
  for (const name of ['checkpoint.json','checkpoint.json.previous']) {
    if (!fs.existsSync(file(name))) continue;
    try { const r = JSON.parse(fs.readFileSync(file(name),'utf8')); if(hash(r.body)===r.sha256) return JSON.parse(r.body); } catch {}
  }
  if (fs.existsSync(file('checkpoint.json')) || fs.readdirSync(cfg.dataDir).some(n=>n.endsWith('.jsonl'))) throw Error('CHECKPOINT_CORRUPT');
  return {producer:randomUUID(), key:randomBytes(32).toString('hex'), runtime:0, seq:0, ack:0, instances:{}, segment:0};
}
// PID lock recovers after process death. A reused live PID conservatively disables capture.
try {
  const fd = fs.openSync(file('owner.lock'),'wx',0o600); fs.writeFileSync(fd,String(process.pid)); fs.closeSync(fd);
} catch {
  const pid = Number(fs.readFileSync(file('owner.lock'),'utf8'));
  try { process.kill(pid,0); throw Error('OUTBOX_ALREADY_OWNED'); }
  catch (e:any) { if(e.code !== 'ESRCH') throw e; }
  fs.unlinkSync(file('owner.lock'));
  const fd = fs.openSync(file('owner.lock'),'wx',0o600); fs.writeFileSync(fd,String(process.pid)); fs.closeSync(fd);
}
process.on('exit',()=>{try{fs.unlinkSync(file('owner.lock'));}catch{}});
const meta = readMeta();
const pending: {event:any; segment:string}[] = [];
let degraded = false, paused = false, closing = false, persisted = meta.ack;
let token = fs.readFileSync(cfg.tokenFile,'utf8').trim();
function fault(code:string) { degraded=true; parentPort!.postMessage({kind:'fault',code}); }
for(const name of fs.readdirSync(cfg.dataDir).filter(n=>/^segment-\d+\.jsonl$/.test(n)).sort()) {
  const bytes=fs.readFileSync(file(name)); let offset=0;
  while(offset<bytes.length) {
    const end=bytes.indexOf(10,offset);
    if(end<0) { fs.truncateSync(file(name),offset); break; }
    try {
      const r=JSON.parse(bytes.subarray(offset,end).toString());
      if(r.version!==1 || Buffer.byteLength(r.body)!==r.length || hash(r.body)!==r.sha256) throw Error();
      const event=JSON.parse(r.body);
      meta.seq=Math.max(meta.seq,event.producer_seq); persisted=Math.max(persisted,event.producer_seq);
      meta.runtime=Math.max(meta.runtime,event.runtime_seq);
      meta.segment=Math.max(meta.segment,Number(name.slice(8,-6)));
      if(event.type==='session_start')meta.instances[event.session_id]=Math.max(meta.instances[event.session_id]??0,event.instance_seq);
      if(event.producer_seq>meta.ack) pending.push({event,segment:name});
    } catch { fault('SPOOL_CORRUPT'); break; }
    offset=end+1;
  }
  if(degraded) break;
}
meta.runtime++; const runtime=randomUUID();
writeAtomic('checkpoint.json',meta);
let segment=`segment-${String(++meta.segment).padStart(10,'0')}.jsonl`;
function append(d:Draft) {
  if(meta.seq>=Number.MAX_SAFE_INTEGER) throw Error('SEQUENCE_EXHAUSTED');
  const e:any={schema_version:1,event_id:randomUUID(),agent:'dsh',producer_id:meta.producer,
    runtime_id:runtime,runtime_seq:meta.runtime,producer_seq:++meta.seq,type:d.type};
  if(d.type==='runtime_ready') e.live_instances=d.live_instances ?? [];
  else {
    if(d.type==='session_start') meta.instances[d.session_id!]=(meta.instances[d.session_id!]??0)+1;
    Object.assign(e,{channel:'plugin',session_id:d.session_id,instance_id:d.instance_id,
      instance_seq:meta.instances[d.session_id!],turn_id:d.turn_id??null,turn_seq:d.turn_seq??0,
      attention_id:d.attention_id??null,reason_code:d.reason_code??null,occurred_at:new Date().toISOString()});
    if(d.outcome) e.outcome=d.outcome;
  }
  const body=JSON.stringify(e), line=JSON.stringify({version:1,body,length:Buffer.byteLength(body),sha256:hash(body)})+'\n';
  const size=fs.readdirSync(cfg.dataDir).filter(n=>n.endsWith('.jsonl')).reduce((a,n)=>a+fs.statSync(file(n)).size,0);
  if(size+Buffer.byteLength(line)>(cfg.maxSpoolBytes??64*1024*1024)) throw Error('SPOOL_FULL');
  // Persist counters first. A crash may skip numbers, never reuses an identity.
  writeAtomic('checkpoint.json',meta);
  if(fs.existsSync(file(segment))&&fs.statSync(file(segment)).size>=1024*1024) segment=`segment-${String(++meta.segment).padStart(10,'0')}.jsonl`;
  const fd=fs.openSync(file(segment),'a',0o600);
  try{fs.writeFileSync(fd,line);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}
  persisted=e.producer_seq;pending.push({event:e,segment});
}
function post(route:string, body:unknown):Promise<{code:number; body:any; retry:number}> {
  return new Promise((resolve,reject)=>{
    const payload=JSON.stringify(body);
    const req=http.request(new URL(route,endpoint),{method:'POST',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json','Content-Length':Buffer.byteLength(payload)}},res=>{
      let data='';res.on('data',b=>{data+=b;if(data.length>65536)req.destroy(Error('RESPONSE_TOO_LARGE'));});
      res.on('end',()=>{let value;try{value=JSON.parse(data);}catch{}resolve({code:res.statusCode!,body:value,retry:Math.min(5,Math.max(.25,Number(res.headers['retry-after'])||1))});});
    });
    req.setTimeout(cfg.requestTimeoutMs??200,()=>req.destroy(Error('TIMEOUT')));
    const timer=setTimeout(()=>req.destroy(Error('TIMEOUT')),cfg.requestTimeoutMs??200);
    req.on('close',()=>clearTimeout(timer));req.on('error',reject);req.end(payload);
  });
}
let sending=false, retryAt=0, backoff=.25;
async function pump() {
  if(sending||paused||degraded||!pending.length||Date.now()<retryAt)return;
  sending=true;
  try {
    const first=pending[0], r=await post('/v1/events',first.event);
    if(r.code===200 && r.body?.event_id===first.event.event_id && ['applied','duplicate','stale'].includes(r.body.status)) {
      meta.ack=first.event.producer_seq;writeAtomic('checkpoint.json',meta);pending.shift();backoff=.25;
      for(const n of fs.readdirSync(cfg.dataDir).filter(n=>/^segment-\d+\.jsonl$/.test(n))) {
        if(n!==segment&&!pending.some(p=>p.segment===n)) fs.unlinkSync(file(n));
      }
    } else if([401,403].includes(r.code)) { paused=true;fault('AUTH_FAILED'); }
    else if([400,409,413,422].includes(r.code)) { writeAtomic('quarantine.json',first.event);fault('EVENT_REJECTED'); }
    else { retryAt=Date.now()+1000*(r.code===429?r.retry:backoff)*(.8+Math.random()*.4);backoff=Math.min(5,backoff*2); }
  } catch { retryAt=Date.now()+backoff*1000;backoff=Math.min(5,backoff*2); }
  finally {sending=false;}
}
let heartbeatBusy=false;
async function heartbeat() {
  if(heartbeatBusy)return;heartbeatBusy=true;
  try { await post('/v1/producers/heartbeat',{agent:'dsh',producer_id:meta.producer,runtime_id:runtime,runtime_seq:meta.runtime,
      health:degraded?'degraded':'healthy',persisted_seq:persisted,acked_seq:meta.ack}); } catch {} finally {heartbeatBusy=false;}
}
parentPort!.on('message',m=>{
  if(m.kind==='fault') fault(m.code);
  if(m.kind==='event'&&!degraded) {
    try{append(m.draft);parentPort!.postMessage({kind:'credit',count:1,bytes:m.bytes});void pump();}
    catch {fault('SPOOL_WRITE_FAILED');}
  }
  if(m.kind==='close') {closing=true;process.exit(0);}
});
setInterval(()=>{if(!closing)void pump();},20);
setInterval(()=>void heartbeat(),2000);
void heartbeat();
parentPort!.postMessage({kind:'ready',key:meta.key});
