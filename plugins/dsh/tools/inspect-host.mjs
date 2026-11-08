import { createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { verifyHost } from '../dist/index.js';

const entry = resolve(process.argv[2] || '.');
const expected = {'dsh-agent':'0.2.1-rc.2','dsh-session':'0.2.1-rc.2',cordis:'4.0.5'};
const result = {schema_version:1, compatible:false, entry, detected:{}, expected,
  adapter_version:JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8')).version,
  mismatches:[], error_code:null};
try {
  if (!existsSync(entry) || !process.argv[2]) throw Error('HOST_NOT_FOUND');
  const req = createRequire(entry);
  for (const key of Object.keys(expected)) {
    result.detected[key] = JSON.parse(readFileSync(req.resolve('@deepseek-ai/'+key+'/package.json'),'utf8')).version;
    if (result.detected[key] !== expected[key]) result.mismatches.push(key);
  }
  try { verifyHost(entry); } catch { result.mismatches.push('host_fingerprints'); throw Error('UNSUPPORTED_VERSION'); }
  result.compatible = true;
} catch (error) {
  result.error_code = error.message === 'UNSUPPORTED_VERSION' ? 'UNSUPPORTED_VERSION' : 'HOST_NOT_FOUND';
}
process.stdout.write(JSON.stringify(result)+'\n');
