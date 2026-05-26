import { useState, useEffect } from 'react'

// ─── Mock student DB ──────────────────────────────────────────────────────────
// Keyed by TOKEN_NNN prefix; lookup accepts full tokens like TOKEN_001_5lzkju.
const STUDENTS = {
  TOKEN_001: { id: 1,  name: 'Alice Johnson',  balance: 5000.00, dailyLimit: 2000, dailyUsed: 500  },
  TOKEN_002: { id: 2,  name: 'Bob Smith',       balance: 3200.00, dailyLimit: 2000, dailyUsed: 0    },
  TOKEN_003: { id: 3,  name: 'Carol White',     balance: 1500.00, dailyLimit: 1500, dailyUsed: 200  },
  TOKEN_004: { id: 4,  name: 'David Brown',     balance: 4200.00, dailyLimit: 2000, dailyUsed: 800  },
  TOKEN_005: { id: 5,  name: 'Eva Martinez',    balance: 2800.00, dailyLimit: 2000, dailyUsed: 300  },
  TOKEN_006: { id: 6,  name: 'Frank Wilson',    balance: 3100.00, dailyLimit: 1800, dailyUsed: 0    },
  TOKEN_007: { id: 7,  name: 'Grace Lee',       balance: 4800.00, dailyLimit: 2000, dailyUsed: 900  },
  TOKEN_008: { id: 8,  name: 'Henry Taylor',    balance: 1200.00, dailyLimit: 1500, dailyUsed: 100  },
  TOKEN_009: { id: 9,  name: 'Iris Anderson',   balance: 6200.00, dailyLimit: 3000, dailyUsed: 500  },
  TOKEN_010: { id: 10, name: 'Jack Thomas',     balance: 2300.00, dailyLimit: 2000, dailyUsed: 1500 },
  TOKEN_011: { id: 11, name: 'Karen Jackson',   balance: 1800.00, dailyLimit: 1500, dailyUsed: 750  },
  TOKEN_012: { id: 12, name: 'Liam Harris',     balance: 3900.00, dailyLimit: 2000, dailyUsed: 0    },
  TOKEN_013: { id: 13, name: 'Mia Garcia',      balance: 500.00,  dailyLimit: 1000, dailyUsed: 400  },
  TOKEN_014: { id: 14, name: 'Noah Martinez',   balance: 4100.00, dailyLimit: 2500, dailyUsed: 200  },
  TOKEN_015: { id: 15, name: 'Olivia Davis',    balance: 2600.00, dailyLimit: 2000, dailyUsed: 1000 },
  TOKEN_016: { id: 16, name: 'Peter Robinson',  balance: 3700.00, dailyLimit: 2000, dailyUsed: 600  },
  TOKEN_017: { id: 17, name: 'Quinn Thompson',  balance: 1100.00, dailyLimit: 1500, dailyUsed: 300  },
  TOKEN_018: { id: 18, name: 'Rachel Lewis',    balance: 4500.00, dailyLimit: 2000, dailyUsed: 0    },
  TOKEN_019: { id: 19, name: 'Samuel Walker',   balance: 2900.00, dailyLimit: 2000, dailyUsed: 700  },
  TOKEN_020: { id: 20, name: 'Tina Hall',       balance: 3300.00, dailyLimit: 2000, dailyUsed: 450  },
}

const AVATAR_COLORS = ['#1e3a2f','#1a2d4a','#3a1a1a','#2d1a3a','#1a3a3a','#3a2d1a']

// ─── Utilities ────────────────────────────────────────────────────────────────

function loadLS(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback }
  catch { return fallback }
}

async function sha256hex(str) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(str))
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('')
}

function fmtRWF(n) {
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' RWF'
}

function r2(n) { return Math.round(n * 100) / 100 }

function initials(name) {
  return name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
}

function avatarBg(id) { return AVATAR_COLORS[(id - 1) % AVATAR_COLORS.length] }

