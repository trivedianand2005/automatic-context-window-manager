import dagre from "@dagrejs/dagre";
import { Background, Controls, MarkerType, ReactFlow } from "@xyflow/react";
import type { Edge, Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { basename, dirname } from "../lib/format";
import type { GraphEdge, GraphNode } from "../lib/types";

const TYPE_COLOR: Record<string, string> = {
  source: "#1e3a5f",
  test: "#14432f",
  config: "#4a3a12",
  docs: "#3b2a5c",
};
const NODE_W = 210;
const NODE_H = 46;

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Paths to emphasise (e.g. the selected context). */
  highlight?: Set<string>;
  /** If set, only show these paths plus their direct neighbours. */
  focus?: Set<string>;
  onSelect?: (path: string) => void;
  height?: number;
}

/** Interactive, auto-laid-out file dependency graph (dagre left-to-right). */
export function DependencyGraph({ nodes, edges, highlight, focus, onSelect, height = 520 }: Props) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const fileNodes = nodes.filter((n) => n.kind === "file");
    let visible = new Set(fileNodes.map((n) => n.id));
    if (focus && focus.size) {
      const focusIds = new Set([...focus].map((p) => `file:${p}`));
      visible = new Set(focusIds);
      for (const e of edges) {
        if (focusIds.has(e.source)) visible.add(e.target);
        if (focusIds.has(e.target)) visible.add(e.source);
      }
    } else {
      // Hide isolated files (no relationships) to keep the overview readable.
      const connected = new Set(edges.flatMap((e) => [e.source, e.target]));
      visible = new Set([...visible].filter((id) => connected.has(id)));
    }
    const shownEdges = edges.filter((e) => visible.has(e.source) && visible.has(e.target));

    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 18, ranksep: 70 });
    g.setDefaultEdgeLabel(() => ({}));
    for (const id of visible) g.setNode(id, { width: NODE_W, height: NODE_H });
    for (const e of shownEdges) g.setEdge(e.source, e.target);
    dagre.layout(g);

    const byId = new Map(fileNodes.map((n) => [n.id, n]));
    const rfNodes: Node[] = [...visible].map((id) => {
      const n = byId.get(id)!;
      const pos = g.node(id);
      const hot = highlight?.has(n.path);
      return {
        id,
        position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
        data: {
          label: (
            <div className="text-left leading-tight" title={n.path}>
              <div className="truncate text-[12px] font-medium text-zinc-50">{basename(n.path)}</div>
              <div className="truncate text-[10px] text-zinc-400">{dirname(n.path) || "./"}</div>
            </div>
          ),
        },
        style: {
          width: NODE_W,
          background: TYPE_COLOR[n.file_type] ?? "#27272a",
          border: hot ? "2px solid #38bdf8" : "1px solid #3f3f46",
          borderRadius: 8,
          padding: "6px 10px",
          boxShadow: hot ? "0 0 0 3px rgba(56,189,248,0.2)" : undefined,
          opacity: highlight && highlight.size && !hot ? 0.55 : 1,
        },
      };
    });
    const dash: Record<string, string | undefined> = { high: undefined, medium: "6 4", low: "2 4" };
    // Edge labels only when the view is small enough to read them.
    const showLabels = shownEdges.length <= 24;
    const rfEdges: Edge[] = shownEdges.map((e, i) => ({
      id: `${e.source}->${e.target}-${i}`,
      source: e.source,
      target: e.target,
      label: showLabels ? e.relation : undefined,
      labelStyle: { fill: "#a1a1aa", fontSize: 10 },
      labelBgStyle: { fill: "#09090b" },
      style: { stroke: "#71717a", strokeWidth: 1.5, strokeDasharray: dash[e.confidence] },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#71717a", width: 16, height: 16 },
    }));
    return { rfNodes, rfEdges };
  }, [nodes, edges, highlight, focus]);

  if (!rfNodes.length) {
    return <div className="py-10 text-center text-sm text-zinc-500">No dependency relationships to show.</div>;
  }
  return (
    <div style={{ height }} className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        minZoom={0.15}
        nodesConnectable={false}
        nodesDraggable
        colorMode="dark"
        onNodeClick={(_, node) => onSelect?.(node.id.replace(/^file:/, ""))}
      >
        <Background color="#27272a" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function GraphLegend() {
  return (
    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-400">
      {Object.entries(TYPE_COLOR).map(([t, c]) => (
        <span key={t} className="flex items-center gap-1.5">
          <span className="inline-block size-3 rounded-sm border border-zinc-600" style={{ background: c }} /> {t}
        </span>
      ))}
      <span>— solid: high confidence</span>
      <span>- - dashed: medium</span>
      <span>··· dotted: low</span>
    </div>
  );
}
