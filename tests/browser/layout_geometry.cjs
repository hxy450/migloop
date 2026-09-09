/* Serializable, read-only browser geometry checks. Includes atom nodes AND stubs. */
function readLayoutGeometry() {
  const graph = document.querySelector('#graph');
  const rect = graph.getBoundingClientRect();
  const toolbar = graph.querySelector('.toolbar');
  const viewport = {left:rect.left + graph.clientLeft, right:rect.left + graph.clientLeft + graph.clientWidth,
    top:rect.top + graph.clientTop + (toolbar?.offsetHeight || 0) + 6,
    bottom:rect.top + graph.clientTop + graph.clientHeight};
  const nodes = [...document.querySelectorAll('#canvas .node')].map((element, index) => {
    const r = element.getBoundingClientRect();
    return {id:element.dataset.tid || String(index), text:element.textContent.slice(0, 100),
      left:r.left, right:r.right, top:r.top, bottom:r.bottom,
      atom:!element.classList.contains('leaf')};
  });
  const overlaps = [];
  for (let i=0; i<nodes.length; i++) for (let j=i+1; j<nodes.length; j++) {
    const a=nodes[i], b=nodes[j];
    if (Math.min(a.right,b.right)-Math.max(a.left,b.left)>0.5
        && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>0.5) overlaps.push({a:a.id,b:b.id,aText:a.text,bText:b.text});
  }
  const outside = nodes.filter(n=>n.left<viewport.left-1 || n.right>viewport.right+1
    || n.top<viewport.top-1 || n.bottom>viewport.bottom+1).map(n=>({id:n.id,text:n.text}));
  return {nodeCount:nodes.length, atomCount:nodes.filter(n=>n.atom).length, viewport, overlaps, outside};
}

module.exports = {readLayoutGeometry};
