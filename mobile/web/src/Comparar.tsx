import { useState, type FormEvent, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ErrorApi, pesos, type Comparacion, type PrecioOtro, type Producto, type RankingCadenas,
  type Zona } from './api'

const fechaCorta = (iso: string) => new Date(iso + 'T12:00:00')
  .toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' })
const pct = (actual: number, referencia: number) => Math.round((actual / referencia - 1) * 100)

function TablaCadenas({ zona }: { zona: Zona }) {
  const { data, isError } = useQuery({
    queryKey: ['cadenas', zona.estado, zona.municipio],
    queryFn: () => api<RankingCadenas>('/precios/cadenas?' + new URLSearchParams(
      { estado: zona.estado, municipio: zona.municipio })),
    staleTime: 300000,
  })
  if (isError) return <p className="notice" role="alert">No se pudo cargar la comparación de cadenas.</p>
  if (!data) return null
  if (data.cadenas.length < 2) return <p className="notice">En {zona.municipio} no hay productos en común entre
    cadenas para compararlas.</p>
  return <section className="ranking" aria-label={`Cadenas de ${zona.municipio} de la más barata a la más cara`}>
    <h2>¿Qué cadena es más barata en {zona.municipio}?</h2>
    <table>
      <thead><tr><th scope="col">Cadena</th><th scope="col">Sobre la más barata</th><th scope="col">Más barata en</th></tr></thead>
      <tbody>{data.cadenas.map((c, i) => <tr key={c.cadena} className={i === 0 ? 'barato' : undefined}>
        <th scope="row">{c.cadena}</th>
        <td className="cifra">{c.sobre_mas_barata_pct === 0 ? '0%' : `+${c.sobre_mas_barata_pct.toFixed(1)}%`}</td>
        <td>{c.mas_barata} de {c.productos}</td>
      </tr>)}</tbody>
    </table>
    <small>Promedio de {data.productos} productos idénticos que venden al menos dos cadenas de la zona: en cada uno
      se compara la mediana de la cadena contra la más barata. Datos Profeco al {fechaCorta(data.fecha!)}.</small>
    {data.productos < 5 && <small>Son pocos productos en común: tómalo como referencia, no como conclusión.</small>}
  </section>
}

function Elegir<T>({ etiqueta, placeholder, buscar, titulo, detalle, elegido, onElegir }: {
  etiqueta: string; placeholder: string; buscar: (q: string) => Promise<T[]>
  titulo: (item: T) => ReactNode; detalle: (item: T) => ReactNode
  elegido: T | null; onElegir: (item: T | null) => void
}) {
  const [q, setQ] = useState('')
  const [items, setItems] = useState<T[]>([])
  const [estado, setEstado] = useState('')
  const [busy, setBusy] = useState(false)
  if (elegido) return <div className="elegido">
    <span><small>{etiqueta}</small><strong>{titulo(elegido)}</strong><small>{detalle(elegido)}</small></span>
    <button type="button" onClick={() => onElegir(null)}>Cambiar</button>
  </div>
  async function enviar(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setEstado('')
    try {
      const resultado = await buscar(q.trim())
      setItems(resultado)
      if (!resultado.length) setEstado('Sin resultados. Prueba con otra palabra.')
    } catch (error) { setEstado(error instanceof ErrorApi ? error.message : 'No se pudo buscar.') }
    finally { setBusy(false) }
  }
  return <div className="stack">
    <form className="input-row" onSubmit={enviar}>
      <label>{etiqueta}<input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder}
        minLength={2} maxLength={100} required /></label>
      <button disabled={busy}>Buscar</button>
    </form>
    {estado && <p className="notice" role="status">{estado}</p>}
    {items.length > 0 && <ul className="sucursales">{items.map((item, i) => <li key={i}>
      <button type="button" className="store full" onClick={() => { onElegir(item); setItems([]) }}>
        <span><strong>{titulo(item)}</strong><small>{detalle(item)}</small></span>
      </button>
    </li>)}</ul>}
  </div>
}

