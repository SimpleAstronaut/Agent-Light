import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,writeFileSync,readFileSync,readdirSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import http from 'node:http';
import { Reporter } from '../dist/reporter.js';

const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn) {for(let i=0;i<100;i++){if(fn())return;await wait(50);}throw Error('TIMEOUT');}
test('durable offline replay preserves IDs and ignores malformed ACK',async()=>{
  const dir=mkdtempSync(path.join(tmpdir(),'agent-light-'));
  const tokenFile=path.join(dir,'token');writeFileSync(tokenFile,'TOKEN-CANARY');
  const server=http.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const port=server.address().port;await new Promise(r=>server.close(r));
  const cfg={endpoint:`http://127.0.0.1:${port}`,tokenFile,dataDir:path.join(dir,'outbox')};
  let reporter=new Reporter(cfg), receiver;
  try {
    await reporter.start();
    reporter.send({type:'session_start',session_id:'opaque',instance_id:'instance-a'});
    reporter.send({type:'runtime_ready',live_instances:['instance-a']});
    await until(()=>reporter.count===0);
    const files=readdirSync(cfg.dataDir).filter(n=>n.endsWith('.jsonl'));
    const disk=files.map(n=>readFileSync(path.join(cfg.dataDir,n),'utf8')).join('');
    assert(!disk.includes('TOKEN-CANARY'));
    const original=JSON.parse(JSON.parse(disk.split('\n')[0]).body);
    await reporter.close();
    const received=[];let valid=false;
    receiver=http.createServer((req,res)=>{
      let body='';req.on('data',b=>body+=b);req.on('end',()=>{
        const event=JSON.parse(body);res.setHeader('Content-Type','application/json');
        if(req.url.endsWith('/heartbeat')){res.end('{}');return;}
        received.push(event);res.end(JSON.stringify(valid?{event_id:event.event_id,status:'applied'}:{status:'applied'}));
      });
    });
    await new Promise(r=>receiver.listen(port,'127.0.0.1',r));
    reporter=new Reporter(cfg);await reporter.start();
    await until(()=>received.length>0);
    assert.equal(received[0].event_id,original.event_id);
    const checkpoint=JSON.parse(JSON.parse(readFileSync(path.join(cfg.dataDir,'checkpoint.json'),'utf8')).body);
    assert.equal(checkpoint.ack,0);
    valid=true;
    await until(()=>{
      const cp=JSON.parse(JSON.parse(readFileSync(path.join(cfg.dataDir,'checkpoint.json'),'utf8')).body);
      return cp.ack===2;
    });
    assert(received.filter(e=>e.event_id===original.event_id).length>=2);
  } finally {
    await reporter.close();
    if(receiver)await new Promise(r=>receiver.close(r));
    if(path.dirname(path.resolve(dir))!==path.resolve(tmpdir())||!path.basename(dir).startsWith('agent-light-'))throw Error('UNSAFE_TEMP_PATH');
    rmSync(dir,{recursive:true,force:true,maxRetries:10,retryDelay:100});
  }
});
