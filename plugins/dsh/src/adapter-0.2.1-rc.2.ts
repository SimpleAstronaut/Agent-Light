import { createHmac, randomUUID } from 'node:crypto';
import type { Reporter } from './reporter.js';

// Structural boundary: only the locked host supplies these objects. Never serialize them.
interface Instance {
  agent:any; session:string; id:string; turn:number;
  waits:Map<string,{turn:number; phase:'foreground'|'continued'; projected:boolean; cleanup?:()=>void}>;
  resolved:Set<string>; projectionQueued:boolean; reconcile:number|null; watermark:number;
}
export function observe(ctx:any, reporter:Reporter, key:string, sendReady=true) {
  const instances=new Map<any,Instance>(), bySession=new Map<any,Instance>();
  const disposers:(()=>void)[]=[];
  const digest=(id:string)=>createHmac('sha256',key).update(id).digest('hex');
  const safe=(fn:()=>void)=>{try{fn();}catch{reporter.fault('OBSERVER_FAILED');}};
  const emit=(s:Instance,type:string,extra:any={})=>reporter.send({type,session_id:s.session,instance_id:s.id,
      turn_seq:s.turn,turn_id:s.turn?`turn:${s.turn}`:null,...extra});
  const open=(s:Instance,id:string,reason='question')=>{
    if(s.resolved.has(id)||s.waits.has(id))return;
    s.waits.set(id,{turn:s.turn,phase:'foreground',projected:false});
    emit(s,'attention_open',{attention_id:id,reason_code:reason,turn_id:s.turn?`turn:${s.turn}`:'bootstrap'});
  };
  const finish=(s:Instance,id:string,reason='answered')=>{
    const w=s.waits.get(id);if(!w)return;
    w.cleanup?.();s.waits.delete(id);s.resolved.add(id);
    emit(s,'attention_resolve',{attention_id:id,turn_seq:w.turn,turn_id:w.turn?`turn:${w.turn}`:'bootstrap',reason_code:reason});
  };
  function projection(s:Instance, endTurn:number|null=null) {
    const view=ctx.sessionProjections.snapshot(s.agent.session,['userQuestions']).values.userQuestions;
    if(!view||!Array.isArray(view.active)||!Array.isArray(view.settled)){reporter.fault('PROJECTION_MISSING');return;}
    const active=new Set<string>(), settled=new Set<string>();
    for(const q of view.active) {
      const id='question:'+digest(String(q.callId));active.add(id);
      open(s,id);const w=s.waits.get(id);
      if(w){w.projected=true;if(q.state==='continued'){w.phase='continued';w.cleanup?.();}}
    }
    for(const q of view.settled)settled.add('question:'+digest(String(q.callId)));
    for(const [id,w] of s.waits) {
      if(!id.startsWith('question:'))continue;
      if(settled.has(id))finish(s,id);
      else if(!active.has(id)&&(w.projected||w.turn===endTurn))finish(s,id,'withdrawn');
    }
  }
  function queueProjection(s:Instance, endTurn:number|null=null) {
    if(endTurn!==null)s.reconcile=Math.max(s.reconcile??0,endTurn);
    if(s.projectionQueued)return;s.projectionQueued=true;
    queueMicrotask(()=>safe(()=>{
      s.projectionQueued=false;const reconcile=s.reconcile;s.reconcile=null;
      if(instances.has(s.agent))projection(s,reconcile);
    }));
  }
  const on=(name:string,fn:(...a:any[])=>void)=>disposers.push(ctx.on(name,(...a:any[])=>safe(()=>fn(...a)),{global:true}));
  const created=(agent:any)=>safe(()=>{
    if(instances.has(agent)||!ctx.agents.roots().includes(agent))return;
    const s:Instance={agent,session:digest(String(agent.session.header.id)),id:randomUUID(),turn:0,
      waits:new Map(),resolved:new Set(),projectionQueued:false,reconcile:null,watermark:-1};
    instances.set(agent,s);bySession.set(agent.session,s);
    emit(s,'session_start');projection(s);
  });
  on('agent/created',({agent})=>created(agent));
  on('agent/disposed',({agent})=>{
    const s=instances.get(agent);if(!s)return;
    for(const w of s.waits.values())w.cleanup?.();
    emit(s,'session_end',{reason_code:'agent_disposed',outcome:'disposed'});
    instances.delete(agent);bySession.delete(agent.session);
  });
  on('session/event',(session,event)=>{
    const s=bySession.get(session);if(!s)return;
    const d=event.data;
    if(event.type==='turn/start'){
      if(!Number.isSafeInteger(d.turn)||d.turn<=0){reporter.fault('INVALID_TURN');return;}
      s.turn=d.turn;emit(s,'turn_start');
    } else if(event.type==='turn/end') {
      const kind=d.reason?.kind;
      const mapping:Record<string,[string,string|null]>={completed:['turn_complete',null],aborted:['turn_cancelled','user_cancelled'],
        error:['error','turn_failed'],blocked:['error','turn_blocked'],'max-tokens':['error','output_limit']};
      if(mapping[kind]){
        const [type,reason_code]=mapping[kind];emit(s,type,{reason_code,turn_seq:d.turn,turn_id:`turn:${d.turn}`});
      } else if(!['interrupted','forked'].includes(kind))reporter.fault('UNSUPPORTED_END_REASON');
      queueProjection(s,d.turn);
    } else if(event.type==='approval/asked')open(s,'approval:'+digest(String(d.id)),'permission');
    else if(event.type==='approval/decided')finish(s,'approval:'+digest(String(d.id)),'withdrawn');
    else if(event.type==='step/start'||event.type==='step/end')emit(s,'activity');
  });
  on('agent/assistant-stream',({agent})=>{const s=instances.get(agent);if(s)emit(s,'activity');});
  disposers.push(ctx.sessionProjections.onChanged((session:any,k:string,_v:unknown,seq:number)=>safe(()=>{
    const s=bySession.get(session);
    if(s&&k==='userQuestions'&&seq>s.watermark){s.watermark=seq;queueProjection(s);}
  })));
  // Only next() participates in the business outcome. Observation errors are contained.
  disposers.push(ctx.on('user-questions/request',async(request:any,next:()=>Promise<unknown>)=>{
    const s=instances.get(request.agent);if(!s)return next();
    const timed=Boolean(request.wait?.callId), id='question:'+(timed?digest(String(request.wait.callId)):randomUUID());
    safe(()=>open(s,id));
    const signal:AbortSignal|undefined=request.signal;
    const code=(e:any)=>typeof e?.code==='string'?e.code:undefined;
    const timeout=()=>safe(()=>{const w=s.waits.get(id);if(w){w.phase='continued';w.cleanup?.();}});
    const abort=()=>safe(()=>{
      const w=s.waits.get(id);if(!w||w.phase!=='foreground')return;
      if(timed&&code(signal?.reason)==='ASK_TIMED_OUT')timeout();else finish(s,id,'withdrawn');
    });
    safe(()=>{
      const w=s.waits.get(id);if(w){w.cleanup=()=>signal?.removeEventListener('abort',abort);signal?.addEventListener('abort',abort,{once:true});}
      if(signal?.aborted)abort();
    });
    try {
      const result=await next();
      safe(()=>{if(s.waits.get(id)?.phase==='foreground'&&!signal?.aborted)finish(s,id);});
      return result;
    } catch(e) {
      safe(()=>{
        const w=s.waits.get(id);if(!w||w.phase!=='foreground')return;
        if(timed&&code(e)==='ASK_TIMED_OUT')timeout();
        else if(!(timed&&request.wait.timed===true&&code(e)==='NO_PROVIDER'))finish(s,id,'withdrawn');
      });
      throw e;
    }
  },{global:true,prepend:true}));
  if(sendReady)reporter.send({type:'runtime_ready',live_instances:[]});
  const close=()=>{
    for(const s of instances.values())for(const w of s.waits.values())w.cleanup?.();
    for(const d of disposers.reverse())d();
  };
  return Object.assign(close,{created,liveInstances:()=>[...instances.values()].map(s=>s.id)});
}
