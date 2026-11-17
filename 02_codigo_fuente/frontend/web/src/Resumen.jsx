import { useCallback, useEffect, useState } from 'react'
import { leer } from './util.js'

const PERIODOS = [
  { dias: 7, texto: '7 días' },
  { dias: 30, texto: '30 días' },
  { dias: 90, texto: '90 días' },
]
const NOMBRE_ETAPA = {
  en_cola: 'En cola',
  en_produccion: 'En producción',
  terminada: 'Terminada',
  entregada: 'Entregada',
}
const NOMBRE_MENSAJE = { cliente: 'Clientes', agente: 'Agente', asesor: 'Asesor', sistema: 'Avisos del sistema' }

function Dato({ titulo, valor, nota }) {
  return (
    <div className="dato">
      <span className="dato-titulo">{titulo}</span>
      <strong className="dato-valor">{valor}</strong>
      {nota && <small>{nota}</small>}
    </div>
  )
}

function Barras({ filas, clase = '' }) {
  const maximo = Math.max(1, ...filas.map((f) => f.valor))
  return (
    <ul className="barras">
      {filas.map((f) => (
        <li key={f.nombre}>
          <span className="barra-nombre">{f.nombre}</span>
          <span className="barra-pista">
            <span className={`barra-relleno ${clase}`} style={{ width: `${(f.valor * 100) / maximo}%` }} />
          </span>
          <span className="barra-valor">{f.valor}</span>
        </li>
      ))}
    </ul>
  )
}

const diaCorto = (iso) => {
  const [, mes, dia] = iso.split('-')
  return `${dia}/${mes}`
}

// Indicadores del negocio: lo que atiende el agente, lo que escala a una persona y la producción.
export default function Resumen() {
  const [dias, setDias] = useState(30)
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState(null)

  const cargar = useCallback(() => {
    fetch(`/api/metricas?dias=${dias}`)
      .then(leer)
      .then((d) => {
        setDatos(d)
        setError(null)
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
  return (
    <section aria-label="Resumen del negocio">
      <h2 className="cola-titulo">
        Resumen
        <span className="periodos" role="group" aria-label="Periodo">
          {PERIODOS.map((p) => (
            <button
              key={p.dias}
              type="button"
              className={dias === p.dias ? 'activa' : ''}
              onClick={() => setDias(p.dias)}
            >
              {p.texto}
            </button>
          ))}
        </span>
        <button type="button" onClick={cargar}>
          Actualizar
        </button>
      </h2>
      {error && <p className="estado error">{error}</p>}

      <div className="datos">
        <Dato titulo="Conversaciones" valor={datos.conversaciones} nota={`últimos ${datos.dias} días`} />
        <Dato
          titulo="Resueltas por el agente"
          valor={tasa === null ? '—' : `${tasa}%`}
          nota={`${datos.resueltas_por_agente} sin intervención de una persona`}
        />
        <Dato titulo="Escaladas a un asesor" valor={datos.escaladas} nota={`${datos.por_estado.escalada} esperan ahora`} />
        <Dato
          titulo="Órdenes"
          valor={datos.ordenes_total}
          nota={`${datos.ordenes_con_acuse_pendiente} con acuse pendiente`}
        />
        <Dato
          titulo="Tiempo medio de entrega"
          valor={datos.horas_promedio_entrega === null ? '—' : `${datos.horas_promedio_entrega} h`}
          nota="desde que se crea la orden"
        />
        <Dato titulo="Clientes" valor={datos.clientes} />
      </div>

      <div className="paneles">
        <article className="panel-tarjeta">
          <h3>Conversaciones por día</h3>
          <Barras
            filas={datos.conversaciones_por_dia.map((d) => ({ nombre: diaCorto(d.dia), valor: d.conversaciones }))}
          />
        </article>
        <article className="panel-tarjeta">
          <h3>Órdenes por etapa</h3>
          <Barras
            clase="produccion"
            filas={datos.ordenes_por_etapa.map((e) => ({ nombre: NOMBRE_ETAPA[e.etapa], valor: e.ordenes }))}
          />
        </article>
        <article className="panel-tarjeta">
          <h3>Mensajes por autor</h3>
          <Barras
            clase="mensajes"
            filas={Object.entries(NOMBRE_MENSAJE).map(([clave, nombre]) => ({
              nombre,
              valor: datos.mensajes[clave] ?? 0,
            }))}
          />
        </article>
      </div>
    </section>
  )
}
