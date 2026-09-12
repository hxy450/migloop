"""The report seeds the same lossless, lazy temporal tree as manual expansion."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exact_scope_grouping_preserves_claims_edges_and_microseconds():
    assertions = r"""
const assert = require('node:assert/strict');
const {EvidenceTreeModel, scopeIdentity, measureTree, GEOMETRY, visibleRelation} = require('./src/migloop/inquiry/tree.js');
const at='2026-01-01T00:00:01.000001Z';
const root={kind:'file',key:'/out',at,since:null};
const row=(id,kind,key,extra={})=>({id,relation:kind==='agent'?'write':'read',
  at,strength:'confirmed',source:'indexed',evidence:['e-12345678'],claim:id,
  node:{kind,key,at,since:null},...extra});
const writer=row('native:w','agent','worker');
const input=row('native:r','file','/full/path/spec');
const candidate=row('model:c','file','/candidate',{strength:'candidate',source:'model_review'});
const lexical={...candidate,id:'native:guess',source:'indexed'};
assert(!visibleRelation(lexical),'ordinary candidates stay out of the human tree');
assert(visibleRelation(candidate),'reviewed relations with evidence remain visible');
assert(!visibleRelation({...candidate,evidence:[]}), 'unsubstantiated model edge is hidden');
assert(!visibleRelation({...writer,time_unknown:true}), 'undated effects are not confirmed temporal edges');
const original={id:'A:origin',finding:'A',kind:'file',key:'/full/path/spec',
  at:'2026-01-01T00:00:09Z',since:'2026-01-01T00:00:00Z',exists:true,
  scope:'s-original',role:'origin',reason:'Original reason',evidence:['e-abcdef12']};
const report={nodes:[original,{...original,id:'B:origin',finding:'B',reason:'Second reason'}],
 tree:{root,paths:[
  {finding:'A',node:'A:origin',status:'native',steps:[writer,input]},
  {finding:'B',node:'B:origin',status:'native',steps:[writer,input]},
  {finding:'A',node:'A:origin',status:'model_review',steps:[writer,candidate]},
  {finding:'C',node:'C:origin',status:'unclosed',steps:[row('bad','agent','ghost')],diagnostic:'Missing source'},
 ]}};
