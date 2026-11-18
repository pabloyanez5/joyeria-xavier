import { useEffect, useRef, useState } from 'react'
import Icono from './Icono.jsx'
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
const NOMBRE_CANAL = { whatsapp: 'WhatsApp', messenger: 'Messenger', instagram: 'Instagram' }
const FILTROS = [
  { id: 'todas', titulo: 'Todas', estado: null },
  { id: 'escalada', titulo: 'Esperan asesor', estado: 'escalada' },
  { id: 'activa', titulo: 'Con el agente', estado: 'activa' },
  { id: 'cerrada', titulo: 'Cerradas', estado: 'cerrada' },
]
const formatoHoraCorta = new Intl.DateTimeFormat('es-EC', { timeStyle: 'short' })
const formatoDia = new Intl.DateTimeFormat('es-EC', { day: '2-digit', month: '2-digit' })
// Hora si fue hoy; si no, el día.
function horaCorta(valor) {
  if (!valor) return ''
  const momento = new Date(valor)
  const hoy = new Date().toDateString() === momento.toDateString()
  return hoy ? formatoHoraCorta.format(momento) : formatoDia.format(momento)
}
const NOMBRE_ETAPA = {
  por_verificar: 'Por verificar',
  en_cola: 'En cola',
  en_produccion: 'En producción',
  terminada: 'Terminada',
  entregada: 'Entregada',
  cancelada: 'Cancelada',
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
  const [filtro, setFiltro] = useState(null) // null = todas
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

  const cuenta = (estado) => lista.filter((c) => !estado || c.estado === estado).length
  const visibles = lista.filter((c) => !filtro || c.estado === filtro)

  function elegir(id) {
    setElegida(id)
    setAviso(null)
  }

  function crearOrden(intereses) {
    onCrearOrden({
      clienteId: String(d.orden_sugerida.cliente_id),
      descripciones: intereses ? intereses.map((i) => i.descripcion_de_orden) : [d.orden_sugerida.descripcion],
      ...(intereses ? { intereses: intereses.map((i) => i.numero) } : {}),
    })
  }

  if (error && lista.length === 0) return <p className="estado error">{error}</p>
  if (lista.length === 0) {
    return (
      <p className="estado">
        Todavía no hay conversaciones. Escribe al número de WhatsApp, a la página de Messenger o usa el
        chat del catálogo.
      </p>
    )
  }

  return (
    <div className="conv-rejilla">
      <aside className="conv-bandeja" aria-label="Bandeja de conversaciones">
        <div className="conv-bandeja-cabeza">
          <h2>
            Bandeja <span>({lista.length})</span>
          </h2>
          <button
            type="button"
            className="boton-icono"
            onClick={() => setVersion((v) => v + 1)}
            aria-label="Actualizar la bandeja"
            title="Actualizar"
          >
            <Icono nombre="actualizar" tamano={16} />
          </button>
        </div>
        <div className="conv-filtros" role="group" aria-label="Filtrar conversaciones">
          {FILTROS.map((f) => (
            <button key={f.id} type="button" aria-pressed={filtro === f.estado} onClick={() => setFiltro(f.estado)}>
              {f.titulo} · {cuenta(f.estado)}
            </button>
          ))}
        </div>
        {error && <p className="estado error">{error}</p>}
        <ul className="conv-lista">
          {visibles.length === 0 && <li className="nota">No hay conversaciones en este grupo.</li>}
          {visibles.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`conv-item ${c.estado}`}
                aria-current={c.id === idActual ? 'true' : undefined}
                onClick={() => elegir(c.id)}
              >
                <span className="avatar" aria-hidden="true">
                  {(c.cliente ?? '?').trim().charAt(0).toUpperCase()}
                </span>
                <span className="conv-item-texto">
                  <span className="conv-fila">
                    <strong>{c.cliente}</strong>
                    <span className="conv-hora">{horaCorta(c.actualizado_en)}</span>
                  </span>
                  <span className="conv-vista">
                    {c.ultimo_autor ? `${AUTOR[c.ultimo_autor]}: ` : ''}
                    {c.ultimo_mensaje ?? 'Sin mensajes'}
                  </span>
                  <span className="conv-fila">
                    <Estado valor={c.estado} />
                    <span className="conv-canal">{NOMBRE_CANAL[c.canal] ?? c.canal}</span>
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {!d && <p className="estado conv-cargando">Cargando conversación…</p>}
      {d && (
        <>
          <section className="conv-chat" aria-label={`Chat con ${d.cliente}`}>
            <header className="conv-cabecera">
              <div>
                <h2>{d.cliente}</h2>
                <p className="nota">
                  {NOMBRE_CANAL[d.canal] ?? d.canal} · conversación #{d.id} · {d.total_mensajes} mensajes
                </p>
              </div>
              <Estado valor={d.estado} />
              <div className="conv-cabecera-acciones">
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
                    Cerrar
                  </button>
                )}
              </div>
            </header>

            {d.motivo_escalamiento && (
              <p className="conv-motivo">Motivo de la derivación: {d.motivo_escalamiento}</p>
            )}

            <div className="conv-mensajes" ref={caja}>
              {d.historial.map((m) => (
                <div key={m.id} className={`conv-mensaje ${m.autor}`}>
                  <p className={`burbuja ${m.autor}`}>
                    <small className="burbuja-autor">
                      {AUTOR[m.autor]}
                      {m.origen && ORIGEN[m.origen] ? ` · ${ORIGEN[m.origen]}` : ''}
                      {m.usuario ? ` · ${m.usuario}` : ''}
                    </small>
                    {m.contenido}
                    <small className="burbuja-hora">{hora(m.creado_en)}</small>
                  </p>
                </div>
              ))}
            </div>

            {aviso && (
              <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`} role="status">
                {aviso.texto}
              </p>
            )}

            {d.estado !== 'cerrada' ? (
              <form className="conv-responder" onSubmit={responder}>
                <label className="solo-lectores" htmlFor="respuesta-asesor">
                  Mensaje al cliente
                </label>
                <textarea
                  id="respuesta-asesor"
                  rows={2}
                  value={texto}
                  maxLength={1000}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder={`Escribe a ${d.cliente} por ${NOMBRE_CANAL[d.canal] ?? 'su canal'}…`}
                />
                <button type="submit" className="boton primario" disabled={ocupado || !texto.trim()}>
                  Enviar
                </button>
              </form>
            ) : (
              <p className="nota conv-cerrada">
                Conversación cerrada. Si el cliente vuelve a escribir, se abre una nueva.
              </p>
            )}
          </section>

          <aside className="conv-ficha" aria-label="Ficha de contexto">
            <h3>Ficha de contexto</h3>
            <Datos items={d.datos_del_cliente} />
            {d.ordenes_activas > 0 && <p className="nota">{d.ordenes_activas} orden(es) activa(s)</p>}

            <h4>Joyas que le interesan</h4>
            {d.intereses.length === 0 && (
              <>
                <p className="nota">El agente todavía no anotó ninguna joya.</p>
                <button type="button" className="boton" onClick={() => crearOrden(null)}>
                  Crear orden para este cliente
                </button>
              </>
            )}
            {d.intereses.map((i) => (
              <div key={i.numero} className={`interes ${i.activo ? 'activo' : ''}`}>
                <p className="interes-titulo">
                  <strong>
                    {d.intereses.length > 1 ? `${i.numero} · ` : ''}
                    {i.titulo}
                  </strong>
                  {i.activo && d.intereses.length > 1 && <span className="etiqueta neutro">De esta se habla</span>}
                </p>
                <Datos items={i.datos} />
                {i.orden ? (
                  <span className="etiqueta aviso interes-orden">
                    Orden {i.orden} · {NOMBRE_ETAPA[i.etapa_de_la_orden] ?? i.etapa_de_la_orden}
                  </span>
                ) : (
                  <button type="button" className="interes-crear" onClick={() => crearOrden([i])}>
                    Crear orden de esta joya
                  </button>
                )}
              </div>
            ))}
            {sinOrden.length > 1 && (
              <button type="button" className="boton primario" onClick={() => crearOrden(sinOrden)}>
                Crear un pedido con las {sinOrden.length} joyas
                {sinOrden.length < d.intereses.length ? ' sin orden' : ''}
              </button>
            )}
          </aside>
        </>
      )}
    </div>
  )
}
