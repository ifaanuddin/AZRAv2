
import { useEffect, useRef, useState } from 'react'
import './App.css'

const API = 'http://127.0.0.1:8000'

type User = {
  username: string
  name: string
  role: 'owner' | 'cashier' | 'inventory'
  role_label: string
}

type MenuItem = {
  id: string
  name: string
  category: string
  price: number
}

type Ingredient = {
  id: string
  name: string
  quantity: number
  unit: string
  reorder_level: number
  unit_cost: number
}

type Order = {
  id: number
  total: number
  payment_method: string
  payment_status: string
  collected_by: string
  created_at: string
  items: { name: string; quantity: number }[]
}

type Dashboard = {
  metrics?: {
    revenue: number
    estimated_profit: number
    orders: number
    average_order: number
    top_items: { name: string; quantity: number }[]
    sales_by_day: { date: string; revenue: number }[]
  }
  stock?: Ingredient[]
  low_stock?: Ingredient[]
  menu?: MenuItem[]
  recent_orders?: Order[]
  today_revenue?: number
  today_orders?: number
}

const demoAccounts = [
  { label: 'Café Owner', username: 'owner', password: 'PalmOwner123!', icon: '♙' },
  { label: 'Cashier 1', username: 'cashier1', password: 'PalmCashier123!', icon: '▣' },
  { label: 'Inventory Manager', username: 'stockmanager', password: 'PalmStock123!', icon: '▤' },
]

