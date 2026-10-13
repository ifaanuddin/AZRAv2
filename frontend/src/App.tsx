
import { useState } from 'react'
import './App.css'

function App() {
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function connectToBackend() {
    setLoading(true)
    setError('')
    setMessage('')

    try {
      const response = await fetch('http://127.0.0.1:8000/')
      
      if (!response.ok) {
        throw new Error(`Server returned ${response.status}`)
      }

      const data = await response.json()
      setMessage(data.message)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'Something went wrong'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{
      maxWidth: '600px',
      margin: '100px auto',
      padding: '24px',
      fontFamily: 'Arial, sans-serif',
      textAlign: 'center'
    }}>
      <h1>AZRA V2 🌱</h1>
      <p>Your business companion is taking shape.</p>

      <button onClick={connectToBackend} disabled={loading}>
        {loading ? 'Connecting...' : 'Connect to AZRA'}
      </button>

      {message && <p>Backend says: {message}</p>}
      {error && <p role="alert">Connection failed: {error}</p>}
    </main>
  )
}

export default App
