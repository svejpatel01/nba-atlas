"use client";

import { useEffect, useRef } from "react";
import { HEX_SIZE_FT, hexCenter, type HexAggregate } from "../../lib/shot-quality";

interface Props {
  hexes: HexAggregate[];
  colorMode: "diff" | "xfg";
  onCourtClick: (xFt: number, yFt: number) => void;
  clickedPoint: { x: number; y: number } | null;
}

// Court in feet: x in [-25, 25] (width), y in [0, 47] (baseline to half
// court) — same bounds as the Python grid (hub/shots/grid.py), so a click
// here maps directly onto the same coordinate space the model was
// evaluated on.
const X_MIN = -25;
const X_MAX = 25;
const Y_MIN = 0;
const Y_MAX = 47;
const PADDING = 20;

function diffColor(diff: number): string {
  // Diverging red (worse than expected) -> gray -> blue (better than expected).
  const clamped = Math.max(-0.2, Math.min(0.2, diff));
  const t = clamped / 0.2; // -1..1
  if (t >= 0) {
    const g = Math.round(240 - t * 120);
    return `rgb(${Math.round(240 - t * 190)}, ${g}, ${Math.round(240 - t * 40)})`;
  }
  const g = Math.round(240 + t * 120);
  return `rgb(${Math.round(240 + t * -10)}, ${g}, ${Math.round(240 + t * 190)})`;
}

function xfgColor(xfg: number): string {
  // Sequential scale: low xFG (light) -> high xFG (dark blue).
  const t = Math.max(0, Math.min(1, xfg / 0.7));
  return `rgb(${Math.round(235 - t * 200)}, ${Math.round(240 - t * 140)}, ${Math.round(250 - t * 60)})`;
}

export default function CourtCanvas({ hexes, colorMode, onCourtClick, clickedPoint }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    canvas.width = width * devicePixelRatio;
    canvas.height = height * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);

    const scale = Math.min((width - 2 * PADDING) / (X_MAX - X_MIN), (height - 2 * PADDING) / (Y_MAX - Y_MIN));
    const toPx = (xFt: number, yFt: number): [number, number] => [
      width / 2 + xFt * scale,
      PADDING + yFt * scale,
    ];

    ctx.clearRect(0, 0, width, height);

    // Court lines.
    ctx.strokeStyle = "#5A5F7A";
    ctx.lineWidth = 1.5;

    // Baseline.
    let [bx1, by1] = toPx(X_MIN, Y_MIN);
    let [bx2] = toPx(X_MAX, Y_MIN);
    ctx.beginPath();
    ctx.moveTo(bx1, by1);
    ctx.lineTo(bx2, by1);
    ctx.stroke();

    // Hoop.
    const [hoopX, hoopY] = toPx(0, 0);
    ctx.beginPath();
    ctx.arc(hoopX, hoopY, 0.75 * scale, 0, 2 * Math.PI);
    ctx.stroke();

    // Lane (16 ft wide, 19 ft deep).
    const [laneX1, laneY1] = toPx(-8, 0);
    const [laneX2, laneY2] = toPx(8, 19);
    ctx.strokeRect(laneX1, laneY1, laneX2 - laneX1, laneY2 - laneY1);

    // Free-throw circle.
    const [ftX, ftY] = toPx(0, 19);
    ctx.beginPath();
    ctx.arc(ftX, ftY, 6 * scale, 0, 2 * Math.PI);
    ctx.stroke();

    // Three-point line: corners (straight to 14ft) + arc (23.75ft radius).
    ctx.beginPath();
    const [lc1x, lc1y] = toPx(-22, 0);
    const [lc2x, lc2y] = toPx(-22, 14);
    ctx.moveTo(lc1x, lc1y);
    ctx.lineTo(lc2x, lc2y);
    ctx.stroke();
    ctx.beginPath();
    const [rc1x, rc1y] = toPx(22, 0);
    const [rc2x, rc2y] = toPx(22, 14);
    ctx.moveTo(rc1x, rc1y);
    ctx.lineTo(rc2x, rc2y);
    ctx.stroke();
    ctx.beginPath();
    const [arcCx, arcCy] = toPx(0, 0);
    const startAngle = Math.acos(22 / 23.75);
    ctx.arc(arcCx, arcCy, 23.75 * scale, Math.PI / 2 - startAngle, Math.PI / 2 + startAngle);
    ctx.stroke();

    [bx1, by1] = toPx(X_MIN, Y_MIN);
    [bx2] = toPx(X_MAX, Y_MIN);

    // Hexagons.
    const maxAttempts = Math.max(1, ...hexes.map((h) => h.attempts));
    for (const hex of hexes) {
      const [xFt, yFt] = hexCenter(hex.hex_id);
      if (xFt < X_MIN || xFt > X_MAX || yFt < Y_MIN || yFt > Y_MAX) continue;
      const [cx, cy] = toPx(xFt, yFt);
      const fgPct = hex.makes / hex.attempts;
      const xfgPct = hex.xfg_sum / hex.attempts;
      const color = colorMode === "diff" ? diffColor(fgPct - xfgPct) : xfgColor(xfgPct);
      const sizeFrac = 0.4 + 0.6 * Math.sqrt(hex.attempts / maxAttempts);
      const r = HEX_SIZE_FT * scale * sizeFrac;

      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 180) * (60 * i);
        const px = cx + r * Math.cos(angle);
        const py = cy + r * Math.sin(angle);
        if (i === 0) ctx.moveTo(px, py);
        else ctx.lineTo(px, py);
      }
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    }

    if (clickedPoint) {
      const [cx, cy] = toPx(clickedPoint.x, clickedPoint.y);
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, 2 * Math.PI);
      ctx.strokeStyle = "#FF6B35";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    function handleClick(event: MouseEvent) {
      const rect = canvas!.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const xFt = (px - width / 2) / scale;
      const yFt = (py - PADDING) / scale;
      if (xFt >= X_MIN && xFt <= X_MAX && yFt >= Y_MIN && yFt <= Y_MAX) {
        onCourtClick(xFt, yFt);
      }
    }
    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [hexes, colorMode, onCourtClick, clickedPoint]);

  return <canvas ref={canvasRef} style={{ width: "100%", height: "100%", cursor: "crosshair" }} />;
}
