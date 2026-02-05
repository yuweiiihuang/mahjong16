type HandRailProps = {
  labels: string[]
  orientation?: 'horizontal' | 'vertical'
}

export function HandRail({ labels, orientation = 'horizontal' }: HandRailProps) {
  return (
    <div
      className={`hand-rail ${orientation === 'vertical' ? 'vertical' : 'horizontal'}`}
      aria-label="hand-rail"
    >
      {labels.map((label, idx) => (
        <div key={`${label}-${idx}`} className="tile" data-label={label} />
      ))}
    </div>
  )
}
