import { useCallback, useEffect, useState } from 'react'
import Icono from './Icono.jsx'
import { pedir } from './sesion.js'
import { leer } from './util.js'

const PERIODOS = [
  { dias: 7, texto: '7 días' },
  { dias: 30, texto: '30 días' },
  { dias: 90, texto: '90 días' },
]
// Cada etapa con su color del tema (los mismos del tablero).
const ETAPAS = [
  { etapa: 'por_verificar', nombre: 'Por verificar' },
  { etapa: 'en_cola', nombre: 'En cola' },
  { etapa: 'en_produccion', nombre: 'En producción' },
  { etapa: 'terminada', nombre: 'Terminada' },
  { etapa: 'entregada', nombre: 'Entregada' },
  { etapa: 'cancelada', nombre: 'Cancelada' },
]
const AUTORES = [
  { clave: 'cliente', nombre: 'Clientes' },
  { clave: 'agente', nombre: 'Agente' },
  { clave: 'asesor', nombre: 'Asesor' },
  { clave: 'sistema', nombre: 'Avisos del sistema' },
]

const numero = new Intl.NumberFormat('es-EC', { maximumFractionDigits: 1 })
const horaCorta = new Intl.DateTimeFormat('es-EC', { timeStyle: 'short' })
const DIA_SEMANA = new Intl.DateTimeFormat('es-EC', { weekday: 'short' })

// 30 h se lee mejor en horas; 130 h, en días.
function duracion(horas) {
  if (horas === null || horas === undefined) return '—'
  return horas < 48 ? `${numero.format(horas)} h` : `${numero.format(horas / 24)} días`
}

function diaDe(iso) {
  const [anio, mes, dia] = iso.split('-').map(Number)
  const fecha = new Date(anio, mes - 1, dia)
  return { semana: DIA_SEMANA.format(fecha).replace('.', ''), fecha: `${String(dia).padStart(2, '0')}/${String(mes).padStart(2, '0')}` }
}

function Indicador({ titulo, valor, nota, destacado, ancho, children }) {
  return (
    <div className={`indicador ${destacado ? 'destacado' : ''} ${ancho ? 'ancho' : ''}`}>
      <span className="indicador-titulo">{titulo}</span>
      <strong className="indicador-valor">{valor}</strong>
      {children}
      {nota && <small>{nota}</small>}
    </div>
  )
}

