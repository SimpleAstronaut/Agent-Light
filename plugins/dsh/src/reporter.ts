import { Worker } from 'node:worker_threads';
import { EventEmitter } from 'node:events';
import type { Config, Draft } from './types.js';

export class Reporter extends EventEmitter {
  worker: Worker;
  count = 0;
  bytes = 0;
  failed = false;
  code = 'STARTING';
  activity = new Map<string, number>();
  constructor(public config: Config) {
    super();
    this.worker = new Worker(new URL('./worker.js', import.meta.url), { workerData: config });
    this.worker.on('error', (error:NodeJS.ErrnoException) => {
      const known=new Set(['OUTBOX_ALREADY_OWNED','CHECKPOINT_CORRUPT','INVALID_ENDPOINT','ABSOLUTE_PATH_REQUIRED']);
      this.failed=true;
      this.code=known.has(error.message)?error.message:
        ['ENOENT','EACCES','EPERM','ENOSPC'].includes(error.code??'')?'WORKER_'+error.code:'WORKER_FAILED';
      this.emit('startup-failure',this.code);this.emit('diagnostic',this.code);
    });
    this.worker.on('exit', code => {
      if (code&&!this.failed) { this.failed = true; this.code = 'WORKER_EXIT'; this.emit('startup-failure',this.code); }
    });
    this.worker.on('message', m => {
      if (m.kind === 'credit') { this.count -= m.count; this.bytes -= m.bytes; }
      if (m.kind === 'fault') { this.failed = true; this.code = m.code; this.emit('diagnostic', m.code); }
      if (m.kind === 'ready') this.emit('ready', m);
    });
  }
  start(): Promise<{ key: string }> {
    if(this.failed)return Promise.reject(Object.assign(new Error(this.code),{code:this.code}));
    return new Promise((resolve, reject) => {
      let settled=false;
      const cleanup=()=>{clearTimeout(timer);this.off('ready',ready);this.off('startup-failure',failed);};
      const ready=(m:{key:string})=>{if(settled)return;settled=true;cleanup();resolve(m);};
      const failed=(code:string)=>{if(settled)return;settled=true;cleanup();reject(Object.assign(new Error(code),{code}));};
      // DSH boot can block the parent event loop longer than the deadline.
      // Drain queued MessagePort readiness before declaring a timeout.
      const timer=setTimeout(()=>setImmediate(()=>failed('WORKER_START_FAILED')),5000);
      this.once('ready',ready);this.once('startup-failure',failed);
    });
  }
  fault(code: string) {
    if (!this.failed) { this.failed = true; this.code = code; this.worker.postMessage({kind:'fault', code}); }
  }
  send(d: Draft): void {
    if (this.failed) return;
    if (d.type === 'activity') {
      const now = Date.now(), id = d.instance_id!;
      if (now - (this.activity.get(id) ?? 0) < (this.config.activityIntervalMs ?? 1000)) return;
      this.activity.set(id, now);
    }
    const size = Buffer.byteLength(JSON.stringify(d));
    if (this.count >= 4096 || this.bytes + size > 8 * 1024 * 1024) {
      if (d.type !== 'activity') this.fault('CAPTURE_OVERFLOW');
      return;
    }
    this.count++; this.bytes += size;
    this.worker.postMessage({kind:'event', draft:d, bytes:size});
    if (d.type === 'session_end') this.activity.delete(d.instance_id!);
  }
  async close() {
    if(this.worker.threadId===-1)return;
    this.worker.postMessage({kind:'close'});
    await Promise.race([new Promise<void>(r => this.worker.once('exit', () => r())),
      new Promise<void>(r => setTimeout(r, 500))]);
    await this.worker.terminate();
  }
}