function lookupByToken(raw) {
  const prefix = raw.trim().toUpperCase().match(/^(TOKEN_\d+)/)?.[1]
  const row = prefix ? STUDENTS[prefix] : null
  return row ? { ...row } : null
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function Header({ isOnline }) {
  return (
    <header className="header">
      <span className="header-title">SCHOOL CANTEEN PAYMENT SYSTEM</span>
      <span className={`online-dot ${isOnline ? 'on' : 'off'}`} title={isOnline ? 'Online' : 'Offline'} />
    </header>
  )
}

function OfflineBanner({ queueCount }) {
  return (
    <div className="offline-banner">
      <span className="offline-label">⚠  OFFLINE MODE (No WiFi)</span>
      {queueCount > 0 && (
        <span className="offline-queue">
          Queued: {queueCount} transaction{queueCount !== 1 ? 's' : ''} pending sync
        </span>
      )}
    </div>
  )
}

function Section({ label, children }) {
  return (
    <section className="section">
      <p className="section-lbl">{label}</p>
      {children}
    </section>
  )
}

function TokenInput({ value, onChange, onLookup, error }) {
  return (
    <Section label="QR Code Scanner Input">
      <div className="token-row">
        <input
          className="field"
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && onLookup()}
          placeholder="Scan student card or enter token..."
          autoFocus
          autoComplete="off"
          spellCheck={false}
        />
        <button className="btn" onClick={onLookup}>LOOKUP</button>
      </div>
      {error && <p className="field-err">{error}</p>}
    </Section>
  )
}

