import { useState } from 'react'
import { pedir } from './sesion.js'
import { leer } from './util.js'

const JOYA_VACIA = {
  productoId: '',
  descripcion: '',
  peso: '',
  total: '',
  entregaTaller: '',
  entregaCliente: '',
  foto: '',
  interes: null, // número de la joya en la ficha del cliente, si viene de una conversación
}
const MAX_JOYAS = 8

function contactoDe(clientes, clienteId) {
  const cliente = clientes.find((c) => String(c.id) === String(clienteId))
  return { nombre: cliente?.nombre_completo ?? '', telefono: cliente?.telefono ?? '' }
}

function joyaParaEnviar(j) {
  return {
    producto_id: j.productoId ? Number(j.productoId) : null,
    descripcion: j.descripcion,
    peso_gramos: j.peso,
    fecha_entrega_taller: j.entregaTaller,
    fecha_entrega_cliente: j.entregaCliente,
    total: j.total,
    foto_referencia_url: j.foto.trim() || null,
    interes: j.interes,
  }
}

// Formulario de la orden (RF-03): datos del cliente y una o varias joyas. Con varias joyas se
// crea una orden por cada una y quedan unidas en un pedido.
export default function FormularioOrden({ clientes, productos, inicial, onCreada }) {
  const [clienteId, setClienteId] = useState(inicial?.clienteId ?? '')
  // Lo que el asesor escribe; mientras no escriba, se usa lo que ya se sabe del cliente.
  // Así los datos aparecen aunque la lista de clientes llegue después de abrir el formulario.
  const [editado, setEditado] = useState({})
  const sugerido = contactoDe(clientes, clienteId)
  const contacto = {
    nombre: editado.nombre ?? sugerido.nombre,
    telefono: editado.telefono ?? sugerido.telefono,
  }
  const clienteEnLista = clientes.some((c) => String(c.id) === String(clienteId))
  const [joyas, setJoyas] = useState(() =>
    (inicial?.descripciones ?? ['']).map((descripcion, n) => ({
      ...JOYA_VACIA,
      descripcion,
      interes: inicial?.intereses?.[n] ?? null,
    })),
  )
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)

  function elegirCliente(e) {
    setClienteId(e.target.value)
    setEditado({})
    // Las joyas de la ficha eran del cliente anterior: ya no se marcan como pedidas.
    setJoyas((lista) => lista.map((j) => ({ ...j, interes: null })))
  }

  function cambiarJoya(indice, campo) {
    return (e) =>
      setJoyas((lista) => lista.map((j, n) => (n === indice ? { ...j, [campo]: e.target.value } : j)))
  }

  async function crear(e) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    const cliente = {
      cliente_id: Number(clienteId),
      nombre_completo: contacto.nombre,
      telefono: contacto.telefono,
    }
    try {
      if (joyas.length === 1) {
        const orden = await pedir('/api/ordenes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...cliente, ...joyaParaEnviar(joyas[0]) }),
        }).then(leer)
        onCreada(`Orden ${orden.codigo} creada. Entra a la cola del taller cuando registres el abono.`)
      } else {
        const pedido = await pedir('/api/ordenes/pedido', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...cliente, joyas: joyas.map(joyaParaEnviar) }),
        }).then(leer)
        const codigos = pedido.ordenes.map((o) => o.codigo).join(', ')
        onCreada(
          `Pedido ${pedido.codigo} creado con ${pedido.ordenes.length} órdenes (${codigos}). ` +
            'Cada una entra a la cola del taller cuando registres su abono.',
        )
      }
    } catch (fallo) {
      setError(fallo.message)
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="orden-form" onSubmit={crear}>
      <fieldset>
        <legend>Cliente</legend>
        <label>
          Cliente
          <select value={clienteId} onChange={elegirCliente} required>
            <option value="">Elige un cliente</option>
            {clienteId && !clienteEnLista && <option value={clienteId}>Cargando cliente…</option>}
            {clientes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nombre} ({c.canal})
              </option>
            ))}
          </select>
        </label>
        <label>
          Nombre completo
          <input
            value={contacto.nombre}
            onChange={(e) => setEditado((c) => ({ ...c, nombre: e.target.value }))}
            maxLength={150}
            placeholder="Confírmalo con el cliente"
            required
          />
        </label>
        <label>
          Teléfono de contacto
          <input
            type="tel"
            value={contacto.telefono}
            onChange={(e) => setEditado((c) => ({ ...c, telefono: e.target.value }))}
            maxLength={30}
            placeholder="Ej. 0991234567"
            required
          />
        </label>
      </fieldset>

      {joyas.map((j, n) => (
        <fieldset key={n}>
          <legend>
            {joyas.length > 1 ? `Joya ${n + 1}` : 'Joya'}
            {joyas.length > 1 && (
              <button type="button" onClick={() => setJoyas((lista) => lista.filter((_, m) => m !== n))}>
                Quitar
              </button>
            )}
          </legend>
          <label className="orden-descripcion">
            Detalle de la joya
            <textarea
              rows={2}
              value={j.descripcion}
              onChange={cambiarJoya(n, 'descripcion')}
              maxLength={1000}
              placeholder="Material, quilataje, talla, grabado…"
              required
            />
          </label>
          <label>
            Joya del catálogo (opcional)
            <select value={j.productoId} onChange={cambiarJoya(n, 'productoId')}>
              <option value="">A medida / sin producto</option>
              {productos.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre}
                </option>
              ))}
            </select>
          </label>
          <label>
            Peso promedio (g)
            <input type="number" min="0.01" step="0.01" value={j.peso} onChange={cambiarJoya(n, 'peso')} required />
          </label>
          <label>
            Total (USD)
            <input type="number" min="0.01" step="0.01" value={j.total} onChange={cambiarJoya(n, 'total')} required />
          </label>
          <label>
            Entrega al taller
            <input type="date" value={j.entregaTaller} onChange={cambiarJoya(n, 'entregaTaller')} required />
          </label>
          <label>
            Entrega al cliente
            <input
              type="date"
              value={j.entregaCliente}
              min={j.entregaTaller || undefined}
              onChange={cambiarJoya(n, 'entregaCliente')}
              required
            />
          </label>
          <label>
            Foto de referencia (enlace, opcional)
            <input type="url" value={j.foto} onChange={cambiarJoya(n, 'foto')} maxLength={500} placeholder="https://…" />
          </label>
        </fieldset>
      ))}

      <div className="orden-acciones">
        {joyas.length < MAX_JOYAS && (
          <button type="button" onClick={() => setJoyas((lista) => [...lista, { ...JOYA_VACIA }])}>
            Añadir otra joya al pedido
          </button>
        )}
        <button type="submit" className="boton primario" disabled={enviando}>
          {enviando
            ? 'Creando…'
            : joyas.length > 1
              ? `Crear pedido con ${joyas.length} órdenes`
              : 'Crear orden'}
        </button>
      </div>
      {error && <p className="estado error">{error}</p>}
    </form>
  )
}
