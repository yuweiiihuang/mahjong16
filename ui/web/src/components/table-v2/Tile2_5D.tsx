import type { CSSProperties } from 'react'

type Tile2_5DProps = {
  label: string
  concealed?: boolean
  size?: 'hand' | 'back' | 'river' | 'mini'
  selected?: boolean
  disabled?: boolean
  ariaLabel?: string
  onClick?: () => void
}

export function Tile2_5D({
  label,
  concealed = false,
  size = 'hand',
  selected = false,
  disabled = false,
  ariaLabel,
  onClick,
}: Tile2_5DProps) {
  const className = [
    'tile-v2',
    `tile-v2-${size}`,
    concealed ? 'is-back' : 'is-face',
    selected ? 'is-selected' : '',
    onClick ? 'is-clickable' : '',
  ]
    .filter(Boolean)
    .join(' ')
  const style = { ['--tile-label' as keyof CSSProperties]: `"${concealed ? '' : label}"` } as CSSProperties

  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        style={style}
        aria-label={ariaLabel ?? `tile-${label}`}
        aria-pressed={selected}
        disabled={disabled}
        onClick={onClick}
      />
    )
  }

  return (
    <div
      className={className}
      style={style}
      aria-label={ariaLabel ?? (concealed ? 'concealed-tile' : `tile-${label}`)}
    />
  )
}
