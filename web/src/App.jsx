import React, { useEffect, useMemo, useRef, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080'

function useSessionId() {
  const [id, setId] = useState('')
  useEffect(() => {
    let sid = localStorage.getItem('utahai_session_id')
    if (!sid) {
      sid = `web-${Math.random().toString(36).slice(2, 10)}`
      localStorage.setItem('utahai_session_id', sid)
    }
    setId(sid)
  }, [])
  return id
}

function SourceCard({ item }) {
  const title = item.title || 'Untitled document'
  const uri = item.uri || '#'
  const snippet = item.snippet || ''
  return (
    <div className="source-card">
      <div className="source-title">
        {uri && uri !== '#' ? (
          <a href={uri} target="_blank" rel="noreferrer">{title}</a>
        ) : (
          <span>{title}</span>
        )}
      </div>
      {snippet && <div className="source-snippet">{snippet}</div>}
    </div>
  )
}

function Message({ role, content, sources }) {
  return (
    <div className={`message ${role}`}>
      <div className="bubble">
        <div className="content">{content}</div>
        {sources && sources.length > 0 && (
          <div className="sources">
            <div className="sources-header">Sources</div>
            <div className="sources-list">
              {sources.map((s, i) => (
                <SourceCard key={i} item={s} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const sessionId = useSessionId()
  const [messages, setMessages] = useState([
    { role: 'assistant', content: 'Hi! Ask me anything about your documents. I will search your GCP-connected knowledge base and cite sources.' }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const containerRef = useRef(null)

  const endpoint = useMemo(() => `${API_URL}`.replace(/\/$/, ''), [])

  useEffect(() => {
    // Auto-scroll to bottom on new messages
    containerRef.current?.scrollTo({ top: containerRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function ask(question) {
    const q = question.trim()
    if (!q || loading) return

    setMessages(prev => [...prev, { role: 'user', content: q }])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch(`${endpoint}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, session_id: sessionId })
      })

      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }

      const data = await res.json()
      const answer = data.answer || 'No answer.'
      const sources = Array.isArray(data.results) ? data.results : []

      setMessages(prev => [...prev, { role: 'assistant', content: answer, sources }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(e) {
    e.preventDefault()
    ask(input)
  }

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">UtahAI Chat</div>
        <div className="env">API: {endpoint}</div>
      </header>

      <main className="chat" ref={containerRef}>
        {messages.map((m, i) => (
          <Message key={i} role={m.role} content={m.content} sources={m.sources} />
        ))}
        {loading && (
          <div className="message assistant"><div className="bubble"><div className="typing">Thinking…</div></div></div>
        )}
      </main>

      <form className="composer" onSubmit={onSubmit}>
        <input
          type="text"
          placeholder="Ask about your documents…"
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? 'Sending…' : 'Send'}
        </button>
      </form>

      <footer className="footer">
        <div>Tip: Configure VITE_API_URL in web/.env to point to your Cloud Run URL when not running locally.</div>
      </footer>
    </div>
  )
}
