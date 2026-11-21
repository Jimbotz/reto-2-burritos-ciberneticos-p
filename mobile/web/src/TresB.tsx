import type { Resultado } from './api'

// Los tres frentes del reto leídos con el lema de 3B. Solo el frente del motivo se marca como falla;
// lo que el motor no confirmó queda "por revisar", para no culpar al frente equivocado.
const FRENTES = [
  { nombre: 'Bueno', pregunta: 'Producto correcto', checks: ['producto', 'codigo_barras'],
    motivos: ['DESCRIPCION_INCOMPLETA', 'PRODUCTO_NO_COINCIDE', 'CONTRATIPO_INVALIDO', 'PRODUCTO_NO_VISIBLE'] },
  { nombre: 'Bonito', pregunta: 'Evidencia clara y de la tienda correcta', checks: ['sucursal', 'tienda_fachada'],
    motivos: ['CAPTURA_BORROSA', 'CAPTURA_LEJANA', 'FOTO_DE_PANTALLA', 'FACHADA_INCORRECTA'] },
  { nombre: 'Barato', pregunta: 'Etiqueta y precio válidos', checks: ['evidencia_precio'],
    motivos: ['SIN_ETIQUETA_PRECIO', 'SIN_PRECIO_UNITARIO', 'PRECIO_NO_COINCIDE'] },
] as const
const ESTADOS = { ok: ['✓', 'confirmado'], falla: ['✕', 'motivo del rechazo'], revisar: ['?', 'por revisar'] } as const

export function TresB({ resultado }: { resultado: Resultado }) {
  return <ul className="tresb" aria-label="Bueno, bonito y barato">
    {FRENTES.map((frente) => {
      const valores = frente.checks.map((check) => resultado.validaciones[check]).filter(Boolean)
      const estado = (frente.motivos as readonly string[]).includes(resultado.reason_code) ? 'falla'
        : valores.length && valores.every((valor) => valor === 'ok') ? 'ok' : 'revisar'
      const [icono, texto] = ESTADOS[estado]
      return <li key={frente.nombre} className={`pastilla ${estado}`} title={`${frente.pregunta}: ${texto}`}>
        <span aria-hidden="true">{icono}</span> {frente.nombre}
        <span className="sr-only">: {frente.pregunta}, {texto}</span>
      </li>
    })}
  </ul>
}