export function ComparacionProfeco({ zona, sku, precio }: { zona: Zona; sku: Producto; precio: string }) {
  const { data, isError } = useQuery({
    queryKey: ['comparar', zona.estado, zona.municipio, sku.id_product],
    queryFn: () => api<Comparacion>('/precios/comparar?' + new URLSearchParams(
      { estado: zona.estado, municipio: zona.municipio, sku: sku.id_product })),
    staleTime: 60000,
  })
  if (isError) return <p className="notice" role="alert">No se pudo cargar la comparación.</p>
  if (!data) return <p role="status" className="muted">Buscando precios Profeco…</p>
  const { exacto, presentaciones, alternativas, unidad, factor } = data
  const otros = [...presentaciones, ...alternativas]
  if (!exacto.length && !otros.length) return <p className="notice">
    Profeco no registra este producto ni similares en {zona.municipio}.</p>
  const porUnidad = (centavos: number) => factor && unidad ? `${pesos(Math.round(centavos * factor))}/${unidad}` : ''
  const masBarato = exacto[0]?.mediana_centavos
  const maximo = Math.max(...exacto.map((c) => c.mediana_centavos))
  const masBaratoOtro = otros.reduce<PrecioOtro | null>((mejor, c) =>
    !mejor || c.por_unidad_centavos < mejor.por_unidad_centavos ? c : mejor, null)
  // se marca solo si por unidad le gana también al mismo producto
  const mejorOtro = masBaratoOtro && (masBarato === undefined || !factor
    || masBaratoOtro.por_unidad_centavos < masBarato * factor) ? masBaratoOtro : null
  const texto = precio.trim().replace(',', '.')
  const tuyo = /^\d{1,6}(\.\d{1,2})?$/.test(texto) ? Math.round(Number(texto) * 100) : 0
  const fecha = [...exacto, ...otros].reduce((reciente, c) => c.fecha > reciente ? c.fecha : reciente, '')
  const veredicto = (actual: number, referencia: number) => actual <= referencia
    ? 'igual o por debajo de lo más barato' : `${pct(actual, referencia)}% arriba de lo más barato`
  const caro = exacto[exacto.length - 1]
  const resumen = masBarato !== undefined ? <>
    En {zona.municipio}, lo más barato es <b>{exacto[0].cadena}</b> a <b>{pesos(masBarato)}</b>
    {caro.mediana_centavos > masBarato && <>; {caro.cadena} cobra {pct(caro.mediana_centavos, masBarato)}% más</>}.
    {tuyo > 0 && <> Tu etiqueta ({pesos(tuyo)}) está {veredicto(tuyo, masBarato)}.</>}
  </> : masBaratoOtro && <>
    Profeco no tiene este producto exacto en {zona.municipio}. Lo más barato por {unidad} es <b>{masBaratoOtro.marca}</b>
    {' '}({masBaratoOtro.presentacion}) en {masBaratoOtro.cadena}, a <b>{pesos(masBaratoOtro.por_unidad_centavos)}/{unidad}</b>.
    {tuyo > 0 && factor && <> Tu etiqueta sale a {porUnidad(tuyo)}:
      {' '}{veredicto(Math.round(tuyo * factor), masBaratoOtro.por_unidad_centavos)}.</>}
  </>
  const fila = (c: PrecioOtro) => <li key={c.marca + c.presentacion + c.cadena}
    className={c === mejorOtro ? 'barato' : undefined}>
    <div className="fila">
      <span><strong>{c.marca}</strong>{c === mejorOtro && <span className="sello">Más barato por {unidad}</span>}
        <small>{c.presentacion} · {c.cadena}</small></span>
      <span className="cifra"><b>{pesos(c.por_unidad_centavos)}</b>/{unidad}<small>{pesos(c.mediana_centavos)} el empaque</small></span>
    </div>
  </li>
  return <section className="comparacion" aria-label="Comparación con precios Profeco">
    <div className="comparacion-titulo"><h2>Precios Profeco</h2>
      <small>Tiendas de {zona.municipio} · datos al {fechaCorta(fecha)}</small></div>
    <p className="resumen">{resumen}</p>
    {exacto.length > 0 && <div className="nivel">
      <h3>Mismo producto</h3>
      <ul>
        {exacto.map((c) => <li key={c.cadena}
          className={exacto.length > 1 && c.mediana_centavos === masBarato ? 'barato' : undefined}>
          <div className="fila">
            <span><strong>{c.cadena}</strong>
              {exacto.length > 1 && c.mediana_centavos === masBarato && <span className="sello">Más barato</span>}
              <small>Mediana de {c.tiendas} {c.tiendas === 1 ? 'tienda' : 'tiendas'}</small></span>
            <span className="cifra"><b>{pesos(c.mediana_centavos)}</b><small>{porUnidad(c.mediana_centavos)}</small></span>
          </div>
          <div className="barra" aria-hidden="true"><span style={{ width: `${(c.mediana_centavos / maximo) * 100}%` }} /></div>
        </li>)}
      </ul>
    </div>}
    {presentaciones.length > 0 && <details className="nivel" open={!exacto.length}>
      <summary>Misma marca, otra presentación ({presentaciones.length})</summary>
      <ul>{presentaciones.map(fila)}</ul>
    </details>}
    {alternativas.length > 0 && <details className="nivel" open={!exacto.length && !presentaciones.length}>
      <summary>Otras marcas del mismo tipo ({alternativas.length})</summary>
      <ul>{alternativas.map(fila)}</ul>
    </details>}
    {otros.length > 0 && <small>Otras presentaciones y marcas se comparan por {unidad}: los empaques grandes
      suelen salir más baratos.</small>}
  </section>
}

