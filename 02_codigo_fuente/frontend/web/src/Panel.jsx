import { useEffect, useState } from 'react'

const FORM_VACIO = { clienteId: '', productoId: '', descripcion: '' }

const formatoHora = new Intl.DateTimeFormat('es-EC', {
  dateStyle: 'short',
  timeStyle: 'medium',
})

function hora(valor) {
  return valor ? formatoHora.format(new Date(valor)) : '—'
}

async function leer(respuesta) {
  if (respuesta.ok) return respuesta.json()
  let detalle = `Error ${respuesta.status}`
  try {
    const cuerpo = await respuesta.json()
    if (typeof cuerpo.detail === 'string') detalle = cuerpo.detail
    else if (Array.isArray(cuerpo.detail)) detalle = 'Revisa los datos del formulario'
  } catch {
    // se deja el mensaje genérico
  }
  throw new Error(detalle)
}

export default function Panel() {
  const [clientes, setClientes] = useState([])
  const [productos, setProductos] = useState([])
  const [cola, setCola] = useState([])
  const [errorCarga, setErrorCarga] = useState(null)
  const [version, setVersion] = useState(0)
  const [form, setForm] = useState(FORM_VACIO)
  const [aviso, setAviso] = useState(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    Promise.all([
      fetch('/api/clientes').then(leer),
      fetch('/api/productos').then(leer),
      fetch('/api/ordenes/cola').then(leer),
    ])
      .then(([c, p, o]) => {
        setClientes(c)
        setProductos(p)
        setCola(o)
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

  async function darAcuse(id) {
    try {
      await fetch(`/api/ordenes/${id}/acuse`, { method: 'POST' }).then(leer)
      setVersion((v) => v + 1)
    } catch (error) {
      setAviso({ tipo: 'error', texto: error.message })
    }
  }

  const puedeCrear = form.clienteId && form.descripcion.trim().length >= 3 && !enviando

  return (
    <main className="pagina">
      <header className="encabezado">
        <h1>Panel del asesor</h1>
        <p>Órdenes de producción · Joyería Xavier</p>
      </header>

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

      <section aria-label="Cola del taller">
        <h2 className="cola-titulo">
          Cola del taller <span>({cola.length})</span>
          <button type="button" onClick={() => setVersion((v) => v + 1)}>
            Actualizar
          </button>
        </h2>
        {cola.length === 0 ? (
          <p className="estado">No hay órdenes en la cola.</p>
        ) : (
          <table className="cola">
            <thead>
              <tr>
                <th>Orden</th>
                <th>Cliente</th>
                <th>Joya</th>
                <th>Detalle</th>
                <th>Publicada</th>
                <th>Acuse</th>
              </tr>
            </thead>
            <tbody>
              {cola.map((o) => (
                <tr key={o.id}>
                  <td>{o.codigo}</td>
                  <td>{o.cliente}</td>
                  <td>{o.producto ?? 'A medida'}</td>
                  <td>{o.descripcion}</td>
                  <td>{hora(o.publicada_en)}</td>
                  <td>
                    {o.acuse_pendiente ? (
                      <>
                        <span className="insignia pendiente">Acuse pendiente</span>
                        <button type="button" onClick={() => darAcuse(o.id)}>
                          Simular acuse del taller
                        </button>
                      </>
                    ) : (
                      <span className="insignia recibida">Recibida por el taller</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  )
}
