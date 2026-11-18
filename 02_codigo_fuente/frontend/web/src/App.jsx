import { useEffect, useState } from 'react'
import './App.css'
import Chat from './Chat.jsx'

const MATERIALES = ['oro', 'plata']
const FILTROS_VACIOS = { categoria: '', material: '', q: '', precioMax: '' }
const PERSONALIZADO = '__personalizado__'
const MENSAJE_SIN_RESULTADOS =
  'Hola, no encontré en el catálogo la joya que busco. ¿Me pueden ayudar?'

const formatoDolar = new Intl.NumberFormat('es-EC', {
  style: 'currency',
  currency: 'USD',
})

function dinero(valor) {
  return formatoDolar.format(Number(valor))
}

function construirConsulta({ categoria, material, q, precioMax }) {
  const params = new URLSearchParams()
  if (categoria) params.set('categoria', categoria)
  if (material) params.set('material', material)
  if (q.trim()) params.set('q', q.trim())
  if (precioMax) params.set('precio_max', precioMax)
  const texto = params.toString()
  return texto ? `?${texto}` : ''
}

// Canales de contacto de la joyería (WhatsApp, Messenger, Instagram) con el mensaje ya escrito.
function useCanales(mensaje) {
  const [canales, setCanales] = useState([])
  useEffect(() => {
    const control = new AbortController()
    fetch(`/api/contacto?mensaje=${encodeURIComponent(mensaje)}`, {
      signal: control.signal,
    })
      .then((r) => (r.ok ? r.json() : []))
      .then(setCanales)
      .catch(() => {})
    return () => control.abort()
  }, [mensaje])
  return canales
}

const MENSAJE_GENERAL = 'Hola, quisiera más información sobre sus joyas.'

function ContactoAsesor({ titulo, mensaje }) {
  const canales = useCanales(mensaje)
  const [canal, setCanal] = useState('whatsapp')

  const elegido = canales.find((c) => c.canal === canal) ?? canales[0]

  return (
    <div className="contacto">
      <p>{titulo}</p>
      {elegido && (
        <>
          <label>
            Canal preferido
            <select
              value={elegido.canal}
              onChange={(e) => setCanal(e.target.value)}
            >
              {canales.map((c) => (
                <option key={c.canal} value={c.canal}>
                  {c.nombre}
                </option>
              ))}
            </select>
          </label>
          <a
            className="boton primario"
            href={elegido.enlace}
            target="_blank"
            rel="noreferrer"
          >
            Contactar a un asesor por {elegido.nombre}
          </a>
        </>
      )}
    </div>
  )
}