export function Comparar() {
  const zonas = useQuery({ queryKey: ['zonas'], queryFn: () => api<Zona[]>('/zonas'), staleTime: 300000 })
  const [clave, setClave] = useState('')
  const [sku, setSku] = useState<Producto | null>(null)
  const [precio, setPrecio] = useState('')
  const zona = zonas.data?.find((z) => z.estado + '|' + z.municipio === clave) ?? null
  const variosEstados = new Set(zonas.data?.map((z) => z.estado)).size > 1
  return <section className="panel">
    <div className="encabezado">
      <h1>Comparar nuestros productos</h1>
      <p className="muted">Elige una zona y un producto del catálogo para ver lo que registró Profeco en las
        tiendas de esa zona.</p>
    </div>
    <label>Zona<select value={clave} onChange={(e) => setClave(e.target.value)}>
      <option value="">{zonas.isPending ? 'Cargando zonas…' : 'Elige una alcaldía o municipio'}</option>
      {zonas.data?.map((z) => <option key={z.estado + z.municipio} value={z.estado + '|' + z.municipio}>
        {z.municipio}{variosEstados && `, ${z.estado}`} · {z.tiendas} {z.tiendas === 1 ? 'tienda' : 'tiendas'}</option>)}
    </select></label>
    {zonas.isError && <p className="notice" role="alert">No se pudieron cargar las zonas.</p>}
    {zona && <TablaCadenas zona={zona} />}
    <Elegir<Producto> etiqueta="Producto" placeholder="Nombre o código de barras" elegido={sku} onElegir={setSku}
      buscar={(q) => api<Producto[]>(/^\d{8,14}$/.test(q) ? `/productos?codigo=${q}` : `/productos?q=${encodeURIComponent(q)}`)}
      titulo={(p) => p.product_name} detalle={(p) => `SKU ${p.id_product} · ${p.product_barcode}`} />
    {zona && sku && <>
      <label>Precio que viste en la etiqueta (opcional)<input className="precio" inputMode="decimal" value={precio}
        placeholder="0.00" maxLength={9} onChange={(e) => setPrecio(e.target.value)} /></label>
      <ComparacionProfeco key={clave + sku.id_product} zona={zona} sku={sku} precio={precio} />
    </>}
  </section>
}
