const svg = d3.select("#graph");
const container = document.getElementById("graph-container");
const tooltip = document.getElementById("tooltip");
const panel = document.getElementById("panel");
const panelContent = document.getElementById("panel-content");
const statsEl = document.getElementById("stats");

const g = svg.append("g");
const linkLayer = g.append("g").attr("class", "links");
const nodeLayer = g.append("g").attr("class", "nodes");

let width = container.clientWidth;
let height = container.clientHeight;
svg.attr("viewBox", [0, 0, width, height]);

const zoom = d3.zoom()
  .scaleExtent([0.15, 6])
  .on("zoom", (event) => g.attr("transform", event.transform));
svg.call(zoom);

let graphData = null;
let colorBy = "instance_of";
let hideIsolated = false;
let selectedNode = null;

const color = d3.scaleOrdinal(d3.schemeTableau10);
const visitScale = d3.scaleSequential(d3.interpolateYlOrRd);

fetch("data/graph.json")
  .then((r) => r.json())
  .then((data) => {
    graphData = data;
    init(data);
  });

function topCategories(nodes, n) {
  const counts = d3.rollup(nodes, (v) => v.length, (d) => d.instance_of || "unknown");
  return new Set(
    Array.from(counts.entries())
      .sort((a, b) => d3.descending(a[1], b[1]))
      .slice(0, n)
      .map((d) => d[0])
  );
}

function init(data) {
  const degree = new Map(data.nodes.map((n) => [n.id, 0]));
  data.edges.forEach((e) => {
    degree.set(e.source, (degree.get(e.source) || 0) + 1);
    degree.set(e.target, (degree.get(e.target) || 0) + 1);
  });
  data.nodes.forEach((n) => (n.degree = degree.get(n.id) || 0));

  const top = topCategories(data.nodes, 12);
  data.nodes.forEach((n) => {
    n.category = top.has(n.instance_of) ? n.instance_of : (n.instance_of ? "other" : "unknown");
  });

  const maxVisits = d3.max(data.nodes, (d) => d.visits) || 1;
  visitScale.domain([1, maxVisits]);

  statsEl.textContent = `${data.nodes.length} articles · ${data.edges.length} connections`;

  const simulation = d3.forceSimulation(data.nodes)
    .force("link", d3.forceLink(data.edges).id((d) => d.id).distance((d) => 140 - Math.min(d.weight * 20, 100)).strength((d) => Math.min(0.15 + d.weight * 0.05, 0.6)))
    .force("charge", d3.forceManyBody().strength(-90))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collide", d3.forceCollide().radius((d) => nodeRadius(d) + 4));

  const link = linkLayer.selectAll("line")
    .data(data.edges)
    .join("line")
    .attr("class", "link")
    .attr("stroke-width", (d) => Math.max(0.6, Math.min(d.weight, 4)))
    .on("mouseenter", (event, d) => showEdgeTooltip(event, d))
    .on("mousemove", (event) => positionTooltip(event))
    .on("mouseleave", hideTooltip);

  const node = nodeLayer.selectAll("g.node")
    .data(data.nodes)
    .join("g")
    .attr("class", "node")
    .call(drag(simulation))
    .on("click", (event, d) => selectNode(d))
    .on("mouseenter", (event, d) => showNodeTooltip(event, d))
    .on("mousemove", (event) => positionTooltip(event))
    .on("mouseleave", hideTooltip);

  node.append("circle")
    .attr("r", nodeRadius)
    .attr("fill", nodeColor);

  node.append("text")
    .text((d) => d.label)
    .attr("dx", (d) => nodeRadius(d) + 3)
    .attr("dy", 3);

  simulation.on("tick", () => {
    link
      .attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
    node.attr("transform", (d) => `translate(${d.x},${d.y})`);
  });

  window.__graph = { link, node, simulation, data };

  document.getElementById("search").addEventListener("input", onSearch);
  document.getElementById("colorBy").addEventListener("change", (e) => {
    colorBy = e.target.value;
    node.select("circle").attr("fill", nodeColor);
  });
  document.getElementById("hideIsolated").addEventListener("change", (e) => {
    hideIsolated = e.target.checked;
    node.classed("dimmed", (d) => hideIsolated && d.degree === 0);
  });
  document.getElementById("panel-close").addEventListener("click", () => {
    selectedNode = null;
    panel.classList.add("hidden");
    clearHighlight();
  });

  window.addEventListener("resize", () => {
    width = container.clientWidth;
    height = container.clientHeight;
    svg.attr("viewBox", [0, 0, width, height]);
    simulation.force("center", d3.forceCenter(width / 2, height / 2));
    simulation.alpha(0.3).restart();
  });
}