// Conversaciones de los últimos 7 días, en columnas.
function Columnas({ dias }) {
  const maximo = Math.max(1, ...dias.map((d) => d.conversaciones))
  return (
    <ol className="columnas" aria-label="Conversaciones por día">
      {dias.map((d) => {
        const { semana, fecha } = diaDe(d.dia)
        return (
          <li key={d.dia} aria-label={`${fecha}: ${d.conversaciones} conversaciones`}>
            <span className="columna-valor">{d.conversaciones}</span>
            <span className="columna-pista" aria-hidden="true">
              <span className="columna-relleno" style={{ height: `${(d.conversaciones * 100) / maximo}%` }} />
            </span>
            <span className="columna-dia" aria-hidden="true">
              {semana}
              <small>{fecha}</small>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function Barras({ filas }) {
  const maximo = Math.max(1, ...filas.map((f) => f.valor))
  return (
    <ul className="barras">
      {filas.map((f) => (
        <li key={f.nombre}>
          <span className="barra-nombre">
            <span className={`punto ${f.clase}`} aria-hidden="true" />
            {f.nombre}
          </span>
          <span className="barra-pista" aria-hidden="true">
            <span className={`barra-relleno ${f.clase}`} style={{ width: `${(f.valor * 100) / maximo}%` }} />
          </span>
          <span className="barra-valor">{f.valor}</span>
        </li>
      ))}
    </ul>
  )
}

// Quién escribe los mensajes: una sola barra repartida y su leyenda.
function Reparto({ mensajes }) {
  const total = AUTORES.reduce((suma, a) => suma + (mensajes[a.clave] ?? 0), 0)
  return (
    <div className="reparto">
      <div className="reparto-barra" aria-hidden="true">
        {AUTORES.map((a) =>
          mensajes[a.clave] ? (
            <span key={a.clave} className={`autor-${a.clave}`} style={{ flexGrow: mensajes[a.clave] }} />
          ) : null,
        )}
      </div>
      <ul className="reparto-leyenda">
        {AUTORES.map((a) => (
          <li key={a.clave}>
            <span className={`punto autor-${a.clave}`} aria-hidden="true" />
            {a.nombre}
            <strong>{mensajes[a.clave] ?? 0}</strong>
            <small>{total ? `${numero.format(((mensajes[a.clave] ?? 0) * 100) / total)} %` : '—'}</small>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Indicadores del negocio (RF-06, JOY-92): lo que atiende el agente, lo que escala a una
// persona y la producción. Los valores vienen de /metricas sin cambiar sus cálculos.
export default function Resumen() {
  const [dias, setDias] = useState(30)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState(null)
  const [cargadoEn, setCargadoEn] = useState(null)

  const cargar = useCallback(() => {
    pedir(`/api/metricas?dias=${dias}`)
      .then(leer)
      .then((d) => {
        setDatos(d)
        setError(null)
        setCargadoEn(new Date())
      })
      .catch((e) => setError(e.message))
  }, [dias])

  useEffect(() => {
    cargar()
    const reloj = setInterval(cargar, 15000)
    return () => clearInterval(reloj)
  }, [cargar])

  if (!datos) return <p className={`estado ${error ? 'error' : ''}`}>{error ?? 'Cargando indicadores…'}</p>

  const tasa = datos.tasa_resolucion_agente
  const esperan = datos.por_estado.escalada ?? 0
  // JOY-94: qué parte de las respuestas libres salió de la IA (el resto, del motor de reglas).
  const origen = datos.respuestas_por_origen ?? {}
  const conIa = datos.respuestas_con_ia
  const intentos = datos.intentos_bloqueados ?? {}
  const bloqueados = Object.values(intentos).reduce((suma, n) => suma + n, 0)
  const activas = datos.ordenes_por_etapa
    .filter((e) => !['entregada', 'cancelada'].includes(e.etapa))
    .reduce((suma, e) => suma + e.ordenes, 0)

  return (
    <section className="resumen" aria-label="Indicadores del negocio">
      <div className="resumen-barra">
        <div className="selector-vista" role="group" aria-label="Periodo">
          {PERIODOS.map((p) => (
            <button key={p.dias} type="button" aria-pressed={dias === p.dias} onClick={() => setDias(p.dias)}>
              {p.texto}
            </button>
          ))}
        </div>
        {cargadoEn && <small className="nota">Actualizado a las {horaCorta.format(cargadoEn)}</small>}
        <button type="button" className="boton-icono" onClick={cargar} aria-label="Actualizar los indicadores">
          <Icono nombre="actualizar" tamano={16} />
        </button>
      </div>
      {error && <p className="estado error">{error}</p>}

      <div className="indicadores">
        <Indicador titulo="Conversaciones" valor={datos.conversaciones} nota={`Últimos ${datos.dias} días`} />
        <Indicador
          titulo="Resueltas por el agente"
          valor={tasa === null ? '—' : `${numero.format(tasa)} %`}
          nota={`${datos.resueltas_por_agente} sin intervención de una persona`}
        >
          {tasa !== null && (
            <span className="medidor" aria-hidden="true">
              <span style={{ width: `${tasa}%` }} />
            </span>
          )}
        </Indicador>
        <Indicador
          titulo="Escaladas a un asesor"
          valor={datos.escaladas}
          nota={esperan === 0 ? 'Ninguna espera ahora' : `${esperan} ${esperan === 1 ? 'espera' : 'esperan'} respuesta ahora`}
          destacado={esperan > 0}
        />
        <Indicador
          titulo="Órdenes activas"
          valor={activas}
          nota={`${datos.ordenes_total} en total · ${datos.ordenes_con_acuse_pendiente} con acuse pendiente`}
        />
        <Indicador
          titulo="Tiempo medio de entrega"
          valor={duracion(datos.horas_promedio_entrega)}
          nota="Desde que se crea la orden hasta que se entrega"
        />
        <Indicador
          titulo="Respuestas con IA"
          valor={conIa === null || conIa === undefined ? '—' : `${numero.format(conIa)} %`}
          nota={`${origen.modelo ?? 0} del modelo · ${origen.respaldo ?? 0} del respaldo · ${origen.reglas ?? 0} con reglas (sin IA)`}
          destacado={conIa !== null && conIa !== undefined && conIa < 90}
        >
          {conIa !== null && conIa !== undefined && (
            <span className="medidor" aria-hidden="true">
              <span style={{ width: `${conIa}%` }} />
            </span>
          )}
        </Indicador>
        <Indicador titulo="Clientes" valor={datos.clientes} nota="Registrados por todos los canales" />
        <Indicador
          titulo="Intentos bloqueados"
          valor={bloqueados}
          ancho
          nota={
            bloqueados === 0
              ? 'La seguridad del agente no bloqueó nada en el periodo'
              : `${intentos.instrucciones ?? 0} por manipular al agente · ${intentos.limite_de_mensajes ?? 0} por exceso de mensajes · ${intentos.respuesta_corregida ?? 0} respuestas corregidas`
          }
        />
      </div>

      <div className="graficos">
        <article className="grafico">
          <h3>Conversaciones por día</h3>
          <p className="nota">Últimos 7 días</p>
          <Columnas dias={datos.conversaciones_por_dia} />
        </article>
        <article className="grafico">
          <h3>Órdenes por etapa</h3>
          <p className="nota">Todas las órdenes registradas</p>
          <Barras
            filas={ETAPAS.map(({ etapa, nombre }) => ({
              nombre,
              clase: etapa,
              valor: datos.ordenes_por_etapa.find((e) => e.etapa === etapa)?.ordenes ?? 0,
            }))}
          />
        </article>
        <article className="grafico">
          <h3>Quién escribe</h3>
          <p className="nota">Mensajes de las conversaciones del periodo</p>
          <Reparto mensajes={datos.mensajes} />
        </article>
      </div>
    </section>
  )
}