function StudentCard({ student }) {
  const pct      = Math.min((student.dailyUsed / student.dailyLimit) * 100, 100)
  const remaining = r2(student.dailyLimit - student.dailyUsed)
  const lowBal   = student.balance < 300

  return (
    <Section label="Student Account">
      <div className="stu-top">
        <div className="avatar" style={{ background: avatarBg(student.id) }}>
          {initials(student.name)}
        </div>
        <div className="stu-meta">
          <div className="stu-name">{student.name}</div>
          <div className="stu-id">ID · {String(student.id).padStart(4, '0')}</div>
        </div>
      </div>

      <div className="info-grid">
        <span className="ig-label">BALANCE</span>
        <span className={`ig-value ${lowBal ? 'yellow' : 'green'}`}>{fmtRWF(student.balance)}</span>

        <span className="ig-label">DAILY LIMIT</span>
        <span className="ig-value">{fmtRWF(student.dailyLimit)}</span>

        <span className="ig-label">USED TODAY</span>
        <span className={`ig-value ${remaining <= 0 ? 'red' : ''}`}>
          {fmtRWF(student.dailyUsed)}
          <span className="dim">
            {remaining > 0 ? ` (Remaining: ${fmtRWF(remaining)})` : '  LIMIT REACHED'}
          </span>
        </span>
      </div>

      <div className="bar-row">
        <div className="bar-bg">
          <div
            className={`bar-fill ${pct >= 100 ? 'red' : pct >= 80 ? 'yellow' : 'green'}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="bar-pct dim">{Math.round(pct)}%</span>
      </div>
    </Section>
  )
}

function TransactionForm({ amount, pin, onAmount, onPin, onSubmit, processing, student }) {
  const remaining = r2(student.dailyLimit - student.dailyUsed)
  const canGo     = !processing && amount && parseFloat(amount) > 0 && pin.length >= 4

  return (
    <Section label="Transaction">
      <div className="form-row">
        <label className="form-lbl">Amount</label>
        <input
          className="field field-num"
          type="number"
          min="1"
          step="0.01"
          max={Math.min(student.balance, remaining)}
          value={amount}
          onChange={e => onAmount(e.target.value)}
          placeholder="0.00"
        />
        <span className="field-unit">RWF</span>
      </div>

      <div className="form-row">
        <label className="form-lbl">Enter PIN</label>
        <input
          className="field field-pin"
          type="password"
          inputMode="numeric"
          maxLength={6}
          value={pin}
          onChange={e => onPin(e.target.value)}
          placeholder="••••"
        />
        <span className="field-unit dim">(hidden)</span>
      </div>

      <button className="btn-primary" onClick={onSubmit} disabled={!canGo}>
        {processing ? '⟳  PROCESSING...' : '[ COMPLETE TRANSACTION ]'}
      </button>
    </Section>
  )
}

function StatusBox({ status, onReset }) {
  const ok = status.type === 'success'
  return (
    <Section label="Status">
      <div className={`status-line ${ok ? 'green' : 'red'}`}>
        <span className="status-icon">{ok ? '✓' : '✗'}</span>
        <span className="status-msg">{status.message}</span>
      </div>

      {ok && (
        <>
          <p className="status-meta">
            Time: {status.time}
            &nbsp;·&nbsp;
            Balance: <span className="green">{fmtRWF(status.balanceAfter)}</span>
          </p>
          <p className="status-hash">Hash: {status.hash}…</p>
        </>
      )}

      <button className="btn btn-new" onClick={onReset}>NEW TRANSACTION</button>
    </Section>
  )
}

function RecentTxns({ txns }) {
  return (
    <Section label="Recent Transactions">
      {txns.length === 0
        ? <span className="dim small">No transactions recorded yet.</span>
        : txns.map(tx => (
            <div key={tx.id} className="txn-row">
              <span className="txn-time">{tx.time}</span>
              <span className="dim"> – </span>
              <span className="txn-name">{tx.name.split(' ')[0]}</span>
              <span className="dim"> – </span>
              <span className="txn-amt red">−{fmtRWF(tx.amount)}</span>
              <span className="dim"> – </span>
              <span className="txn-hash dim">Hash: {tx.hash}…</span>
            </div>
          ))
      }
    </Section>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [tokenInput, setTokenInput] = useState('')
  const [student,    setStudent]    = useState(null)
  const [lookupErr,  setLookupErr]  = useState('')
  const [amount,     setAmount]     = useState('')
  const [pin,        setPin]        = useState('')
  const [status,     setStatus]     = useState(null)
  const [processing, setProcessing] = useState(false)
  const [recentTxns, setRecentTxns] = useState(() => loadLS('cw_txns', []))
  const [isOnline,   setIsOnline]   = useState(navigator.onLine)
  const [offlineQ,   setOfflineQ]   = useState(() => loadLS('cw_offline_q', []))

  // Online / offline listener
  useEffect(() => {
    const goOn  = () => setIsOnline(true)
    const goOff = () => setIsOnline(false)
    window.addEventListener('online',  goOn)
    window.addEventListener('offline', goOff)
    return () => {
      window.removeEventListener('online',  goOn)
      window.removeEventListener('offline', goOff)
    }
  }, [])

  function doLookup() {
    setLookupErr('')
    setStudent(null)
    setStatus(null)
    setAmount('')
    setPin('')

    const s = lookupByToken(tokenInput)
    if (!s) {
      setLookupErr(tokenInput.trim()
        ? 'No student found for this token.'
        : 'Enter a token to look up.')
      return
    }
    setStudent(s)
  }

  async function doTransaction() {
    const amt = parseFloat(amount)
    if (isNaN(amt) || amt <= 0 || pin.length < 4) return

    setProcessing(true)
    await new Promise(r => setTimeout(r, 700)) // simulate network round-trip

    // PIN check (server-side in production; hardcoded to "1234" for demo)
    if (pin !== '1234') {
      setProcessing(false)
      setStatus({ type: 'error', message: 'Invalid PIN. Transaction declined.' })
      return
    }
    if (amt > student.balance) {
      setProcessing(false)
      setStatus({ type: 'error', message: `Insufficient balance. Available: ${fmtRWF(student.balance)}` })
      return
    }
    const remaining = r2(student.dailyLimit - student.dailyUsed)
    if (amt > remaining) {
      setProcessing(false)
      setStatus({ type: 'error', message: `Daily limit exceeded. Remaining: ${fmtRWF(remaining)}` })
      return
    }

    // Build SHA-256 chain link matching the Python _compute_hash signature
    const ts       = new Date().toISOString()
    const prevHash = recentTxns[0]?.fullHash ?? '0'.repeat(64)
    const hash     = await sha256hex(`${prevHash}${student.id}${amt.toFixed(10)}${ts}`)

    const newBalance  = r2(student.balance - amt)
    const time        = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

    const record = {
      id: Date.now(), time, name: student.name,
      amount: amt, hash: hash.slice(0, 12), fullHash: hash, ts,
    }

    setStudent(s => ({ ...s, balance: newBalance, dailyUsed: r2(s.dailyUsed + amt) }))

    const updated = [record, ...recentTxns].slice(0, 5)
    setRecentTxns(updated)
    localStorage.setItem('cw_txns', JSON.stringify(updated))

    if (!isOnline) {
      const q = [...offlineQ, record]
      setOfflineQ(q)
      localStorage.setItem('cw_offline_q', JSON.stringify(q))
    }

    setStatus({ type: 'success', message: 'Transaction complete', time, amount: amt, balanceAfter: newBalance, hash: hash.slice(0, 16) })
    setProcessing(false)
  }

  function doReset() {
    setStatus(null)
    setAmount('')
    setPin('')
    setTokenInput('')
    setStudent(null)
  }

  return (
    <div className="app">
      <Header isOnline={isOnline} />
      {!isOnline && <OfflineBanner queueCount={offlineQ.length} />}
      <TokenInput value={tokenInput} onChange={setTokenInput} onLookup={doLookup} error={lookupErr} />
      {student && <StudentCard student={student} />}
      {student && !status && (
        <TransactionForm
          amount={amount} pin={pin}
          onAmount={setAmount} onPin={setPin}
          onSubmit={doTransaction}
          processing={processing}
          student={student}
        />
      )}
      {status && <StatusBox status={status} onReset={doReset} />}
      <RecentTxns txns={recentTxns} />
    </div>
  )
}
