import { useMemo } from 'react'
import { SessionApp } from './components/SessionApp'
import { Table } from './components/Table'
import { TableV2 } from './components/table-v2/TableV2'
import { TableViewport } from './components/table-v2/TableViewport'
import { resolveTableStateFromSearch } from './state/tableStore'
import './styles/global.css'

function App() {
  const search = window.location.search
  const params = useMemo(() => new URLSearchParams(search), [search])
  const isAnchorMode = useMemo(() => params.has('anchor'), [params])
  const useTableV2 = useMemo(() => params.get('layout') === 'v2', [params])
  const anchorTable = useMemo(() => resolveTableStateFromSearch(search), [search])

  return (
    <div className="page">
      {isAnchorMode && useTableV2 ? (
        <div className="anchor-v2-page">
          <TableViewport>
            <TableV2 table={anchorTable} />
          </TableViewport>
        </div>
      ) : isAnchorMode ? (
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
