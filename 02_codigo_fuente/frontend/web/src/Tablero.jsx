import { useCallback, useEffect, useState } from 'react'
import GestionOrden from './GestionOrden.jsx'
import { pedir } from './sesion.js'
import { hora, leer } from './util.js'

const COLUMNAS = [
  { etapa: 'por_verificar', titulo: 'Por verificar' },
  { etapa: 'en_cola', titulo: 'En cola' },
  { etapa: 'en_produccion', titulo: 'En producción' },
  { etapa: 'terminada', titulo: 'Terminada' },
  { etapa: 'entregada', titulo: 'Entregada' },
  // Las canceladas no son una etapa del proceso: su columna aparece solo si hay alguna (JOY-23).
  { etapa: 'cancelada', titulo: 'Cancelada', soloSiHay: true },
]
const NOMBRE = Object.fromEntries(COLUMNAS.map((c) => [c.etapa, c.titulo]))
const nombreEtapa = (etapa) => NOMBRE[etapa] ?? etapa
// Cómo se lee en el historial lo que no es un avance normal.
const TITULO_CAMBIO = {
  modificacion: () => 'Datos modificados',
  retroceso: (p) => `Devuelta a ${nombreEtapa(p.etapa).toLowerCase()}`,
  cancelacion: () => 'Cancelada',
}

const formatoDolar = new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' })
const dinero = (valor) => formatoDolar.format(Number(valor))
// Las fechas llegan como AAAA-MM-DD; se muestran como DD/MM/AAAA sin pasar por zonas horarias.
const fecha = (iso) => (iso ? iso.split('-').reverse().join('/') : '—')

const FILTROS_VACIOS = { q: '', etapa: '', desde: '', hasta: '' }

function consultaDe(filtros) {
  const params = new URLSearchParams()
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor.trim()) params.set(clave, valor.trim())
  }
  const texto = params.toString()
  return texto ? `?${texto}` : ''
}

// Historial cronológico de una orden: cada etapa, cuándo y quién la registró (JOY-83).
function Historial({ orden }) {
  const [pasos, setPasos] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    pedir(`/api/ordenes/${orden.id}/historial`)
      .then(leer)
      .then(setPasos)
      .catch((e) => setError(e.message))
  }, [orden.id, orden.etapa_actual, orden.ultimo_cambio])

  if (error) return <p className="estado error">{error}</p>
  if (!pasos) return <small>Cargando historial…</small>
  return (
    <ol className="historial">
      {pasos.map((p, n) => (
        <li key={n} className={p.tipo && p.tipo !== 'etapa' ? `cambio ${p.tipo}` : undefined}>
          <strong>{TITULO_CAMBIO[p.tipo]?.(p) ?? nombreEtapa(p.etapa)}</strong>
          <small>
            {hora(p.creado_en)}
            {p.usuario ? ` · ${p.usuario}` : ''}
          </small>
          {p.nota && <small className="historial-nota">{p.nota}</small>}
        </li>
      ))}
    </ol>
  )
}

const TEXTO_AVISO = {
  enviado: 'El cliente recibió el aviso por su canal.',
  no_enviado: 'La orden avanzó, pero el aviso no se pudo enviar',
  omitido: 'La orden avanzó sin avisar al cliente',
}

