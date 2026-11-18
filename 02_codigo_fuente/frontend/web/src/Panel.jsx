import { useEffect, useState } from 'react'
import Acceso from './Acceso.jsx'
import Icono from './Icono.jsx'
import InterruptorTema from './InterruptorTema.jsx'
import PanelLateral from './PanelLateral.jsx'
import Conversaciones from './Conversaciones.jsx'
import FormularioOrden from './FormularioOrden.jsx'
import Resumen from './Resumen.jsx'
import Tablero from './Tablero.jsx'
import { ROL, SESION_CERRADA, pedir, puede, salir, sesionGuardada } from './sesion.js'
import { useTema } from './tema.js'
import { leer } from './util.js'

// Cada sección del panel y los roles que la ven (el rol admin ve todas).
const VISTAS = [
  { id: 'conversaciones', titulo: 'Conversaciones', icono: 'chat', roles: ['asesor'] },
  { id: 'ordenes', titulo: 'Órdenes', icono: 'tablero', roles: ['asesor', 'taller'] },
  { id: 'resumen', titulo: 'Resumen', icono: 'grafico', roles: ['direccion'] },
]

const LOGO = { claro: '/marca/logo-durazno.png', oscuro: '/marca/logo-blanco.png' }

function iniciales(nombre) {
  return (nombre ?? '')
    .split(/\s+/)
    .filter((p) => p.length > 2) // "Asesor de prueba" -> AP
    .slice(0, 2)
    .map((p) => p[0].toUpperCase())
    .join('')
}

// Menú lateral (JOY-88): logo, secciones del rol, switch de tema y usuario.
function MenuLateral({ usuario, vistas, vista, onElegir, tema, onAlternarTema }) {
  return (
    <nav className="lateral" aria-label="Secciones del panel">
      <img className="lateral-logo" src={LOGO[tema]} alt="Joyería Xavier, inspirado en ti" />
      <ul className="lateral-secciones">
        {vistas.map((v) => (
          <li key={v.id}>
            <button
              type="button"
              aria-current={vista === v.id ? 'page' : undefined}
              onClick={() => onElegir(v.id)}
            >
              <Icono nombre={v.icono} />
              {v.titulo}
            </button>
          </li>
        ))}
      </ul>
      <div className="lateral-pie">
        <InterruptorTema tema={tema} onAlternar={onAlternarTema} />
        <div className="lateral-usuario">
          <span className="avatar" aria-hidden="true">
            {iniciales(usuario.nombre)}
          </span>
          <span className="lateral-usuario-datos">
            <strong>{usuario.nombre}</strong>
            <small>{ROL[usuario.rol] ?? usuario.rol}</small>
          </span>
          <button type="button" className="boton-icono" onClick={salir} aria-label="Cerrar sesión" title="Cerrar sesión">
            <Icono nombre="salir" />
          </button>
        </div>
      </div>
    </nav>
  )
}


// El panel pide iniciar sesión; al cerrarla (o si caduca) vuelve a la pantalla de acceso.
export default function Panel() {
  const [sesion, setSesion] = useState(sesionGuardada)
  const [tema, alternarTema] = useTema()

  useEffect(() => {
    const cerrar = () => setSesion(null)
    window.addEventListener(SESION_CERRADA, cerrar)
    return () => window.removeEventListener(SESION_CERRADA, cerrar)
  }, [])

  if (!sesion) return <Acceso onEntrar={setSesion} tema={tema} onAlternarTema={alternarTema} />
  return (
    <PanelInterno
      key={sesion.usuario.id}
      usuario={sesion.usuario}
      tema={tema}
      onAlternarTema={alternarTema}
    />
  )
}

function PanelInterno({ usuario, tema, onAlternarTema }) {
  const vistas = VISTAS.filter((v) => puede(usuario, ...v.roles))
  const esAsesor = puede(usuario, 'asesor')
  const [clientes, setClientes] = useState([])
  const [productos, setProductos] = useState([])
  const [errorCarga, setErrorCarga] = useState(null)
  const [version, setVersion] = useState(0)
  // Datos precargados desde una conversación; `turno` reinicia el formulario al cambiar.
  const [precarga, setPrecarga] = useState({ turno: 0, inicial: null })
  const [aviso, setAviso] = useState(null)
  const [vista, setVista] = useState(vistas[0]?.id ?? null)
  const [formAbierto, setFormAbierto] = useState(false)

  useEffect(() => {
    if (!esAsesor) return // solo el asesor crea órdenes: los demás no necesitan estas listas
    Promise.all([
      pedir('/api/clientes').then(leer),
      fetch('/api/productos').then(leer),
    ])
      .then(([c, p]) => {
        setClientes(c)
        setProductos(p)
        setErrorCarga(null)
      })
      .catch((e) => setErrorCarga(e.message))
  }, [version, esAsesor])

  function ordenCreada(texto) {
    setFormAbierto(false)
    setAviso({ tipo: 'ok', texto })
    setPrecarga((p) => ({ turno: p.turno + 1, inicial: null }))
    setVersion((v) => v + 1)
  }

  function crearDesdeConversacion(inicial) {
    setPrecarga((p) => ({ turno: p.turno + 1, inicial }))
    setVersion((v) => v + 1) // recarga los clientes: el de la conversación puede ser nuevo
    setAviso({
      tipo: 'ok',
      texto: 'Datos precargados desde la conversación. Complétalos con el cliente y crea la orden.',
    })
    setVista('ordenes')
    setFormAbierto(true)
  }

  const actual = vistas.find((v) => v.id === vista)

  return (
    <div className="panel-app">
      <MenuLateral
        usuario={usuario}
        vistas={vistas}
        vista={vista}
        onElegir={setVista}
        tema={tema}
        onAlternarTema={onAlternarTema}
      />
    <main className="panel-contenido">
      <h1 className="panel-titulo">{actual?.titulo ?? 'Panel interno'}</h1>

      {vistas.length === 0 && (
        <p className="estado error">Tu rol todavía no tiene secciones asignadas en el panel.</p>
      )}

      {vista === 'resumen' && <Resumen />}

      {vista === 'conversaciones' && <Conversaciones onCrearOrden={crearDesdeConversacion} />}

      {vista === 'ordenes' && (
        <>
          {esAsesor && aviso && (
            <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`} role="status">
              {aviso.texto}
            </p>
          )}
          <Tablero
            version={version}
            puedeAvanzar={puede(usuario, 'taller')}
            puedeVerificar={esAsesor}
            onNuevaOrden={
              esAsesor
                ? () => {
                    setAviso(null)
                    setFormAbierto(true)
                  }
                : undefined
            }
          />
          {esAsesor && formAbierto && (
            <PanelLateral
              titulo="Nueva orden"
              subtitulo="Una o varias joyas del mismo cliente"
              onCerrar={() => setFormAbierto(false)}
            >
              {errorCarga && <p className="estado error">{errorCarga}</p>}
              {clientes.length === 0 && !errorCarga && (
                <p className="nota">
                  Todavía no hay clientes. Escríbele al asistente desde el catálogo para crear uno.
                </p>
              )}
              {aviso && (
                <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`}>{aviso.texto}</p>
              )}
              <FormularioOrden
                key={precarga.turno}
                clientes={clientes}
                productos={productos}
                inicial={precarga.inicial}
                onCreada={ordenCreada}
              />
            </PanelLateral>
          )}
        </>
      )}
    </main>
    </div>
  )
}
