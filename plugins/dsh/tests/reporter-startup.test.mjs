import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,mkdirSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Reporter } from '../dist/reporter.js';

function fixture() {
  const dir=mkdtempSync(path.join(tmpdir(),'agent-light-readiness-'));
  const tokenFile=path.join(dir,'token'),dataDir=path.join(dir,'outbox');
  writeFileSync(tokenFile,'synthetic-token');mkdirSync(dataDir);
  return {dir,dataDir,config:{endpoint:'http://127.0.0.1:1',tokenFile,dataDir}};
}
function clean(dir) {
  if(path.dirname(dir)!==path.resolve(tmpdir())||!path.basename(dir).startsWith('agent-light-readiness-'))throw Error('TEMP_PATH');
  rmSync(dir,{recursive:true,force:true,maxRetries:10,retryDelay:100});
}

test('already queued Worker readiness survives a parent event loop stall past the deadline',async()=>{
  const f=fixture(),reporter=new Reporter(f.config);
  try {
    const starting=reporter.start();
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,5500);
    const ready=await starting;
    assert.match(ready.key,/^[a-f0-9]{64}$/);
    assert.equal(reporter.failed,false);
  } finally {await reporter.close();clean(f.dir);}
});

test('an owned outbox returns its specific startup error instead of a generic timeout',async()=>{
  const f=fixture();writeFileSync(path.join(f.dataDir,'owner.lock'),String(process.pid));
  const reporter=new Reporter(f.config);
  try {
    await assert.rejects(reporter.start(),e=>e.code==='OUTBOX_ALREADY_OWNED');
  } finally {await reporter.close();clean(f.dir);}
});
