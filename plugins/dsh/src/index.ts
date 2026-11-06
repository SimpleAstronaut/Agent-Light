import { createRequire } from 'node:module';
import { readFileSync,writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { createHash } from 'node:crypto';
import { Reporter } from './reporter.js';
import { observe } from './adapter-0.2.1-rc.2.js';
import type { Config } from './types.js';
import { hostFingerprints } from './host-lock.js';
export const name='agent-light-dsh';
export const inject=['agents','sessionProjections'];
export function verifyHost(entry:string) {
  const req=createRequire(entry);
  for(const [pkg,version] of [['@deepseek-ai/dsh-agent','0.2.1-rc.2'],['@deepseek-ai/dsh-session','0.2.1-rc.2'],['@deepseek-ai/cordis','4.0.5']]) {
    if(JSON.parse(readFileSync(req.resolve(pkg+'/package.json'),'utf8')).version!==version)throw Error('UNSUPPORTED_VERSION');
  }
  const base=dirname(dirname(req.resolve('@deepseek-ai/dsh-agent/package.json')));
  for(const [file,hash] of Object.entries(hostFingerprints)) {
    if(createHash('sha256').update(readFileSync(join(base,file))).digest('hex').toUpperCase()!==hash)throw Error('UNSUPPORTED_VERSION');
  }
}
export async function apply(ctx:any,config:Config) {
  if(config.enabled===false)return;
  const log=ctx.logger?.('agent-light');
  let reporter:Reporter|undefined;
  let release:()=>void=()=>{};
  let removeGate:()=>void=()=>{};
  let observer:ReturnType<typeof observe>|undefined;
  let phase='verify_host';
  const diagnostic=(code:string)=>{
    const record={code,phase,time:new Date().toISOString()};
    console.warn('[agent-light]',JSON.stringify(record));
    try{writeFileSync(join(config.dataDir,'diagnostics.json'),JSON.stringify(record));}catch{}
  };
  try {
    verifyHost(process.argv[1]);
    if(ctx.agents.roots().length){log?.warn('RESTART_REQUIRED');diagnostic('RESTART_REQUIRED');return;}
    // Cold-start only: DSH can announce roots while the Worker is initializing.
    // Hold creation completion at the official serial boundary, before any turn
    // is released. Normal operation never waits for disk, HTTP or the Worker.
    const ready=new Promise<void>(resolve=>{release=resolve;});
    let initializing=true;
    removeGate=ctx.on('agent/created',async({agent}:any)=>{
      if(initializing){await ready;observer?.created(agent);}
    },{global:true,prepend:true});
    phase='worker_start';
    reporter=new Reporter({...config,endpoint:config.endpoint??'http://127.0.0.1:17321'});
    reporter.on('diagnostic',(code:string)=>{log?.warn(code);diagnostic(code);});
    const {key}=await reporter.start();
    phase='register_observers';
    observer=observe(ctx,reporter,key,false);
    for(const agent of ctx.agents.roots())observer.created(agent);
    phase='runtime_barrier';
    reporter.send({type:'runtime_ready',live_instances:observer.liveInstances()});
    initializing=false;release();removeGate();
    phase='cleanup_registration';
    ctx.effect(()=>async()=>{diagnostic('CAPTURE_STOPPED');observer?.();await reporter!.close();},'agent-light.capture');
    diagnostic('CAPTURE_READY');
  } catch(error:any) {
    log?.warn('CAPTURE_DISABLED');
    diagnostic('CAPTURE_DISABLED_'+(['TypeError','Error','CordisError'].includes(error?.name)?error.name:'UNKNOWN')+
      (typeof error?.code==='string'&&/^[A-Z_]{1,40}$/.test(error.code)?'_'+error.code:''));
    if(reporter)await reporter.close();
  } finally {
    release();removeGate();
  }
}
