"""The report seeds the same lossless, lazy temporal tree as manual expansion."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_exact_scope_grouping_preserves_claims_edges_and_microseconds():
    assertions = r"""
const assert = require('node:assert/strict');
const {EvidenceTreeModel, scopeIdentity, visibleRelation} = require('./src/migloop/inquiry/tree.js');
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


def test_inquiry_page_uses_prototype_renderer_not_new_tree_renderer():
    page = (ROOT / "src/migloop/inquiry/page.html").read_text(encoding="utf-8")
    viewer = (ROOT / "src/migloop/inquiry/viewer.js").read_text(encoding="utf-8")
    projection = (ROOT / "src/migloop/inquiry/tree.js").read_text(encoding="utf-8")
    assert "class InquiryTree" not in projection
    assert "document.createElement" not in projection
    for function in (
        "renderTree",
        "addTreeNode",
        "drawEdges",
        "hiliteEdges",
        "head",
        "fileVersionSection",
    ):
        assert f"function {function}(" in viewer
    assert "__INQUIRY_ASSET_BASE__/tree.js" in page
    assert "__INQUIRY_ASSET_BASE__/viewer.js" in page
    assert "__INQUIRY_CONFIG__" in page
    assert '(config.api_base || "") + route' in viewer
    for identifier in ("rail", "canvas", "wires", "side", "reportsDialog"):
        assert f'id="{identifier}"' in page
    for removed in (
        "viewport",
        "structuredReport",
        "queryPanel",
        "restorePaths",
        "rawRecord",
        "askai",
    ):
        assert f'id="{removed}"' not in page


def test_prototype_css_and_presentation_functions_are_retained_verbatim():
    import hashlib
    import re

    page = (ROOT / "src/migloop/inquiry/page.html").read_text(encoding="utf-8")
    viewer = (ROOT / "src/migloop/inquiry/viewer.js").read_text(encoding="utf-8")
    # SHA256 of the original migbot-server template, before the time adapter.
    expected = {
        "css": "90d849c7b8ce7e3103718069f92073766dfcfa1101af779994500e9e3fb26504",
        "el": "e0d6d210f2f38c82b48ac8634c54bab12fad2ed22efb0d02b35d6b67337fa3b0",
        "pill": "b15b833409ceb410b2030b0e00e0fec1581d277755e718dd03a10b4535f52f18",
        "rsec": "90cfbd126fb6196307696488b60e4648acfb705e1aeb9a55d027645958afa7e0",
        "ritem": "ce568082de5c1ef774554aec9ecbe06645cd707a50fb4805d9d05d210bd188ec",
        "vline": "b8b29a5ed4b8eb9d19edac33e76930c71c592b4a1d3a6c7468f440bf3f66d7a9",
        "xtNode": "d280d17fb12391118972e18e082c03dce1f6dff1a7c4ec2adac3e00075e7d176",
        "addKid": "6d4be60ffa2405be90e723e98bc7679a358cb138d252e1ca30fe5b5622b6612e",
        "addRight": "c3ec29355d2001fe6de35684b9f3cdaaa3c8950fc405eb092cf37444fd558e04",
        "collapse": "894fc26f78115d235a7dd1543e5e0c6c656776481b2aec296cf45e35199b8bc7",
        "measure": "07b4f3d7ffcf64535d865247a29351852b0c0c04a0d089c6bfbff40f70196ed8",
        "place": "d74f608509cd5d0937f4b82f357f96d82d993733df9dba2a89307682028554e9",
        "canvasTop": "840f9c340e0f2e4a164fdb2f83742ca683aa52ec03bc3805699b6e9706e8bc1e",
        "applyZoom": "5f9c129903a82f8c0420116a805b9f9ec30f4b2ae223ff565308dc5445ff825c",
        "fitView": "6cdd90d839e0e74c21a2b25f09a45d7af2d71d09022aba50f7c03fd3c2536558",
        "renderTree": "208ef15576b779eadda3597a51ceec64ad0a0dd98aee6d83baa118746689602d",
        "hiliteEdges": "1a8247f06df1a83d5fb2c8e296df15b50af07bb21fc84d8a3c121fefc9139612",
        "head": "d3623bc2a5d08047d04f392264cce06946c1e5058654805360b424459b35db8c",
        "sec": "83641870bb92a272ee54cc8c086c24d430196b829cfd59c7512e12384404dbb8",
        "kv": "f0a13bb6617cac50f471b30b79ec64df4382c9a76651bb1d56feb2b2f3724c85",
        "pills": "7ddc126e2c11beb6d7335514632be68217060da37e9af650991710aa33dfd7df",
        "lnk": "e0ddce049df61653e9b4b54fe319496cadb4503528289fcffc5bd9401ec31975",
        "quote": "0d126e9e2d8bdb0813cfdecdc3a60052e1ec5983c23398b1d1d3d6eb2732b343",
        "quoteLong": "c0b530c3acec5ed32e96bc4f57a350aadb33c328c17a436c9247af5cf4c7fa95",
    }
    for name, sha in expected.items():
        if name == "css":
            content = re.search(r"<style>[\s\S]*?</style>", page).group()
        else:
            start = viewer.index("    function " + name + "(")
            line_end = viewer.index("\n", start)
            end = (
                line_end
                if viewer[start:line_end].endswith("}")
                else viewer.index("\n    }", start) + 6
            )
            content = viewer[start:end].strip()
        assert hashlib.sha256(content.encode()).hexdigest() == sha, name
