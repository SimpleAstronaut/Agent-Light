import { test } from 'node:test';
import assert from 'node:assert/strict';
import { observe } from '../dist/adapter-0.2.1-rc.2.js';

function fixture() {
  const listeners=new Map(), events=[], faults=[];
  const view={active:[],settled:[]};
  const agent={session:{header:{id:'root'}}};
  const ctx={agents:{roots:()=>[agent]},on:(name,fn)=>{listeners.set(name,fn);return()=>listeners.delete(name);},
    sessionProjections:{snapshot:()=>({values:{userQuestions:view}}),onChanged:fn=>{listeners.set('projection',fn);return()=>{};}}};
  const reporter={send:e=>events.push(e),fault:e=>faults.push(e)};
  const close=observe(ctx,reporter,'test-key');
  listeners.get('agent/created')({agent});
  const session=(type,data)=>listeners.get('session/event')(agent.session,{type,data});
  session('turn/start',{turn:1});
  return {listeners,events,faults,view,agent,session,close};
}

test('retry is not a terminal error, cancellation is not success, child is ignored',()=>{
  const f=fixture();
  f.listeners.get('agent/created')({agent:{session:{header:{id:'child'}}}});
  f.session('turn/end',{turn:1,reason:{kind:'aborted',reason:{kind:'user'}}});
  assert.equal(f.events.filter(e=>e.type==='session_start').length,1);
  assert.equal(f.events.at(-1).type,'turn_cancelled');
  assert(!f.events.some(e=>e.type==='turn_complete'));
  assert(!JSON.stringify(f.events).includes('root'));
});

test('real discriminated turn outcomes map by kind without copying error content',()=>{
  for(const [kind,type] of [['completed','turn_complete'],['error','error'],['blocked','error'],['max-tokens','error'],['aborted','turn_cancelled']]) {
    const f=fixture();
    f.session('turn/end',{turn:1,reason:{kind,error:{message:'CANARY',code:'UNKNOWN'}}});
    assert.equal(f.events.at(-1).type,type);
    assert.deepEqual(f.faults,[]);
    assert(!JSON.stringify(f.events).includes('CANARY'));
  }
});

test('legacy wrapper preserves exact return/error and pairs waiting',async()=>{
  const f=fixture(), handler=f.listeners.get('user-questions/request');
  const answer={private:'CANARY'};
  assert.equal(await handler({agent:f.agent},async()=>answer),answer);
  const error=Error('CANARY');
  await assert.rejects(handler({agent:f.agent},async()=>{throw error;}),e=>e===error);
  assert.equal(f.events.filter(e=>e.type==='attention_open').length,2);
  assert.equal(f.events.filter(e=>e.type==='attention_resolve').length,2);
  assert(!JSON.stringify(f.events).includes('CANARY'));
});

test('timed timeout cleanup abort does not resolve continued question',async()=>{
  const f=fixture(), handler=f.listeners.get('user-questions/request'), control=new AbortController();
  const timeout=Object.assign(Error(),{code:'ASK_TIMED_OUT'});
  await assert.rejects(handler({agent:f.agent,wait:{callId:'call-a',timed:true},signal:control.signal},async()=>{throw timeout;}));
  control.abort(Object.assign(Error(),{code:'ASK_ABORTED'}));
  assert.equal(f.events.filter(e=>e.type==='attention_resolve').length,0);
  f.view.active=[{callId:'call-a',state:'continued'}];
  f.listeners.get('projection')(f.agent.session,'userQuestions',null,1);
  await new Promise(r=>queueMicrotask(r));
  f.view.active=[];f.view.settled=[{callId:'call-a'}];
  f.listeners.get('projection')(f.agent.session,'userQuestions',null,2);
  await new Promise(r=>queueMicrotask(r));
  assert.equal(f.events.filter(e=>e.type==='attention_resolve').length,1);
  assert.equal(f.events.at(-1).turn_seq,1);
});