const before=JSON.stringify(report);
const tree=new EvidenceTreeModel(root); tree.seed(report);
assert.equal(tree.insert(tree.root,lexical),null,'manual expansion cannot add lexical candidates');
const hidden=new EvidenceTreeModel(root);
hidden.seed({nodes:[original],tree:{paths:[{node:original.id,status:'candidate',steps:[writer,lexical,input]}]}});
assert.equal(hidden.nodes.size,1,'hidden middle edge cannot reconnect surrounding confirmed edges');
assert.equal(hidden.unclosed.length,1);
assert.equal(tree.root.children.length,1,'shared report prefixes merge');
const worker=tree.root.children[0];
assert.deepEqual(worker.children[0].claims.map(n=>n.id),['A:origin','B:origin']);
assert.equal(worker.children[0].claims[0].scope,'s-original');
assert.equal(worker.children[0].claims[0].at,'2026-01-01T00:00:09Z');
assert.equal(worker.children[0].coordinate.at,at,'query coordinate does not rewrite original claim');
assert.equal(tree.insert(tree.root,writer),worker,'manual and seeded row have same identity');
assert(worker.origins.has('report') && worker.origins.has('manual'));
const independent=tree.insert(tree.root,{...writer,id:'native:w2'});
assert.notEqual(independent,worker,'same-second operations remain separate');
const later=tree.insert(worker,{...input,id:'native:r2',node:{...input.node,at:'2026-01-01T00:00:01.000002Z'}});
assert.notEqual(scopeIdentity(later.coordinate),scopeIdentity(input.node),'microseconds remain exact');
const otherPath=tree.insert(worker,{...input,id:'native:r3',node:{...input.node,key:'/other/path/spec'}});
assert.notEqual(scopeIdentity(otherPath.coordinate),scopeIdentity(input.node),'basenames are not identity');
const cycle=tree.insert(worker,row('native:cycle','file','/out'));
assert.equal(cycle.reference,tree.root.id,'ancestor coordinate terminates cycles');
assert.equal(tree.unclosed.length,1);
assert(![...tree.nodes.values()].some(n=>n.coordinate.key==='ghost'),'unclosed paths draw no invented nodes');
assert.equal(worker.children[1].row.strength,'candidate');
assert.equal(worker.children[1].row.source,'model_review');
const separate=new EvidenceTreeModel(root); separate.seed(report,'B');
assert.equal(separate.root.children[0].children.length,1,'finding filter only seeds its own path');
assert.deepEqual(separate.root.children[0].children[0].claims.map(n=>n.id),['B:origin']);
const invalid=new EvidenceTreeModel(root);
invalid.seed({nodes:[],tree:{paths:[{status:'native',steps:[writer,{...input,strength:'unknown'}]}]}});
assert.equal(invalid.nodes.size,1,'invalid path cannot leave a partial fake branch');
assert.equal(invalid.unclosed.length,1);
const anchored=new EvidenceTreeModel(root);
anchored.seed({nodes:[original],tree:{paths:[{finding:'A',node:'A:origin',status:'model_review',steps:[],anchor:candidate}]}});
assert.equal(anchored.nodes.size,1,'root evidence does not invent a problematic writer');
assert.equal(anchored.root.anchors[0].row.strength,'candidate');
assert.equal(anchored.root.anchors[0].row.source,'model_review');
const repaired=new EvidenceTreeModel(root);
const repair={...writer,id:'native:repair',strength:'candidate'};
repaired.seed({nodes:[],tree:{paths:[
  {finding:'A',status:'candidate',steps:[],repair_anchor:repair},
  {finding:'B',status:'candidate',steps:[],repair_anchor:repair},
]}});
assert.equal(repaired.nodes.size,1,'repair evidence does not create an attributed node');
assert.equal(repaired.root.repairAnchors.length,1,'same repair evidence deduplicates across findings');
assert.deepEqual([...repaired.root.repairAnchors[0].findings],['A','B']);
assert.equal(repaired.root.repairAnchors[0].row.strength,'candidate');
const disconnected=new EvidenceTreeModel(root);
disconnected.seed({nodes:[{...original,...root,id:'unclosed'}],tree:{paths:[{node:'unclosed',status:'unclosed',steps:[]}]}});
assert.equal(disconnected.root.claims.length,0,'unclosed attribution stays in audit even at a shared coordinate');
assert.equal(JSON.stringify(report),before,'original report is immutable');
worker.collapsed=true;
assert(!tree.visible().some(r=>r.node===later));
worker.collapsed=false;
const rights=tree.insert(tree.root,row('native:reader','agent','reader',{relation:'read'}),'manual','downstream');
assert.equal(tree.rights.length,1);
assert(rights.isRight && !tree.root.children.includes(rights));
assert.equal(tree.insert(worker,writer,'manual','downstream'),null,'only root has right-side projections');
const layout=measureTree(tree);
assert.deepEqual(GEOMETRY,{width:196,height:30,gapY:8,gapX:74,top:34,left:24});
assert(layout.positions.get(rights.id).x>layout.positions.get(tree.root.id).x);
assert(layout.positions.get(worker.id).x<layout.positions.get(tree.root.id).x);
const columns=new Map();
for(const {node,depth} of layout.visible){
  const p=layout.positions.get(node.id);assert(p.y>=34);
  if(!columns.has(depth))columns.set(depth,[]);columns.get(depth).push(p.y);
}
for(const ys of columns.values()){
  ys.sort((a,b)=>a-b);for(let i=1;i<ys.length;i++)assert(ys[i]-ys[i-1]>=38,'original compact rows do not overlap');
}
tree.root.collapsed=true;
assert.equal(tree.visible().length,1,'collapse hides both sides without inventing new state');
console.log('temporal tree invariants passed');
"""
    result = subprocess.run(
        ["node", "-e", assertions],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    )
    assert "temporal tree invariants passed" in result.stdout


def test_inquiry_page_has_only_the_shared_tree_renderer():
    page = (ROOT / "src/migloop/inquiry/page.html").read_text(encoding="utf-8")
    viewer = (ROOT / "src/migloop/inquiry/viewer.js").read_text(encoding="utf-8")
    assert "function draw(" not in page
    assert "function presentationGraph(" not in page
    assert "new InquiryEvidenceTree.InquiryTree(" in viewer
    assert "__INQUIRY_ASSET_BASE__/tree.js" in page
    assert "__INQUIRY_ASSET_BASE__/viewer.js" in page
    assert "__INQUIRY_CONFIG__" in page
    assert '(config.api_base || "") + route' in viewer
    for identifier in ("rail", "viewport", "side", "reportsDialog", "load"):
        assert f'id="{identifier}"' in page
    for removed in ("structuredReport", "queryPanel", "restorePaths", "rawRecord"):
        assert f'id="{removed}"' not in page
