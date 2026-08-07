interface Props {
  value: number;
  label: string;
}

function colorFor(v: number): string {
  if (v >= 65) return "#26a69a";
  if (v >= 45) return "#f0b90b";
  return "#ef5350";
}

export default function ScoreGauge({ value, label }: Props) {
  const color = colorFor(value);
  const pct = Math.max(0, Math.min(100, value)) / 100;

  return (
    <div className="score-card">
      <div className="gauge-wrap">
        <svg width="180" height="100" viewBox="0 0 180 100">
          <path
            d="M 15 95 A 70 70 0 0 1 165 95"
            fill="none"
            stroke="#232937"
            strokeWidth="13"
            strokeLinecap="round"
          />
          <path
            d="M 15 95 A 70 70 0 0 1 165 95"
            fill="none"
            stroke={color}
            strokeWidth="13"
            strokeLinecap="round"
            strokeDasharray={`${pct * 219.9} 219.9`}
          />
        </svg>
        <div className="gauge-value">{Math.round(value)}</div>
      </div>
      <div className="gauge-label">{label}</div>
    </div>
  );
}
