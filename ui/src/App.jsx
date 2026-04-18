import { useState, useEffect, useRef } from 'react'
import './App.css'

const API = 'http://localhost:8002'

const STAGE_CONFIG = {
  application_submitted: { label: 'Application',  color: '#6366f1', bg: '#eef2ff', step: 1 },
  document_review:       { label: 'Doc Review',   color: '#f59e0b', bg: '#fffbeb', step: 2 },
  underwriting:          { label: 'Underwriting', color: '#3b82f6', bg: '#eff6ff', step: 3 },
  approved:              { label: 'Approved',      color: '#10b981', bg: '#ecfdf5', step: 4 },
  closing:               { label: 'Closing',       color: '#8b5cf6', bg: '#f5f3ff', step: 5 },
}

const DEMO_LOANS = [
  { loan_id: 'LN-2024-001', borrower_name: 'John Smith',     loan_type: 'FHA',           loan_amount: 308800,  stage: 'application_submitted', credit_score: 680, dti_ratio: 42.3, interest_rate: 6.750, property_address: '123 Oak St, Austin TX' },
  { loan_id: 'LN-2024-002', borrower_name: 'Maria Garcia',   loan_type: 'Conventional',  loan_amount: 432000,  stage: 'document_review',       credit_score: 748, dti_ratio: 34.7, interest_rate: 7.125, property_address: '456 Elm Ave, Dallas TX' },
  { loan_id: 'LN-2024-003', borrower_name: 'Robert Johnson', loan_type: 'VA',            loan_amount: 432437,  stage: 'underwriting',          credit_score: 712, dti_ratio: 33.1, interest_rate: 6.875, property_address: '789 Pecan Blvd, San Antonio TX' },
  { loan_id: 'LN-2024-004', borrower_name: 'Sarah Chen',     loan_type: 'Jumbo',         loan_amount: 1480000, stage: 'approved',              credit_score: 798, dti_ratio: 29.2, interest_rate: 7.125, property_address: '1201 River Oaks Blvd, Houston TX' },
  { loan_id: 'LN-2024-005', borrower_name: 'Michael Brown',  loan_type: 'FHA Refinance', loan_amount: 291250,  stage: 'closing',               credit_score: 695, dti_ratio: 30.2, interest_rate: 5.990, property_address: '567 Birch Lane, Austin TX' },
]

const SUGGESTED_QUESTIONS = {
  application_submitted: [
    'Is this borrower eligible for an FHA loan?',
    'What is the borrower credit score and DTI ratio?',
    'What is the upfront MIP cost for this loan?',
  ],
  document_review: [
    'Has the appraisal been completed and what did it find?',
    'What is the LTV ratio and does it avoid PMI?',
    'Summarize the borrower financial profile.',
  ],
  underwriting: [
    'Does the veteran meet VA residual income requirements?',
    'What conditions are still outstanding in underwriting?',
    'What is the VA funding fee for this loan?',
  ],
  approved: [
    'What are the jumbo loan approval conditions that were met?',
    'When does the rate lock expire?',
    'What reserves does the borrower have available?',
  ],
  closing: [
    'What is the cash to close amount?',
    'What is the new monthly payment after refinance?',
    'When is the first payment due after closing?',
  ],
}

function StageProgressBar({ stage }) {
  const current = STAGE_CONFIG[stage]?.step || 1
  return (
    <div className="stage-bar">
      <div className="stage-line-bg">
        <div className="stage-line-fill" style={{ width: `${((current - 1) / 4) * 100}%` }} />
      </div>
      {Object.entries(STAGE_CONFIG).map(([key, cfg]) => (
        <div key={key} className={`stage-step ${cfg.step <= current ? 'done' : ''} ${cfg.step === current ? 'current' : ''}`}>
          <div className="stage-dot" style={{ background: cfg.step <= current ? cfg.color : '#d1d5db', borderColor: cfg.step === current ? cfg.color : 'transparent' }}>
            {cfg.step < current && <span>✓</span>}
            {cfg.step === current && <span>{cfg.step}</span>}
            {cfg.step > current && <span style={{ color: '#9ca3af' }}>{cfg.step}</span>}
          </div>
          <span className="stage-label" style={{ color: cfg.step <= current ? cfg.color : '#9ca3af' }}>{cfg.label}</span>
        </div>
      ))}
    </div>
  )
}

