import { useCallback, useEffect, useState } from 'react'
import { hora, leer } from './util.js'

const COLUMNAS = [
  { etapa: 'en_cola', titulo: 'En cola' },
  { etapa: 'en_produccion', titulo: 'En producción' },
  { etapa: 'terminada', titulo: 'Terminada' },
  { etapa: 'entregada', titulo: 'Entregada' },
]
const NOMBRE = Object.fromEntries(COLUMNAS.map((c) => [c.etapa, c.titulo]))

const TEXTO_AVISO = {
  enviado: 'El cliente recibió el aviso por su canal.',
  no_enviado: 'La orden avanzó, pero el aviso no se pudo enviar',
  omitido: 'La orden avanzó sin avisar al cliente',
}

// Tablero de producción: una columna por etapa; el taller avanza cada orden a la siguiente.
export default function Tablero({ version, onCambio }) {
  const [ordenes, setOrdenes] = useState([])
  const [error, setError] = useState(null)
  const [aviso, setAviso] = useState(null)
  const [avisar, setAvisar] = useState(true)
  const [ocupada, setOcupada] = useState(null)

  const cargar = useCallback(() => {
    fetch('/api/ordenes')
      .then(leer)
      .then((o) => {
        setOrdenes(o)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    cargar()
    const reloj = setInterval(cargar, 10000)
    return () => clearInterval(reloj)
  }, [cargar, version])

  async function avanzar(orden) {
    setOcupada(orden.id)
    setAviso(null)
    try {
      const r = await fetch(`/api/ordenes/${orden.id}/etapa`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ etapa: orden.siguiente_etapa, avisar_al_cliente: avisar }),
      }).then(leer)
      const base = `${r.codigo} pasó a «${NOMBRE[r.etapa_actual]}». `
      const texto = TEXTO_AVISO[r.aviso_al_cliente] + (r.detalle_aviso ? `: ${r.detalle_aviso}` : '')
      setAviso({ tipo: r.aviso_al_cliente === 'no_enviado' ? 'error' : 'ok', texto: base + texto })
      cargar()
      onCambio?.()
    } catch (e) {
      setAviso({ tipo: 'error', texto: e.message })
    } finally {
      setOcupada(null)
    }
  }

  async function darAcuse(orden) {
    try {
      await fetch(`/api/ordenes/${orden.id}/acuse`, { method: 'POST' }).then(leer)
      cargar()
    } catch (e) {
      setAviso({ tipo: 'error', texto: e.message })
    }
  }

  return (
    <section aria-label="Tablero de producción">
      <h2 className="cola-titulo">
        Tablero del taller <span>({ordenes.length})</span>
        <label className="tablero-avisar">
          <input type="checkbox" checked={avisar} onChange={(e) => setAvisar(e.target.checked)} />
          Avisar al cliente por WhatsApp
        </label>
        <button type="button" onClick={cargar}>
          Actualizar
        </button>
      </h2>

      {error && <p className="estado error">{error}</p>}
      {aviso && <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`}>{aviso.texto}</p>}

      <div className="tablero">
        {COLUMNAS.map(({ etapa, titulo }) => {
          const tarjetas = ordenes.filter((o) => o.etapa_actual === etapa)
          return (
            <div key={etapa} className={`tablero-col ${etapa}`}>
              <h3>
                {titulo} <span>{tarjetas.length}</span>
              </h3>
              {tarjetas.length === 0 && <p className="tablero-vacio">Sin órdenes</p>}
              {tarjetas.map((o) => (
                <article key={o.id} className="tarjeta-orden">
                  <strong>{o.codigo}</strong>
                  <span className="tarjeta-cliente">{o.cliente ?? 'Cliente'}</span>
                  <p>{o.descripcion}</p>
                  <small>{o.producto ?? 'A medida'} · {hora(o.publicada_en ?? o.creado_en)}</small>
                  {o.acuse_pendiente && (
                    <div>
                      <span className="insignia pendiente">Acuse pendiente</span>
                      <button type="button" onClick={() => darAcuse(o)}>
                        Simular acuse del taller
                      </button>
                    </div>
                  )}
                  {o.siguiente_etapa && (
                    <button
                      type="button"
                      className="boton primario"
                      disabled={ocupada === o.id}
                      onClick={() => avanzar(o)}
                    >
                      {ocupada === o.id ? 'Avanzando…' : `Pasar a ${NOMBRE[o.siguiente_etapa].toLowerCase()}`}
                    </button>
                  )}
                </article>
              ))}
            </div>
          )
        })}
      </div>
    </section>
  )
}
