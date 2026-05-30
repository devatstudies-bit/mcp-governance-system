import { useMemo } from 'react'

interface HealthGaugeProps {
  score: number   // 0–100
  size?: number
}

export function HealthGauge({ score, size = 160 }: HealthGaugeProps) {
  const { path, color, label } = useMemo(() => {
    // Semi-circle gauge: sweeps from -180° to 0° (left to right)
    const r = 56
    const cx = size / 2
    const cy = size / 2 + 10
    const startAngle = Math.PI         // 180°
    const angle = startAngle - (score / 100) * Math.PI

    const x = cx + r * Math.cos(angle)
    const y = cy - r * Math.sin(angle)

    const trackPath = [
      `M ${cx - r} ${cy}`,
      `A ${r} ${r} 0 0 1 ${cx + r} ${cy}`,
    ].join(' ')

    const fillPath = [
      `M ${cx - r} ${cy}`,
      `A ${r} ${r} 0 0 1 ${x} ${y}`,
    ].join(' ')

    const c =
      score >= 80 ? '#22c55e' :
      score >= 60 ? '#f59e0b' :
      score >= 40 ? '#f97316' :
                    '#ef4444'

    const l =
      score >= 80 ? 'Healthy' :
      score >= 60 ? 'Fair' :
      score >= 40 ? 'At Risk' :
                    'Critical'

    return { path: { track: trackPath, fill: fillPath }, color: c, label: l }
  }, [score, size])

  return (
    <div className="flex flex-col items-center">
      <svg width={size} height={size / 2 + 30} viewBox={`0 0 ${size} ${size / 2 + 30}`}>
        {/* Track */}
        <path
          d={path.track}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={12}
          strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={path.fill}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
        />
        {/* Score text */}
        <text
          x={size / 2}
          y={size / 2 + 10}
          textAnchor="middle"
          fontSize={28}
          fontWeight={700}
          fill="#111827"
          fontFamily="Inter, sans-serif"
        >
          {score}
        </text>
        <text
          x={size / 2}
          y={size / 2 + 28}
          textAnchor="middle"
          fontSize={11}
          fill="#6b7280"
          fontFamily="Inter, sans-serif"
        >
          {label}
        </text>
      </svg>
    </div>
  )
}
