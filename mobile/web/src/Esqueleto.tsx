// Placeholder animado mientras algo carga; el texto solo lo oyen los lectores de pantalla.
export function Esqueleto({ texto, lineas = 3, foto = false }: { texto: string; lineas?: number; foto?: boolean }) {
  return <div className="esqueleto" role="status">
    <span className="sr-only">{texto}</span>
    {foto && <span className="hueso foto-hueso" aria-hidden="true" />}
    {Array.from({ length: lineas }, (_, i) => <span key={i} className="hueso" aria-hidden="true" />)}
  </div>
}