const rupees = (value = 0) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('azra_token') || '')
  const [user, setUser] = useState<User | null>(null)
  const [dashboard, setDashboard] = useState<Dashboard>({})
  const [username, setUsername] = useState('owner')
  const [password, setPassword] = useState('PalmOwner123!')
  const [loginError, setLoginError] = useState('')
  const [busy, setBusy] = useState(false)
  const [page, setPage] = useState('Overview')
  const [cart, setCart] = useState<Record<string, number>>({})
  const [payment, setPayment] = useState('Cash')
  const [customerName, setCustomerName] = useState('')
  const [customerOrders, setCustomerOrders] = useState<any[]>([])
  const [customerLookupBusy, setCustomerLookupBusy] = useState(false)
  const [customerSuggestions, setCustomerSuggestions] = useState<string[]>([])
  const [paymentConfirmed, setPaymentConfirmed] = useState(false)
  
  const [chatInputs, setChatInputs] = useState<Record<string, string>>({
    owner: '',
    cashier: '',
    inventory: '',
  })

  
  const [chatHistories, setChatHistories] = useState<
    Record<string, { role: string; text: string }[]>
  >({
    owner: [
      {
        role: 'happy',
        text: "Good to see you, boss! 🌱 I'm ready to help you understand Palm Bistro's performance. Ask me about revenue, estimated profit, best sellers, sales trends, or stock that needs attention.",
      },
    ],
    cashier: [
      {
        role: 'happy',
        text: "Hey there! 🌱 I'm here to make your shift easier. I can help with order totals, payment methods, today's orders, and customers' previous purchases. What do you need?",
      },
    ],
    inventory: [
      {
        role: 'happy',
        text: "Hey, stockroom hero! 🌱 Let's keep Palm Bistro prepared. Ask me about ingredient levels, low stock, deliveries, usage, or what needs restocking.",
      },
    ],
  })


  const [chatMessages, setChatMessages] = useState<{ role: string; text: string }[]>([
    { role: 'happy', text: 'Hey! I’m Happy 🌱 Ask me about Palm Bistro’s sales, popular products, or ingredient stock.' },
  ])
  const [toast, setToast] = useState('')

  async function api(path: string, options: RequestInit = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    })
    const result = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(result.detail || 'Something went wrong.')
    return result
  }

  async function refreshDashboard() {
    const data = await api('/api/dashboard')
    setDashboard(data)
  }

  async function login(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setLoginError('')
    try {
      const response = await fetch(`${API}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Unable to sign in.')
      sessionStorage.setItem('azra_token', data.token)
      setToken(data.token)
      setUser(data.user)
      setPage(data.user.role === 'cashier' ? 'New Order' : data.user.role === 'inventory' ? 'Inventory' : 'Overview')
    } catch (error) {
      setLoginError(error instanceof Error ? error.message : 'Unable to sign in.')
    } finally {
      setBusy(false)
    }
  }

  function logout() {
    void api('/api/logout', { method: 'POST' }).catch(() => {})
    sessionStorage.removeItem('azra_token')
    setToken('')
    setUser(null)
    setDashboard({})
    setCart({})
    setPage('Overview')
  }

  useEffect(() => {
    if (!token) return
    let cancelled = false
    async function load() {
      try {
        const [me, data] = await Promise.all([
          api('/api/me'),
          api('/api/dashboard'),
        ])
        if (cancelled) return
        setUser(me)
        setDashboard(data)
        if (page === 'Overview' && me.role === 'cashier') setPage('New Order')
        if (page === 'Overview' && me.role === 'inventory') setPage('Inventory')
      } catch {
        if (!cancelled) {
          sessionStorage.removeItem('azra_token')
          setToken('')
          setUser(null)
        }
      }
    }
    void load()
    return () => { cancelled = true }
  // Initial session restoration only.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  
async function completeOrder() {
  const items = Object.entries(cart)
    .filter(([, quantity]) => quantity > 0)
    .map(([menu_id, quantity]) => ({ menu_id, quantity }))

  if (!items.length) {
    setToast('Add at least one menu item.')
    return
  }
  if (!paymentConfirmed) {
    setToast('Confirm that payment was received first.')
    return
  }

  setBusy(true)
  try {
    const result = await api('/api/orders', {
      method: 'POST',
      body: JSON.stringify({
        items,
        payment_method: payment,
        payment_confirmed: true,
        customer_name: customerName.trim() || null,
      }),
    })

    setToast(
      `Order #${result.order.id} completed · ${payment} · ${
        result.order.customer_name
          ? `Customer: ${result.order.customer_name} · `
          : ''
      }Collected by ${result.order.collected_by}`
    )

    setCart({})
    setCustomerName('')
    setPaymentConfirmed(false)
    await refreshDashboard()
  } catch (error) {
    setToast(error instanceof Error ? error.message : 'Order failed.')
  } finally {
    setBusy(false)
  }
}

async function searchCustomers(value: string) {
  const query = value.trim()

  if (query.length < 2) {
    setCustomerSuggestions([])
    return
  }

  try {
    const result = await api(
      `/api/customers/search?q=${encodeURIComponent(query)}`
    )
    setCustomerSuggestions(result.customers || [])
  } catch {
    setCustomerSuggestions([])
  }
}

async function loadCustomerHistory(name: string) {
  setCustomerName(name)
  setCustomerSuggestions([])
  setCustomerLookupBusy(true)

  try {
    const result = await api('/api/customers/history', {
      method: 'POST',
      body: JSON.stringify({ customer_name: name }),
    })

    setCustomerOrders(result.orders || [])
  } catch (error) {
    setCustomerOrders([])
    setToast(
      error instanceof Error
        ? error.message
        : 'Could not load customer history.'
    )
  } finally {
    setCustomerLookupBusy(false)
  }
}

  async function receiveDelivery(item: Ingredient) {
    const raw = window.prompt(`Quantity received for ${item.name} (${item.unit}):`)
    if (raw === null) return
    const quantity = Number(raw)
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setToast('Enter a positive whole-number quantity.')
      return
    }
    try {
      await api(`/api/inventory/${item.id}/deliveries`, {
        method: 'POST',
        body: JSON.stringify({ quantity }),
      })
      await refreshDashboard()
      setToast(`${item.name} stock updated.`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'Delivery could not be recorded.')
    }
  }

  
async function askHappy(
  event: React.FormEvent,
  role: 'owner' | 'cashier' | 'inventory'
) {
  event.preventDefault()

  const message = chatInputs[role].trim()
  if (!message) return

  setChatHistories((previous) => ({
    ...previous,
    [role]: [
      ...previous[role],
      { role: 'user', text: message },
    ],
  }))

  setChatInputs((previous) => ({
    ...previous,
    [role]: '',
  }))

  try {
    const result = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    })

    setChatHistories((previous) => ({
      ...previous,
      [role]: [
        ...previous[role],
        { role: 'happy', text: result.answer },
      ],
    }))
  } catch (error) {
    setChatHistories((previous) => ({
      ...previous,
      [role]: [
        ...previous[role],
        {
          role: 'happy',
          text: error instanceof Error
            ? error.message
            : 'I couldn’t answer that just now.',
        },
      ],
    }))
  }
}


  if (!user) {
    return (
      <div className="login-page">
        <section className="login-art">
          <div className="brand"><span className="brand-mark">p.</span><span>AZRA</span></div>
          <div className="login-copy">
            <span className="eyebrow light">YOUR CAFÉ, IN HARMONY</span>
            <h1>Good coffee.<br />Better decisions.</h1>
            <p>One thoughtful place to run The Palm Bistro, from the counter to the stockroom.</p>
            <div className="coffee-orbit"><span>☕</span><i>✳</i><b>✦</b></div>
          </div>
          <div className="login-footer">THE PALM BISTRO · EST. 2026</div>
        </section>

        <section className="login-panel">
          <div className="login-form-wrap">
            <span className="eyebrow">WELCOME BACK</span>
            <h2>Sign in to AZRA</h2>
            <p className="muted">Choose your workspace and pick up where the day takes you.</p>
            <div className="demo-accounts">
              <span className="field-label">QUICK DEMO ACCESS</span>
              {demoAccounts.map((account) => (
                <button className={`account-option ${username === account.username ? 'selected' : ''}`} key={account.username}
                  onClick={() => { setUsername(account.username); setPassword(account.password); setLoginError('') }}>
                  <span className="account-icon">{account.icon}</span>
                  <span>{account.label}<small>{account.username}</small></span>
                  <span className="account-arrow">↗</span>
                </button>
              ))}
            </div>
            <form onSubmit={login} className="login-form">
              <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required /></label>
              <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
              {loginError && <p className="error-text">{loginError}</p>}
              <button className="primary-button full-button" disabled={busy}>{busy ? 'Signing in…' : 'Enter The Palm Bistro →'}</button>
            </form>
            <p className="login-note">Demo environment · Sample café data</p>
          </div>
        </section>
      </div>
    )
  }

  const owner = user.role === 'owner'
  const cashier = user.role === 'cashier'
  const inventoryManager = user.role === 'inventory'
  const menu = dashboard.menu || []
  const stockItems = dashboard.stock || []
  const metrics = dashboard.metrics
  const nav = owner
    ? [{ label: 'Overview', icon: '◫' }, { label: 'Orders', icon: '▤' }, { label: 'Inventory', icon: '▧' }]
    : cashier
      ? [{ label: 'New Order', icon: '＋' }, { label: 'Orders', icon: '▤' }]
      : [{ label: 'Inventory', icon: '▧' }, { label: 'Orders', icon: '▤' }]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">p.</span><span>AZRA</span></div>
        <div className="cafe-identity"><span className="cafe-symbol">✳</span><div><strong>The Palm Bistro</strong><small>Café management</small></div></div>
        <span className="nav-heading">WORKSPACE</span>
        <nav>{nav.map((item) => <button key={item.label} className={`nav-link ${page === item.label ? 'active' : ''}`} onClick={() => setPage(item.label)}><span>{item.icon}</span>{item.label}</button>)}</nav>
        <div className="sidebar-bottom">
          <div className="open-status"><span /> Demo café is open<small>Sample data workspace</small></div>
          <button className="profile-button" onClick={logout}><span className="avatar">{user.name.charAt(0)}</span><span className="profile-info"><strong>{user.name}</strong><small>{user.role_label}</small></span><span>↪</span></button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div><span className="eyebrow">THE PALM BISTRO</span><h1>{page === 'Overview' ? 'A little overview' : page}</h1></div>
          <div className="topbar-right"><span className="today-pill">● Demo mode</span><span className="avatar">{user.name.charAt(0)}</span></div>
        </header>

        {page === 'Overview' && owner && (
          <div className="page-content">
            <section className="welcome-banner">
              <div><span className="eyebrow light">YOUR DAILY BRIEFING</span><h2>Good morning, {user.name.split(' ')[0]}.</h2><p>Here's how your café is doing. Let's make today a good one.</p></div>
              <div className="banner-illustration">☕<span>✦</span><i>✳</i></div>
            </section>
            <section className="metric-grid">
              <Metric label="Recorded revenue" value={rupees(metrics?.revenue)} note="Completed orders" icon="↗" />
              <Metric label="Estimated profit" value={rupees(metrics?.estimated_profit)} note="After tracked ingredients" icon="◈" />
              <Metric label="Completed orders" value={String(metrics?.orders || 0)} note="Across this demo session" icon="▤" />
              <Metric label="Average order" value={rupees(metrics?.average_order)} note="Per completed order" icon="◷" />
            </section>
            <div className="content-grid">
              <section className="card sales-card">
                <div className="card-heading"><div><span className="eyebrow">PERFORMANCE</span><h3>Sales at a glance</h3></div><span className="subtle-pill">Recorded orders</span></div>
                <SalesChart data={metrics?.sales_by_day || []} />
              </section>
              <section className="card">
                <div className="card-heading"><div><span className="eyebrow">HAPPY NOTICED</span><h3>Needs attention</h3></div><span className="happy-dot">✳</span></div>
                {(dashboard.low_stock || []).length ? <div className="insight-box"><strong>Stock is running low</strong><p>{dashboard.low_stock?.map((i) => i.name).join(', ')} may need replenishment. Ask your inventory manager to review the stockroom.</p><button className="text-button" onClick={() => setPage('Inventory')}>Review inventory →</button></div> : <div className="insight-box calm"><strong>You're off to a steady start.</strong><p>As orders come in, I'll help you spot sales trends and ingredients that need attention.</p><button className="text-button" onClick={() => document.getElementById('happy-input')?.focus()}>Ask Happy →</button></div>}
                <div className="top-product"><span className="product-medallion">☕</span><div><small>TOP SELLER</small><strong>{metrics?.top_items?.[0]?.name || 'Waiting for first order'}</strong></div><span className="top-product-value">{metrics?.top_items?.[0]?.quantity || 0} sold</span></div>
              </section>
            </div>
            <OrdersTable orders={dashboard.recent_orders || []} />
            
            <HappyPanel
              messages={chatHistories.owner}
              input={chatInputs.owner}
              setInput={(value) => setChatInputs((previous) => ({ ...previous, owner: value }))}
              onSubmit={(event) => askHappy(event, 'owner')}
            />

          </div>
        )}

        {page === 'New Order' && cashier && (
          <div className="page-content cashier-layout">
            <section className="card menu-card">
              <div className="card-heading"><div><span className="eyebrow">THE MENU</span><h3>What are we serving?</h3></div><span className="subtle-pill">{menu.length} items</span></div>
              <div className="menu-grid">{menu.map((item) => <div className="menu-item" key={item.id}><div className="menu-emoji">{item.category === 'Desserts' ? '🍰' : item.category === 'Food' ? '🥪' : item.category === 'Cold Drinks' ? '🧋' : '☕'}</div><span className="menu-category">{item.category}</span><strong>{item.name}</strong><div className="menu-bottom"><b>{rupees(item.price)}</b><button className="add-button" onClick={() => setCart((old) => ({ ...old, [item.id]: (old[item.id] || 0) + 1 }))}>＋</button></div>{(cart[item.id] || 0) > 0 && <div className="quantity-controls"><button onClick={() => setCart((old) => ({ ...old, [item.id]: Math.max(0, (old[item.id] || 0) - 1) }))}>−</button><span>{cart[item.id]}</span><button onClick={() => setCart((old) => ({ ...old, [item.id]: (old[item.id] || 0) + 1 }))}>＋</button></div>}</div>)}</div>
            </section>
            <section className="card checkout-card">
              <span className="eyebrow">CURRENT ORDER</span><h3>Checkout</h3>
              
              <label className="field-label" htmlFor="customer-name">
                CUSTOMER NAME (OPTIONAL)
              </label>
              
              <input
                id="customer-name"
                className="customer-name-input"
                type="text"
                placeholder="Enter customer's full name"
                value={customerName}
                onChange={(e) => {
                  setCustomerName(e.target.value)
                  setCustomerOrders([])
                  void searchCustomers(e.target.value)
                }}
                maxLength={120}
              />

              {customerSuggestions.length > 0 && (
                <div className="customer-suggestions">
                  {customerSuggestions.map((name) => (
                    <button
                      type="button"
                      key={name}
                      className="customer-suggestion"
                      onClick={() => void loadCustomerHistory(name)}
                    >
                      {name}
                    </button>
                  ))}
                </div>
              )}


{customerName.trim() && (
  <div className="customer-history">
    <h4>Previous orders</h4>

    {customerLookupBusy ? (
      <p>Loading order history…</p>
    ) : customerOrders.length === 0 ? (
      <p className="checkout-note">
        Select a customer name above to view their previous orders.
      </p>
    ) : (
      customerOrders.map((order) => (
        <div className="customer-order-card" key={order.id}>
          <div className="customer-order-heading">
            <strong>Order #{order.id}</strong>
            <strong>{rupees(order.total)}</strong>
          </div>

          <small>
            {new Date(order.created_at).toLocaleString('en-IN', {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </small>

          <div className="customer-order-items">
            {order.items.map((item: any, index: number) => (
              <div key={`${order.id}-${item.menu_item_id}-${index}`}>
                {item.name} × {item.quantity}
              </div>
            ))}
          </div>

          <button
            type="button"
            className="secondary-button full-button"
            onClick={() => {
              const repeatedItems = order.items.reduce(
                (next: Record<string, number>, item: any) => {
                  next[item.menu_item_id] =
                    (next[item.menu_item_id] || 0) + item.quantity
                  return next
                },
                {} as Record<string, number>
              )

              setCart((current) => {
                const updated = { ...current }

                for (const [id, quantity] of Object.entries(repeatedItems)) {
                  updated[id] = (updated[id] || 0) + Number(quantity)
                }

                return updated
              })

              setPaymentConfirmed(false)
              setToast(`Order #${order.id} items added to the cart.`)
            }}
          >
            Repeat order →
          </button>
        </div>
      ))
    )}
  </div>
)}

              {Object.entries(cart).filter(([, q]) => q > 0).length === 0 ? <div className="empty-cart"><span>＋</span><p>Your order starts here.</p><small>Add something delicious from the menu.</small></div> : <div className="cart-lines">{Object.entries(cart).filter(([, q]) => q > 0).map(([id, quantity]) => { const item = menu.find((m) => m.id === id); return item ? <div className="cart-line" key={id}><div><strong>{item.name}</strong><small>{quantity} × {rupees(item.price)}</small></div><b>{rupees(quantity * item.price)}</b></div> : null })}</div>}
              <div className="checkout-total"><span>Total</span><strong>{rupees(menu.reduce((sum, item) => sum + item.price * (cart[item.id] || 0), 0))}</strong></div>
              <span className="field-label">PAYMENT METHOD</span><div className="payment-options">{['Cash', 'UPI', 'Card'].map((method) => <button key={method} className={payment === method ? 'payment-option chosen' : 'payment-option'} onClick={() => { setPayment(method); setPaymentConfirmed(false) }}><span>{method === 'Cash' ? '₹' : method === 'UPI' ? '⌁' : '▣'}</span>{method}</button>)}</div>
              <label className="confirm-payment"><input type="checkbox" checked={paymentConfirmed} onChange={(e) => setPaymentConfirmed(e.target.checked)} /><span>I've confirmed the {payment} payment was received.</span></label>
              <button className="primary-button full-button" disabled={busy || !paymentConfirmed || !Object.values(cart).some((q) => q > 0)} onClick={completeOrder}>{busy ? 'Completing…' : 'Complete order →'}</button>
              <p className="checkout-note">Completed orders update sales and ingredient stock.</p>
            </section>

            
            <HappyPanel
              messages={chatHistories.cashier}
              input={chatInputs.cashier}
              setInput={(value) => setChatInputs((previous) => ({ ...previous, cashier: value }))}
              onSubmit={(event) => askHappy(event, 'cashier')}
            />

          </div>
        )}

        {page === 'Inventory' && (owner || inventoryManager) && (
          <div className="page-content">
            <section className="welcome-banner inventory-banner"><div><span className="eyebrow light">THE STOCKROOM</span><h2>Know what you have.</h2><p>Keep your ingredients ready for the next order.</p></div><div className="banner-illustration">♧<span>✦</span></div></section>
            <section className="metric-grid inventory-metrics"><Metric label="Ingredients tracked" value={String(stockItems.length)} note="Across the stockroom" icon="▤" /><Metric label="Needs replenishing" value={String((dashboard.low_stock || []).length)} note="At or below reorder level" icon="!" /><Metric label="Recorded orders" value={String(dashboard.recent_orders?.length || 0)} note="Recent transactions" icon="↗" /></section>
            <section className="card"><div className="card-heading"><div><span className="eyebrow">INGREDIENTS</span><h3>Inventory overview</h3></div><span className="subtle-pill">Live demo stock</span></div><div className="inventory-list">{stockItems.map((item) => { const low = item.quantity <= item.reorder_level; const percentage = Math.min(100, item.quantity / (item.reorder_level * 3) * 100); return <div className="inventory-row" key={item.id}><div className="ingredient-icon">{item.id === 'beans' ? '☕' : item.id === 'milk' ? '♧' : item.id === 'bread' ? '♨' : '◇'}</div><div className="ingredient-info"><strong>{item.name}</strong><small>Reorder at {item.reorder_level.toLocaleString()} {item.unit}</small><div className="stock-track"><span className={low ? 'low' : ''} style={{ width: `${percentage}%` }} /></div></div><div className="stock-quantity"><strong>{item.quantity.toLocaleString()}</strong><small>{item.unit}</small></div><span className={low ? 'stock-badge low-badge' : 'stock-badge'}>{low ? 'Low stock' : 'In stock'}</span><button className="secondary-button" onClick={() => receiveDelivery(item)}>＋ Receive</button></div> })}</div></section>
            <OrdersTable orders={dashboard.recent_orders || []} />
                          <HappyPanel
                          messages={chatHistories.inventory}
                          input={chatInputs.inventory}
                          setInput={(value) => setChatInputs((previous) => ({ ...previous, inventory: value }))}
                          onSubmit={(event) => askHappy(event, 'inventory')}
                          />
          </div>
        )}

        {page === 'Orders' && (
          <div className="page-content"><OrdersTable orders={dashboard.recent_orders || []} /></div>
        )}

        {toast && <div className="toast" role="status"><span>{toast}</span><button onClick={() => setToast('')}>×</button></div>}
      </main>
    </div>
  )
}

