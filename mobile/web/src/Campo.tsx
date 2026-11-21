import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ErrorApi, pesos, post, subir, type Borrador, type Captura, type Config,
  type Posicion, type Producto, type Referencia, type Sucursal, type Visita } from './api'
import { borradores, borrarBorrador, guardarBorrador, uuid } from './borradores'

const decisiones = { aprobada: 'Aprobada', rechazada: 'Rechazada', revision_manual: 'Revisión manual' }
const mensaje = (error: unknown) => error instanceof ErrorApi ? error.message : 'No se pudo conectar con el servidor.'
const ahora = () => Date.now() / 1000

function visitaGuardada(): Visita | null {
  try { return JSON.parse(localStorage.getItem('validat3b.visita') || 'null') as Visita | null }
  catch { return null }
}

function ElegirSucursal({ config, abrir }: { config?: Config; abrir: (visita: Visita) => void }) {
  const [posicion, setPosicion] = useState<Posicion | null>(null)
  const [tiendas, setTiendas] = useState<Sucursal[]>([])
  const [sugerida, setSugerida] = useState<string | null>(null)
  const [busqueda, setBusqueda] = useState('')
  const [cadena, setCadena] = useState('')
  const [nombre, setNombre] = useState('')
  const [busy, setBusy] = useState(false)
  const [estado, setEstado] = useState('')
  const permiteUbicacion = window.isSecureContext && Boolean(navigator.geolocation)

  async function ubicar() {
    setBusy(true)
    setEstado('Obteniendo tu ubicación…')
    try {
      const geo = await new Promise<GeolocationPosition>((resolve, reject) => navigator.geolocation.getCurrentPosition(
        resolve, reject, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
      ))
      const p = { lat: geo.coords.latitude, lon: geo.coords.longitude,
        precision_m: geo.coords.accuracy, medida_en: geo.timestamp / 1000 }
      const resultado = await post<{ candidatas: Sucursal[]; sugerida_id: string | null }>('/sucursales/cercanas', p)
      setPosicion(p)
      setTiendas(resultado.candidatas)
      setSugerida(resultado.sugerida_id)
      setEstado(resultado.candidatas.length
        ? `Precisión aproximada de ±${Math.round(p.precision_m)} m. Confirma la dirección.`
        : 'Sin sucursales registradas cerca. Usa el buscador o registra la sucursal manualmente.')
    } catch (error) {
      setEstado(error instanceof ErrorApi ? error.message : 'No pudimos obtener tu ubicación. Puedes buscar la sucursal.')
    } finally { setBusy(false) }
  }

  async function buscar(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setEstado('')
    try {
      const r = await api<Sucursal[]>(`/sucursales?q=${encodeURIComponent(busqueda)}`)
      setTiendas(r)
      setSugerida(null)
      if (!r.length) setEstado('No encontramos una sucursal con ese nombre.')
    } catch (error) { setEstado(mensaje(error)) }
    finally { setBusy(false) }
  }

  async function confirmar(sucursal?: Sucursal) {
    setBusy(true)
    try { abrir(await post<Visita>('/visitas', { sucursal_id: sucursal?.id, cadena, nombre, posicion })) }
    catch (error) { setEstado(mensaje(error)) }
    finally { setBusy(false) }
  }

  return <section className="panel">
    <h1>Elige tu sucursal</h1>
    <p className="muted">{permiteUbicacion
      ? 'Confirma la tienda una vez para capturar varios productos en la misma visita.'
      : 'Busca la tienda por nombre o dirección y confírmala una vez por visita.'}</p>
    {permiteUbicacion && <button className="primary full" disabled={busy} onClick={ubicar}>Usar mi ubicación</button>}
    <form className="input-row" onSubmit={buscar}>
      <label><span>Nombre, cadena o dirección</span><input value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
        placeholder="Ej. Soriana Centro" minLength={2} maxLength={120} required /></label>
      <button className={permiteUbicacion ? undefined : 'primary'} disabled={busy}>Buscar</button>
    </form>
    {estado && <p className="notice" role="status">{estado}</p>}
    {tiendas.length > 0 && <ul className="sucursales">
      {tiendas.map((tienda) => <li key={tienda.id}>
        <button className="store full" disabled={busy} onClick={() => void confirmar(tienda)}>
          <span><strong>{tienda.nombre}</strong><small>{tienda.direccion || `${tienda.municipio}, ${tienda.estado}`}</small>
            <small>{tienda.fuente}{tienda.distancia_m === undefined ? '' : ` · ${Math.round(tienda.distancia_m)} m`}</small></span>
          {sugerida === tienda.id && <span className="badge">Sugerida</span>}
        </button>
      </li>)}
    </ul>}
    <details>
      <summary>Registrar una sucursal manualmente</summary>
      <form className="stack" onSubmit={(event) => { event.preventDefault(); void confirmar() }}>
        <label>Cadena<select required value={cadena} onChange={(e) => setCadena(e.target.value)}>
          <option value="">Elige una cadena</option>
          {(config?.cadenas || []).map((c) => <option key={c}>{c}</option>)}
        </select></label>
        <label>Nombre o dirección<input minLength={3} maxLength={160} required value={nombre}
          onChange={(e) => setNombre(e.target.value)} /></label>
        <button disabled={busy}>Iniciar visita manual</button>
      </form>
    </details>
  </section>
}

