// Reproduce a root announcement while the outbox Worker is still initializing.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdtempSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { apply,verifyHost } from '../dist/index.js';
const host=process.argv[2];verifyHost(host);process.argv[1]=host;
const require=createRequire(host);
const {Context}=require('@deepseek-ai/cordis');
const {AgentRegistry}=require('@deepseek-ai/dsh-agent');
const {Session}=require('@deepseek-ai/dsh-session');
const {SessionProjectionRegistry}=require('@deepseek-ai/dsh-session-projection');
const {userQuestionProjectionDefinition}=require(path.join(path.dirname(require.resolve('@deepseek-ai/dsh-user-questions/package.json')),'lib/types/projection.js'));
const dir=mkdtempSync(path.join(tmpdir(),'agent-light-startup-'));
const ctx=new Context();new AgentRegistry(ctx);new SessionProjectionRegistry(ctx);
ctx.sessionProjections.register(userQuestionProjectionDefinition);
const tokenFile=path.join(dir,'token');writeFileSync(tokenFile,'synthetic-token');
const received=[];
const server=http.createServer((req,res)=>{
  let body='';req.on('data',chunk=>body+=chunk);req.on('end',()=>{
    const e=JSON.parse(body);if(e.type)received.push(e);
    res.setHeader('Content-Type','application/json');res.end(JSON.stringify({event_id:e.event_id,status:'applied'}));
  });
});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
let announced,agent;
try {
  const initializing=apply(ctx,{endpoint:`http://127.0.0.1:${server.address().port}`,tokenFile,dataDir:path.join(dir,'outbox')});
  await new Promise(resolve=>setTimeout(()=>{
    const session=Session.create('synthetic-startup');agent={id:session.id,session,ctx};
    ctx.agents.enter(agent,undefined);announced=ctx.agents.announce(agent,'startup');resolve();
  },5));
  await initializing;await announced;
  for(const [type,data] of [['turn/start',{turn:1}],['turn/end',{turn:1,reason:{kind:'completed'}}]]) {
    ctx.emit('session/event',agent.session,agent.session.append(type,data));
  }
  for(let n=0;n<100&&!received.some(e=>e.type==='turn_complete');n++)await new Promise(r=>setTimeout(r,25));
  assert.deepEqual(received.map(e=>e.type),['session_start','runtime_ready','turn_start','turn_complete']);
  assert.deepEqual(received[1].live_instances,[received[0].instance_id]);
  console.log('PASS: cold-start root is initialized before runtime_ready and its first turn is captured');
} finally {
  await ctx.fiber.dispose();await new Promise(r=>server.close(r));
  if(path.dirname(dir)!==path.resolve(tmpdir())||!path.basename(dir).startsWith('agent-light-startup-'))throw Error('TEMP_PATH');
  rmSync(dir,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}
