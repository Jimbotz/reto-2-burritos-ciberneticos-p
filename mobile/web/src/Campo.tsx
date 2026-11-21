import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ErrorApi, pesos, post, subir, type Borrador, type Captura,
  type Config, type Posicion, type Sucursal, type Visita } from './api'
import { borradores, borrarBorrador, guardarBorrador, uuid } from './borradores'
import { Hallazgos } from './Hallazgos'
import { Esqueleto } from './Esqueleto'

const decisiones = { aprobada: '✓ Aprobada', rechazada: '✕ Rechazada', revision_manual: '! Revisión manual' }
const mensaje = (error: unknown) => error instanceof ErrorApi ? error.message : 'No se pudo conectar con el servidor.'
const ahora = () => Date.now() / 1000
const PASOS = ['Ubicación', 'Producto', 'Etiqueta'] as const

function Pasos({ actual }: { actual: number }) {
  return <ol className="pasos" aria-label={`Paso ${actual + 1} de ${PASOS.length}`}>
    {PASOS.map((paso, i) => <li key={paso} className={i < actual ? 'hecho' : i === actual ? 'actual' : undefined}
      aria-current={i === actual ? 'step' : undefined}>{paso}</li>)}
  </ol>
}

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

  const formBuscar = <form className="input-row" onSubmit={buscar}>
    <label><span>Nombre, cadena o dirección</span><input value={busqueda} onChange={(e) => setBusqueda(e.target.value)}
      placeholder="Ej. Soriana Centro" minLength={2} maxLength={120} required /></label>
    <button className={permiteUbicacion ? undefined : 'primary'} disabled={busy}>Buscar</button>
  </form>

  return <section className="panel">
    <Pasos actual={0} />
    <h1>¿En qué tienda estás?</h1>
    <p className="muted">Tu ubicación reemplaza la foto de la fachada. Confírmala una vez por visita.</p>
    {permiteUbicacion && <button className="primary full" disabled={busy} onClick={ubicar}>Usar mi ubicación</button>}
    {permiteUbicacion ? <details><summary>Buscar por nombre o dirección</summary>{formBuscar}</details> : formBuscar}
    {estado && !busy && <p className="notice" role="status">{estado}</p>}
    {busy && <Esqueleto texto={estado || 'Buscando sucursales…'} lineas={3} />}
    {!busy && tiendas.length > 0 && <ul className="sucursales">
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
  return <label className={file ? 'foto con-foto' : 'foto'}>
    <span className="foto-titulo">{label}</span>
    {preview ? <img src={preview} alt={`Foto: ${label}`} /> : <span className="foto-vacia" aria-hidden="true" />}
    <span className="foto-accion">{file ? 'Cambiar' : 'Tomar foto'}</span>
    <input aria-label={label} key={file ? 'con-foto' : 'sin-foto'} type="file" accept="image/*" capture="environment"
      onChange={(event) => onFile(event.currentTarget.files?.[0] || null)} />
  </label>
}

function Formulario({ visita, encolar, aviso }: {
  visita: Visita; encolar: (draft: Borrador) => Promise<void>; aviso: string
}) {
  const [paso, setPaso] = useState<1 | 2>(1)
  const [producto, setProducto] = useState<File | null>(null)
  const [etiqueta, setEtiqueta] = useState<File | null>(null)
  const [estado, setEstado] = useState(aviso)
  const [busy, setBusy] = useState(false)

  async function enviar(event: FormEvent) {
    event.preventDefault()
    if (!producto || !etiqueta) { setEstado('Toma la foto de la etiqueta para enviar la captura.'); return }
    setBusy(true)
    try {
      await encolar({ id: uuid(), visita_id: visita.id, capturada_en: ahora(), producto, etiqueta })
    } catch {
      setEstado('No hubo espacio para guardar el borrador. Libera almacenamiento e inténtalo de nuevo.')
      setBusy(false)
    }
  }

  return <section className="panel">
    <Pasos actual={paso} />
    {paso === 1 ? <>
      <h1>Foto del producto</h1>
      <p className="muted">Que se vean el nombre, la presentación y, si se puede, el código de barras.</p>
      <div className="fotos unica"><Foto label="Producto" file={producto} onFile={setProducto} /></div>
      {estado && <p role="status" className="notice">{estado}</p>}
      <button className="primary full" disabled={!producto} onClick={() => { setEstado(''); setPaso(2) }}>Siguiente</button>
    </> : <form className="stack" onSubmit={enviar}>
      <h1>Foto de la etiqueta</h1>
      <p className="muted">Toma la etiqueta de precio completa y de frente; el precio se lee de aquí.</p>
      <div className="fotos unica"><Foto label="Etiqueta" file={etiqueta} onFile={setEtiqueta} /></div>
      {estado && <p role="status" className="notice">{estado}</p>}
      <div className="acciones">
        <button type="button" disabled={busy} onClick={() => setPaso(1)}>Atrás</button>
        <button className="primary" disabled={busy || !etiqueta}>{busy ? 'Guardando…' : 'Enviar captura'}</button>
      </div>
    </form>}
  </section>
}

