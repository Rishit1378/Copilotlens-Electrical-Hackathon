"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  MagnifyingGlassIcon,
  ArrowPathIcon,
  CpuChipIcon,
  InformationCircleIcon,
  CubeIcon,
} from "@heroicons/react/24/outline";

interface GraphNode {
  id: string;
  label?: string;
  is_circular?: boolean;
  is_hub?: boolean;
  imported_by_count?: number;
  imports_count?: number;
  centrality?: number;
}

interface GraphEdge {
  source: string;
  target: string;
}

interface DependencyGraph {
  nodes?: GraphNode[];
  edges?: GraphEdge[];
  circular?: string[][];
}

interface HotspotItem {
  path?: string;
}

interface SelectedNode extends GraphNode {
  nodeType?: string;
}

interface VisDataSet<T> {
  clear(): void;
  add(items: T[]): void;
}

interface VisNodeData {
  id: string;
  label: string;
  title: string;
  value: number;
  size: number;
  color: {
    background: string;
    border: string;
    highlight: { background: string; border: string };
    hover: { background: string; border: string };
  };
  font: {
    color: string;
    size: number;
    face: string;
    background: string;
    strokeWidth: number;
  };
  raw: SelectedNode;
}

interface VisEdgeData {
  from: string;
  to: string;
  arrows: { to: { enabled: boolean; scaleFactor: number } };
  color: { color: string; highlight: string; hover: string };
  width: number;
  smooth: { type: string };
}

interface VisApi {
  DataSet: new <T>(items: T[]) => VisDataSet<T>;
  Network: new (
    container: HTMLDivElement,
    data: { nodes: VisDataSet<VisNodeData>; edges: VisDataSet<VisEdgeData> },
    options: Record<string, unknown>
  ) => {
    destroy: () => void;
    on: (event: string, handler: (params: { nodes: string[] }) => void) => void;
    selectNodes: (ids: string[]) => void;
    unselectNodes: () => void;
    fit: (options?: { animation?: boolean }) => void;
  };
}

interface Neo4jCanvasProps {
  depGraph: DependencyGraph;
  hotspots: HotspotItem[];
}

