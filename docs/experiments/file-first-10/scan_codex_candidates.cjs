// Read-only audit of the two original rollouts. Never evaluates historical commands.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = 'C:/Users/hongy/OneDrive/Documents/xwechat_files/wxid_1d7icrbx732s22_2384/msg/file/2026-08';
const names = [
  'rollout-2026-08-16T17-54-23-01a009fe-68e3-7f42-b76b-5e863c555976.jsonl',
  'rollout-2026-08-21T09-18-20-01a021e5-c150-7b12-a610-d40c07816b98.jsonl',
];
const [mode = 'inventory', which = 'all', query = '', cap = '1200'] = process.argv.slice(2);
const limit = Number(cap);
for (const [index, name] of names.entries()) {
  if (which !== 'all' && Number(which) !== index) continue;
  const bytes = fs.readFileSync(path.join(root, name));
  const lines = bytes.toString('utf8').split(/\r?\n/).filter(Boolean);
  const rows = lines.map((raw, n) => ({...JSON.parse(raw), line:n+1, raw}));
  const digest = crypto.createHash('sha256').update(bytes).digest('hex');
  const printable = r => {
    const p = r.payload || {};
    const v = p.input ?? p.arguments ?? p.output ?? p.message ?? (Array.isArray(p.content) ? p.content.map(c => c.text || '').join('\n') : null);
    return v === null || v === undefined ? (p.type === 'patch_apply_end' || p.type === 'sub_agent_activity' ? JSON.stringify(p) : '') : typeof v === 'string' ? v : Array.isArray(v) ? v.map(x=>x.text || '').join('\n') : JSON.stringify(v);
  };
  const show = r => {
    const p = r.payload || {};
    if (p.role === 'developer' || p.role === 'system') return;
    if (!printable(r)) return;
    const safe = String(printable(r)).replace(/("(?:keyPassword|storePassword)"\s*:\s*")[^"]*/g, '$1[REDACTED]');
    console.log(JSON.stringify({file:name,line:r.line,time:r.timestamp,type:r.type,kind:p.type,role:p.role,channel:p.channel,name:p.name,call_id:p.call_id ?? null,hash:crypto.createHash('sha256').update(r.raw).digest('hex'),text:safe.slice(0,limit)}));
  };
  if(mode === 'validate') {
    const refs = JSON.parse(fs.readFileSync(path.join(__dirname,'candidate-codex.json'),'utf8'));
    const inv = JSON.parse(fs.readFileSync(path.join(__dirname,'codex-native-write-inventory.json'),'utf8'));
    const expectedSource = inv.sources.find(s=>s.source_basename===name);
    if(expectedSource.sha256 !== digest || expectedSource.physical_lines !== rows.length) throw new Error('source identity mismatch: '+name);
    const evidence = refs.evidence.filter(e=>e.source_basename===name);
    for(const e of evidence) {
      const r=rows[e.physical_line-1];
      if(crypto.createHash('sha256').update(r.raw).digest('hex')!==e.record_sha256) throw new Error('evidence hash mismatch: '+e.id);
      if(r.timestamp!==e.timestamp_utc || (r.payload.call_id??null)!==e.call_id) throw new Error('evidence locator mismatch: '+e.id);
      if(!e.quote_fragments.every(q=>String(printable(r)).includes(q))) throw new Error('evidence quote mismatch: '+e.id);
    }
    const events = inv.independent_native_events.filter(e=>e.file===name);
    const actualEvents = rows.filter(r=>r.payload?.type==='patch_apply_end');
    if(events.length!==actualEvents.length) throw new Error('event coverage mismatch: '+name);
    for(const e of events) {
      const r=rows[e.line-1];
      if(crypto.createHash('sha256').update(r.raw).digest('hex')!==e.record_sha256) throw new Error('event hash mismatch: '+e.line);
      if(r.payload.call_id!==e.call_id || r.payload.success!==e.success) throw new Error('event identity mismatch: '+e.line);
      if(JSON.stringify(Object.keys(r.payload.changes||{}))!==JSON.stringify(e.files)) throw new Error('event files mismatch: '+e.line);
    }
    console.log(JSON.stringify({file:name,source_identity:'PASS',evidence_records:evidence.length,independent_events:events.length,validation:'PASS'}));
  } else if(mode === 'inventory') {
    console.log(JSON.stringify({file:name,sha256:digest,lines:lines.length}));
    const counts = {};
    for (const r of rows) {
      const p = r.payload || {};
      if (/call$/.test(p.type || '')) counts[p.name] = (counts[p.name] || 0) + 1;
      if ((p.type === 'custom_tool_call' || p.type === 'function_call') && (/apply_patch$/.test(p.name || '') || /tools\.apply_patch\s*\(/.test(String(printable(r))))) {
        const text = String(printable(r));
        const literals = [...text.matchAll(/"(?:\\.|[^"\\])*"/g)].map(m => {try{return JSON.parse(m[0]);}catch{return '';}});
        const decoded = [text,...literals].filter(x => x.includes('*** Begin Patch')).join('\n');
        const files = [...decoded.matchAll(/^\*\*\* (Update|Add|Delete|Move to)(?: File)?: (.+)$/gm)].map(m => ({action:m[1],file:m[2]}));
        const result = rows.find(x => x.line > r.line && x.payload?.call_id === p.call_id && /output$/.test(x.payload?.type || ''));
        const nextPatch = rows.find(x => x.line > r.line && /call$/.test(x.payload?.type || '') && /tools\.apply_patch\s*\(/.test(String(printable(x))));
        const events = rows.filter(x => x.line > r.line && x.line < (nextPatch?.line ?? Infinity) && x.payload?.type === 'patch_apply_end' && (x.line < (result?.line ?? 0) || Object.keys(x.payload.changes || {}).some(f=>files.some(p=>p.file===f))));
        console.log(JSON.stringify({patch_line:r.line,time:r.timestamp,call_id:p.call_id,files,result_line:result?.line,result:result?String(printable(result)).slice(0,180):null,event_association:'temporal_and_path_candidate_only; outer and event call_id namespaces differ; native event is independent write evidence',events:events.map(x=>({line:x.line,call_id:x.payload.call_id,success:x.payload.success,stdout:x.payload.stdout,stderr:x.payload.stderr,changes:Object.keys(x.payload.changes || {})}))}));
      }
    }
    console.log(JSON.stringify({tool_counts:counts}));
  } else if (mode === 'events') {
    for (const r of rows.filter(x=>x.payload?.type === 'patch_apply_end')) {
      const p = r.payload;
      console.log(JSON.stringify({file:name,line:r.line,time:r.timestamp,record_sha256:crypto.createHash('sha256').update(r.raw).digest('hex'),call_id:p.call_id,turn_id:p.turn_id,success:p.success,files:Object.keys(p.changes || {}),stdout:p.stdout,stderr:p.stderr}));
    }
  } else if(mode === 'agents') {
    const seen = new Set();
    for (const r of rows.filter(x=>x.payload?.type === 'sub_agent_activity')) {
      const p=r.payload;
      if (seen.has(p.agent_thread_id)) continue;
      seen.add(p.agent_thread_id);
      console.log(JSON.stringify({file:name,line:r.line,time:r.timestamp,event_id:p.event_id,agent_thread_id:p.agent_thread_id,agent_path:p.agent_path}));
    }
  } else if (mode === 'writes') {
    for (const r of rows.filter(x=>/call$/.test(x.payload?.type || '') && x.payload?.name === 'exec')) {
      const text = printable(r);
      if (/write_text|writeFile|write_bytes|\.write\(|\bcp\s|\bmv\s|\brm\s|sed\s+-i|cat\s*>|tee\s|tools\.apply_patch/.test(text)) show(r);
    }
  } else if (mode === 'lines') {
    for (const token of query.split(',')) {
      const [a,b=a] = token.split('-').map(Number);
      for (const r of rows) if(r.line>=a && r.line<=b) show(r);
    }
  } else if(mode === 'search') {
    const re = new RegExp(query,'i');
    for (const r of rows) {
      if (r.type === 'turn_context' || r.type === 'session_meta') continue;
      if (r.payload?.role === 'developer' || r.payload?.role === 'system') continue;
      const text = String(printable(r));
      const match = re.exec(text);
      if(match) {
        const start = Math.max(0,match.index-150);
        const p = r.payload || {};
        console.log(JSON.stringify({file:name,line:r.line,time:r.timestamp,type:r.type,kind:p.type,role:p.role,channel:p.channel,name:p.name,call_id:p.call_id ?? null,text:text.slice(start,start+limit)}));
      }
    }
  }
}
