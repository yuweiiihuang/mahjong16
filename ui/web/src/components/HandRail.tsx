import type { CSSProperties } from 'react'

type HandRailProps = {
  labels: string[]
  tileIds?: Array<number | undefined>
  orientation?: 'horizontal' | 'vertical'
  selectedTileId?: number | null
  onTileClick?: (tileId: number, index: number) => void
  concealed?: boolean
}

export function HandRail({
  labels,
  tileIds,
  orientation = 'horizontal',
  selectedTileId,
  onTileClick,
  concealed = false,
}: HandRailProps) {
  return (
    <div
      className={`hand-rail ${orientation === 'vertical' ? 'vertical' : 'horizontal'}`}
      aria-label="hand-rail"
    >
      {labels.map((label, idx) => (
        (() => {
          const tileId = tileIds?.[idx]
          const isClickable = typeof tileId === 'number' && typeof onTileClick === 'function'
          const className = [
            'tile',
            concealed ? 'is-concealed' : '',
            isClickable ? 'is-clickable' : '',
            selectedTileId === tileId ? 'is-selected' : '',
          ]
            .filter(Boolean)
            .join(' ')

          if (isClickable) {
            return (
              <button
                key={`${label}-${idx}`}
                type="button"
                className={className}
                data-label={concealed ? '' : label}
                aria-pressed={selectedTileId === tileId}
                aria-label={`tile-${concealed ? 'concealed' : label}-${orientation}-${idx}`}
                onClick={() => onTileClick(tileId, idx)}
                style={{ ['--i' as keyof CSSProperties]: idx } as CSSProperties}
              />
            )
          }

          return (
            <div
              key={`${label}-${idx}`}
              className={className}
              data-label={concealed ? '' : label}
              style={{ ['--i' as keyof CSSProperties]: idx } as CSSProperties}
            />
          )
        })()
      ))}
    </div>
  )
}
