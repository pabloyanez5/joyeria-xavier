import { useCallback, useEffect, useState } from 'react'
import GestionOrden from './GestionOrden.jsx'
import Icono from './Icono.jsx'
import PanelLateral from './PanelLateral.jsx'
import { pedir } from './sesion.js'
import { hora, leer } from './util.js'

const COLUMNAS = [
  { etapa: 'por_verificar', titulo: 'Por verificar' },
  { etapa: 'en_cola', titulo: 'En cola' },
  { etapa: 'en_produccion', titulo: 'En producción' },
  { etapa: 'terminada', titulo: 'Terminada' },
  { etapa: 'entregada', titulo: 'Entregada', cerrada: true },
  // Las canceladas no son una etapa del proceso: su columna aparece solo si hay alguna (JOY-23).
  { etapa: 'cancelada', titulo: 'Cancelada', soloSiHay: true, cerrada: true },
]
const PROCESO = COLUMNAS.filter((c) => !c.soloSiHay).map((c) => c.etapa)
const NOMBRE = Object.fromEntries(COLUMNAS.map((c) => [c.etapa, c.titulo]))
const nombreEtapa = (etapa) => NOMBRE[etapa] ?? etapa
// Cómo se lee en el historial lo que no es un avance normal.
const TITULO_CAMBIO = {
  modificacion: () => 'Datos modificados',
  retroceso: (p) => `Devuelta a ${nombreEtapa(p.etapa).toLowerCase()}`,
  cancelacion: () => 'Cancelada',
}
// Lo entregado o cancelado hace más de esto no se muestra en el tablero (sí en los filtros).
const DIAS_CERRADAS = 30

const formatoDolar = new Intl.NumberFormat('es-EC', { style: 'currency', currency: 'USD' })
const dinero = (valor) => formatoDolar.format(Number(valor))
// Las fechas llegan como AAAA-MM-DD; se muestran como DD/MM/AAAA sin pasar por zonas horarias.
const fecha = (iso) => (iso ? iso.split('-').reverse().join('/') : '—')
const fechaCorta = (iso) => (iso ? iso.split('-').reverse().slice(0, 2).join('/') : '—')
const diaIso = (ms) => new Date(ms).toLocaleDateString('en-CA') // AAAA-MM-DD en hora local

const FILTROS_VACIOS = { q: '', etapa: '', desde: '', hasta: '' }
const NOMBRE_CANAL = { whatsapp: 'WhatsApp', messenger: 'Messenger', instagram: 'Instagram' }
const canalDe = (orden) => NOMBRE_CANAL[orden.canal] ?? 'su canal'

// Vista de órdenes que eligió la persona (tablero o lista), recordada en este navegador.
const CLAVE_VISTA = 'joyeria.vista_ordenes'
function vistaGuardada() {
  try {
    return localStorage.getItem(CLAVE_VISTA) === 'lista' ? 'lista' : 'tablero'
  } catch {
    return 'tablero'
  }
}
function guardarVista(vista) {
  try {
    localStorage.setItem(CLAVE_VISTA, vista)
  } catch {
    // sin almacenamiento: la elección vale solo para esta visita
  }
}

const POR_PAGINA = [25, 50, 100]

function consultaDe(filtros) {
  const params = new URLSearchParams()
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor.trim()) params.set(clave, valor.trim())
  }
  const texto = params.toString()
  return texto ? `?${texto}` : ''
}

// Nombre corto de la joya para la tarjeta: el producto del catálogo o, si viene de la ficha
// ("Joya: Aretes; Modelo: …; Material: oro. Origen: …"), su modelo y material.
function tituloJoya(orden) {
  if (orden.producto) return orden.producto
  const texto = orden.descripcion.split('. Origen:')[0]
  const datos = Object.fromEntries(
    texto
      .split(';')
      .map((parte) => parte.split(':').map((s) => s.trim()))
      .filter((par) => par.length === 2 && par[1]),
  )
  const base = datos.Modelo ?? datos.Joya
  if (base) return datos.Material ? `${base} de ${datos.Material}` : base
  return texto
}