function Metric({ label, value, note, icon }: { label: string; value: string; note: string; icon: string }) {
  return <section className="metric-card"><div className="metric-top"><span>{label}</span><span className="metric-icon">{icon}</span></div><strong className="metric-value">{value}</strong><small>{note}</small></section>
}

function SalesChart({ data }: { data: { date: string; revenue: number }[] }) {
  const values = data.length ? data : [{ date: 'Today', revenue: 0 }]
  const max = Math.max(1, ...values.map((d) => d.revenue))
  return <div className="chart-wrap"><div className="chart-y-labels"><span>₹{Math.round(max).toLocaleString('en-IN')}</span><span>₹{Math.round(max / 2).toLocaleString('en-IN')}</span><span>₹0</span></div><div className="bar-chart">{values.map((item, index) => <div className="bar-column" key={`${item.date}-${index}`}><div className="bar-area"><span className="bar-value">{rupees(item.revenue)}</span><div className="bar" style={{ height: `${Math.max(2, item.revenue / max * 100)}%` }} /></div><small>{item.date === 'Today' ? 'Today' : new Date(item.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}</small></div>)}</div></div>
}

function OrdersTable({ orders }: { orders: Order[] }) {
  return <section className="card orders-card"><div className="card-heading"><div><span className="eyebrow">TRANSACTION LOG</span><h3>Recent orders</h3></div><span className="subtle-pill">{orders.length} shown</span></div>{!orders.length ? <div className="empty-table">No orders yet. Completed café orders will appear here.</div> : <div className="table-scroll"><table><thead><tr><th>ORDER</th><th>ITEMS</th><th>PAYMENT</th><th>COLLECTED BY</th><th>STATUS</th><th>TOTAL</th></tr></thead><tbody>{orders.map((order) => <tr key={order.id}><td><strong>#{order.id}</strong><small>{new Date(order.created_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</small></td><td>{order.items.map((item) => `${item.name} × ${item.quantity}`).join(', ')}</td><td>{order.payment_method}</td><td>{order.collected_by}</td><td><span className="paid-badge">{order.payment_status}</span></td><td><strong>{rupees(order.total)}</strong></td></tr>)}</tbody></table></div>}</section>
}

function HappyPanel({ messages, input, setInput, onSubmit }: { messages: { role: string; text: string }[]; input: string; setInput: (value: string) => void; onSubmit: (event: React.FormEvent) => void }) {
  
const messagesContainerRef = useRef<HTMLDivElement>(null)

useEffect(() => {
  const container = messagesContainerRef.current
  if (container) {
    container.scrollTo({
      top: container.scrollHeight,
      behavior: 'smooth',
    })
  }
}, [messages])


  return (
    <section className="card happy-panel">
      <div className="card-heading">
        <div>
          <span className="eyebrow">YOUR LITTLE BUSINESS COMPANION</span>
          <h3>Talk to Happy</h3>
        </div>
        <span className="happy-dot">✳</span>
      </div>

      <div className="happy-messages" ref={messagesContainerRef}>
        {messages.map((message, index) => (
          <div key={index} className={`chat-message ${message.role}`}>
            <span className="chat-avatar">
              {message.role === 'happy' ? '✳' : 'Y'}
            </span>
            <p>{message.text}</p>
          </div>
        ))}
        
      </div>

      <form className="happy-input" onSubmit={onSubmit}>
        <input
          id="happy-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about sales, profit or stock…"
        />
        <button aria-label="Send message">↑</button>
      </form>

      <small className="checkout-note">
        Happy uses recorded demo data. His answers are not a substitute for your accounts.
      </small>
    </section>
  )
}

export default App
