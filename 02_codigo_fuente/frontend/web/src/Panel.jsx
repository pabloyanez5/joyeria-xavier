import { useEffect, useState } from 'react'
import Conversaciones from './Conversaciones.jsx'
import Tablero from './Tablero.jsx'
import { leer } from './util.js'

const FORM_VACIO = { clienteId: '', productoId: '', descripcion: '' }

export default function Panel() {
  const [clientes, setClientes] = useState([])
  const [productos, setProductos] = useState([])
  const [errorCarga, setErrorCarga] = useState(null)
  const [version, setVersion] = useState(0)
  const [form, setForm] = useState(FORM_VACIO)
  const [aviso, setAviso] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [vista, setVista] = useState('conversaciones')

  useEffect(() => {
    Promise.all([
      fetch('/api/clientes').then(leer),
      fetch('/api/productos').then(leer),
    ])
      .then(([c, p]) => {
        setClientes(c)
        setProductos(p)
        setErrorCarga(null)
      })
      .catch((e) => setErrorCarga(e.message))
  }, [version])

  function cambiar(campo) {
    return (e) => setForm((f) => ({ ...f, [campo]: e.target.value }))
  }

  async function crear(e) {
    e.preventDefault()
    setEnviando(true)
    setAviso(null)
    try {
      const orden = await fetch('/api/ordenes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cliente_id: Number(form.clienteId),
          producto_id: form.productoId ? Number(form.productoId) : null,
          descripcion: form.descripcion,
        }),
      }).then(leer)
      setAviso({ tipo: 'ok', texto: `Orden ${orden.codigo} creada y publicada en la cola del taller.` })
      setForm(FORM_VACIO)
      setVersion((v) => v + 1)
    } catch (error) {
      setAviso({ tipo: 'error', texto: error.message })
    } finally {
      setEnviando(false)
    }
  }

  function crearDesdeConversacion(datos) {
    setForm(datos)
    setAviso({ tipo: 'ok', texto: 'Datos precargados desde la conversación. Revísalos y crea la orden.' })
    setVista('ordenes')
  }

  const puedeCrear = form.clienteId && form.descripcion.trim().length >= 3 && !enviando

  return (
    <main className="pagina">
      <header className="encabezado">
        <h1>Panel del asesor</h1>
        <p>Conversaciones y órdenes de producción · Joyería Xavier</p>
      </header>

      <nav className="pestanas" aria-label="Secciones del panel">
        <button
          type="button"
          className={vista === 'conversaciones' ? 'activa' : ''}
          onClick={() => setVista('conversaciones')}
        >
          Conversaciones
        </button>
        <button type="button" className={vista === 'ordenes' ? 'activa' : ''} onClick={() => setVista('ordenes')}>
          Órdenes
        </button>
      </nav>

      {vista === 'conversaciones' && <Conversaciones onCrearOrden={crearDesdeConversacion} />}

      {vista === 'ordenes' && (
        <>
      {errorCarga && <p className="estado error">{errorCarga}</p>}

      <form className="filtros orden-form" onSubmit={crear}>
        <label>
          Cliente
          <select value={form.clienteId} onChange={cambiar('clienteId')} required>
            <option value="">Elige un cliente</option>
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre} ({c.canal})
              </option>
            ))}
          </select>
        </label>
        <label>
          Joya del catálogo (opcional)
          <select value={form.productoId} onChange={cambiar('productoId')}>
            <option value="">A medida / sin producto</option>
            {productos.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="orden-descripcion">
          Detalle de la orden
          <textarea
            rows={3}
            value={form.descripcion}
            onChange={cambiar('descripcion')}
            maxLength={1000}
            placeholder="Material, quilataje, talla, grabado, fecha de entrega…"
            required
          />
        </label>
        <button type="submit" disabled={!puedeCrear}>
          {enviando ? 'Creando…' : 'Crear orden'}
        </button>
      </form>

      {clientes.length === 0 && !errorCarga && (
        <p className="estado">
          Todavía no hay clientes. Escríbele al asistente desde el catálogo para crear uno.
        </p>
      )}
      {aviso && <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`}>{aviso.texto}</p>}

      <Tablero version={version} />
        </>
      )}
    </main>
  )
}