function Foto({ label, file, onFile }: { label: string; file: File | null; onFile: (file: File | null) => void }) {
  const [preview, setPreview] = useState('')
  useEffect(() => {
    if (!file) { setPreview(''); return }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])
  return <label className="foto">
    <span>{label}</span>
    {preview && <img src={preview} alt={label} />}
    <span className="foto-accion">{file ? 'Cambiar foto' : 'Tomar foto'}</span>
    <input aria-label={label} key={file ? 'con-foto' : 'sin-foto'} type="file" accept="image/*" capture="environment"
      onChange={(event) => onFile(event.currentTarget.files?.[0] || null)} />
  </label>
}

function Formulario({ visita, encolar }: { visita: Visita; encolar: (draft: Borrador) => Promise<void> }) {
  const [codigo, setCodigo] = useState('')
  const [sku, setSku] = useState<Producto | null>(null)
  const [nombre, setNombre] = useState('')
  const [opciones, setOpciones] = useState<Producto[]>([])
  const [precio, setPrecio] = useState('')
  const [producto, setProducto] = useState<File | null>(null)
  const [etiqueta, setEtiqueta] = useState<File | null>(null)
  const [estado, setEstado] = useState('')
  const [busy, setBusy] = useState(false)
  const referencia = useQuery({
    queryKey: ['qqp', visita.id, sku?.id_product],
    queryFn: () => api<Referencia | null>(`/precios/qqp?visita_id=${visita.id}&sku=${encodeURIComponent(sku!.id_product)}`),
    enabled: !!sku, staleTime: 60000,
  }).data

  async function buscar(codigoLeido?: string) {
    setBusy(true)
    setEstado('')
    try {
      const query = codigoLeido ? 'codigo=' + encodeURIComponent(codigoLeido) : 'q=' + encodeURIComponent(nombre)
      const items = await api<Producto[]>('/productos?' + query)
      setOpciones(items.length === 1 ? [] : items)
      if (items.length === 1) setSku(items[0])
      else setEstado(items.length ? 'Elige el producto esperado.' : 'Sin coincidencia en el catálogo. Puedes enviar a revisión.')
    } catch (error) { setEstado(mensaje(error)) }
    finally { setBusy(false) }
  }

  async function leer() {
    if (!producto) return
    setBusy(true)
    setEstado('')
    try {
      const form = new FormData()
      form.append('foto', producto)
      const { codigos } = await api<{ codigos: string[] }>('/codigos/leer', { method: 'POST', body: form })
      if (codigos.length !== 1) {
        setEstado('El código no se distinguió con claridad. Escríbelo o toma otra foto.')
        return
      }
      setCodigo(codigos[0])
      await buscar(codigos[0])
    } catch (error) { setEstado(mensaje(error)) }
    finally { setBusy(false) }
  }

  async function enviar(event: FormEvent) {
    event.preventDefault()
    if (!producto || !etiqueta) { setEstado('Agrega las dos fotos para guardar la captura.'); return }
    const pesosTexto = precio.trim().replace(',', '.')
    if (!/^\d{1,6}(\.\d{1,2})?$/.test(pesosTexto) || Number(pesosTexto) <= 0) {
      setEstado('Escribe un precio válido con hasta dos decimales.')
      return
    }
    setBusy(true)
    try {
      await encolar({ id: uuid(), visita_id: visita.id, sku: sku?.id_product || null, codigo,
        precio: pesosTexto, capturada_en: ahora(), producto, etiqueta })
      setCodigo(''); setSku(null); setPrecio(''); setProducto(null); setEtiqueta(null); setOpciones([])
      setEstado('Captura guardada.')
    } catch { setEstado('No hubo espacio para guardar el borrador. Libera almacenamiento e inténtalo de nuevo.') }
    finally { setBusy(false) }
  }

  return <section className="panel">
    <h1>Captura el precio</h1>
    <form className="stack" onSubmit={enviar}>
      <div className="fotos">
        <Foto label="Foto del producto" file={producto} onFile={setProducto} />
        <Foto label="Foto de la etiqueta" file={etiqueta} onFile={setEtiqueta} />
      </div>
      <div className="input-row">
        <label>Código de barras<input value={codigo} required inputMode="numeric" pattern="[0-9]{8,14}"
          maxLength={14} onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ''))} /></label>
        <button type="button" disabled={busy || codigo.length < 8} onClick={() => void buscar(codigo)}>Buscar SKU</button>
      </div>
      {producto && <button type="button" disabled={busy} onClick={() => void leer()}>Leer código de la foto</button>}
      <details>
        <summary>Buscar el producto esperado por nombre</summary>
        <div className="input-row">
          <label>Nombre del producto<input value={nombre} maxLength={100} onChange={(e) => setNombre(e.target.value)} /></label>
          <button type="button" disabled={busy || nombre.trim().length < 2} onClick={() => void buscar()}>Buscar</button>
        </div>
        {opciones.map((item) => <button key={item.id_product} type="button" className="choice full"
          onClick={() => { setSku(item); setOpciones([]); setEstado('') }}>{item.product_name} · {item.product_barcode}</button>)}
      </details>
      {sku && <div className="notice"><strong>{sku.product_name}</strong><small>SKU {sku.id_product} · {sku.product_barcode}</small></div>}
      {referencia && <div className="notice">
        <strong>Referencia Profeco {pesos(referencia.precio_centavos)}</strong>
        <small>{referencia.fecha} · {referencia.sucursal} · {referencia.presentacion}</small>
      </div>}
      <label>Precio en la etiqueta (MXN)<input className="precio" required inputMode="decimal" value={precio}
        placeholder="0.00" maxLength={9} onChange={(e) => setPrecio(e.target.value)} /></label>
      {estado && <p role="status" className="notice">{estado}</p>}
      <button className="primary full" disabled={busy}>Guardar captura</button>
    </form>
  </section>
}