function Configurador({ productoId, onCerrar }) {
  const [detalle, setDetalle] = useState({ producto: null, error: null })
  const [seleccion, setSeleccion] = useState(null)
  const [cotizacion, setCotizacion] = useState({
    clave: null,
    datos: null,
    error: null,
    ms: null,
  })

  const combos = detalle.producto?.precios ?? []
  const materiales = [...new Set(combos.map((c) => c.material))]
  const todosQuilatajes = [
    ...new Set(combos.map((c) => c.quilataje).filter(Boolean)),
  ].sort()
  const quilatajesDe = (m) =>
    combos.filter((c) => c.material === m).map((c) => c.quilataje).filter(Boolean)

  const material = seleccion?.material ?? null
  const quilataje = seleccion?.quilataje ?? null
  const clave = `${material}|${quilataje ?? ''}`
  const noEstandar = material === PERSONALIZADO || quilataje === PERSONALIZADO

  useEffect(() => {
    fetch(`/api/productos/${productoId}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Error ${r.status} al cargar la joya`)
        return r.json()
      })
      .then((producto) => {
        setDetalle({ producto, error: null })
        const primero = producto.precios[0]
        if (primero) {
          setSeleccion({
            material: primero.material,
            quilataje: primero.quilataje,
          })
        }
      })
      .catch((e) => setDetalle({ producto: null, error: e.message }))
  }, [productoId])

  useEffect(() => {
    if (material === null || material === PERSONALIZADO) return undefined
    if (quilataje === PERSONALIZADO) return undefined
    const control = new AbortController()
    const inicio = performance.now()
    const params = new URLSearchParams({ material })
    if (quilataje) params.set('quilataje', quilataje)
    fetch(`/api/productos/${productoId}/cotizacion?${params}`, {
      signal: control.signal,
    })
      .then((r) => {
        if (!r.ok) throw new Error('Combinación no disponible')
        return r.json()
      })
      .then((datos) =>
        setCotizacion({
          clave,
          datos,
          error: null,
          ms: Math.round(performance.now() - inicio),
        }),
      )
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setCotizacion({ clave, datos: null, error: e.message, ms: null })
        }
      })
    return () => control.abort()
  }, [productoId, material, quilataje, clave])

  function cambiarMaterial(e) {
    const m = e.target.value
    setSeleccion({
      material: m,
      quilataje: m === PERSONALIZADO ? null : (quilatajesDe(m)[0] ?? null),
    })
  }

  function cambiarQuilataje(e) {
    setSeleccion((s) => ({ ...s, quilataje: e.target.value }))
  }

  const cotizando =
    material !== null && !noEstandar && cotizacion.clave !== clave
  const disponibles = material ? quilatajesDe(material) : []

  return (
    <div className="fondo-modal" onClick={onCerrar}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Configurar joya"
        onClick={(e) => e.stopPropagation()}
      >
        {detalle.error && <p className="estado error">{detalle.error}</p>}
        {!detalle.error && !detalle.producto && <p className="estado">Cargando…</p>}
        {detalle.producto && (
          <>
            {detalle.producto.imagen_url && (
              <img
                className="foto"
                src={detalle.producto.imagen_url}
                alt={detalle.producto.nombre}
              />
            )}
            <div className="modal-info">
            <span className="categoria">{detalle.producto.categoria}</span>
            <h2>{detalle.producto.nombre}</h2>
            <p className="descripcion">{detalle.producto.descripcion}</p>

            <div className="selectores">
              <label>
                Material
                <select value={material ?? ''} onChange={cambiarMaterial}>
                  {materiales.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                  <option value={PERSONALIZADO}>Otro (personalizado)</option>
                </select>
              </label>
              <label>
                Quilataje
                <select
                  value={quilataje ?? ''}
                  onChange={cambiarQuilataje}
                  disabled={disponibles.length === 0}
                >
                  {disponibles.length === 0 && <option value="">No aplica</option>}
                  {todosQuilatajes.map((q) => (
                    <option key={q} value={q} disabled={!disponibles.includes(q)}>
                      {q}
                      {disponibles.includes(q) ? '' : ' (no disponible)'}
                    </option>
                  ))}
                  {disponibles.length > 0 && (
                    <option value={PERSONALIZADO}>Otro (personalizado)</option>
                  )}
                </select>
              </label>
            </div>

            {noEstandar ? (
              <ContactoAsesor
                titulo="Esta combinación no se puede cotizar automáticamente. Un asesor te ayuda."
                mensaje={`Hola, quiero cotizar "${detalle.producto.nombre}" con un material o quilataje distinto a los del catálogo.`}
              />
            ) : (
              <div className="resultado" aria-live="polite">
                {cotizando && <span className="estado">Calculando…</span>}
                {!cotizando && cotizacion.error && (
                  <span className="estado error">{cotizacion.error}</span>
                )}
                {!cotizando && cotizacion.datos && (
                  <>
                    <span className="precio-grande">
                      {dinero(cotizacion.datos.precio)}
                    </span>
                    {cotizacion.datos.metodo === 'formula' && (
                      <ul className="desglose" aria-label="Cómo se calcula el precio">
                        <li>
                          Material: {Number(cotizacion.datos.peso_gramos)} g ×{' '}
                          {dinero(cotizacion.datos.precio_gramo)}/g ={' '}
                          {dinero(cotizacion.datos.costo_material)}
                        </li>
                        <li>Mano de obra: {dinero(cotizacion.datos.mano_obra)}</li>
                      </ul>
                    )}
                    <span className="nota">
                      Precio referencial · respondió en {cotizacion.ms} ms
                    </span>
                  </>
                )}
              </div>
            )}
            </div>
          </>
        )}
        <button type="button" className="boton-icono modal-cerrar" onClick={onCerrar} aria-label="Cerrar">
          ×
        </button>
      </div>
    </div>
  )
}

