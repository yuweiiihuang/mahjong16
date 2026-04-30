import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { SCENE_H, SCENE_W } from './layout'

type TableViewportProps = {
  children: ReactNode
  actionDock?: ReactNode
}

export function TableViewport({ children, actionDock }: TableViewportProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [size, setSize] = useState({ width: SCENE_W, height: SCENE_H })

  useLayoutEffect(() => {
    const element = rootRef.current
    if (!element) {
      return
    }

    const update = () => {
      const rect = element.getBoundingClientRect()
      setSize({ width: rect.width, height: rect.height })
    }

    update()
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', update)
      return () => window.removeEventListener('resize', update)
    }

    const observer = new ResizeObserver(update)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  const scale = Math.min(size.width / SCENE_W, size.height / SCENE_H, 1)
  const frameWidth = SCENE_W * scale
  const frameHeight = SCENE_H * scale

  return (
    <div className="table-v2-viewport" ref={rootRef}>
      <div className="table-v2-frame" style={{ width: frameWidth, height: frameHeight }}>
        <div
          className="table-v2-scale"
          style={{
            width: SCENE_W,
            height: SCENE_H,
            transform: `scale(${scale})`,
          }}
        >
          {children}
        </div>
      </div>
      {actionDock ? <div className="table-v2-action-overlay">{actionDock}</div> : null}
    </div>
  )
}
