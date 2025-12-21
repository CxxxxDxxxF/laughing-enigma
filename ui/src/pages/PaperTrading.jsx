import React, { useState, useEffect } from 'react'
import { paperTradingAPI } from '../api/client'

function PaperTrading() {
  const [sessionId, setSessionId] = useState('')
  const [sessionConfig, setSessionConfig] = useState({
    instrument: 'AAPL',
    max_position_size: 1000,
    max_daily_loss: -10000,
    fixed_fee: 1.0,
  })
  const [showCreateSession, setShowCreateSession] = useState(false)
  
  const [positions, setPositions] = useState([])
  const [orders, setOrders] = useState([])
  const [fills, setFills] = useState([])
  const [loading, setLoading] = useState(false)
  
  const [signalForm, setSignalForm] = useState({
    instrument: 'AAPL',
    signal_type: 'buy',
    quantity: 100,
  })
  
  const [executeForm, setExecuteForm] = useState({
    orderId: '',
    price: 0,
  })

  // Load data when session changes
  useEffect(() => {
    if (sessionId) {
      loadData()
      // Poll every 2 seconds
      const interval = setInterval(loadData, 2000)
      return () => clearInterval(interval)
    }
  }, [sessionId])

  const loadData = async () => {
    if (!sessionId) return
    
    try {
      setLoading(true)
      const [positionsData, ordersData, fillsData] = await Promise.all([
        paperTradingAPI.listPositions(sessionId),
        paperTradingAPI.listOrders(sessionId),
        paperTradingAPI.listFills(sessionId),
      ])
      setPositions(positionsData)
      setOrders(ordersData)
      setFills(fillsData)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSession = async (e) => {
    e.preventDefault()
    try {
      const response = await paperTradingAPI.createSession({
        instrument: sessionConfig.instrument,
        max_position_size: sessionConfig.max_position_size || null,
        max_daily_loss: sessionConfig.max_daily_loss || null,
        fixed_fee: sessionConfig.fixed_fee || 0.0,
      })
      setSessionId(response.session_id)
      setShowCreateSession(false)
      await loadData()
    } catch (error) {
      console.error('Failed to create session:', error)
      alert(`Failed to create session: ${error.message}`)
    }
  }

  const handleSubmitSignal = async (e) => {
    e.preventDefault()
    if (!sessionId) {
      alert('Please create or select a session first')
      return
    }
    
    try {
      await paperTradingAPI.submitSignal({
        session_id: sessionId,
        instrument: signalForm.instrument,
        signal_type: signalForm.signal_type,
        quantity: parseFloat(signalForm.quantity),
      })
      await loadData()
      setSignalForm({ instrument: sessionConfig.instrument, signal_type: 'buy', quantity: 100 })
    } catch (error) {
      console.error('Failed to submit signal:', error)
      alert(`Failed to submit signal: ${error.message}`)
    }
  }

  const handleExecuteOrder = async (e) => {
    e.preventDefault()
    if (!sessionId) {
      alert('Please create or select a session first')
      return
    }
    
    if (!executeForm.orderId || !executeForm.price) {
      alert('Please select an order and enter a price')
      return
    }
    
    try {
      await paperTradingAPI.executeOrder(executeForm.orderId, {
        session_id: sessionId,
        current_price: parseFloat(executeForm.price),
      })
      await loadData()
      setExecuteForm({ orderId: '', price: 0 })
    } catch (error) {
      console.error('Failed to execute order:', error)
      alert(`Failed to execute order: ${error.message}`)
    }
  }

  const pendingOrders = orders.filter(o => o.status === 'accepted' || o.status === 'partially_filled')

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">Paper Trading</h1>
        {!sessionId && (
          <button className="btn btn-primary" onClick={() => setShowCreateSession(true)}>
            Create Session
          </button>
        )}
        {sessionId && (
          <div>
            <span style={{ marginRight: '10px' }}>Session: {sessionId.substring(0, 8)}...</span>
            <button className="btn btn-secondary" onClick={() => setSessionId('')}>
              New Session
            </button>
          </div>
        )}
      </div>

      {showCreateSession && (
        <div className="card">
          <h2>Create Paper Trading Session</h2>
          <form onSubmit={handleCreateSession}>
            <div className="form-group">
              <label className="form-label">Instrument</label>
              <input
                type="text"
                className="form-input"
                value={sessionConfig.instrument}
                onChange={(e) => setSessionConfig({ ...sessionConfig, instrument: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Max Position Size</label>
              <input
                type="number"
                className="form-input"
                value={sessionConfig.max_position_size}
                onChange={(e) => setSessionConfig({ ...sessionConfig, max_position_size: parseFloat(e.target.value) })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Max Daily Loss</label>
              <input
                type="number"
                className="form-input"
                value={sessionConfig.max_daily_loss}
                onChange={(e) => setSessionConfig({ ...sessionConfig, max_daily_loss: parseFloat(e.target.value) })}
              />
            </div>
            <div className="form-group">
              <label className="form-label">Fixed Fee</label>
              <input
                type="number"
                step="0.01"
                className="form-input"
                value={sessionConfig.fixed_fee}
                onChange={(e) => setSessionConfig({ ...sessionConfig, fixed_fee: parseFloat(e.target.value) })}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary">
              Create Session
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => setShowCreateSession(false)} style={{ marginLeft: '10px' }}>
              Cancel
            </button>
          </form>
        </div>
      )}

      {sessionId && (
        <>
          <div className="card">
            <h2>Submit Signal</h2>
            <form onSubmit={handleSubmitSignal}>
              <div className="form-group">
                <label className="form-label">Instrument</label>
                <input
                  type="text"
                  className="form-input"
                  value={signalForm.instrument}
                  onChange={(e) => setSignalForm({ ...signalForm, instrument: e.target.value })}
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Signal Type</label>
                <select
                  className="form-input"
                  value={signalForm.signal_type}
                  onChange={(e) => setSignalForm({ ...signalForm, signal_type: e.target.value })}
                  required
                >
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                  <option value="hold">Hold</option>
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Quantity</label>
                <input
                  type="number"
                  className="form-input"
                  value={signalForm.quantity}
                  onChange={(e) => setSignalForm({ ...signalForm, quantity: e.target.value })}
                  required
                />
              </div>
              <button type="submit" className="btn btn-primary">
                Submit Signal
              </button>
            </form>
          </div>

          {pendingOrders.length > 0 && (
            <div className="card">
              <h2>Execute Order</h2>
              <form onSubmit={handleExecuteOrder}>
                <div className="form-group">
                  <label className="form-label">Order</label>
                  <select
                    className="form-input"
                    value={executeForm.orderId}
                    onChange={(e) => setExecuteForm({ ...executeForm, orderId: e.target.value })}
                    required
                  >
                    <option value="">Select an order...</option>
                    {pendingOrders.map(order => (
                      <option key={order.id} value={order.id}>
                        {order.id.substring(0, 8)}... - {order.side.toUpperCase()} {order.quantity} @ {order.instrument}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">Price</label>
                  <input
                    type="number"
                    step="0.01"
                    className="form-input"
                    value={executeForm.price}
                    onChange={(e) => setExecuteForm({ ...executeForm, price: e.target.value })}
                    required
                  />
                </div>
                <button type="submit" className="btn btn-primary">
                  Execute Order
                </button>
              </form>
            </div>
          )}

          <div className="card">
            <h2>Positions</h2>
            {loading && <p>Loading...</p>}
            {!loading && positions.length === 0 && <p>No positions</p>}
            {!loading && positions.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Instrument</th>
                    <th>Quantity</th>
                    <th>Cost Basis</th>
                    <th>Realized PnL</th>
                    <th>Updated At</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map(position => (
                    <tr key={position.instrument}>
                      <td>{position.instrument}</td>
                      <td>{position.quantity.toFixed(2)}</td>
                      <td>${position.cost_basis.toFixed(2)}</td>
                      <td style={{ color: position.realized_pnl >= 0 ? 'green' : 'red' }}>
                        ${position.realized_pnl.toFixed(2)}
                      </td>
                      <td>{new Date(position.updated_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h2>Orders</h2>
            {loading && <p>Loading...</p>}
            {!loading && orders.length === 0 && <p>No orders</p>}
            {!loading && orders.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>Instrument</th>
                    <th>Side</th>
                    <th>Quantity</th>
                    <th>Status</th>
                    <th>Created At</th>
                    <th>Rejection Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map(order => (
                    <tr key={order.id}>
                      <td><code>{order.id.substring(0, 8)}...</code></td>
                      <td>{order.instrument}</td>
                      <td>{order.side.toUpperCase()}</td>
                      <td>{order.quantity}</td>
                      <td>
                        <span className={`status-badge status-${order.status}`}>
                          {order.status}
                        </span>
                      </td>
                      <td>{new Date(order.created_at).toLocaleString()}</td>
                      <td>{order.rejection_reason || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="card">
            <h2>Fills</h2>
            {loading && <p>Loading...</p>}
            {!loading && fills.length === 0 && <p>No fills</p>}
            {!loading && fills.length > 0 && (
              <table className="table">
                <thead>
                  <tr>
                    <th>Fill ID</th>
                    <th>Order ID</th>
                    <th>Instrument</th>
                    <th>Side</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Fee</th>
                    <th>Filled At</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.map(fill => (
                    <tr key={fill.id}>
                      <td><code>{fill.id.substring(0, 8)}...</code></td>
                      <td><code>{fill.order_id.substring(0, 8)}...</code></td>
                      <td>{fill.instrument}</td>
                      <td>{fill.side.toUpperCase()}</td>
                      <td>{fill.quantity.toFixed(2)}</td>
                      <td>${fill.price.toFixed(2)}</td>
                      <td>${fill.fee.toFixed(2)}</td>
                      <td>{new Date(fill.filled_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}

      {!sessionId && !showCreateSession && (
        <div className="card">
          <p>Create a paper trading session to get started.</p>
        </div>
      )}
    </div>
  )
}

export default PaperTrading