function Tarjeta({ producto, onConfigurar }) {
  return (
    <li className="tarjeta">
      <button type="button" className="tarjeta-foto" onClick={() => onConfigurar(producto.id)}>
        {producto.imagen_url ? (
          <img className="foto" src={producto.imagen_url} alt="" loading="lazy" />
        ) : (
          <span className="foto foto-vacia" aria-hidden="true" />
        )}
        <span className="solo-lectores">Ver {producto.nombre}</span>
      </button>
      <div className="tarjeta-cuerpo">
        <span className="categoria">{producto.categoria}</span>
        <h3>{producto.nombre}</h3>
        <p className="descripcion">{producto.descripcion}</p>
        <ul className="opciones" aria-label="Materiales disponibles">
          {producto.precios.map((p) => (
            <li key={`${p.material}-${p.quilataje}`}>
              {p.material} {p.quilataje ?? ''} · {dinero(p.precio)}
            </li>
          ))}
        </ul>
        <div className="tarjeta-pie">
          {producto.precio_desde && (
            <span className="desde">
              <small>Desde</small> {dinero(producto.precio_desde)}
            </span>
          )}
          <button type="button" className="boton primario" onClick={() => onConfigurar(producto.id)}>
            Cotizar
          </button>
        </div>
      </div>
    </li>
  )
}

// Los enlaces del asistente llevan filtros en la URL (?categoria=Anillos&material=oro).
function filtrosDesdeUrl() {
  const params = new URLSearchParams(window.location.search)
  const material = params.get('material') ?? ''
  return {
    ...FILTROS_VACIOS,
    categoria: params.get('categoria') ?? '',
    material: MATERIALES.includes(material) ? material : '',
  }
}