function LoanCard({ loan, selected, onClick }) {
  const cfg = STAGE_CONFIG[loan.stage] || STAGE_CONFIG.application_submitted
  return (
    <div className={`loan-card ${selected ? 'selected' : ''}`} onClick={onClick}>
      <div className="loan-card-header">
        <span className="loan-id">{loan.loan_id}</span>
        <span className="stage-badge" style={{ color: cfg.color, background: cfg.bg }}>{cfg.label}</span>
      </div>
      <div className="loan-borrower">{loan.borrower_name}</div>
      <div className="loan-meta">
        <span className="loan-type-tag">{loan.loan_type}</span>
        <span className="loan-amount">${(loan.loan_amount / 1000).toFixed(0)}K</span>
      </div>
    </div>
  )
}

function MetricCard({ label, value, sub, color }) {
  return (
    <div className="metric-card">
      <div className="metric-value" style={{ color: color || '#111827' }}>{value}</div>
      <div className="metric-label">{label}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  )
}

function ChatMessage({ msg }) {
  return (
    <div className={`chat-msg ${msg.role}`}>
      <div className="chat-avatar">{msg.role === 'user' ? '👤' : '🤖'}</div>
      <div className="chat-bubble">
        <p style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p>
        {msg.sources?.length > 0 && (
          <div className="sources">
            <span className="sources-label">Sources:</span>
            {msg.sources.map((s, i) => (
              <span key={i} className="source-tag">📄 {s.doc_type} · {s.score}</span>
            ))}
          </div>
        )}
        {msg.trace_id && (
          <div className="trace-id">🔍 trace: {msg.trace_id.slice(0, 12)}…</div>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [selected, setSelected] = useState(DEMO_LOANS[0])
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [docStatus, setDocStatus] = useState([])
  const [activeTab, setActiveTab] = useState('chat')
  const bottomRef = useRef(null)

  useEffect(() => {
    setMessages([])
    fetchDocStatus()
  }, [selected])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function fetchDocStatus() {
    try {
      const res = await fetch(`${API}/loans/${selected.loan_id}/status`)
      const data = await res.json()
      setDocStatus(data.documents || [])
    } catch {
      setDocStatus([])
    }
  }

  async function sendMessage(question) {
    const q = (question || input).trim()
    if (!q || loading) return
    setInput('')
    setMessages(m => [...m, { role: 'user', content: q }])
    setLoading(true)
    try {
      const res = await fetch(`${API}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, loan_id: selected.loan_id }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Query failed')
      setMessages(m => [...m, { role: 'assistant', content: data.answer, sources: data.sources, trace_id: data.trace_id }])
    } catch (e) {
      setMessages(m => [...m, { role: 'assistant', content: `⚠️ ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const cfg = STAGE_CONFIG[selected.stage] || STAGE_CONFIG.application_submitted
  const creditColor = selected.credit_score >= 740 ? '#10b981' : selected.credit_score >= 680 ? '#f59e0b' : '#ef4444'
  const dtiColor = selected.dti_ratio <= 36 ? '#10b981' : selected.dti_ratio <= 43 ? '#f59e0b' : '#ef4444'

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">🏦 MortgageRAG</div>
          <div className="logo-sub">AI Underwriting Assistant</div>
        </div>
        <div className="sidebar-section-label">LOAN PIPELINE</div>
        <div className="loan-list">
          {DEMO_LOANS.map(loan => (
            <LoanCard
              key={loan.loan_id}
              loan={loan}
              selected={selected.loan_id === loan.loan_id}
              onClick={() => setSelected(loan)}
            />
          ))}
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        {/* Loan Header */}
        <div className="loan-header">
          <div className="loan-header-top">
            <div>
              <h1>{selected.borrower_name}</h1>
              <div className="loan-header-meta">
                <span>{selected.loan_id}</span>
                <span className="sep">·</span>
                <span>{selected.loan_type}</span>
                <span className="sep">·</span>
                <span>{selected.property_address}</span>
              </div>
            </div>
            <span className="stage-badge-lg" style={{ color: cfg.color, background: cfg.bg }}>{cfg.label}</span>
          </div>

          <StageProgressBar stage={selected.stage} />

          <div className="metrics-row">
            <MetricCard label="Loan Amount"   value={`$${(selected.loan_amount / 1000).toFixed(0)}K`} />
            <MetricCard label="Credit Score"  value={selected.credit_score} color={creditColor}
              sub={selected.credit_score >= 740 ? '● Excellent' : selected.credit_score >= 680 ? '● Good' : '● Fair'} />
            <MetricCard label="DTI Ratio" value={`${selected.dti_ratio}%`} color={dtiColor}
              sub={selected.dti_ratio <= 36 ? '● Low risk' : selected.dti_ratio <= 43 ? '● Acceptable' : '● High'} />
            <MetricCard label="Interest Rate" value={`${selected.interest_rate}%`} />
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          <button className={`tab ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>
            💬 AI Assistant
          </button>
          <button className={`tab ${activeTab === 'docs' ? 'active' : ''}`} onClick={() => { setActiveTab('docs'); fetchDocStatus() }}>
            📁 Documents {docStatus.length > 0 && <span className="tab-badge">{docStatus.length}</span>}
          </button>
        </div>

        {/* Chat Tab */}
        {activeTab === 'chat' && (
          <div className="chat-panel">
            <div className="chat-messages">
              {messages.length === 0 && (
                <div className="suggestions">
                  <div className="suggestions-title">Suggested questions for <strong>{selected.borrower_name}</strong> ({cfg.label} stage):</div>
                  <div className="suggestions-list">
                    {(SUGGESTED_QUESTIONS[selected.stage] || []).map((q, i) => (
                      <button key={i} className="suggestion-btn" onClick={() => sendMessage(q)}>{q}</button>
                    ))}
                  </div>
                </div>
              )}
              {messages.map((m, i) => <ChatMessage key={i} msg={m} />)}
              {loading && (
                <div className="chat-msg assistant">
                  <div className="chat-avatar">🤖</div>
                  <div className="chat-bubble loading">
                    <span /><span /><span />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <div className="chat-input-row">
              <input
                className="chat-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && sendMessage()}
                placeholder={`Ask about ${selected.borrower_name}'s loan…`}
                disabled={loading}
              />
              <button className="send-btn" onClick={() => sendMessage()} disabled={loading || !input.trim()}>
                {loading ? '…' : 'Send'}
              </button>
            </div>
          </div>
        )}

        {/* Documents Tab */}
        {activeTab === 'docs' && (
          <div className="docs-panel">
            {docStatus.length === 0 ? (
              <div className="empty-docs">
                <div className="empty-icon">📂</div>
                <p>No documents ingested yet for <strong>{selected.loan_id}</strong>.</p>
                <p>Run <code>./load_demo_data.sh</code> to load all demo documents.</p>
              </div>
            ) : (
              <table className="docs-table">
                <thead>
                  <tr><th>Document</th><th>Status</th><th>Chunks</th><th>Ingested</th></tr>
                </thead>
                <tbody>
                  {docStatus.map((d, i) => (
                    <tr key={i}>
                      <td className="doc-type-cell">📄 {d.doc_type}</td>
                      <td><span className={`status-pill ${d.status}`}>{d.status}</span></td>
                      <td>{d.chunks || 0}</td>
                      <td>{d.ingested_at && d.ingested_at !== 'None' ? new Date(d.ingested_at).toLocaleDateString() : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
