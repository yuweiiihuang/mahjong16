import { useMemo } from 'react'
import { SessionApp } from './components/SessionApp'
import { Table } from './components/Table'
import { resolveTableStateFromSearch } from './state/tableStore'
import './styles/global.css'

function App() {
  const search = window.location.search
  const isAnchorMode = useMemo(() => new URLSearchParams(search).has('anchor'), [search])
  const anchorTable = useMemo(() => resolveTableStateFromSearch(search), [search])

  return (
    <div className="page">
      {isAnchorMode ? (
        <div className="table-outer">
          <Table table={anchorTable} />
        </div>
      ) : (
        <SessionApp />
      )}
    </div>
  )
}

export default App
