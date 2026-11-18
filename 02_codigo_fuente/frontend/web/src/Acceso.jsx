import { useState } from 'react'
import InterruptorTema from './InterruptorTema.jsx'
import { entrar } from './sesion.js'

// Pantalla de inicio de sesión del panel interno (JOY-78), con la marca de la joyería (JOY-88).
export default function Acceso({ onEntrar, tema, onAlternarTema }) {
  const [email, setEmail] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState(null)
  const [enviando, setEnviando] = useState(false)

  async function enviar(e) {
    e.preventDefault()
    setEnviando(true)
    setError(null)
    try {
      onEntrar(await entrar(email, clave))
    } catch (fallo) {
      setError(fallo.message)
      setClave('')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="acceso-pantalla">
      <section className="acceso-marca" aria-label="Joyería Xavier">
        <img src="/marca/logo-blanco.png" alt="Joyería Xavier, inspirado en ti" />
        <div>
          <p className="acceso-lema">Diseñando joyas con amor desde 1964</p>
          <p>Panel interno para asesores, taller y dirección.</p>
        </div>
        <small>Quito · Ecuador</small>
      </section>

      <main className="acceso-lado">
        <div className="acceso-barra">
          <InterruptorTema tema={tema} onAlternar={onAlternarTema} />
        </div>
        <form className="acceso" onSubmit={enviar}>
          <div>
            <h1>Bienvenido</h1>
            <p className="acceso-ayuda">Ingresa con tu correo de la joyería.</p>
          </div>
          <label>
            Correo
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
              autoFocus
            />
          </label>
          <label>
            Clave
            <input
              type="password"
              value={clave}
              onChange={(e) => setClave(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button type="submit" className="boton primario" disabled={enviando || !email || !clave}>
            {enviando ? 'Entrando…' : 'Entrar'}
          </button>
          {error && (
            <p className="estado error" role="alert">
              {error}
            </p>
          )}
          <p className="acceso-ayuda">
            Tras 5 intentos fallidos el acceso se bloquea 15 minutos. La sesión se cierra sola a
            las 8 horas.
          </p>
        </form>
      </main>
    </div>
  )
}