// Tablero de producción: una columna por etapa. El asesor registra el abono de las órdenes por
// verificar; desde ahí el taller avanza cada orden a la etapa siguiente.
export default function Tablero({ version, onCambio, puedeAvanzar = false, puedeVerificar = false }) {
  const [ordenes, setOrdenes] = useState([])
  const [error, setError] = useState(null)
  const [aviso, setAviso] = useState(null)
  const [avisar, setAvisar] = useState(true)
  const [ocupada, setOcupada] = useState(null)
  const [abonos, setAbonos] = useState({}) // lo que el asesor va escribiendo, por orden
  const [filtros, setFiltros] = useState(FILTROS_VACIOS)
  const [abiertas, setAbiertas] = useState({}) // órdenes con el historial desplegado
  const consulta = consultaDe(filtros)
  const filtrando = consulta !== ''
  const hayCanceladas = ordenes.some((o) => o.etapa_actual === 'cancelada')
  const visibles = COLUMNAS.filter((c) => !c.soloSiHay || hayCanceladas)

  const cargar = useCallback(() => {
    pedir(`/api/ordenes${consulta}`)
      .then(leer)
      .then((o) => {
        setOrdenes(o)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [consulta])

  function filtrar(campo) {
    return (e) => setFiltros((f) => ({ ...f, [campo]: e.target.value }))
  }

  useEffect(() => {
    cargar()
    const reloj = setInterval(cargar, 10000)
    return () => clearInterval(reloj)
  }, [cargar, version])

  async function avanzar(orden) {
    setOcupada(orden.id)
    setAviso(null)
    try {
      const r = await pedir(`/api/ordenes/${orden.id}/etapa`, {
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

  async function verificar(e, orden) {
    e.preventDefault()
    setOcupada(orden.id)
    setAviso(null)
    try {
      const r = await pedir(`/api/ordenes/${orden.id}/verificar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ abono: abonos[orden.id], avisar_al_cliente: avisar }),
      }).then(leer)
      const base = `Abono de ${dinero(r.abono)} registrado: ${r.codigo} entró a la cola del taller. `
      const texto = r.aviso_al_cliente === 'enviado' ? TEXTO_AVISO.enviado : (r.detalle_aviso ?? '')
      setAviso({ tipo: r.aviso_al_cliente === 'no_enviado' ? 'error' : 'ok', texto: base + texto })
      cargar()
      onCambio?.()
    } catch (fallo) {
      setAviso({ tipo: 'error', texto: fallo.message })
    } finally {
      setOcupada(null)
    }
  }

  function gestionada(modo, r) {
    if (modo === 'modificar') {
      const taller = r.acuse_pendiente && r.etapa_actual !== 'por_verificar'
      setAviso({
        tipo: 'ok',
        texto: `${r.codigo} modificada.` + (taller ? ' El taller debe confirmar que vio el cambio.' : ''),
      })
    } else if (modo === 'retroceder') {
      setAviso({ tipo: 'ok', texto: `${r.codigo} volvió a «${nombreEtapa(r.etapa_actual)}».` })
    } else {
      const texto = r.aviso_al_cliente === 'enviado' ? TEXTO_AVISO.enviado : (r.detalle_aviso ?? '')
      setAviso({
        tipo: r.aviso_al_cliente === 'no_enviado' ? 'error' : 'ok',
        texto: `${r.codigo} cancelada. ${texto}`,
      })
    }
    cargar()
    onCambio?.()
  }

  async function darAcuse(orden) {
    try {
      await pedir(`/api/ordenes/${orden.id}/acuse`, { method: 'POST' }).then(leer)
      cargar()
    } catch (e) {
      setAviso({ tipo: 'error', texto: e.message })
    }
  }

  return (
    <section aria-label="Tablero de producción">
      <h2 className="cola-titulo">
        Tablero del taller <span>({ordenes.length})</span>
        {(puedeAvanzar || puedeVerificar) && (
          <label className="tablero-avisar">
            <input type="checkbox" checked={avisar} onChange={(e) => setAvisar(e.target.checked)} />
            Avisar al cliente por WhatsApp
          </label>
        )}
        <button type="button" onClick={cargar}>
          Actualizar
        </button>
      </h2>

      <form className="tablero-filtros" role="search" onSubmit={(e) => e.preventDefault()}>
        <label>
          Buscar
          <input
            type="search"
            value={filtros.q}
            onChange={filtrar('q')}
            maxLength={100}
            placeholder="OP-000012, PD-000003, cliente o detalle"
          />
        </label>
        <label>
          Etapa
          <select value={filtros.etapa} onChange={filtrar('etapa')}>
            <option value="">Todas</option>
            {COLUMNAS.map((c) => (
              <option key={c.etapa} value={c.etapa}>
                {c.titulo}
              </option>
            ))}
          </select>
        </label>
        <label>
          Creadas desde
          <input type="date" value={filtros.desde} onChange={filtrar('desde')} />
        </label>
        <label>
          Hasta
          <input type="date" value={filtros.hasta} min={filtros.desde || undefined} onChange={filtrar('hasta')} />
        </label>
        <button type="button" disabled={!filtrando} onClick={() => setFiltros(FILTROS_VACIOS)}>
          Limpiar filtros
        </button>
      </form>
      {filtrando && (
        <p className="nota">
          {ordenes.length === 0 ? 'Ninguna orden cumple los filtros.' : `${ordenes.length} orden(es) con estos filtros.`}
        </p>
      )}

      {error && <p className="estado error">{error}</p>}
      {aviso && <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`}>{aviso.texto}</p>}

      <div className={`tablero ${hayCanceladas ? 'con-canceladas' : ''}`}>
        {visibles.map(({ etapa, titulo }) => {
          const tarjetas = ordenes.filter((o) => o.etapa_actual === etapa)
          return (
            <div key={etapa} className={`tablero-col ${etapa}`}>
              <h3>
                {titulo} <span>{tarjetas.length}</span>
              </h3>
              {tarjetas.length === 0 && <p className="tablero-vacio">Sin órdenes</p>}
              {tarjetas.map((o) => (
                <article key={o.id} className="tarjeta-orden">
                  <strong>
                    {o.codigo}
                    {o.pedido && <span className="tarjeta-pedido"> · pedido {o.pedido}</span>}
                  </strong>
                  <span className="tarjeta-cliente">{o.cliente ?? 'Cliente'}</span>
                  <p>{o.descripcion}</p>
                  <small>{o.producto ?? 'A medida'} · {hora(o.publicada_en ?? o.creado_en)}</small>
                  {o.total !== null && (
                    <small>
                      {Number(o.peso_gramos)} g · entrega al cliente {fecha(o.fecha_entrega_cliente)}
                    </small>
                  )}
                  {puedeVerificar && o.total !== null && etapa !== 'cancelada' && (
                    <small>
                      Total {dinero(o.total)} · abono {dinero(o.abono ?? 0)} · saldo {dinero(o.saldo ?? 0)}
                    </small>
                  )}
                  {puedeVerificar && o.total !== null && etapa === 'cancelada' && (
                    // Cancelada no cobra saldo. Si hubo abono, el sistema no lo devuelve: lo gestiona el asesor.
                    <small className={Number(o.abono) > 0 ? 'tarjeta-devolucion' : undefined}>
                      Total {dinero(o.total)} ·{' '}
                      {Number(o.abono) > 0
                        ? `abono recibido: ${dinero(o.abono)} (revisar devolución)`
                        : 'sin abono'}
                    </small>
                  )}
                  {etapa === 'por_verificar' && !puedeVerificar && (
                    <span className="insignia pendiente">Esperando el abono (previsión)</span>
                  )}
                  {etapa === 'por_verificar' && puedeVerificar && (
                    <form className="tarjeta-abono" onSubmit={(e) => verificar(e, o)}>
                      <label>
                        Abono recibido (USD)
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          max={o.total ?? undefined}
                          value={abonos[o.id] ?? ''}
                          onChange={(e) => setAbonos((a) => ({ ...a, [o.id]: e.target.value }))}
                          required
                        />
                      </label>
                      <button type="submit" className="boton primario" disabled={ocupada === o.id}>
                        {ocupada === o.id ? 'Registrando…' : 'Registrar abono y pasar al taller'}
                      </button>
                    </form>
                  )}
                  {o.verificada_por && etapa !== 'por_verificar' && (
                    <small>
                      Abono verificado por {o.verificada_por} · {hora(o.verificada_en)}
                    </small>
                  )}
                  {o.acuse_pendiente && etapa !== 'por_verificar' && (
                    <div>
                      <span className="insignia pendiente">Acuse pendiente</span>
                      {puedeAvanzar && (
                        <button type="button" onClick={() => darAcuse(o)}>
                          Confirmar recibo
                        </button>
                      )}
                    </div>
                  )}
                  <button
                    type="button"
                    className="tarjeta-historial"
                    aria-expanded={Boolean(abiertas[o.id])}
                    onClick={() => setAbiertas((a) => ({ ...a, [o.id]: !a[o.id] }))}
                  >
                    {abiertas[o.id] ? 'Ocultar historial' : 'Ver historial'}
                  </button>
                  {o.ultimo_cambio && <small className="tarjeta-cambio">{o.ultimo_cambio}</small>}
                  {abiertas[o.id] && <Historial orden={o} />}
                  {o.acuse_por && (
                    <small>
                      Recibida por {o.acuse_por} · {hora(o.acuse_en)}
                    </small>
                  )}
                  {puedeAvanzar && o.siguiente_etapa && (
                    <button
                      type="button"
                      className="boton primario"
                      disabled={ocupada === o.id}
                      onClick={() => avanzar(o)}
                    >
                      {ocupada === o.id ? 'Avanzando…' : `Pasar a ${NOMBRE[o.siguiente_etapa].toLowerCase()}`}
                    </button>
                  )}
                  {puedeVerificar && (
                    <GestionOrden orden={o} avisar={avisar} nombreEtapa={nombreEtapa} onHecho={gestionada} />
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