export function Campo() {
  const [visita, setVisita] = useState(visitaGuardada)
  const [pendientes, setPendientes] = useState<Borrador[]>([])
  const [enviada, setEnviada] = useState('')  // '' = capturando; id = viendo el resultado de esa captura
  const [aviso, setAviso] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [recaptura, setRecaptura] = useState({ motivo: '', n: 0 })
  const sincronizando = useRef(false)
  const sincronizarDeNuevo = useRef(false)
  const config = useQuery({ queryKey: ['config'], queryFn: () => api<Config>('/config'), staleTime: 60000 }).data
  const enCola = pendientes.some((draft) => draft.id === enviada)
  const resultado = useQuery({
    queryKey: ['captura', enviada], queryFn: () => api<Captura>('/capturas/' + enviada), enabled: !!enviada && !enCola,
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
          await subir(draft)
          await borrarBorrador(draft.id)
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
    setEnviada(draft.id)
    void sincronizar()
  }

  const r = resultado?.resultado
  return <>
    {visita && <div className="visit">
      <div><small>{visita.ubicacion === 'verificada' ? 'Ubicación verificada' : 'Visita con verificación pendiente'}</small>
        <strong>{visita.nombre}</strong></div>
      <button onClick={() => { abrir(null); setEnviada('') }}>Cambiar</button>
    </div>}
    {!visita ? <ElegirSucursal config={config} abrir={abrir} />
      : !enviada ? <Formulario key={`${visita.id}-${recaptura.n}`} visita={visita} encolar={encolar} aviso={recaptura.motivo} />
      : <section className="panel" aria-live="polite">
        <h1>Tu captura</h1>
        {enCola && !navigator.onLine && <p className="notice">Guardada en el teléfono. Se enviará en cuanto haya señal.</p>}
        {r ? <>
          <strong className={`decision ${r.decision}`}>{decisiones[r.decision]}</strong>
          {resultado.precio_centavos > 0 && <p>Precio: <strong>{pesos(resultado.precio_centavos)}</strong></p>}
          <p>{r.explicacion}</p>
          <Hallazgos resultado={r} />
          {r.decision === 'rechazada' && <button className="primary full" onClick={() => {
            setRecaptura({ motivo: `Vuelve a tomar las fotos. ${r.accion_sugerida || ''}`.trim(), n: Date.now() })
            setEnviada('')
          }}>Volver a capturar</button>}
        </> : <Esqueleto texto={enCola && !navigator.onLine ? 'Esperando señal para enviar…' : 'Validando tu captura…'} lineas={4} />}
        <button className={r?.decision === 'rechazada' ? 'full' : 'primary full'} onClick={() => {
          setRecaptura({ motivo: '', n: Date.now() }); setEnviada('')
        }}>Capturar otro producto</button>
      </section>}
    {pendientes.length > 0 && <section className="panel compact">
      <h2>Envíos pendientes ({pendientes.length})</h2>
      {aviso && <p role="status" className="notice">{aviso}</p>}
      {pendientes.map((draft) => <div key={draft.id} className="visit">
        <span>Captura de las {new Date(draft.capturada_en * 1000).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' })}</span>
        <button disabled={enviando} onClick={async () => {
          if (!window.confirm('¿Eliminar esta captura pendiente del teléfono?')) return
          await borrarBorrador(draft.id)
          setPendientes(await borradores())
        }}>Quitar</button>
      </div>)}
      <button disabled={enviando} onClick={() => void sincronizar()}>{enviando ? 'Enviando…' : 'Reintentar envíos'}</button>
    </section>}
  </>
}