// Lo que pide atención en cada orden, en el orden en que importa.
function etiquetas(orden, esAsesor, hoy) {
  const lista = []
  const cerrada = orden.etapa_actual === 'entregada' || orden.etapa_actual === 'cancelada'
  if (!cerrada && orden.fecha_entrega_cliente && orden.fecha_entrega_cliente < hoy) {
    lista.push({ texto: 'Atrasada', tono: 'peligro' })
  }
  if (orden.etapa_actual === 'por_verificar') {
    lista.push({ texto: esAsesor ? 'Abono pendiente' : 'Esperando el abono', tono: esAsesor ? 'aviso' : 'neutro' })
  } else if (orden.acuse_pendiente && !cerrada) {
    const modificada = orden.ultimo_cambio?.startsWith('Modificada')
    lista.push({ texto: modificada ? 'Modificada · confirmar' : 'Acuse pendiente', tono: 'aviso' })
  }
  if (orden.etapa_actual === 'terminada') lista.push({ texto: 'Coordinar entrega', tono: 'info' })
  if (orden.etapa_actual === 'cancelada' && esAsesor && Number(orden.abono) > 0) {
    lista.push({ texto: `Devolver abono ${dinero(orden.abono)}`, tono: 'peligro' })
  }
  return lista
}

function Progreso({ etapa }) {
  const hecho = PROCESO.indexOf(etapa)
  return (
    <span className="progreso" aria-hidden="true">
      {PROCESO.map((e, n) => (
        <span key={e} className={n <= hecho ? `lleno ${e}` : ''} />
      ))}
    </span>
  )
}

