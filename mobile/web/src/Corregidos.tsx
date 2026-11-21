import { ERRORES } from './errores'

export function Corregidos() {
  return <section className="panel">
    <div className="encabezado">
      <h1>Errores corregidos</h1>
      <p className="muted">Capturas que el modelo anterior decidió mal y que Validat3B ahora resuelve, de la más
        a la menos relevante.</p>
    </div>
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
