import { useEffect, useRef } from 'react'
import Icono from './Icono.jsx'

// Panel que se abre desde la derecha (JOY-89): detalle de una orden o el formulario de una
// nueva. Se cierra con la X, tocando el fondo o con la tecla Escape.
export default function PanelLateral({ titulo, subtitulo, onCerrar, children }) {
  const cerrar = useRef(null)

  useEffect(() => {
    cerrar.current?.focus()
  }, [titulo])

  // Escape cierra aunque el foco se haya ido (por ejemplo, tras enviar un formulario).
  useEffect(() => {
    const alPresionar = (e) => e.key === 'Escape' && onCerrar()
    document.addEventListener('keydown', alPresionar)
    return () => document.removeEventListener('keydown', alPresionar)
  }, [onCerrar])

  return (
    <div className="lateral-velo">
      <button type="button" className="lateral-fondo" aria-label="Cerrar" tabIndex={-1} onClick={onCerrar} />
      <aside className="panel-lateral" role="dialog" aria-modal="true" aria-label={titulo}>
        <header className="panel-lateral-cabeza">
          <div>
            {subtitulo && <small>{subtitulo}</small>}
            <h2>{titulo}</h2>
          </div>
          <button ref={cerrar} type="button" className="boton-icono" onClick={onCerrar} aria-label="Cerrar">
            <Icono nombre="cerrar" />
          </button>
        </header>
        <div className="panel-lateral-cuerpo">{children}</div>
      </aside>
    </div>
  )
}
