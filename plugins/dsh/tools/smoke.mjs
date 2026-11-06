// Real PC HTTP/SQLite + real Cordis observer + real outbox Worker, synthetic lifecycle only.
import { spawn, spawnSync } from 'node:child_process';
import { mkdtempSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { randomBytes } from 'node:crypto';
import http from 'node:http';
import { createRequire } from 'node:module';
import { verifyHost } from '../dist/index.js';

const entry=process.argv[2];verifyHost(entry);
const {boot,loadOverlayPatches,PluginPackages,createRuntimeResolution}=createRequire(entry)('@deepseek-ai/dsh-app-boot');
const hostRequire=createRequire(entry);
const {AgentRegistry}=hostRequire('@deepseek-ai/dsh-agent');
const {Session}=hostRequire('@deepseek-ai/dsh-session');
const {SessionProjectionRegistry}=hostRequire('@deepseek-ai/dsh-session-projection');
const {userQuestionProjectionDefinition}=hostRequire(path.join(path.dirname(hostRequire.resolve('@deepseek-ai/dsh-user-questions/package.json')),'lib/types/projection.js'));
const root=path.resolve(import.meta.dirname,'../../..');
const dir=mkdtempSync(path.join(tmpdir(),'agent-light-integration-'));
const probe=http.createServer();await new Promise(r=>probe.listen(0,'127.0.0.1',r));
const port=probe.address().port;await new Promise(r=>probe.close(r));
const token=randomBytes(32).toString('hex'), tokenFile=path.join(dir,'token');writeFileSync(tokenFile,token);
const endpoint=`http://127.0.0.1:${port}`, config=path.join(dir,'config.json');
writeFileSync(config,JSON.stringify({endpoint,tokenFile,dataDir:path.join(dir,'spool'),database:path.join(dir,'state.db'),
  brightness:35,completedHoldSeconds:300,port:null,vid:0x483,pid:0x5740,serialNumber:'synthetic-no-device'}));
const python=path.join(root,'pc/.venv/Scripts/python.exe');
const service=spawn(python,['-m','agent_light.cli','--config',config,'serve'],{cwd:root,windowsHide:true,stdio:'ignore'});
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const request=async(route)=>{const r=await fetch(endpoint+'/v1/'+route,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(1000)});if(!r.ok)throw Error('HTTP_'+r.status);return r.json();};
async function until(fn) {for(let n=0;n<100;n++){try{if(await fn())return;}catch{}await wait(50);}throw Error('SMOKE_TIMEOUT');}
let ctx;
try {
  await until(async()=>await request('health'));
  const overlay=spawnSync(python,['-m','agent_light.cli','--config',config,'overlay'],{cwd:root,windowsHide:true,encoding:'utf8'});
  if(overlay.status!==0)throw Error('OVERLAY_GENERATION_FAILED');
  const patch=path.join(dir,'overlay.yml'), hostConfig=path.join(dir,'cordis.yml');
  writeFileSync(patch,overlay.stdout);writeFileSync(hostConfig,'[]');
  // Match the real launcher identity for the gate, while using isolated synthetic services.
  process.argv[1]=entry;
  const resolution=await createRuntimeResolution({installAnchor:path.resolve(entry,'../../package.json'),home:dir});
  ctx=await boot('agent-light-smoke',hostConfig,loadOverlayPatches('agent-light-smoke',patch),async ctx=>{
    await ctx.plugin(PluginPackages,{resolution});
    new AgentRegistry(ctx);
    new SessionProjectionRegistry(ctx);
    ctx.sessionProjections.register(userQuestionProjectionDefinition);
  });
  if(![...ctx.loader.entries()].find(e=>e.options.id==='agent-light-dsh')?.fiber)throw Error('PLUGIN_NOT_LOADED');
  await until(async()=>Object.keys((await request('status')).sources).length===1);
  const session=Session.create('synthetic-session');
  const agent={id:session.id,session,ctx};
  ctx.agents.enter(agent,undefined);
  await ctx.agents.announce(agent,'startup');
  const publish=(type,data)=>ctx.emit('session/event',session,session.append(type,data));
  publish('turn/start',{turn:1});
  await until(async()=>(await request('status')).desired==='RUNNING');
  publish('approval/asked',{id:'synthetic-approval',toolName:'synthetic-tool'});
  await until(async()=>(await request('status')).desired==='ATTENTION');
  publish('approval/decided',{id:'synthetic-approval',outcome:'allowed-once'});
  publish('turn/end',{turn:1,reason:{kind:'completed'}});
  await until(async()=>(await request('status')).desired==='COMPLETED');
  const status=await request('status');
  console.log(JSON.stringify({result:'PASS',flow:['RUNNING','ATTENTION','COMPLETED'],sessions:Object.keys(status.sessions).length,hardware:status.connected?'connected':'not-used'}));
} finally {
  if(ctx)await ctx.fiber.dispose();
  const exited=new Promise(r=>service.once('exit',r));service.kill();await exited;
  if(path.dirname(path.resolve(dir))!==path.resolve(tmpdir())||!path.basename(dir).startsWith('agent-light-integration-'))throw Error('UNSAFE_TEMP_PATH');
  rmSync(dir,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}
