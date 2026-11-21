import { useState, type FormEvent } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { createRootRoute, createRoute, createRouter, Link, Outlet, RouterProvider } from '@tanstack/react-router'
import { api, ErrorApi, pesos, post, type Captura, type Rol } from './api'
import { Campo } from './Campo'
import { Comparar } from './Comparar'
import { Corregidos } from './Corregidos'
import { TresB } from './TresB'
import { Comparativo } from './Comparativo'
import logo3b from './assets/logo-3b.png'
import '@fontsource/inter/400.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/barlow-condensed/600.css'
import '@fontsource/barlow-condensed/700.css'
import './styles.css'

const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } })

function Acceso() {
  const query = useQueryClient()
  const [clave, setClave] = useState('')
  const [estado, setEstado] = useState('')
  const [enviando, setEnviando] = useState(false)
  async function entrar(event: FormEvent) {
    event.preventDefault()
    setEnviando(true)
    setEstado('')
    try {
      const resultado = await post<{ rol: Rol }>('/sesion', { clave })
      localStorage.setItem('validat3b.rol', resultado.rol)
      query.setQueryData(['sesion'], resultado)
    } catch (error) {
      setEstado(error instanceof ErrorApi ? error.message : 'No pudimos conectar con el servidor.')
    } finally { setEnviando(false) }
  }
  return <section className="panel acceso">
    <h1>Captura en campo</h1>
    <p className="muted">Ingresa tu clave para registrar visitas y precios de anaquel.</p>
    <form className="stack" onSubmit={entrar}>
      <label>Clave de acceso<input type="password" autoComplete="current-password" required maxLength={180}
        value={clave} onChange={(event) => setClave(event.target.value)} /></label>
      {estado && <p className="notice" role="alert">{estado}</p>}
      <button className="primary full" disabled={enviando}>{enviando ? 'Entrando…' : 'Entrar'}</button>
    </form>
  </section>
}

function App() {
  const query = useQueryClient()
  const sesion = useQuery({
    queryKey: ['sesion'], queryFn: () => api<{ rol: Rol }>('/sesion'), staleTime: 60000,
  })
  const guardado = localStorage.getItem('validat3b.rol')
  const rol = sesion.data?.rol || (!navigator.onLine && guardado === 'operador' ? guardado : null)
  const [aviso, setAviso] = useState('')
  async function salir() {
    try {
      await api('/sesion', { method: 'DELETE' })
      localStorage.removeItem('validat3b.rol')
      localStorage.removeItem('validat3b.visita')
      localStorage.removeItem('validat3b.ultimo')
      query.setQueryData(['sesion'], null)
      query.removeQueries({ predicate: (item) => item.queryKey[0] !== 'sesion' })
    } catch { setAviso('Conéctate a la red para cerrar la sesión.') }
  }

  return <>
    <header className="top"><div className="top-inner">
      <Link to="/" className="brand"><img src={logo3b} width="36" height="36" alt="Tiendas 3B" />Validat3B</Link>
      {rol && <button className="top-action" onClick={() => void salir()}>Salir</button>}
    </div></header>
    {rol && <nav className="pestanas" aria-label="Secciones"><div className="pestanas-inner">
      <Link to={rol === 'revisor' ? '/revisar' : '/'}>{rol === 'revisor' ? 'Revisión' : 'Capturar'}</Link>
      <Link to="/comparar">Comparar</Link>
      {rol === 'revisor' && <Link to="/comparativo">Versiones</Link>}
      <Link to="/corregidos">Errores corregidos</Link>
    </div></nav>}
    <main className="main">
      {aviso && <p className="notice" role="status">{aviso}</p>}
      {rol ? <Outlet /> : sesion.isPending && navigator.onLine
        ? <p role="status">Cargando tu sesión…</p> : <Acceso />}
    </main>
  </>
}

function useRol() {
  return useQuery<{ rol: Rol }>({ queryKey: ['sesion'], queryFn: () => api('/sesion'), staleTime: 60000 }).data?.rol
    || (!navigator.onLine ? localStorage.getItem('validat3b.rol') : null)
}

function Inicio() {
  const rol = useRol()
  return rol === 'revisor' ? <section className="panel">
    <h1>Revisión de capturas</h1>
    <Link className="button primary" to="/revisar">Abrir bandeja</Link>
    <Link className="button" to="/comparativo">Comparativo de versiones</Link>
  </section> : <Campo />
}