export function Neo4jCanvas({ depGraph, hotspots }: Neo4jCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<InstanceType<VisApi["Network"]> | null>(null);
  const nodesDataRef = useRef<VisDataSet<VisNodeData> | null>(null);
  const edgesDataRef = useRef<VisDataSet<VisEdgeData> | null>(null);
  const nodesIndexRef = useRef<Map<string, VisNodeData>>(new Map());
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const rawNodes = useMemo(() => depGraph.nodes || [], [depGraph.nodes]);
  const rawEdges = useMemo(() => depGraph.edges || [], [depGraph.edges]);
  const hotspotPaths = useMemo(() => new Set(hotspots.map((h) => h.path)), [hotspots]);
  const circularSet = useMemo(() => new Set((depGraph.circular || []).flat()), [depGraph.circular]);

  const buildVisNodes = (nodes: GraphNode[]): VisNodeData[] =>
    nodes.map((n) => {
      const isHot = hotspotPaths.has(n.id);
      const isCircular = n.is_circular || circularSet.has(n.id);
      const isHub = n.is_hub || (n.imported_by_count ?? 0) >= 5;

      let colorBg = "#ffffff";
      let colorBorder = "rgba(15, 23, 42, 0.14)";
      let nodeType = "Module";

      if (isCircular) {
        colorBg = "#fff7ed";
        colorBorder = "#ea580c";
        nodeType = "Circular";
      } else if (isHot) {
        colorBg = "#eef4ff";
        colorBorder = "#1d4ed8";
        nodeType = "Hotspot";
      } else if (isHub) {
        colorBg = "#f8fafc";
        colorBorder = "#475569";
        nodeType = "Hub";
      }

      const sizeVal = Math.max(16, Math.min(34, 16 + (n.imported_by_count || 0) * 3));

      return {
        id: n.id,
        label: String(n.label ?? n.id.split("/").pop() ?? n.id),
        title: `${n.id} | Imported By: ${n.imported_by_count ?? 0}`,
        value: sizeVal,
        size: sizeVal,
        color: {
          background: colorBg,
          border: colorBorder,
          highlight: { background: "#ffffff", border: "#0f172a" },
          hover: { background: "#ffffff", border: "#0f172a" },
        },
        font: {
          color: "#0f172a",
          size: 11,
          face: "Inter, SF Pro Text, sans-serif",
          background: "rgba(255,255,255,0.92)",
          strokeWidth: 0,
        },
        raw: { ...n, nodeType },
      };
    });

  const buildVisEdges = (edges: GraphEdge[]): VisEdgeData[] =>
    edges.map((e) => ({
      from: e.source,
      to: e.target,
      arrows: { to: { enabled: true, scaleFactor: 0.9 } },
      color: {
        color: "rgba(15,23,42,0.42)",
        highlight: "#0071e3",
        hover: "#0f172a",
      },
      width: 2.4,
      smooth: { type: "continuous" },
    }));

  useEffect(() => {
    if (!containerRef.current || typeof window === "undefined") return;

    const visApi = (window as Window & { vis?: VisApi }).vis;
    if (!visApi || !visApi.Network || !visApi.DataSet) return;

    if (!nodesDataRef.current) {
      nodesDataRef.current = new visApi.DataSet<VisNodeData>([]);
    }
    if (!edgesDataRef.current) {
      edgesDataRef.current = new visApi.DataSet<VisEdgeData>([]);
    }

    const visNodes = buildVisNodes(rawNodes);
    const visEdges = buildVisEdges(rawEdges);
    nodesIndexRef.current = new Map(visNodes.map((node) => [node.id, node]));

    nodesDataRef.current.clear();
    edgesDataRef.current.clear();
    nodesDataRef.current.add(visNodes);
    edgesDataRef.current.add(visEdges);

    if (!networkRef.current) {
      networkRef.current = new visApi.Network(
        containerRef.current,
        { nodes: nodesDataRef.current, edges: edgesDataRef.current },
        {
          nodes: {
            shape: "dot",
            borderWidth: 1.5,
            borderWidthSelected: 3,
            shadow: { enabled: true, color: "rgba(15,23,42,0.14)", size: 12, x: 0, y: 4 },
          },
          physics: {
            solver: "forceAtlas2Based",
            forceAtlas2Based: {
              gravitationalConstant: -58,
              centralGravity: 0.01,
              springLength: 126,
              springConstant: 0.05,
            },
            maxVelocity: 50,
            minVelocity: 0.1,
            stabilization: { iterations: 100 },
          },
          interaction: {
            hover: true,
            tooltipDelay: 150,
            dragNodes: true,
            zoomView: true,
          },
          edges: {
            smooth: { type: "dynamic" },
            width: 2.2,
            color: {
              color: "rgba(15,23,42,0.42)",
              highlight: "#0071e3",
              hover: "#0f172a",
            },
          },
          layout: {
            improvedLayout: true,
          },
        }
      );

      networkRef.current.on("selectNode", function (params: { nodes: string[] }) {
        const selectedId = params.nodes[0];
        const target = nodesIndexRef.current.get(selectedId);
        if (target) {
          setSelectedNode(target.raw);
        }
      });

      networkRef.current.on("deselectNode", function () {
        setSelectedNode(null);
      });
    }

    if (selectedNode && !nodesIndexRef.current.has(selectedNode.id)) {
      setSelectedNode(null);
    }
  }, [rawNodes, rawEdges, hotspotPaths, circularSet, selectedNode]);

  const handleSearch = (val: string) => {
    setSearchQuery(val);
    if (!networkRef.current) return;
    if (!val) {
      networkRef.current.unselectNodes();
      return;
    }
    const match = rawNodes.find((n) => n.id.toLowerCase().includes(val.toLowerCase()));
    if (match) {
      networkRef.current.selectNodes([match.id]);
      const found = nodesIndexRef.current.get(match.id);
      if (found) setSelectedNode(found.raw);
    }
  };

  const handleReset = () => {
    if (networkRef.current) {
      networkRef.current.fit({ animation: true });
      networkRef.current.unselectNodes();
      setSelectedNode(null);
      setSearchQuery("");
    }
  };

  return (
    <div className="subtle-card p-5 space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <CpuChipIcon className="w-5 h-5 text-[#1d4ed8]" />
            <h2 className="text-lg font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              Dependency graph
            </h2>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">
            Live module imports with persistent layout, highlighted hotspots, and circular relationships.
          </p>
          <div className="flex flex-wrap gap-2 pt-1 text-xs text-[var(--text-secondary)]">
            <span className="apple-chip rounded-full px-3 py-1.5">{rawNodes.length} nodes</span>
            <span className="apple-chip rounded-full px-3 py-1.5">{rawEdges.length} edges</span>
            <span className="apple-chip rounded-full px-3 py-1.5">{hotspots.length} hotspots</span>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="relative flex-1 sm:w-72">
            <MagnifyingGlassIcon className="absolute left-3 top-2.5 w-4 h-4 text-[var(--text-muted)]" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => handleSearch(e.target.value)}
              placeholder="Search node..."
              className="w-full rounded-full border border-[rgba(15,23,42,0.08)] bg-white/90 py-2.5 pl-9 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] shadow-sm outline-none transition-all focus:border-[#0071e3]/30 focus:ring-4 focus:ring-[#0071e3]/10"
            />
          </div>
          <button
            onClick={handleReset}
            className="inline-flex items-center gap-1.5 rounded-full bg-[#0f172a] px-4 py-2.5 text-xs font-semibold text-white transition-all hover:-translate-y-0.5 hover:bg-[#1e293b]"
          >
            <ArrowPathIcon className="w-3.5 h-3.5" /> Fit
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div
          ref={containerRef}
          style={{ height: "520px", width: "100%" }}
          className="lg:col-span-3 relative overflow-hidden rounded-3xl border border-[rgba(15,23,42,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(241,245,249,0.92))] shadow-[0_18px_50px_rgba(15,23,42,0.08)]"
        >
          <div className="pointer-events-none absolute inset-0 soft-grid opacity-45" />
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,113,227,0.05),transparent_56%)]" />
        </div>

        <div className="max-h-[520px] overflow-y-auto space-y-4 rounded-3xl border border-[rgba(15,23,42,0.08)] bg-white/82 p-4 shadow-[0_18px_50px_rgba(15,23,42,0.06)]">
          <div className="border-b border-[rgba(15,23,42,0.08)] pb-3">
            <span className="text-[10px] font-semibold uppercase tracking-[0.24em] text-[var(--text-muted)]">
              Node Inspector
            </span>
            <h3 className="mt-1 truncate text-sm font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
              {selectedNode ? selectedNode.id : "No Node Selected"}
            </h3>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {selectedNode
                ? `Category: ${selectedNode.nodeType || "Module"}`
                : "Click any node to inspect coupling"}
            </p>
          </div>

          {selectedNode ? (
            <div className="space-y-3 text-xs">
              <div className="space-y-2 rounded-2xl border border-[rgba(15,23,42,0.08)] bg-white p-3.5">
                <div className="flex justify-between gap-3">
                  <span className="text-[var(--text-secondary)]">Imported By</span>
                  <span className="font-semibold text-[var(--text-primary)]">
                    {selectedNode.imported_by_count ?? 0} modules
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-[var(--text-secondary)]">Imports</span>
                  <span className="font-semibold text-[var(--text-primary)]">
                    {selectedNode.imports_count ?? 0} modules
                  </span>
                </div>
                <div className="flex justify-between gap-3">
                  <span className="text-[var(--text-secondary)]">Centrality</span>
                  <span className="font-semibold text-[var(--text-primary)]">
                    {selectedNode.centrality ?? 0}
                  </span>
                </div>
              </div>

              <div className="flex gap-2 rounded-2xl border border-[#bfdbfe] bg-[#eff6ff] p-3 text-xs leading-relaxed text-[var(--text-primary)]">
                <InformationCircleIcon className="w-4 h-4 shrink-0 text-[#1d4ed8]" />
                <span>
                  {(selectedNode.imported_by_count ?? 0) > 3
                    ? "High dependency coupling. Exercise care when modifying signature interfaces."
                    : "Isolated module node. Low blast radius."}
                </span>
              </div>
            </div>
          ) : (
            <div className="h-48 flex flex-col items-center justify-center gap-2 text-center text-[var(--text-secondary)]">
              <CubeIcon className="w-8 h-8 opacity-50 text-[#1d4ed8]" />
              <span className="text-xs font-medium">Click or drag any node in the canvas</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
