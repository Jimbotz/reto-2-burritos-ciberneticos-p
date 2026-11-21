export type Rol = 'operador' | 'revisor'
export type Posicion = { lat: number; lon: number; precision_m: number; medida_en: number }
export type Sucursal = {
  id: string; cadena: string; nombre: string; direccion: string
  municipio: string; estado: string; fuente: string; distancia_m?: number
}
export type Visita = { id: string; cadena: string; nombre: string; ubicacion: 'verificada' | 'manual' }
export type Producto = { id_product: string; product_name: string; product_barcode: string }
export type Resultado = {
  decision: 'aprobada' | 'rechazada' | 'revision_manual'
  explicacion: string; reason_code: string; precio_detectado: number | null
  validaciones: Record<string, 'ok' | 'falla'>
}
export type Captura = {
  id: string; estado: 'pendiente' | 'validando' | 'procesada'
  resultado: Resultado | null; revision: { decision: string; motivo: string } | null
  precio_centavos: number; cadena?: string; sucursal?: string
}
export type Referencia = { precio_centavos: number; fecha: string; sucursal: string; presentacion: string }
export type Config = { cadenas: string[]; fuentes: Record<string, number>; foundry: boolean }
export type Borrador = {
  id: string; visita_id: string; sku: string | null; codigo: string; precio: string
  capturada_en: number; producto: File; etiqueta: File
}

export class ErrorApi extends Error {
  constructor(public status: number, mensaje: string) { super(mensaje) }
}

export async function api<T>(ruta: string, init?: RequestInit): Promise<T> {
  const response = await fetch('/api' + ruta, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: unknown } | null
    const detail = typeof body?.detail === 'string' ? body.detail : ''
    const mensaje = response.status === 413 ? 'Las fotos superan el tamaño permitido.'
      : response.status === 422 ? 'Revisa los datos ingresados.' : 'No se pudo completar la solicitud.'
    throw new ErrorApi(response.status, detail || mensaje)
  }
  return response.json() as Promise<T>
}

export function post<T>(ruta: string, body: unknown) {
  return api<T>(ruta, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}

export function subir(draft: Borrador) {
  const { producto, etiqueta, ...datos } = draft
  const form = new FormData()
  form.set('datos', JSON.stringify(datos))
  form.set('producto', producto)
  form.set('etiqueta', etiqueta)
  return api<Captura>('/capturas', { method: 'POST', body: form })
}

export const pesos = (centavos: number) => new Intl.NumberFormat('es-MX', {
  style: 'currency', currency: 'MXN',
}).format(centavos / 100)
