"use client";

import { extent } from "d3-array";
import { quadtree as d3quadtree } from "d3-quadtree";
import { scaleLinear } from "d3-scale";
import { select } from "d3-selection";
import { zoom as d3zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { useEffect, useRef } from "react";
import { archmax, type Archetype, type StyleMapPoint } from "../../lib/style-map";

interface Props {
  points: StyleMapPoint[];
  archetypes: Archetype[];
  selectedIndex: number | null;
  highlightedArchetype: number | null;
  onSelect: (index: number) => void;
  onHover: (index: number | null) => void;
}

const DOT_RADIUS = 2.5;
const SELECTED_RADIUS = 5;

export default function StyleMapCanvas({
  points,
  archetypes,
  selectedIndex,
  highlightedArchetype,
  onSelect,
  onHover,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transformRef = useRef<ZoomTransform>(zoomIdentity);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * devicePixelRatio;
    canvas.height = height * devicePixelRatio;

    const xExtent = extent(points, (p) => p.x) as [number, number];
    const yExtent = extent(points, (p) => p.y) as [number, number];
    const xScale = scaleLinear().domain(xExtent).range([40, width - 40]);
    const yScale = scaleLinear().domain(yExtent).range([height - 40, 40]);

    const tree = d3quadtree<StyleMapPoint>()
      .x((p) => xScale(p.x))
      .y((p) => yScale(p.y))
      .addAll(points);

    function draw() {
      const t = transformRef.current;
      ctx!.save();
      ctx!.scale(devicePixelRatio, devicePixelRatio);
      ctx!.clearRect(0, 0, width, height);
      ctx!.translate(t.x, t.y);
      ctx!.scale(t.k, t.k);

      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        const archId = archmax(p);
        const color = archetypes[archId]?.color ?? "#888";
        const isSelected = i === selectedIndex;
        const dimmed = highlightedArchetype !== null && archId !== highlightedArchetype;
        ctx!.beginPath();
        ctx!.arc(
          xScale(p.x),
          yScale(p.y),
          (isSelected ? SELECTED_RADIUS : DOT_RADIUS) / t.k,
          0,
          2 * Math.PI,
        );
        ctx!.fillStyle = color;
        ctx!.globalAlpha = dimmed ? 0.08 : isSelected ? 1 : 0.65;
        ctx!.fill();
        if (isSelected) {
          ctx!.lineWidth = 1.5 / t.k;
          ctx!.strokeStyle = "#F5F5F0";
          ctx!.globalAlpha = 1;
          ctx!.stroke();
        }
      }
      ctx!.restore();
    }

    draw();

    const zoomBehavior = d3zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.5, 20])
      .on("zoom", (event) => {
        transformRef.current = event.transform;
        draw();
      });

    const selection = select(canvas);
    selection.call(zoomBehavior);

    function handleMove(event: MouseEvent) {
      const rect = canvas!.getBoundingClientRect();
      const t = transformRef.current;
      const mx = (event.clientX - rect.left - t.x) / t.k;
      const my = (event.clientY - rect.top - t.y) / t.k;
      const found = tree.find(mx, my, 15 / t.k);
      onHover(found ? points.indexOf(found) : null);
    }
    function handleClick(event: MouseEvent) {
      const rect = canvas!.getBoundingClientRect();
      const t = transformRef.current;
      const mx = (event.clientX - rect.left - t.x) / t.k;
      const my = (event.clientY - rect.top - t.y) / t.k;
      const found = tree.find(mx, my, 15 / t.k);
      if (found) onSelect(points.indexOf(found));
    }
    canvas.addEventListener("mousemove", handleMove);
    canvas.addEventListener("click", handleClick);

    return () => {
      canvas.removeEventListener("mousemove", handleMove);
      canvas.removeEventListener("click", handleClick);
      selection.on(".zoom", null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, archetypes, selectedIndex, highlightedArchetype]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: "100%", height: "100%", cursor: "crosshair", touchAction: "none" }}
    />
  );
}