function Etiqueta({ texto, tono }) {
  return <span className={`etiqueta ${tono}`}>{texto}</span>
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

// Todo lo de una orden, en el panel lateral: datos, acción principal, historial y más acciones.
function DetalleOrden({ orden, puedeAvanzar, puedeVerificar, avisar, ocupada, acciones }) {
  const [abono, setAbono] = useState('')
  const [retira, setRetira] = useState('')
  const enProceso = orden.etapa_actual !== 'por_verificar' && orden.etapa_actual !== 'cancelada'
  // JOY-18: en la cola, confirmar el recibo pasa la orden a producción.
  const recibirDeLaCola = orden.acuse_pendiente && orden.etapa_actual === 'en_cola'
  // JOY-19: la entrega física la registra el taller o el asesor, con quién retira.
  const toca = orden.siguiente_etapa
  const entregar = toca === 'entregada' && (puedeAvanzar || puedeVerificar)
  const avanzarEtapa = puedeAvanzar && toca && toca !== 'entregada' && !recibirDeLaCola

  return (
    <div className="detalle">
      <div className="detalle-encabezado">
        <span className={`etapa-chip ${orden.etapa_actual}`}>{nombreEtapa(orden.etapa_actual)}</span>
        <Progreso etapa={orden.etapa_actual} />
      </div>
      <div>
        <h3>{tituloJoya(orden)}</h3>
        <p className="detalle-cliente">{orden.cliente ?? 'Cliente'}</p>
      </div>
      <p className="detalle-descripcion">{orden.descripcion}</p>

      <dl className="detalle-datos">
        <div>
          <dt>Peso</dt>
          <dd>{orden.peso_gramos ? `${Number(orden.peso_gramos)} g` : '—'}</dd>
        </div>
        <div>
          <dt>Joya del catálogo</dt>
          <dd>{orden.producto ?? 'A medida'}</dd>
        </div>
        <div>
          <dt>Entrega al taller</dt>
          <dd>{fecha(orden.fecha_entrega_taller)}</dd>
        </div>
        <div>
          <dt>Entrega al cliente</dt>
          <dd>{fecha(orden.fecha_entrega_cliente)}</dd>
        </div>
        {puedeVerificar && orden.total !== null && (
          <>
            <div>
              <dt>Total</dt>
              <dd>{dinero(orden.total)}</dd>
            </div>
            <div>
              <dt>{orden.etapa_actual === 'cancelada' ? 'Abono recibido' : 'Abono · saldo'}</dt>
              <dd className={orden.etapa_actual === 'cancelada' && Number(orden.abono) > 0 ? 'texto-peligro' : ''}>
                {orden.etapa_actual === 'cancelada'
                  ? `${dinero(orden.abono ?? 0)}${Number(orden.abono) > 0 ? ' (revisar devolución)' : ''}`
                  : `${dinero(orden.abono ?? 0)} · ${dinero(orden.saldo ?? 0)}`}
              </dd>
            </div>
          </>
        )}
      </dl>

      {orden.foto_referencia_url && (
        <a href={orden.foto_referencia_url} target="_blank" rel="noopener noreferrer">
          Ver foto de referencia
        </a>
      )}

      <div className="detalle-registro">
        {orden.verificada_por && (
          <small>
            Abono verificado por {orden.verificada_por} · {hora(orden.verificada_en)}
          </small>
        )}
        {orden.acuse_por && (
          <small>
            Recibida por {orden.acuse_por} · {hora(orden.acuse_en)}
          </small>
        )}
        {orden.entregada_en && (
          <small>
            Entregada por {orden.entregada_por ?? '—'} · {hora(orden.entregada_en)}
          </small>
        )}
        {orden.ultimo_cambio && <small className="tarjeta-cambio">{orden.ultimo_cambio}</small>}
      </div>

      {orden.etapa_actual === 'por_verificar' && puedeVerificar && (
        <form
          className="detalle-accion"
          onSubmit={(e) => {
            e.preventDefault()
            acciones.verificar(orden, abono)
          }}
        >
          <label>
            Abono recibido (USD)
            <input
              type="number"
              min="0.01"
              step="0.01"
              max={orden.total ?? undefined}
              value={abono}
              onChange={(e) => setAbono(e.target.value)}
              required
            />
          </label>
          <button type="submit" className="boton primario" disabled={ocupada}>
            {ocupada ? 'Registrando…' : 'Registrar abono y pasar al taller'}
          </button>
          <small>{avisar ? `Se avisará al cliente por ${canalDe(orden)}.` : 'No se avisará al cliente.'}</small>
        </form>
      )}
      {orden.etapa_actual === 'por_verificar' && !puedeVerificar && (
        <p className="nota">Previsión: entra a la cola cuando el asesor registre el abono.</p>
      )}

      {puedeAvanzar && enProceso && (recibirDeLaCola || orden.acuse_pendiente || avanzarEtapa) && (
        <div className="detalle-accion">
          {recibirDeLaCola && (
            <button type="button" className="boton primario" disabled={ocupada} onClick={() => acciones.acuse(orden)}>
              {ocupada ? 'Confirmando…' : 'Confirmar recibo y pasar a producción'}
            </button>
          )}
          {orden.acuse_pendiente && !recibirDeLaCola && (
            <button type="button" disabled={ocupada} onClick={() => acciones.acuse(orden)}>
              Confirmar que vi el cambio
            </button>
          )}
          {avanzarEtapa && (
            <button type="button" className="boton primario" disabled={ocupada} onClick={() => acciones.avanzar(orden)}>
              {ocupada ? 'Avanzando…' : `Pasar a ${nombreEtapa(toca).toLowerCase()}`}
            </button>
          )}
          {(recibirDeLaCola || avanzarEtapa) && (
            <small>{avisar ? `Se avisará al cliente por ${canalDe(orden)}.` : 'No se avisará al cliente.'}</small>
          )}
        </div>
      )}

      {entregar && (
        <form
          className="detalle-accion"
          onSubmit={(e) => {
            e.preventDefault()
            acciones.entregar(orden, retira)
          }}
        >
          <label>
            ¿Quién retira la joya? <span className="nota">(opcional, si no es el titular)</span>
            <input
              type="text"
              maxLength={200}
              value={retira}
              onChange={(e) => setRetira(e.target.value)}
              placeholder="Ej.: Carlos Pérez (esposo)"
            />
          </label>
          <button type="submit" className="boton primario" disabled={ocupada}>
            {ocupada ? 'Registrando…' : 'Registrar entrega al cliente'}
          </button>
          <small>Queda registrado quién la entregó y cuándo.</small>
        </form>
      )}

      <section className="detalle-historial" aria-label="Historial">
        <h4>Historial</h4>
        <Historial orden={orden} />
      </section>

      {puedeVerificar && orden.etapa_actual !== 'cancelada' && orden.etapa_actual !== 'entregada' && (
        <details className="mas-acciones">
          <summary>Más acciones</summary>
          <GestionOrden orden={orden} avisar={avisar} nombreEtapa={nombreEtapa} onHecho={acciones.gestionada} />
        </details>
      )}
    </div>
  )
}

function Encabezado({ campo, titulo, orden, onOrdenar }) {
  const activo = orden.campo === campo
  const sentido = activo ? (orden.direccion === 'asc' ? 'ascending' : 'descending') : 'none'
  return (
    <th scope="col" aria-sort={sentido}>
      <button type="button" className={activo ? 'activo' : ''} onClick={() => onOrdenar(campo)}>
        {titulo}
        <span aria-hidden="true">{activo ? (orden.direccion === 'asc' ? ' ↑' : ' ↓') : ' ↕'}</span>
      </button>
    </th>
  )
}

// Lista paginada (JOY-90): para cuando hay muchas órdenes. Solo trae la página que se ve.
function ListaOrdenes({ datos, orden, onOrdenar, onPagina, onPorPagina, onAbrir, seleccion, puedeVerificar, hoy }) {
  if (!datos) return <p className="estado">Cargando órdenes…</p>
  const { total, pagina, paginas, por_pagina: porPagina, ordenes } = datos
  const desde = total === 0 ? 0 : (pagina - 1) * porPagina + 1
  const hasta = Math.min(total, pagina * porPagina)
  const col = (campo, titulo) => (
    <Encabezado campo={campo} titulo={titulo} orden={orden} onOrdenar={onOrdenar} />
  )
  return (
    <div className="lista-ordenes">
      <div className="lista-tabla">
        <table>
          <thead>
            <tr>
              {col('codigo', 'Orden')}
              <th scope="col">Joya</th>
              {col('cliente', 'Cliente')}
              {col('etapa', 'Etapa')}
              {col('entrega', 'Entrega')}
              {puedeVerificar && <th scope="col" className="numero">Saldo</th>}
              <th scope="col">Atención</th>
              <th scope="col">
                <span className="solo-lectores">Abrir</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {ordenes.length === 0 && (
              <tr>
                <td colSpan={8} className="lista-vacia">
                  Ninguna orden cumple los filtros.
                </td>
              </tr>
            )}
            {ordenes.map((o) => (
              <tr key={o.id} className={seleccion === o.id ? 'seleccionada' : ''}>
                <td>
                  <strong>{o.codigo}</strong>
                  {o.pedido && <small>{o.pedido}</small>}
                </td>
                <td className="lista-joya">{tituloJoya(o)}</td>
                <td>{o.cliente ?? 'Cliente'}</td>
                <td>
                  <span className="lista-etapa">
                    <span className={`punto ${o.etapa_actual}`} aria-hidden="true" />
                    {nombreEtapa(o.etapa_actual)}
                  </span>
                </td>
                <td>{fecha(o.fecha_entrega_cliente)}</td>
                {puedeVerificar && (
                  <td className="numero">
                    {o.etapa_actual === 'cancelada' || o.saldo === null ? '—' : dinero(o.saldo)}
                  </td>
                )}
                <td>
                  <span className="tarjeta-etiquetas">
                    {etiquetas(o, puedeVerificar, hoy).map((e) => (
                      <Etiqueta key={e.texto} {...e} />
                    ))}
                  </span>
                </td>
                <td className="numero">
                  <button type="button" onClick={() => onAbrir(o.id)} aria-label={`Abrir ${o.codigo}`}>
                    Abrir
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <nav className="paginacion" aria-label="Paginación">
        <span>
          Mostrando {desde}–{hasta} de {total} órdenes
        </span>
        <label>
          Por página
          <select value={porPagina} onChange={(e) => onPorPagina(Number(e.target.value))}>
            {POR_PAGINA.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="paginacion-botones">
          <button type="button" disabled={pagina <= 1} onClick={() => onPagina(pagina - 1)}>
            Anterior
          </button>
          <span aria-current="page">
            Página {pagina} de {paginas}
          </span>
          <button type="button" disabled={pagina >= paginas} onClick={() => onPagina(pagina + 1)}>
            Siguiente
          </button>
        </div>
      </nav>
    </div>
  )
}

// Tablero de producción (JOY-89): contador por etapa, tarjetas compactas y el detalle en un panel
// lateral. El asesor registra el abono; el taller confirma el recibo y avanza cada etapa.
export default function Tablero({
  version,
  onCambio,
  onNuevaOrden,
  puedeAvanzar = false,
  puedeVerificar = false,
}) {
  const [ordenes, setOrdenes] = useState([])
  const [error, setError] = useState(null)
  const [aviso, setAviso] = useState(null)
  const [avisar, setAvisar] = useState(true)
  const [ocupada, setOcupada] = useState(null)
  const [filtros, setFiltros] = useState(FILTROS_VACIOS)
  const [verFiltros, setVerFiltros] = useState(false)
  const [seleccion, setSeleccion] = useState(null)
  const [cargadoEn, setCargadoEn] = useState(0) // momento de la última carga: base de "hoy"
  const [vista, setVista] = useState(vistaGuardada)
  const [pagina, setPagina] = useState(1)
  const [porPagina, setPorPagina] = useState(25)
  const [orden, setOrden] = useState({ campo: 'creacion', direccion: 'desc' })
  const [datosLista, setDatosLista] = useState(null)
  const consulta = consultaDe(filtros)
  const filtrando = consulta !== ''
  const filtrosActivos = ['etapa', 'desde', 'hasta'].filter((c) => filtros[c]).length
  const hayCanceladas = ordenes.some((o) => o.etapa_actual === 'cancelada')
  const visibles = COLUMNAS.filter((c) => !c.soloSiHay || hayCanceladas)
  const fuente = vista === 'lista' ? (datosLista?.ordenes ?? []) : ordenes
  const elegida = fuente.find((o) => o.id === seleccion) ?? null
  const limite = cargadoEn - DIAS_CERRADAS * 24 * 3600 * 1000
  const hoy = cargadoEn ? diaIso(cargadoEn) : ''

  const cargar = useCallback(() => {
    // El tablero trae las órdenes vigentes; la lista solo la página que se está viendo.
    const paginaActual = new URLSearchParams(consulta)
    paginaActual.set('pagina', pagina)
    paginaActual.set('por_pagina', porPagina)
    paginaActual.set('orden', orden.campo)
    paginaActual.set('direccion', orden.direccion)
    const ruta = vista === 'lista' ? `/api/ordenes/pagina?${paginaActual}` : `/api/ordenes${consulta}`
    pedir(ruta)
      .then(leer)
      .then((respuesta) => {
        if (vista === 'lista') setDatosLista(respuesta)
        else setOrdenes(respuesta)
        setCargadoEn(Date.now())
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [consulta, vista, pagina, porPagina, orden])

  function filtrar(campo) {
    return (e) => {
      setFiltros((f) => ({ ...f, [campo]: e.target.value }))
      setPagina(1)
    }
  }

  function cambiarVista(nueva) {
    guardarVista(nueva)
    setVista(nueva)
    setPagina(1)
  }

  function ordenarPor(campo) {
    setOrden((o) =>
      o.campo === campo
        ? { campo, direccion: o.direccion === 'asc' ? 'desc' : 'asc' }
        : { campo, direccion: campo === 'creacion' ? 'desc' : 'asc' },
    )
    setPagina(1)
  }

  function verEnLaLista(etapa) {
    setFiltros((f) => ({ ...f, etapa }))
    cambiarVista('lista')
  }

  useEffect(() => {
    cargar()
    const reloj = setInterval(cargar, 10000)
    return () => clearInterval(reloj)
  }, [cargar, version])

  function avisoDe(r, base) {
    const texto = r.aviso_al_cliente === 'enviado' ? TEXTO_AVISO.enviado : (r.detalle_aviso ?? TEXTO_AVISO[r.aviso_al_cliente])
    setAviso({ tipo: r.aviso_al_cliente === 'no_enviado' ? 'error' : 'ok', texto: `${base} ${texto}` })
  }

  async function ejecutar(orden, trabajo) {
    setOcupada(orden.id)
    setAviso(null)
    try {
      await trabajo()
      cargar()
      onCambio?.()
    } catch (e) {
      setAviso({ tipo: 'error', texto: e.message })
    } finally {
      setOcupada(null)
    }
  }

  const acciones = {
    avanzar: (orden) =>
      ejecutar(orden, async () => {
        const r = await pedir(`/api/ordenes/${orden.id}/etapa`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ etapa: orden.siguiente_etapa, avisar_al_cliente: avisar }),
        }).then(leer)
        avisoDe(r, `${r.codigo} pasó a «${nombreEtapa(r.etapa_actual)}».`)
      }),
    verificar: (orden, abono) =>
      ejecutar(orden, async () => {
        const r = await pedir(`/api/ordenes/${orden.id}/verificar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ abono, avisar_al_cliente: avisar }),
        }).then(leer)
        avisoDe(r, `Abono de ${dinero(r.abono)} registrado: ${r.codigo} entró a la cola del taller.`)
      }),
    acuse: (orden) =>
      ejecutar(orden, async () => {
        const r = await pedir(`/api/ordenes/${orden.id}/acuse`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ avisar_al_cliente: avisar }),
        }).then(leer)
        if (orden.etapa_actual === 'en_cola') {
          avisoDe(r, `${r.codigo}: recibo confirmado, pasó a «${nombreEtapa(r.etapa_actual)}».`)
        } else {
          setAviso({ tipo: 'ok', texto: `${r.codigo}: cambio confirmado.` })
        }
      }),
    entregar: (orden, retira) =>
      ejecutar(orden, async () => {
        const r = await pedir(`/api/ordenes/${orden.id}/etapa`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ etapa: 'entregada', avisar_al_cliente: avisar, nota: retira.trim() || null }),
        }).then(leer)
        avisoDe(r, `${r.codigo} entregada por ${r.entregada_por ?? 'ti'}.`)
      }),
    gestionada: (modo, r) => {
      if (modo === 'modificar') {
        const taller = r.acuse_pendiente && r.etapa_actual !== 'por_verificar'
        setAviso({
          tipo: 'ok',
          texto: `${r.codigo} modificada.` + (taller ? ' El taller debe confirmar que vio el cambio.' : ''),
        })
      } else if (modo === 'retroceder') {
        setAviso({ tipo: 'ok', texto: `${r.codigo} volvió a «${nombreEtapa(r.etapa_actual)}».` })
      } else {
        avisoDe(r, `${r.codigo} cancelada.`)
      }
      cargar()
      onCambio?.()
    },
  }

  return (
    <section className="tablero-seccion" aria-label="Órdenes">
      <div className="tablero-barra">
        <div className="selector-vista" role="group" aria-label="Vista">
          {['tablero', 'lista'].map((v) => (
            <button key={v} type="button" aria-pressed={vista === v} onClick={() => cambiarVista(v)}>
              {v === 'tablero' ? 'Tablero' : 'Lista'}
            </button>
          ))}
        </div>
        <label className="buscador">
          <Icono nombre="buscar" tamano={16} />
          <span className="solo-lectores">Buscar orden</span>
          <input
            type="search"
            value={filtros.q}
            onChange={filtrar('q')}
            maxLength={100}
            placeholder="OP-000012, PD-000003, cliente o detalle"
          />
        </label>
        <button type="button" aria-expanded={verFiltros} onClick={() => setVerFiltros((v) => !v)}>
          <Icono nombre="filtros" tamano={16} />
          Filtros{filtrosActivos > 0 ? ` · ${filtrosActivos}` : ''}
        </button>
        {(puedeAvanzar || puedeVerificar) && (
          <label className="tablero-avisar">
            <input type="checkbox" checked={avisar} onChange={(e) => setAvisar(e.target.checked)} />
            Avisar al cliente por su canal
          </label>
        )}
        <button type="button" onClick={cargar} aria-label="Actualizar el tablero" title="Actualizar">
          <Icono nombre="actualizar" tamano={16} />
        </button>
        {onNuevaOrden && (
          <button type="button" className="boton primario" onClick={onNuevaOrden}>
            <Icono nombre="mas" tamano={16} />
            Nueva orden
          </button>
        )}
      </div>

      {verFiltros && (
        <form className="tablero-filtros" role="search" onSubmit={(e) => e.preventDefault()}>
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
          <button
            type="button"
            disabled={!filtrando}
            onClick={() => {
              setFiltros(FILTROS_VACIOS)
              setPagina(1)
            }}
          >
            Limpiar filtros
          </button>
        </form>
      )}
      {filtrando && vista === 'tablero' && (
        <p className="nota">
          {ordenes.length === 0 ? 'Ninguna orden cumple los filtros.' : `${ordenes.length} orden(es) con estos filtros.`}
        </p>
      )}

      {error && <p className="estado error">{error}</p>}
      {aviso && (
        <p className={`estado ${aviso.tipo === 'error' ? 'error' : 'ok'}`} role="status">
          {aviso.texto}
        </p>
      )}

      {vista === 'lista' && (
        <ListaOrdenes
          datos={datosLista}
          orden={orden}
          onOrdenar={ordenarPor}
          onPagina={setPagina}
          onPorPagina={(n) => {
            setPorPagina(n)
            setPagina(1)
          }}
          onAbrir={setSeleccion}
          seleccion={seleccion}
          puedeVerificar={puedeVerificar}
          hoy={hoy}
        />
      )}

      {vista === 'tablero' && (
        <>
      <ul className="contadores" aria-label="Órdenes por etapa">
        {visibles.map(({ etapa, titulo }) => (
          <li key={etapa}>
            <span className={`punto ${etapa}`} aria-hidden="true" />
            {titulo}
            <strong>{ordenes.filter((o) => o.etapa_actual === etapa).length}</strong>
          </li>
        ))}
      </ul>

      <div className="tablero">
        {visibles.map(({ etapa, titulo, cerrada }) => {
          const todas = ordenes.filter((o) => o.etapa_actual === etapa)
          const ocultas = cerrada && !filtrando
            ? todas.filter((o) => o.actualizado_en && new Date(o.actualizado_en).getTime() < limite)
            : []
          const tarjetas = todas.filter((o) => !ocultas.includes(o))
          return (
            <section key={etapa} className={`tablero-col ${etapa}`} aria-label={titulo}>
              <h3>
                <span className={`punto ${etapa}`} aria-hidden="true" />
                {titulo} <span>{todas.length}</span>
              </h3>
              {tarjetas.length === 0 && <p className="tablero-vacio">Sin órdenes</p>}
              {tarjetas.map((o) => {
                const enProceso = o.etapa_actual !== 'por_verificar' && o.etapa_actual !== 'cancelada'
                return (
                  <article key={o.id} className={`tarjeta-orden ${seleccion === o.id ? 'seleccionada' : ''}`}>
                    <button type="button" className="tarjeta-abrir" onClick={() => setSeleccion(o.id)}>
                      <span className="tarjeta-cabeza">
                        <strong>{o.codigo}</strong>
                        {o.pedido && <span className="tarjeta-pedido">{o.pedido}</span>}
                      </span>
                      <span className="tarjeta-joya">{tituloJoya(o)}</span>
                      <span className="tarjeta-cliente">
                        {o.cliente ?? 'Cliente'}
                        {o.fecha_entrega_cliente && (
                          <>
                            {' · '}
                            <Icono nombre="calendario" tamano={13} /> {fechaCorta(o.fecha_entrega_cliente)}
                          </>
                        )}
                      </span>
                      <Progreso etapa={o.etapa_actual} />
                      <span className="tarjeta-etiquetas">
                        {etiquetas(o, puedeVerificar, hoy).map((e) => (
                          <Etiqueta key={e.texto} {...e} />
                        ))}
                      </span>
                    </button>
                    {puedeAvanzar && enProceso && o.acuse_pendiente && (
                      <button
                        type="button"
                        className={o.etapa_actual === 'en_cola' ? 'boton primario' : undefined}
                        disabled={ocupada === o.id}
                        onClick={() => acciones.acuse(o)}
                      >
                        {o.etapa_actual === 'en_cola' ? 'Recibir y pasar a producción' : 'Confirmar cambio'}
                      </button>
                    )}
                    {puedeAvanzar && enProceso && !o.acuse_pendiente && o.siguiente_etapa && (
                      <button
                        type="button"
                        className="boton primario"
                        disabled={ocupada === o.id}
                        onClick={() => acciones.avanzar(o)}
                      >
                        {ocupada === o.id ? 'Avanzando…' : `Pasar a ${nombreEtapa(o.siguiente_etapa).toLowerCase()}`}
                      </button>
                    )}
                  </article>
                )
              })}
              {ocultas.length > 0 && (
                <p className="tablero-vacio">
                  Últimos {DIAS_CERRADAS} días · {ocultas.length} más antigua(s).{' '}
                  <button type="button" className="enlace" onClick={() => verEnLaLista(etapa)}>
                    Ver todas en la lista
                  </button>
                </p>
              )}
            </section>
          )
        })}
      </div>
        </>
      )}

      {elegida && (
        <PanelLateral
          titulo={elegida.codigo}
          subtitulo={elegida.pedido ? `Pedido ${elegida.pedido}` : 'Orden de producción'}
          onCerrar={() => setSeleccion(null)}
        >
          <DetalleOrden
            key={elegida.id}
            orden={elegida}
            puedeAvanzar={puedeAvanzar}
            puedeVerificar={puedeVerificar}
            avisar={avisar}
            ocupada={ocupada === elegida.id}
            acciones={acciones}
          />
        </PanelLateral>
      )}
    </section>
  )
}