function Revisar() {
  const rol = useRol()
  const { data, refetch, isPending, isError } = useQuery({
    queryKey: ['revision'], queryFn: () => api<Captura[]>('/revision'), enabled: rol === 'revisor',
  })
  const [elegida, setElegida] = useState<Captura | null>(null)
  const [motivo, setMotivo] = useState('')
  const [aviso, setAviso] = useState('')
  const [busy, setBusy] = useState(false)
  async function decidir(decision: string) {
    if (!elegida || motivo.trim().length < 3) return
    setBusy(true)
    setAviso('')
    try {
      await post(`/capturas/${elegida.id}/revision`, { decision, motivo })
      setElegida(null)
      setMotivo('')
      await refetch()
    } catch (error) {
      setAviso(error instanceof ErrorApi ? error.message : 'No se pudo guardar la revisión.')
    } finally { setBusy(false) }
  }
  if (rol !== 'revisor') return <section className="panel">
    <h1>Revisión de capturas</h1><p>Esta pantalla requiere la clave de revisión.</p><Link to="/">Volver a captura</Link>
  </section>
  return <section className="panel">
    <h1>Revisión de capturas</h1>
    {isPending && <p role="status">Cargando capturas…</p>}
    {isError && <p role="alert">No se pudo cargar la bandeja.</p>}
    {data?.length === 0 && <p>Estás al día.</p>}
    {!elegida && <ul className="sucursales">{data?.map((row) => <li key={row.id}>
      <button className="store full" onClick={() => { setElegida(row); setMotivo(''); setAviso('') }}>
        <span><strong>{row.sucursal}</strong><small>{row.resultado?.explicacion}</small></span>
        <strong>{pesos(row.precio_centavos)}</strong>
      </button>
    </li>)}</ul>}
    {elegida && <div className="stack">
      <button onClick={() => setElegida(null)}>Volver a la bandeja</button>
      <h2>{elegida.sucursal} · {pesos(elegida.precio_centavos)}</h2>
      {elegida.resultado && <TresB resultado={elegida.resultado} />}
      <p>{elegida.resultado?.explicacion}</p>
      <div className="fotos">{(['producto', 'etiqueta'] as const).map((tipo) => <a key={tipo}
        href={`/api/capturas/${elegida.id}/foto/${tipo}`} target="_blank" rel="noreferrer">
        <img className="evidencia" src={`/api/capturas/${elegida.id}/foto/${tipo}`} alt={`Foto de ${tipo}`} />
      </a>)}</div>
      <label>Motivo de la revisión<textarea rows={3} maxLength={500} value={motivo}
        onChange={(event) => setMotivo(event.target.value)} /></label>
      {aviso && <p role="alert">{aviso}</p>}
      <div className="acciones">
        <button disabled={busy || motivo.trim().length < 3} onClick={() => void decidir('rechazada')}>Rechazar</button>
        <button className="primary" disabled={busy || motivo.trim().length < 3}
          onClick={() => void decidir('aprobada')}>Aprobar</button>
      </div>
    </div>}
  </section>
}

function ComparativoRevisor() {
  return useRol() === 'revisor' ? <Comparativo /> : <section className="panel">
    <h1>Comparativo de versiones</h1><p>Esta pantalla requiere la clave de revisión.</p><Link to="/">Volver</Link>
  </section>
}

const root = createRootRoute({ component: App })
const router = createRouter({
  routeTree: root.addChildren([
    createRoute({ getParentRoute: () => root, path: '/', component: Inicio }),
    createRoute({ getParentRoute: () => root, path: '/revisar', component: Revisar }),
    createRoute({ getParentRoute: () => root, path: '/comparar', component: Comparar }),
    createRoute({ getParentRoute: () => root, path: '/corregidos', component: Corregidos }),
    createRoute({ getParentRoute: () => root, path: '/comparativo', component: ComparativoRevisor }),
  ]),
})

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={cliente}><RouterProvider router={router} /></QueryClientProvider>,
)
if (window.isSecureContext && 'serviceWorker' in navigator) {
  void navigator.serviceWorker.register('/sw.js').catch(() => {})
}
