"""Display grouping must preserve distinct claims and never create an edge."""

import subprocess
from pathlib import Path


def test_exact_scope_grouping_preserves_claims_edges_and_microseconds():
    page = (
        Path(__file__).resolve().parents[1] / "src/migloop/inquiry/page.html"
    ).read_text(encoding="utf-8")
    helper = page[page.index("    function presentationGraph(") : page.index("    function draw(")]
    assertions = r"""
const assert=require('node:assert/strict');
const node=(id,extra={})=>({id,finding:'A',kind:'agent',key:'worker',
  at:'2026-01-01T00:00:01.000001Z',since:null,exists:true,
  role:'context',reason:id,evidence:['e-'+id],...extra});
const data={nodes:[node('read',{scope:'s-a'}),node('write',{role:'origin',scope:'s-b'}),
  node('source',{kind:'file',key:'/spec'}),node('output',{kind:'file',key:'/out'}),
  node('later',{at:'2026-01-01T00:00:01.000002Z'}),
  node('window',{since:'2026-01-01T00:00:00Z'}),
  node('different-path',{kind:'file',key:'/other/spec'}),
  node('other-finding',{finding:'B'}),
  node('unverified1',{exists:false}),node('unverified2',{exists:false})],
  edges:[{id:'read-edge',finding:'A',from:'source',to:'read',strength:'confirmed'},
    {id:'write-edge',finding:'A',from:'write',to:'output',strength:'candidate'},
    {id:'internal-edge',finding:'A',from:'read',to:'write',strength:'candidate'},
    {id:'self-edge',finding:'A',from:'write',to:'write',strength:'confirmed'}]};
const before=JSON.stringify(data);
data.nodes.forEach(Object.freeze);data.edges.forEach(Object.freeze);
Object.freeze(data.nodes);Object.freeze(data.edges);Object.freeze(data);
const view=presentationGraph(data,'A');
assert.equal(view.nodes.length,8);
assert.deepEqual(view.nodes[0].members.map(n=>n.id),['read','write']);
assert.deepEqual(view.nodes[0].members.map(n=>n.role),['context','origin']);
assert.equal(view.nodes[0].members[1].reason,'write');
assert.deepEqual(view.edges.map(e=>[e.id,e.strength]),data.edges.map(e=>[e.id,e.strength]));
assert.equal(view.edges[0].to,view.edges[1].from);
assert.equal(view.edges[2].from,view.edges[2].to);
assert.equal(view.edges[3].from,view.edges[3].to);
assert.deepEqual(view.edges.map(e=>[e.source_claim,e.target_claim]),data.edges.map(e=>[e.from,e.to]));
assert.deepEqual(presentationGraph(data,'B').nodes[0].members.map(n=>n.id),['other-finding']);
assert.equal(JSON.stringify(data),before);
assert.equal(presentationGraph({...data,edges:[]},'A').edges.length,0);
console.log('grouping invariants passed');
"""
    result = subprocess.run(
        ["node", "-e", helper + assertions],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=True,
    )
    assert "grouping invariants passed" in result.stdout
