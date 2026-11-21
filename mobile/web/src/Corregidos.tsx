import { useQuery } from '@tanstack/react-query'
import { api, type Decision, type Resumen } from './api'
import { ERRORES } from './errores'

const DECISIONES: Decision[] = ['aprobada', 'rechazada', 'revision_manual']
const fmt = (x: number | null) => x === null ? '—' : `${(x * 100).toFixed(1)}%`
const div = (a: number, b: number) => b ? a / b : null

// Métricas sobre la matriz esperada (analista) → predicha (motor).
function metricas(m: Record<string, number>) {
  const n = (e: Decision, p: Decision) => m[`${e}->${p}`] ?? 0
  const suma = (f: (d: Decision) => number) => DECISIONES.reduce((s, d) => s + f(d), 0)
  const total = DECISIONES.reduce((s, e) => s + suma((p) => n(e, p)), 0)
  const de = (d: Decision) => ({
    precision: div(n(d, d), suma((e) => n(e, d))),
    sensibilidad: div(n(d, d), suma((p) => n(d, p))),
  })
  return { exactitud: div(suma((d) => n(d, d)), total), aprobar: de('aprobada'),
    revisionRechazada: n('revision_manual', 'rechazada') }
}

function Metricas() {
  const { data, isError, isPending } = useQuery({
    queryKey: ['resumen'], queryFn: () => api<Resumen>('/resumen'), staleTime: 300000,
  })
  if (isPending) return <p role="status" className="muted">Cargando métricas…</p>
  if (isError) return <p className="notice" role="alert">Aún no hay métricas: genera resultados/resumen.json con
    comparativo.py.</p>
  const versiones = Object.entries(data.versiones)
  const mejor = Math.min(...versiones.map(([, v]) => v.costo_operativo))
  return <section className="stack" aria-labelledby="metricas">
    <h2 id="metricas">Métricas del motor</h2>
    <p className="muted">{data.capturas} capturas de desarrollo contra el analista. En rojo, la de menor costo.</p>
    <div className="tabla-scroll">
      <table className="resumen metricas">
        <thead><tr><th>Versión</th><th>Costo</th><th>Precisión aprobar</th><th>Sensibilidad aprobar</th>
          <th>Exactitud</th><th>Tokens/captura</th></tr></thead>
        <tbody>{versiones.map(([nombre, v]) => {
          const m = metricas(v.esperada_vs_predicha)
          const c = v.costo_operativo
          return <tr key={nombre} className={c === mejor ? 'mejor' : undefined}>
            <th scope="row">{nombre}</th>
            <td><strong>{c}</strong> / {c + m.revisionRechazada} / {c + 3 * m.revisionRechazada}</td>
            <td>{fmt(m.aprobar.precision)}</td><td>{fmt(m.aprobar.sensibilidad)}</td><td>{fmt(m.exactitud)}</td>
            <td>{v.tokens_por_captura?.toLocaleString('es-MX') ?? '—'}</td>
          </tr>
        })}</tbody>
      </table>
    </div>
  </section>
}

export function Corregidos() {
  return <section className="panel">
    <div className="encabezado">
      <h1>Parte técnica</h1>
      <p className="muted">Cómo le va al motor contra el analista y los errores del modelo anterior que ya corrige.</p>
    </div>
    <Metricas />
    <h2>Errores corregidos</h2>
    <p className="muted">Capturas que el modelo anterior decidió mal y que Validat3B ahora resuelve, de la más
      a la menos relevante.</p>
    <ol className="corregidos">
      {[0, 1, 2].map((i) => {
        const caso = ERRORES[i]
        return <li key={i} className={caso ? 'caso' : 'caso vacio'}>
          <span className="caso-numero" aria-hidden="true">{i + 1}</span>
          {caso ? <div className="caso-cuerpo">
            <h2>{caso.titulo}</h2>
            {caso.imagen && <a href={caso.imagen} target="_blank" rel="noreferrer">
              <img src={caso.imagen} alt={`Captura de pantalla: ${caso.titulo}`} /></a>}
            <dl className="antes-ahora">
              <div><dt>Modelo anterior</dt><dd className="mal">✕ {caso.antes}</dd></div>
              <div><dt>Validat3B</dt><dd className="bien">✓ {caso.ahora}</dd></div>
            </dl>
            <p>{caso.porque}</p>
          </div> : <div className="caso-cuerpo">
            <h2>Espacio para el error {i + 1}</h2>
            <p className="muted">Agrega aquí la captura de pantalla y qué cambió. Se edita
              en <code>mobile/web/src/errores.ts</code>.</p>
          </div>}
        </li>
      })}
    </ol>
  </section>
}
