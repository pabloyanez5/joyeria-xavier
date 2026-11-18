import { useEffect, useRef, useState } from 'react'
import { pedir } from './sesion.js'
import { hora, leer } from './util.js'

const ETIQUETA_ESTADO = { activa: 'Atiende el agente', escalada: 'Espera a un asesor', cerrada: 'Cerrada' }
const AUTOR = { cliente: 'Cliente', agente: 'Agente', asesor: 'Asesor', sistema: 'Sistema' }
// Qué redactó la respuesta del agente (sirve para saber si contestó el modelo o un respaldo).
const ORIGEN = {
  modelo: 'modelo',
  respaldo: 'modelo de respaldo',
  reglas: 'reglas',
  menu: 'menú',
  guardrail: 'seguridad',
}
const ACTUALIZAR_CADA_MS = 8000
const NOMBRE_ETAPA = {
  por_verificar: 'Por verificar',
  en_cola: 'En cola',
  en_produccion: 'En producción',
  terminada: 'Terminada',
  entregada: 'Entregada',
}

function Estado({ valor }) {
  return <span className={`insignia estado-${valor}`}>{ETIQUETA_ESTADO[valor] ?? valor}</span>
}

function Datos({ items }) {
  if (items.length === 0) return null
  return (
    <dl>
      {items.map((i) => (
        <div key={i.etiqueta}>
          <dt>{i.etiqueta}</dt>
          <dd>{i.valor}</dd>
        </div>
      ))}
    </dl>
  )
}

