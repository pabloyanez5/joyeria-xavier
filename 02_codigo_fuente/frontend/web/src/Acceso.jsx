import { useState } from 'react'
import { entrar } from './sesion.js'

// Pantalla de inicio de sesión del panel interno.
export default function Acceso({ onEntrar }) {
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
    <main className="pagina">
      <header className="encabezado">
        <h1>Panel interno</h1>
        <p>Joyería Xavier · inicia sesión para continuar</p>
      </header>

      <form className="acceso" onSubmit={enviar}>
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
        {error && <p className="estado error">{error}</p>}
      </form>
    </main>
  )
}