export function Campo() {
  const [visita, setVisita] = useState(visitaGuardada)
  const [pendientes, setPendientes] = useState<Borrador[]>([])
  const [ultimo, setUltimo] = useState(() => localStorage.getItem('validat3b.ultimo') || '')
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const sincronizando = useRef(false)
  const sincronizarDeNuevo = useRef(false)
  const config = useQuery({ queryKey: ['config'], queryFn: () => api<Config>('/config'), staleTime: 60000 }).data
  const resultado = useQuery({
    queryKey: ['captura', ultimo], queryFn: () => api<Captura>('/capturas/' + ultimo), enabled: !!ultimo,
    refetchInterval: (query) => !query.state.error && query.state.data?.estado !== 'procesada' ? 1800 : false,
  }).data

  const sincronizar = useCallback(async function enviarPendientes() {
    if (sincronizando.current) {
      sincronizarDeNuevo.current = true
      return
    }
    sincronizando.current = true
    setEnviando(true)
    try {
      const items = await borradores()
      setPendientes(items)
      if (!navigator.onLine) return
      setAviso('')
      for (const draft of items) {
        try {
          const r = await subir(draft)
          await borrarBorrador(draft.id)
          setUltimo(r.id)
          localStorage.setItem('validat3b.ultimo', r.id)
        } catch (error) {
          setAviso(mensaje(error))
          if (!(error instanceof ErrorApi) || error.status === 401 || error.status >= 500) break
        }
      }
      setPendientes(await borradores())
    } catch { setAviso('El teléfono no pudo abrir el almacenamiento de borradores.') }
    finally {
      sincronizando.current = false
      setEnviando(false)
      if (sincronizarDeNuevo.current) {
        sincronizarDeNuevo.current = false
        void enviarPendientes()
      }
    }
  }, [])

  useEffect(() => {
    void sincronizar()
    const alVolver = () => void sincronizar()
    window.addEventListener('online', alVolver)
    return () => window.removeEventListener('online', alVolver)
  }, [sincronizar])

  function abrir(v: Visita | null) {
    setVisita(v)
    if (v) localStorage.setItem('validat3b.visita', JSON.stringify(v))
    else localStorage.removeItem('validat3b.visita')
  }

  async function encolar(draft: Borrador) {
    await guardarBorrador(draft)
    setPendientes(await borradores())
    void sincronizar()
  }

  return <>
    {visita && <div className="visit">
      <div><small>{visita.ubicacion === 'verificada' ? 'Ubicación verificada' : 'Visita con verificación pendiente'}</small>
        <strong>{visita.nombre}</strong></div>
      <button onClick={() => abrir(null)}>Cambiar</button>
    </div>}
    {visita ? <Formulario key={visita.id} visita={visita} encolar={encolar} /> : <ElegirSucursal config={config} abrir={abrir} />}
    {pendientes.length > 0 && <section className="panel compact">
      <h2>Envíos pendientes ({pendientes.length})</h2>
      {aviso && <p role="status" className="notice">{aviso}</p>}
      {pendientes.map((draft) => <div key={draft.id} className="visit">
        <span>{draft.codigo} · {pesos(Math.round(Number(draft.precio) * 100))}</span>
        <button disabled={enviando} onClick={async () => {
          if (!window.confirm('¿Eliminar esta captura pendiente del teléfono?')) return
          await borrarBorrador(draft.id)
          setPendientes(await borradores())
        }}>Quitar</button>
      </div>)}
      <button disabled={enviando} onClick={() => void sincronizar()}>{enviando ? 'Enviando…' : 'Reintentar envíos'}</button>
    </section>}
    {resultado && <section className="panel compact" aria-live="polite">
      <h2>Última captura</h2>
      <strong>{resultado.resultado ? decisiones[resultado.resultado.decision] : 'Validación en curso'}</strong>
      {resultado.resultado && <p>{resultado.resultado.explicacion}</p>}
    </section>}
  </>
}