export default function Conversaciones({ onCrearOrden }) {
  const [lista, setLista] = useState([])
  const [elegida, setElegida] = useState(null)
  const [detalle, setDetalle] = useState(null)
  const [version, setVersion] = useState(0)
  const [error, setError] = useState(null)
  const [aviso, setAviso] = useState(null)
  const [texto, setTexto] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const caja = useRef(null)

  const idActual = elegida ?? lista[0]?.id ?? null

  useEffect(() => {
    let vigente = true
    function cargar() {
      pedir('/api/conversaciones')
        .then(leer)
        .then((datos) => {
          if (!vigente) return
          setLista(datos)
          setError(null)
        })
        .catch((e) => vigente && setError(e.message))
    }
    cargar()
    const reloj = setInterval(cargar, ACTUALIZAR_CADA_MS)
    return () => {
      vigente = false
      clearInterval(reloj)
    }
  }, [version])

  useEffect(() => {
    if (idActual === null) return undefined
    let vigente = true
    function cargar() {
      pedir(`/api/conversaciones/${idActual}`)
        .then(leer)
        .then((datos) => vigente && setDetalle(datos))
        .catch((e) => vigente && setError(e.message))
    }
    cargar()
    const reloj = setInterval(cargar, ACTUALIZAR_CADA_MS)
    return () => {
      vigente = false
      clearInterval(reloj)
    }
  }, [idActual, version])

  async function ejecutar(ruta, cuerpo, mensajeOk) {
    setOcupado(true)
    setAviso(null)
    try {
      const respuesta = await pedir(`/api/conversaciones/${idActual}/${ruta}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: cuerpo ? JSON.stringify(cuerpo) : undefined,
      }).then(leer)
      setDetalle(respuesta)
      setAviso({ tipo: 'ok', texto: mensajeOk })
      setVersion((v) => v + 1)
      return true
    } catch (e) {
      setAviso({ tipo: 'error', texto: e.message })
      return false
    } finally {
      setOcupado(false)
    }
  }

  async function responder(e) {
    e.preventDefault()
    const enviado = await ejecutar('responder', { texto }, 'Mensaje enviado al cliente.')
    if (enviado) setTexto('')
  }

  const d = detalle && detalle.id === idActual ? detalle : null
  // Las joyas de la ficha que todavía no tienen orden (las demás ya se pidieron).
  const sinOrden = d ? d.intereses.filter((i) => !i.orden) : []
  const totalMensajes = d ? d.historial.length : 0

  // Los mensajes nuevos quedan a la vista sin que el asesor tenga que desplazarse.
  useEffect(() => {
    if (caja.current) caja.current.scrollTop = caja.current.scrollHeight
  }, [idActual, totalMensajes])

  const escaladas = lista.filter((c) => c.estado === 'escalada').length

  return (
    <section className="conversaciones" aria-label="Conversaciones">
      <h2 className="cola-titulo">
        Bandeja <span>({lista.length})</span>
        {escaladas > 0 && <span className="insignia estado-escalada">{escaladas} esperan asesor</span>}
        <button type="button" onClick={() => setVersion((v) => v + 1)}>
          Actualizar
        </button>
      </h2>
      {error && <p className="estado error">{error}</p>}
      {lista.length === 0 && !error && (
        <p className="estado">
          Todavía no hay conversaciones. Escribe al número de WhatsApp o usa el chat del catálogo.
        </p>
      )}

      {lista.length > 0 && (
        <div className="conv-rejilla">
          <ul className="conv-lista">
            {lista.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className={`conv-item ${c.id === idActual ? 'elegida' : ''} ${c.estado}`}
                  onClick={() => {
                    setElegida(c.id)
                    setAviso(null)
                  }}
                >
                  <span className="conv-fila">
                    <strong>{c.cliente}</strong>
                    <span className="conv-hora">{hora(c.actualizado_en)}</span>
                  </span>
                  <span className="conv-fila">
                    <Estado valor={c.estado} />
                    <span className="conv-canal">{c.canal}</span>
                  </span>
                  <span className="conv-vista">
                    {c.ultimo_autor ? `${AUTOR[c.ultimo_autor]}: ` : ''}
                    {c.ultimo_mensaje ?? 'Sin mensajes'}
                  </span>
                </button>
              </li>
            ))}
          </ul>

          <article className="conv-detalle">
            {!d && <p className="estado">Cargando conversación…</p>}
            {d && (
              <>
                <header className="conv-cabecera">
                  <div>
                    <h3>{d.cliente}</h3>
                    <p className="nota">
                      Conversación #{d.id} · {d.canal} · {d.total_mensajes} mensajes
                      {d.ordenes_activas > 0 && ` · ${d.ordenes_activas} orden(es) activa(s)`}
                    </p>
                  </div>
                  <Estado valor={d.estado} />
                </header>

                {d.motivo_escalamiento && (
                  <p className="conv-motivo">Motivo de la derivación: {d.motivo_escalamiento}</p>
                )}

                <section className="ficha" aria-label="Ficha de contexto">
                  <div className="ficha-cabecera">
                    <h4>Ficha de contexto</h4>
                    {sinOrden.length > 1 && (
                      <button
                        type="button"
                        className="boton primario"
                        onClick={() =>
                          onCrearOrden({
                            clienteId: String(d.orden_sugerida.cliente_id),
                            descripciones: sinOrden.map((i) => i.descripcion_de_orden),
                            intereses: sinOrden.map((i) => i.numero),
                          })
                        }
                      >
                        Crear un pedido con las {sinOrden.length} joyas
                        {sinOrden.length < d.intereses.length ? ' sin orden' : ''}
                      </button>
                    )}
                  </div>
                  <Datos items={d.datos_del_cliente} />
                  {d.intereses.length === 0 && (
                    <p className="nota">El agente todavía no anotó ninguna joya.</p>
                  )}
                  {d.intereses.map((i) => (
                    <div key={i.numero} className={`interes ${i.activo ? 'activo' : ''}`}>
                      <p className="interes-titulo">
                        <strong>
                          {d.intereses.length > 1 ? `${i.numero}. ` : ''}
                          {i.titulo}
                        </strong>
                        {i.activo && d.intereses.length > 1 && (
                          <span className="insignia estado-activa">De esta se está hablando</span>
                        )}
                        {i.orden ? (
                          <span className="insignia recibida">
                            Orden {i.orden} · {NOMBRE_ETAPA[i.etapa_de_la_orden] ?? i.etapa_de_la_orden}
                          </span>
                        ) : (
                          <button
                            type="button"
                            onClick={() =>
                              onCrearOrden({
                                clienteId: String(d.orden_sugerida.cliente_id),
                                descripciones: [i.descripcion_de_orden],
                                intereses: [i.numero],
                              })
                            }
                          >
                            Crear orden de esta joya
                          </button>
                        )}
                      </p>
                      <Datos items={i.datos} />
                    </div>
                  ))}
                </section>

                <div className="conv-mensajes" ref={caja}>
                  {d.historial.map((m) => (
                    <p key={m.id} className={`burbuja ${m.autor}`} title={hora(m.creado_en)}>
                      <small className="burbuja-autor">
                        {AUTOR[m.autor]}
                        {m.origen && ORIGEN[m.origen] ? ` · ${ORIGEN[m.origen]}` : ''}
                        {m.usuario ? ` · ${m.usuario}` : ''}
                      </small>
                      {m.contenido}
                    </p>
                  ))}
                </div>

                {d.estado !== 'cerrada' && (
                  <form className="conv-responder" onSubmit={responder}>
                    <textarea
                      rows={2}
                      value={texto}
                      maxLength={1000}
                      onChange={(e) => setTexto(e.target.value)}
                      placeholder="Escribe al cliente por su mismo canal…"
                    />
                    <button type="submit" className="boton primario" disabled={ocupado || !texto.trim()}>
                      Enviar al cliente
                    </button>
                  </form>
                )}

                {aviso && <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`}>{aviso.texto}</p>}

                <div className="conv-acciones">
                  {d.intereses.length === 0 && (
                    <button
                      type="button"
                      className="boton"
                      onClick={() =>
                        onCrearOrden({
                          clienteId: String(d.orden_sugerida.cliente_id),
                          descripciones: [d.orden_sugerida.descripcion],
                        })
                      }
                    >
                      Crear orden para este cliente
                    </button>
                  )}
                  {d.estado === 'escalada' && (
                    <button
                      type="button"
                      className="boton"
                      disabled={ocupado}
                      onClick={() => ejecutar('reactivar', null, 'El agente volvió a atender esta conversación.')}
                    >
                      Reactivar agente
                    </button>
                  )}
                  {d.estado !== 'cerrada' && (
                    <button
                      type="button"
                      className="boton"
                      disabled={ocupado}
                      onClick={() => ejecutar('cerrar', null, 'Conversación cerrada.')}
                    >
                      Cerrar conversación
                    </button>
                  )}
                </div>
              </>
            )}
          </article>
        </div>
      )}
    </section>
  )
}
