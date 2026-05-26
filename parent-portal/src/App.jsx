import { useState, useEffect, useCallback } from 'react'

// ─── API ──────────────────────────────────────────────────────────────────────

async function api(path, options = {}) {
  const token = localStorage.getItem('pp_token')
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  const data = await res.json()
  if (!res.ok) throw Object.assign(new Error(data.error || 'Request failed'), { status: res.status })
  return data
}

// ─── Utils ────────────────────────────────────────────────────────────────────

const fmtRWF  = n => Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' RWF'
const fmtDate = iso => new Date(iso).toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: '2-digit' })

// ─── Layout pieces ────────────────────────────────────────────────────────────

function Header({ parentName, onSignOut }) {
  return (
    <header className="header">
      <div className="header-left">
        <span className="header-logo">CW</span>
        <span className="header-title">PARENT PORTAL</span>
      </div>
      {parentName && (
        <button className="btn-ghost" onClick={onSignOut}>SIGN OUT</button>
      )}
    </header>
  )
}

function Section({ label, children }) {
  return (
    <section className="section">
      {label && <p className="section-lbl">{label}</p>}
      {children}
    </section>
  )
}

// ─── Login ────────────────────────────────────────────────────────────────────

function LoginView({ onLogin }) {
  const [email, setEmail] = useState('')
  const [pass,  setPass]  = useState('')
  const [err,   setErr]   = useState('')
  const [busy,  setBusy]  = useState(false)

  async function submit(e) {
    e.preventDefault()
    setErr('')
    setBusy(true)
    try {
      const d = await api('/api/parent/login', {
        method: 'POST',
        body: JSON.stringify({ email, password: pass }),
      })
      localStorage.setItem('pp_token', d.token)
      onLogin(d)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Section>
        <p className="welcome-title">Welcome</p>
        <p className="dim small">Sign in to manage your child's canteen wallet</p>
      </Section>

      <Section label="Sign In">
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-lbl">Email</label>
            <input
              className="field"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="your@email.com"
              autoFocus
              autoComplete="email"
              required
            />
          </div>
          <div className="form-row">
            <label className="form-lbl">Password</label>
            <input
              className="field"
              type="password"
              value={pass}
              onChange={e => setPass(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              required
            />
          </div>
          {err && <p className="field-err">{err}</p>}
          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? 'SIGNING IN...' : '[ SIGN IN ]'}
          </button>
        </form>
        <div className="demo-hint">
          <p className="dim small">Demo accounts (password: <span>parent1234</span>)</p>
          <p className="dim small">alice.parent@demo.rw · robert.smith@demo.rw · claire.white@demo.rw</p>
        </div>
      </Section>
    </>
  )
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function DashboardView({ parent, student, recharges, onAddMoney }) {
  return (
    <>
      <Section>
        <p className="dim small">Welcome back,</p>
        <p className="parent-name">{parent.name}</p>
      </Section>

      <Section label="Student Account">
        {student ? (
          <>
            <div className="student-row">
              <div>
                <p className="stu-name">{student.name}</p>
                <p className="dim small">ID · {String(student.id).padStart(4, '0')}</p>
              </div>
              <div className="bal-block">
                <p className="bal-amount green">{fmtRWF(student.balance)}</p>
                <p className="dim small">current balance</p>
              </div>
            </div>
            <button className="btn-primary" onClick={onAddMoney}>+ ADD MONEY</button>
          </>
        ) : (
          <p className="dim small">No student linked to this account.</p>
        )}
      </Section>

      <Section label="Recent Recharges">
        {recharges.length === 0
          ? <p className="dim small">No recharges yet.</p>
          : (
            <div className="recharge-list">
              {recharges.map(r => (
                <div key={r.id} className="recharge-row">
                  <span className="re-date dim">{fmtDate(r.created_at)}</span>
                  <span className="re-amt blue">+{fmtRWF(r.amount)}</span>
                  <span className={`re-badge ${r.status}`}>
                    {r.status === 'verified' ? '✓ verified'
                     : r.status === 'failed'  ? '✗ failed'
                     :                          '… pending'}
                  </span>
                </div>
              ))}
            </div>
          )
        }
      </Section>
    </>
  )
}

// ─── Add money ────────────────────────────────────────────────────────────────

function AddMoneyView({ student, defaultPhone, onBack, onInitiated }) {
  const [amount, setAmount] = useState('')
  const [phone,  setPhone]  = useState(defaultPhone || '')
  const [err,    setErr]    = useState('')
  const [busy,   setBusy]   = useState(false)

  async function submit(e) {
    e.preventDefault()
    const amt = parseFloat(amount)
    if (isNaN(amt) || amt < 100) { setErr('Minimum recharge is 100 RWF'); return }
    setErr('')
    setBusy(true)
    try {
      const d = await api('/api/parent/initiate-recharge', {
        method: 'POST',
        body: JSON.stringify({ amount: amt, parent_phone: phone }),
      })
      onInitiated(d)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Section>
        <div className="back-row">
          <button className="btn-ghost" onClick={onBack}>← BACK</button>
          <span className="dim small">Adding funds for {student?.name}</span>
        </div>
      </Section>

      <Section label="Add Money">
        <form onSubmit={submit}>
          <div className="form-row">
            <label className="form-lbl">Amount</label>
            <input
              className="field field-num"
              type="number"
              min="100"
              step="100"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              placeholder="0"
              autoFocus
              required
            />
            <span className="field-unit">RWF</span>
          </div>
          <div className="form-row">
            <label className="form-lbl">MoMo Number</label>
            <input
              className="field"
              type="tel"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              placeholder="07XXXXXXXX"
              required
            />
          </div>
          {err && <p className="field-err">{err}</p>}
          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? 'PROCESSING...' : '[ CONTINUE WITH MOMO ]'}
          </button>
        </form>
        <p className="dim small momo-note">
          You will receive a MoMo prompt to confirm the payment.
        </p>
      </Section>
    </>
  )
}

// ─── Payment pending ──────────────────────────────────────────────────────────

function PaymentView({ txn, onBack, onPaid }) {
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState('')

  async function simulate() {
    setErr('')
    setBusy(true)
    try {
      const d = await api('/api/momo-webhook', {
        method: 'POST',
        body: JSON.stringify({ transaction_id: txn.transaction_id, status: 'completed' }),
      })
      onPaid(d.new_balance)
    } catch (ex) {
      setErr(ex.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Section>
        <div className="back-row">
          <button className="btn-ghost" onClick={onBack}>← BACK</button>
        </div>
      </Section>

      <Section label="MoMo Payment">
        <div className="info-grid">
          <span className="ig-lbl">Transaction</span>
          <span className="mono">{txn.transaction_id}</span>
          <span className="ig-lbl">Amount</span>
          <span className="blue">{fmtRWF(txn.amount)}</span>
          <span className="ig-lbl">Student</span>
          <span>{txn.student_name}</span>
          <span className="ig-lbl">Status</span>
          <span className="yellow">Awaiting payment…</span>
        </div>

        <div className="link-box">
          <p className="dim small">Payment link (open in MoMo app):</p>
          <p className="mono small link-text">{txn.momo_payment_link}</p>
        </div>

        <div className="demo-box">
          <p className="dim small">── Demo mode ──────────────────</p>
          <p className="small">No real MoMo account needed. Simulate a successful payment callback:</p>
          {err && <p className="field-err">{err}</p>}
          <button className="btn-sim" onClick={simulate} disabled={busy}>
            {busy ? '⟳  SIMULATING...' : '[ SIMULATE MOMO PAYMENT ]'}
          </button>
        </div>
      </Section>
    </>
  )
}

// ─── Success ──────────────────────────────────────────────────────────────────

function SuccessView({ amount, newBalance, studentName, onDone }) {
  return (
    <Section label="Payment Confirmed">
      <div className="success-wrap">
        <div className="success-icon green">✓</div>
        <p className="success-title green">Payment verified</p>
        <p className="success-line">
          <span className="blue">+{fmtRWF(amount)}</span> added to {studentName}'s wallet
        </p>
        <p className="dim small">New balance: <span className="green">{fmtRWF(newBalance)}</span></p>
      </div>
      <button className="btn-primary" onClick={onDone}>[ BACK TO DASHBOARD ]</button>
    </Section>
  )
}

// ─── App ──────────────────────────────────────────────────────────────────────

export default function App() {
  const [view,       setView]       = useState('init')
  const [parent,     setParent]     = useState(null)
  const [student,    setStudent]    = useState(null)
  const [recharges,  setRecharges]  = useState([])
  const [pendingTxn, setPendingTxn] = useState(null)
  const [paid,       setPaid]       = useState(null)   // { amount, newBalance, studentName }

  const applyPayload = useCallback(d => {
    setParent(d.parent)
    setStudent(d.student)
    setRecharges(d.recharges || [])
  }, [])

  // Restore session on mount
  useEffect(() => {
    if (!localStorage.getItem('pp_token')) { setView('login'); return }
    api('/api/parent/me')
      .then(d => { applyPayload(d); setView('dashboard') })
      .catch(() => { localStorage.removeItem('pp_token'); setView('login') })
  }, [applyPayload])

  function handleLogin(d)  { applyPayload(d); setView('dashboard') }

  function handleSignOut() {
    api('/api/parent/logout', { method: 'POST' }).catch(() => {})
    localStorage.removeItem('pp_token')
    setParent(null); setStudent(null); setRecharges([])
    setView('login')
  }

  function handleInitiated(txn) { setPendingTxn(txn); setView('payment') }

  function handlePaid(newBalance) {
    setPaid({ amount: pendingTxn.amount, newBalance, studentName: student.name })
    setView('success')
  }

  function handleDone() {
    api('/api/parent/me')
      .then(d => { applyPayload(d); setView('dashboard') })
      .catch(() => setView('dashboard'))
  }

  return (
    <div className="app">
      <Header parentName={parent?.name} onSignOut={handleSignOut} />

      {view === 'init' && (
        <Section><p className="dim small">Loading…</p></Section>
      )}

      {view === 'login' && <LoginView onLogin={handleLogin} />}

      {view === 'dashboard' && (
        <DashboardView
          parent={parent} student={student} recharges={recharges}
          onAddMoney={() => setView('add-money')}
        />
      )}

      {view === 'add-money' && (
        <AddMoneyView
          student={student}
          defaultPhone={parent?.phone}
          onBack={() => setView('dashboard')}
          onInitiated={handleInitiated}
        />
      )}

      {view === 'payment' && pendingTxn && (
        <PaymentView
          txn={pendingTxn}
          onBack={() => setView('dashboard')}
          onPaid={handlePaid}
        />
      )}

      {view === 'success' && paid && (
        <SuccessView
          amount={paid.amount}
          newBalance={paid.newBalance}
          studentName={paid.studentName}
          onDone={handleDone}
        />
      )}
    </div>
  )
}