function nodeRadius(d) {
  return 4 + Math.sqrt(d.visits || 1) * 2.2;
}

function nodeColor(d) {
  if (colorBy === "visits") return visitScale(d.visits);
  return color(d.category);
}

function drag(simulation) {
  function started(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x; d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x; d.fy = event.y;
  }
  function ended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null; d.fy = null;
  }
  return d3.drag().on("start", started).on("drag", dragged).on("end", ended);
}

function showNodeTooltip(event, d) {
  tooltip.innerHTML = `
    <div class="tt-title">${d.label}</div>
    <div>${d.description || ""}</div>
    <div class="tt-reason">${d.visits} visit${d.visits === 1 ? "" : "s"} · last read ${d.last_seen}</div>
  `;
  tooltip.classList.remove("hidden");
  positionTooltip(event);
}

function showEdgeTooltip(event, d) {
  const reasonsHtml = d.reasons.map((r) => `<div class="tt-reason">• ${r.property}: ${r.value}</div>`).join("");
  tooltip.innerHTML = `
    <div class="tt-title">${d.source.label || d.source} ↔ ${d.target.label || d.target}</div>
    ${reasonsHtml}
  `;
  tooltip.classList.remove("hidden");
  positionTooltip(event);
  d3.select(event.currentTarget).classed("highlighted", true);
  event.currentTarget.addEventListener("mouseleave", () => {
    d3.select(event.currentTarget).classed("highlighted", false);
  }, { once: true });
}

function positionTooltip(event) {
  const rect = container.getBoundingClientRect();
  tooltip.style.left = event.clientX - rect.left + 14 + "px";
  tooltip.style.top = event.clientY - rect.top + 14 + "px";
}

function hideTooltip() {
  tooltip.classList.add("hidden");
}

function onSearch(e) {
  const q = e.target.value.trim().toLowerCase();
  const { node } = window.__graph;
  if (!q) {
    node.classed("dimmed", (d) => hideIsolated && d.degree === 0);
    return;
  }
  node.classed("dimmed", (d) => !d.label.toLowerCase().includes(q));
}

function selectNode(d) {
  selectedNode = d;
  const { data } = window.__graph;
  clearHighlight();

  const connected = data.edges.filter((e) => e.source.id === d.id || e.target.id === d.id);
  const neighborIds = new Set(connected.map((e) => (e.source.id === d.id ? e.target.id : e.source.id)));

  linkLayer.selectAll("line").classed("highlighted", (e) => e.source.id === d.id || e.target.id === d.id);
  nodeLayer.selectAll("g.node").classed("dimmed", (n) => n.id !== d.id && !neighborIds.has(n.id));

  connected.sort((a, b) => d3.descending(a.weight, b.weight));

  const connectionsHtml = connected.map((e) => {
    const other = e.source.id === d.id ? e.target : e.source;
    const reasons = e.reasons.map((r) => `${r.property}: ${r.value}`).join(", ");
    return `
      <div class="connection">
        <div class="conn-title" data-id="${other.id}">${other.label}</div>
        <div class="conn-reasons">${reasons}</div>
      </div>`;
  }).join("");

  panelContent.innerHTML = `
    <h2>${d.label}</h2>
    <div class="desc">${d.description || ""}</div>
    <div class="desc">${d.visits} visit${d.visits === 1 ? "" : "s"} · last read ${d.last_seen}</div>
    <h3>Connected articles (${connected.length})</h3>
    ${connectionsHtml || '<div class="desc">No graph connections — this article stood alone in your history.</div>'}
  `;
  panel.classList.remove("hidden");

  panelContent.querySelectorAll(".conn-title").forEach((el) => {
    el.addEventListener("click", () => {
      const target = data.nodes.find((n) => n.id === el.dataset.id);
      if (target) selectNode(target);
    });
  });
}

function clearHighlight() {
  linkLayer.selectAll("line").classed("highlighted", false);
  nodeLayer.selectAll("g.node").classed("dimmed", (d) => hideIsolated && d.degree === 0);
}