function App() {
  const [filtros, setFiltros] = useState(filtrosDesdeUrl)
  const [categorias, setCategorias] = useState([])
  const [configurando, setConfigurando] = useState(null)
  const [resultado, setResultado] = useState({
    consulta: null,
    productos: [],
    error: null,
  })

  const consulta = construirConsulta(filtros)
  const cargando = resultado.consulta !== consulta

  useEffect(() => {
    fetch('/api/productos/categorias')
      .then((r) => (r.ok ? r.json() : []))
      .then(setCategorias)
      .catch(() => setCategorias([]))
  }, [])

  useEffect(() => {
    const control = new AbortController()
    fetch(`/api/productos${consulta}`, { signal: control.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`Error ${r.status} al consultar el catálogo`)
        return r.json()
      })
      .then((productos) => setResultado({ consulta, productos, error: null }))
      .catch((e) => {
        if (e.name !== 'AbortError') {
          setResultado({ consulta, productos: [], error: e.message })
        }
      })
    return () => control.abort()
  }, [consulta])

  function cambiar(campo) {
    return (e) => setFiltros((f) => ({ ...f, [campo]: e.target.value }))
  }

  const sinResultados =
    !resultado.error && !cargando && resultado.productos.length === 0
  const filtrando = Boolean(filtros.q || filtros.categoria || filtros.material || filtros.precioMax)

  return (
    <div className="sitio">
      <header className="sitio-cabecera">
        <a href="/" className="sitio-logo">
          <img src="/marca/logo-durazno.png" alt="Joyería Xavier, inspirado en ti" />
        </a>
        <nav aria-label="Secciones del sitio">
          <a href="#catalogo">Catálogo</a>
          <a href="#como-cotizamos">Cómo cotizamos</a>
          <a href="#contacto">Contacto</a>
        </nav>
        <BotonWhatsApp />
      </header>

      <section className="portada">
        <div className="portada-texto">
          <h1>Diseñando joyas con amor desde 1964</h1>
          <p>
            Joyas en oro y plata hechas en Quito. Elige un modelo y conoce su precio referencial al
            instante; un asesor confirma el valor final.
          </p>
          <div className="portada-acciones">
            <a className="boton oscuro" href="#catalogo">
              Ver el catálogo
            </a>
            <a className="boton contorno" href="#contacto">
              Hablar con un asesor
            </a>
          </div>
        </div>
        <img className="portada-logo" src="/marca/logo-blanco.png" alt="" />
      </section>

      <main id="catalogo" className="catalogo">
        <div className="catalogo-cabeza">
          <h2>Nuestras joyas</h2>
          <div className="selector-material" role="group" aria-label="Material">
            {['', ...MATERIALES].map((m) => (
              <button
                key={m || 'todos'}
                type="button"
                aria-pressed={filtros.material === m}
                onClick={() => setFiltros((f) => ({ ...f, material: m }))}
              >
                {m ? m.charAt(0).toUpperCase() + m.slice(1) : 'Todos'}
              </button>
            ))}
          </div>
        </div>

        <div className="chips" role="group" aria-label="Categoría">
          {['', ...categorias].map((c) => (
            <button
              key={c || 'todas'}
              type="button"
              aria-pressed={filtros.categoria === c}
              onClick={() => setFiltros((f) => ({ ...f, categoria: c }))}
            >
              {c || 'Todas'}
            </button>
          ))}
        </div>

        <section className="filtros" aria-label="Buscar y filtrar">
          <label>
            Buscar
            <input type="search" value={filtros.q} onChange={cambiar('q')} placeholder="Nombre de la joya" />
          </label>
          <label>
            Precio máximo (USD)
            <input
              type="number"
              min="0"
              value={filtros.precioMax}
              onChange={cambiar('precioMax')}
              placeholder="Ej. 500"
            />
          </label>
          <button type="button" className="boton" disabled={!filtrando} onClick={() => setFiltros(FILTROS_VACIOS)}>
            Limpiar filtros
          </button>
        </section>

        {resultado.error && <p className="estado error">{resultado.error}</p>}
        {!resultado.error && cargando && <p className="estado">Cargando…</p>}
        {!resultado.error && !cargando && resultado.productos.length > 0 && (
          <p className="nota catalogo-cuenta">
            {resultado.productos.length} {resultado.productos.length === 1 ? 'joya' : 'joyas'}
          </p>
        )}
        {sinResultados && (
          <ContactoAsesor
            titulo="No hay joyas con esos filtros. Un asesor puede ayudarte a encontrar lo que buscas."
            mensaje={MENSAJE_SIN_RESULTADOS}
          />
        )}

        <ul className="rejilla">
          {resultado.productos.map((p) => (
            <Tarjeta key={p.id} producto={p} onConfigurar={setConfigurando} />
          ))}
        </ul>
      </main>

      <section id="como-cotizamos" className="como">
        <h2>Cómo cotizamos</h2>
        <ol>
          <li>
            <strong>Elige tu joya</strong>
            <span>Filtra por categoría y material y abre el modelo que te guste.</span>
          </li>
          <li>
            <strong>Mira el precio al instante</strong>
            <span>Se calcula con el peso de la pieza por el precio del gramo del material, más la mano de obra.</span>
          </li>
          <li>
            <strong>Un asesor lo confirma</strong>
            <span>Te escribe por tu canal preferido, confirma el valor final y registra tu orden.</span>
          </li>
        </ol>
      </section>

      <section id="contacto" className="sitio-contacto">
        <div>
          <h2>¿Buscas algo distinto?</h2>
          <p>Diseños a medida, otro material o quilataje: cuéntanos y un asesor te ayuda.</p>
        </div>
        <ContactoAsesor titulo="Elige por dónde prefieres que te atendamos." mensaje={MENSAJE_GENERAL} />
      </section>

      <footer className="sitio-pie">
        <img src="/marca/logo-durazno.png" alt="" />
        <span>Joyería Xavier · Quito, Ecuador · Precios referenciales en USD</span>
      </footer>

      <Chat />

      {configurando !== null && (
        <Configurador
          key={configurando}
          productoId={configurando}
          onCerrar={() => setConfigurando(null)}
        />
      )}
    </div>
  )
}

function BotonWhatsApp() {
  const canales = useCanales(MENSAJE_GENERAL)
  const whatsapp = canales.find((c) => c.canal === 'whatsapp') ?? canales[0]
  if (!whatsapp) return null
  return (
    <a className="boton primario sitio-escribenos" href={whatsapp.enlace} target="_blank" rel="noreferrer">
      Escríbenos por {whatsapp.nombre}
    </a>
  )
}

export default App