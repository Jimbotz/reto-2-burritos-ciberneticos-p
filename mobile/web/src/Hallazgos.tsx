import type { Resultado } from './api'

const ICONO = { falla: '✕', aviso: '!', ok: '✓' } as const

// Qué revisó el motor y qué hacer: primero lo que falló, luego avisos; lo que sí pasó queda plegado.
export function Hallazgos({ resultado }: { resultado: Resultado }) {
  const lista = resultado.hallazgos ?? []
  const problemas = lista.filter((x) => x.nivel !== 'ok').sort((a, b) => (a.nivel === 'falla' ? -1 : 0) - (b.nivel === 'falla' ? -1 : 0))
  const bien = lista.filter((x) => x.nivel === 'ok')
  if (!lista.length && !resultado.accion_sugerida) return null
  return <div className="hallazgos">
    {resultado.accion_sugerida && <p className="notice accion"><strong>Qué hacer:</strong> {resultado.accion_sugerida}</p>}
    {problemas.length > 0 && <ul>{problemas.map((x, i) => <li key={i} className={`hallazgo ${x.nivel}`}>
      <span aria-hidden="true">{ICONO[x.nivel]}</span>
      <span>{x.mensaje}{x.accion && x.accion !== resultado.accion_sugerida && <small>{x.accion}</small>}</span>
    </li>)}</ul>}
    {bien.length > 0 && <details>
      <summary>Lo que sí pasó ({bien.length})</summary>
      <ul>{bien.map((x, i) => <li key={i} className="hallazgo ok"><span aria-hidden="true">✓</span><span>{x.mensaje}</span></li>)}</ul>
    </details>}
  </div>
}
