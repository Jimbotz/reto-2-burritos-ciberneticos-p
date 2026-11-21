import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { api, ErrorApi, type CapturaComparada, type Comparativo as Datos, type Decision } from './api'

const ETIQUETA: Record<Decision, string> = { aprobada: 'Aprobada', rechazada: 'Rechazada', revision_manual: 'Revisión' }
const DECISIONES: Decision[] = ['aprobada', 'rechazada', 'revision_manual']

function Chip({ quien, decision, analista }: { quien: string; decision: Decision | null | undefined; analista?: Decision }) {
  if (!decision) return null
  const clase = analista === undefined ? 'chip' : decision === analista ? 'chip igual' : 'chip distinto'
  return <span className={clase}>{quien}: {ETIQUETA[decision]}</span>
}

function Fila({ row, versiones }: { row: CapturaComparada; versiones: string[] }) {
  const a = row.analista.decision
  return <li className="comparada">
    <div className="comparada-titulo">
      <strong>{row.producto}</strong>
      <small className="muted">{row.capture_id} · {row.tienda} · ${row.precio_capturado}</small>
    </div>
    <div className="chips">
      <Chip quien="Analista" decision={a} />
      {versiones.map((v) => <Chip key={v} quien={v} decision={row.versiones[v]?.decision} analista={a} />)}
      <Chip quien="Revisor" decision={row.revisor} analista={a} />
    </div>
    {row.analista.motivo && <small className="muted">Motivo del analista: {row.analista.motivo}</small>}
    <details>
      <summary>Explicaciones</summary>
      {versiones.map((v) => row.versiones[v] && <p key={v}><strong>{v}</strong> · {row.versiones[v].reason_code}
        {' '}({row.versiones[v].confidence_score.toFixed(2)}): {row.versiones[v].explicacion}</p>)}
    </details>
  </li>
}

export function Comparativo() {
  const { data, isPending, error } = useQuery({ queryKey: ['comparativo'], queryFn: () => api<Datos>('/comparativo') })
  const [cadena, setCadena] = useState('')
  const [soloDiferencias, setSoloDiferencias] = useState(true)
  const versiones = useMemo(() => Object.keys(data?.versiones ?? {}), [data])
  const cadenas = useMemo(() => [...new Set(data?.capturas.map((c) => c.tienda))].sort(), [data])
  const filas = useMemo(() => (data?.capturas ?? []).filter((c) => (!cadena || c.tienda === cadena)
    && (!soloDiferencias || versiones.some((v) => c.versiones[v]?.decision !== c.analista.decision))), [data, cadena, soloDiferencias, versiones])
  const analista = useMemo(() => {
    const conteo: Partial<Record<Decision, number>> = {}
    for (const c of data?.capturas ?? []) conteo[c.analista.decision] = (conteo[c.analista.decision] ?? 0) + 1
    return conteo
  }, [data])

  if (isPending) return <p role="status">Cargando comparativo…</p>
  if (error) return <section className="panel">
    <h1>Comparativo de versiones</h1>
    <p role="alert">{error instanceof ErrorApi ? error.message : 'No se pudo cargar el comparativo.'}</p>
    <Link to="/">Volver</Link>
  </section>

  return <section className="panel">
    <h1>Comparativo de versiones</h1>
    <p className="muted">Decisión del analista contra cada versión del motor en el set de desarrollo. Generado {new Date(data.generado).toLocaleString('es-MX')}.</p>
    <div className="tabla-scroll">
      <table className="resumen">
        <thead><tr><th></th><th>Analista</th>{versiones.map((v) => <th key={v}>{v}</th>)}</tr></thead>
        <tbody>
          {DECISIONES.map((d) => <tr key={d}><th>{ETIQUETA[d]}</th><td>{analista[d] ?? 0}</td>
            {versiones.map((v) => <td key={v}>{data.versiones[v].distribucion[d] ?? 0}</td>)}</tr>)}
          <tr><th>Costo operativo</th><td>—</td>{versiones.map((v) => <td key={v}><strong>{data.versiones[v].costo_operativo}</strong></td>)}</tr>
          <tr><th>Precisión de aprobación</th><td>—</td>{versiones.map((v) => {
            const p = data.versiones[v].precision_aprobacion
            return <td key={v}>{p === null ? '—' : `${(p * 100).toFixed(1)}%`}</td>
          })}</tr>
          <tr><th>Tokens por captura</th><td>—</td>{versiones.map((v) => <td key={v}>{data.versiones[v].tokens_por_captura ?? '—'}</td>)}</tr>
        </tbody>
      </table>
    </div>
    <ul className="versiones-desc">{versiones.map((v) => <li key={v}><strong>{v}</strong>: {data.versiones[v].descripcion}</li>)}</ul>
    <div className="filtros">
      <label>Cadena<select value={cadena} onChange={(e) => setCadena(e.target.value)}>
        <option value="">Todas</option>{cadenas.map((c) => <option key={c}>{c}</option>)}
      </select></label>
      <label className="check"><input type="checkbox" checked={soloDiferencias}
        onChange={(e) => setSoloDiferencias(e.target.checked)} /> Solo donde alguna versión difiere del analista</label>
    </div>
    <p className="muted">{filas.length} capturas</p>
    <ul className="sucursales">{filas.map((row) => <Fila key={row.capture_id} row={row} versiones={versiones} />)}</ul>
    <Link to="/">Volver</Link>
  </section>
}
