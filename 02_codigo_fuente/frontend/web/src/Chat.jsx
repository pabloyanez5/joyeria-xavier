import { useEffect, useRef, useState } from 'react'

const BIENVENIDA = {
  de: 'agente',
  texto:
    'Simulador del asistente. Escribe como lo haría un cliente por WhatsApp (por ejemplo: "hola", "busco un anillo de oro" o "quiero hablar con un asesor").',
}

function nuevoIdCliente() {
  return `sim-${Math.random().toString(36).slice(2, 10)}`
}

// Convierte las URLs del texto en enlaces que abren en otra pestaña.
function conEnlaces(texto) {
  return texto.split(/(https?:\/\/\S+)/g).map((trozo, i) =>
    /^https?:\/\//.test(trozo) ? (
      <a key={i} href={trozo} target="_blank" rel="noreferrer">
        {trozo}
      </a>
    ) : (
      trozo
    ),
  )
}

export default function Chat() {
  const [abierto, setAbierto] = useState(false)
  const [mensajes, setMensajes] = useState([BIENVENIDA])
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [escalada, setEscalada] = useState(false)
  const [idCliente, setIdCliente] = useState(nuevoIdCliente)
  const fin = useRef(null)

  useEffect(() => {
    fin.current?.scrollIntoView({ block: 'end' })
  }, [mensajes, abierto])

  async function enviar(e) {
    e.preventDefault()
    const limpio = texto.trim()
    if (!limpio || enviando) return
    setTexto('')
    setMensajes((m) => [...m, { de: 'cliente', texto: limpio }])
    setEnviando(true)
    try {
      const r = await fetch('/api/agente/mensajes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canal: 'whatsapp',
          id_canal: idCliente,
          texto: limpio,
          nombre: 'Cliente de prueba',
        }),
      })
      if (!r.ok) throw new Error(`Error ${r.status}`)
      const datos = await r.json()
      const nuevos = []
      if (datos.respuesta) nuevos.push({ de: 'agente', texto: datos.respuesta })
      if (datos.escalada && !escalada) {
        setEscalada(true)
        nuevos.push({
          de: 'sistema',
          texto: 'La conversación pasó a un asesor. El asistente ya no responde aquí.',
        })
      }
      setMensajes((m) => [...m, ...nuevos])
    } catch (error) {
      setMensajes((m) => [
        ...m,
        { de: 'sistema', texto: `No se pudo contactar al asistente (${error.message}).` },
      ])
    } finally {
      setEnviando(false)
    }
  }

  function reiniciar() {
    setMensajes([BIENVENIDA])
    setEscalada(false)
    setIdCliente(nuevoIdCliente())
  }

  if (!abierto) {
    return (
      <button type="button" className="chat-abrir" onClick={() => setAbierto(true)}>
        Hablar con el asistente
      </button>
    )
  }

  return (
    <section className="chat" aria-label="Asistente virtual">
      <header className="chat-cabecera">
        <strong>Asistente · simulador</strong>
        <span>
          <button type="button" onClick={reiniciar}>
            Nueva conversación
          </button>
          <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar">
            ×
          </button>
        </span>
      </header>
      <div className="chat-mensajes" aria-live="polite">
        {mensajes.map((m, i) => (
          <p key={i} className={`burbuja ${m.de}`}>
            {conEnlaces(m.texto)}
          </p>
        ))}
        {enviando && <p className="burbuja agente">Escribiendo…</p>}
        <div ref={fin} />
      </div>
      <form className="chat-form" onSubmit={enviar}>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escribe un mensaje"
          maxLength={1000}
          aria-label="Mensaje"
        />
        <button type="submit" disabled={enviando || !texto.trim()}>
          Enviar
        </button>
      </form>
    </section>
  )
}
