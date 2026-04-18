'use client';

import { useState, useEffect, useRef } from 'react';
import { Lang } from '../lib/i18n';

export interface GridControlChartProps {
  low: number;
  high: number;
  current: number;
  gridCount: number;
  lowerPct: number;
  upperPct: number;
  mode?: 'normal' | 'infinity';
  lang?: Lang;
  onDrag?: (newLower: number, newUpper: number) => void;
  onCommit?: (newLower: number, newUpper: number) => void;
  readOnly?: boolean;
}

export default function GridControlChart({
  low, high, current, gridCount,
  lowerPct, upperPct, mode = 'normal', lang = 'en',
  onDrag, onCommit, readOnly = false,
}: GridControlChartProps) {
  const ar = lang === 'ar';
  const svgRef = useRef<SVGSVGElement>(null);

  const dragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0, lp: lowerPct, up: upperPct });
  const [isDragging, setIsDragging] = useState(false);
  const [liveLower, setLiveLower] = useState(lowerPct);
  const [liveUpper, setLiveUpper] = useState(upperPct);

  useEffect(() => {
    if (!dragging.current) { setLiveLower(lowerPct); setLiveUpper(upperPct); }
  }, [lowerPct, upperPct]);

  const W = 360, H = 200;
  const PAD = { t: 18, b: 18, l: 10, r: 10 };
  const innerH = H - PAD.t - PAD.b;

  const py = (price: number) => {
    if (high <= low) return H / 2;
    return PAD.t + ((high - price) / (high - low)) * innerH;
  };

  const yCur = Math.min(Math.max(py(current), PAD.t + 2), H - PAD.b - 2);
  const circleCX = W / 2;

  const getSVGPoint = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const rect = svg.getBoundingClientRect();
    return {
      x: ((clientX - rect.left) / rect.width) * W,
      y: ((clientY - rect.top) / rect.height) * H,
    };
  };

  const onPointerDown = (e: React.PointerEvent<SVGCircleElement>) => {
    if (readOnly) return;
    e.preventDefault();
    (e.target as Element).setPointerCapture(e.pointerId);
    const pt = getSVGPoint(e.clientX, e.clientY);
    dragging.current = true;
    dragStart.current = { x: pt.x, y: pt.y, lp: lowerPct, up: upperPct };
    setIsDragging(true);
  };

  const onPointerMove = (e: React.PointerEvent<SVGCircleElement>) => {
    if (!dragging.current) return;
    e.preventDefault();
    const pt = getSVGPoint(e.clientX, e.clientY);
    const dx = pt.x - dragStart.current.x;
    const dy = pt.y - dragStart.current.y;

    const spreadDelta = -dy * 0.08;
    const shiftDelta  =  dx * 0.06;

    const newLower = Math.max(0.5, dragStart.current.lp + spreadDelta - shiftDelta);
    const newUpper = mode === 'infinity'
      ? dragStart.current.up
      : Math.max(0.5, dragStart.current.up + spreadDelta + shiftDelta);

    setLiveLower(newLower);
    setLiveUpper(newUpper);
    onDrag?.(newLower, newUpper);
  };

  const onPointerUp = () => {
    if (!dragging.current) return;
    dragging.current = false;
    setIsDragging(false);
    onCommit?.(liveLower, liveUpper);
  };

  const dispHigh = current > 0 ? current * (1 + liveUpper / 100) : high;
  const dispLow  = current > 0 ? current * (1 - liveLower / 100) : low;
  const dispPyHigh = current > 0 ? py(dispHigh) : py(high);
  const dispPyLow  = current > 0 ? py(dispLow)  : py(low);
  const dispCircleCY = (dispPyHigh + dispPyLow) / 2;

  const liveGridCount = gridCount || 10;
  const liveStep = (dispHigh - dispLow) / Math.max(liveGridCount - 1, 1);
  const liveLevels = Array.from({ length: liveGridCount }, (_, i) => dispLow + i * liveStep);

  const spreadChange = (liveUpper + liveLower) - (upperPct + lowerPct);
  const badgeText = isDragging
    ? (spreadChange >= 0 ? `+${spreadChange.toFixed(1)}%` : `${spreadChange.toFixed(1)}%`)
    : null;

  return (
    <div className="relative w-full rounded-2xl overflow-hidden select-none"
      style={{ background: 'var(--bg-input)', height: 200 }}>
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full h-full"
        preserveAspectRatio="none" style={{ touchAction: 'none' }}>
        <defs>
          <linearGradient id="gcg-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor="#FF7B72" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#00D4AA" stopOpacity="0.12" />
          </linearGradient>
          <filter id="gcg-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
          <radialGradient id="gcg-glass" cx="35%" cy="30%" r="65%">
            <stop offset="0%"   stopColor="rgba(255,255,255,0.55)" />
            <stop offset="40%"  stopColor="rgba(255,255,255,0.15)" />
            <stop offset="100%" stopColor="rgba(255,255,255,0.04)" />
          </radialGradient>
          <filter id="gcg-pulse">
            <feGaussianBlur stdDeviation={isDragging ? '5' : '2'} result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* Range fill */}
        <rect x={PAD.l} y={dispPyHigh}
          width={W - PAD.l - PAD.r} height={Math.max(0, dispPyLow - dispPyHigh)}
          fill="url(#gcg-fill)" rx="4"
          style={{ transition: isDragging ? 'none' : 'all 0.25s ease' }} />

        {/* Grid lines */}
        {liveLevels.map((price, i) => {
          const yp = PAD.t + ((dispHigh - price) / Math.max(dispHigh - dispLow, 0.0001)) * innerH;
          const isBuy  = price < (current || (dispHigh + dispLow) / 2);
          const isSell = price > (current || (dispHigh + dispLow) / 2);
          return (
            <line key={i} x1={PAD.l + 4} y1={yp} x2={W - PAD.r - 4} y2={yp}
              stroke={isBuy ? '#00D4AA' : isSell ? '#FF7B72' : '#F0B90B'}
              strokeWidth={0.8} strokeDasharray="3,4"
              opacity={isDragging ? 0.9 : 0.55}
              style={{ transition: isDragging ? 'none' : 'all 0.25s ease' }} />
          );
        })}

        {/* Boundary lines */}
        <line x1={PAD.l} y1={dispPyHigh} x2={W - PAD.r} y2={dispPyHigh}
          stroke="#FF7B72" strokeWidth="1.5" strokeDasharray="5,3" opacity="0.85"
          style={{ transition: isDragging ? 'none' : 'all 0.25s ease' }} />
        <line x1={PAD.l} y1={dispPyLow} x2={W - PAD.r} y2={dispPyLow}
          stroke="#00D4AA" strokeWidth="1.5" strokeDasharray="5,3" opacity="0.85"
          style={{ transition: isDragging ? 'none' : 'all 0.25s ease' }} />

        {/* Current price */}
        {current > 0 && (
          <line x1={PAD.l} y1={yCur} x2={W - PAD.r} y2={yCur}
            stroke="#F0B90B" strokeWidth="1" opacity="0.5" />
        )}

        {/* Labels */}
        <text x={PAD.l + 4} y={dispPyHigh - 4} fontSize="7.5" fill="#FF7B72" fontWeight="700" opacity="0.9">
          H: {dispHigh > 0 ? dispHigh.toFixed(4) : '—'}
        </text>
        <text x={PAD.l + 4} y={dispPyLow + 10} fontSize="7.5" fill="#00D4AA" fontWeight="700" opacity="0.9">
          L: {dispLow > 0 ? dispLow.toFixed(4) : '—'}
        </text>
        {current > 0 && (
          <text x={W / 2} y={yCur - 4} fontSize="7.5" fill="#F0B90B" fontWeight="800" textAnchor="middle" opacity="0.9">
            ● {current.toFixed(4)}
          </text>
        )}

        {/* Hint arrows */}
        {!isDragging && !readOnly && (
          <>
            <text x={circleCX} y={dispCircleCY - 22} fontSize="9" fill="rgba(255,255,255,0.25)" textAnchor="middle">▲</text>
            <text x={circleCX} y={dispCircleCY + 30} fontSize="9" fill="rgba(255,255,255,0.25)" textAnchor="middle">▼</text>
            <text x={circleCX - 26} y={dispCircleCY + 4} fontSize="9" fill="rgba(255,255,255,0.25)" textAnchor="middle">◀</text>
            <text x={circleCX + 26} y={dispCircleCY + 4} fontSize="9" fill="rgba(255,255,255,0.25)" textAnchor="middle">▶</text>
          </>
        )}

        {/* Control circle */}
        {!readOnly && (
          <g transform={`translate(${circleCX}, ${dispCircleCY})`}
            style={{ cursor: isDragging ? 'grabbing' : 'grab', transition: isDragging ? 'none' : 'transform 0.25s ease' }}>
            <circle r={isDragging ? 20 : 16} fill="none"
              stroke={isDragging ? 'rgba(240,185,11,0.6)' : 'rgba(240,185,11,0.25)'}
              strokeWidth={isDragging ? 2 : 1.5} filter="url(#gcg-pulse)"
              style={{ transition: 'all 0.2s ease' }} />
            <circle r={14} fill="rgba(15,21,32,0.65)"
              stroke={isDragging ? 'rgba(240,185,11,0.9)' : 'rgba(240,185,11,0.5)'}
              strokeWidth={isDragging ? 2 : 1.5} style={{ transition: 'all 0.2s ease' }} />
            <circle r={14} fill="url(#gcg-glass)" />
            <g opacity={isDragging ? 1 : 0.8}>
              {[-4, 0, 4].map(gy => (
                <line key={gy} x1={-5} y1={gy} x2={5} y2={gy}
                  stroke={isDragging ? '#F0B90B' : 'rgba(240,185,11,0.8)'}
                  strokeWidth="1.2" strokeLinecap="round" />
              ))}
            </g>
            <circle r={22} fill="transparent"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp} />
          </g>
        )}

        {/* Percentage badge */}
        {isDragging && badgeText && (
          <g transform={`translate(${circleCX + 28}, ${dispCircleCY - 8})`}>
            <rect x={-2} y={-10} width={badgeText.length * 6 + 8} height={14} rx={4}
              fill={spreadChange >= 0 ? 'rgba(0,212,170,0.85)' : 'rgba(255,123,114,0.85)'} />
            <text x={(badgeText.length * 6 + 4) / 2} y={0}
              fontSize="8.5" fill="#000" fontWeight="800" textAnchor="middle">
              {badgeText}
            </text>
          </g>
        )}

        {isDragging && (
          <text x={W / 2} y={H - 4} fontSize="7" fill="rgba(255,255,255,0.4)" textAnchor="middle">
            {ar ? '↕ توسيع/تضييق  ↔ تحريك' : '↕ expand/shrink  ↔ shift'}
          </text>
        )}
      </svg>

      {!isDragging && !readOnly && (
        <div className="absolute bottom-1.5 left-0 right-0 text-center pointer-events-none"
          style={{ fontSize: 9, color: 'rgba(255,255,255,0.3)', letterSpacing: '0.04em' }}>
          {ar ? 'اسحب الدائرة للتحكم في الشبكة' : 'Drag the circle to control the grid'}
        </div>
      )}
    </div>
  );
}
