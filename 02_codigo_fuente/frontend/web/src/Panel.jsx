import { useEffect, useState } from 'react'
import Acceso from './Acceso.jsx'
import Conversaciones from './Conversaciones.jsx'
import FormularioOrden from './FormularioOrden.jsx'
import Resumen from './Resumen.jsx'
import Tablero from './Tablero.jsx'
import { ROL, SESION_CERRADA, pedir, puede, salir, sesionGuardada } from './sesion.js'
import { leer } from './util.js'

// Cada sección del panel y los roles que la ven (el rol admin ve todas).
const VISTAS = [
  { id: 'conversaciones', titulo: 'Conversaciones', roles: ['asesor'] },
  { id: 'ordenes', titulo: 'Órdenes', roles: ['asesor', 'taller'] },
  { id: 'resumen', titulo: 'Resumen', roles: ['direccion'] },
]

// El panel pide iniciar sesión; al cerrarla (o si caduca) vuelve a la pantalla de acceso.
export default function Panel() {
  const [sesion, setSesion] = useState(sesionGuardada)

  useEffect(() => {
    const cerrar = () => setSesion(null)
    window.addEventListener(SESION_CERRADA, cerrar)
    return () => window.removeEventListener(SESION_CERRADA, cerrar)
  }, [])

  if (!sesion) return <Acceso onEntrar={setSesion} />
  return <PanelInterno key={sesion.usuario.id} usuario={sesion.usuario} />
}

function PanelInterno({ usuario }) {
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
  }

  return (
    <main className="pagina">
      <header className="encabezado">
        <h1>Panel interno</h1>
        <p>Joyería Xavier</p>
        <p className="sesion-actual">
          {usuario.nombre} · {ROL[usuario.rol] ?? usuario.rol}{' '}
          <button type="button" onClick={salir}>
            Cerrar sesión
          </button>
        </p>
      </header>

      {vistas.length === 0 && (
        <p className="estado error">Tu rol todavía no tiene secciones asignadas en el panel.</p>
      )}

      {vistas.length > 1 && (
        <nav className="pestanas" aria-label="Secciones del panel">
          {vistas.map((v) => (
            <button
              key={v.id}
              type="button"
              className={vista === v.id ? 'activa' : ''}
              onClick={() => setVista(v.id)}
            >
              {v.titulo}
            </button>
          ))}
        </nav>
      )}

      {vista === 'resumen' && <Resumen />}

      {vista === 'conversaciones' && <Conversaciones onCrearOrden={crearDesdeConversacion} />}

      {vista === 'ordenes' && (
        <>
      {esAsesor && (
        <>
      {errorCarga && <p className="estado error">{errorCarga}</p>}

      <FormularioOrden
        key={precarga.turno}
        clientes={clientes}
        productos={productos}
        inicial={precarga.inicial}
        onCreada={ordenCreada}
      />

      {clientes.length === 0 && !errorCarga && (
        <p className="estado">
          Todavía no hay clientes. Escríbele al asistente desde el catálogo para crear uno.
        </p>
      )}
      {aviso && <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`}>{aviso.texto}</p>}
        </>
      )}

      <Tablero
        version={version}
        puedeAvanzar={puede(usuario, 'taller')}
        puedeVerificar={esAsesor}
      />
        </>
      )}
    </main>
  )
}
