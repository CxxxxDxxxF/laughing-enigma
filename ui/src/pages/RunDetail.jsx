import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { runsAPI } from '../api/client'
import { mockMetrics } from '../utils/mockData'

const USE_MOCK_DATA = true // Set to false to use real API

function RunDetail() {
  const { runId } = useParams()
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadMetrics()
  }, [runId])

  const loadMetrics = async () => {
    try {
      if (USE_MOCK_DATA) {
        setMetrics(mockMetrics)
      } else {
        const data = await runsAPI.getMetrics(runId)
        setMetrics(data)
      }
    } catch (err) {
      console.error('Failed to load metrics:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="container">
        <div className="card">Loading metrics...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="container">
        <div className="card">
          <h2>Error</h2>
          <p>{error}</p>
          <Link to="/runs" className="link">Back to Runs</Link>
        </div>
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className="container">
        <div className="card">No metrics found for this run.</div>
      </div>
    )
  }

  // Prepare equity curve data for chart
  const equityCurveData = metrics.equity_curve.map((value, index) => ({
    day: index,
    value: value,
  }))

  // Prepare monthly returns data for chart
  const monthlyReturnsData = metrics.monthly_returns.map((returnValue, index) => ({
    month: `Month ${index + 1}`,
    return: (returnValue * 100).toFixed(2), // Convert to percentage
  }))

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">Run Details</h1>
        <Link to="/runs" className="link">Back to Runs</Link>
      </div>

      <div className="card">
        <h2>Run Information</h2>
        <p>
          <strong>Run ID:</strong> {metrics.run_id}
        </p>
        <p>
          <strong>Computed At:</strong> {new Date(metrics.computed_at).toLocaleString()}
        </p>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Final Value</div>
          <div className="stat-value">${metrics.final_value.toLocaleString()}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Return</div>
          <div className="stat-value">{(metrics.total_return * 100).toFixed(2)}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Sharpe Ratio</div>
          <div className="stat-value">{metrics.sharpe_ratio.toFixed(2)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Volatility (Annualized)</div>
          <div className="stat-value">{(metrics.volatility * 100).toFixed(2)}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Max Drawdown</div>
          <div className="stat-value">{(metrics.max_drawdown * 100).toFixed(2)}%</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Max Drawdown Duration</div>
          <div className="stat-value">{metrics.max_drawdown_duration} days</div>
        </div>
      </div>

      <div className="card">
        <h2>Equity Curve</h2>
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={equityCurveData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="day" label={{ value: 'Day', position: 'insideBottom', offset: -5 }} />
            <YAxis label={{ value: 'Portfolio Value ($)', angle: -90, position: 'insideLeft' }} />
            <Tooltip formatter={(value) => `$${value.toLocaleString()}`} />
            <Legend />
            <Line type="monotone" dataKey="value" stroke="#007bff" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {metrics.monthly_returns.length > 0 && (
        <div className="card">
          <h2>Monthly Returns</h2>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={monthlyReturnsData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis label={{ value: 'Return (%)', angle: -90, position: 'insideLeft' }} />
              <Tooltip formatter={(value) => `${value}%`} />
              <Legend />
              <Line type="monotone" dataKey="return" stroke="#28a745" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="card">
        <h2>All Metrics</h2>
        <table className="table">
          <tbody>
            <tr>
              <td><strong>Turnover</strong></td>
              <td>{metrics.turnover.toFixed(4)}</td>
            </tr>
            <tr>
              <td><strong>Equity Curve Points</strong></td>
              <td>{metrics.equity_curve.length}</td>
            </tr>
            <tr>
              <td><strong>Monthly Returns Count</strong></td>
              <td>{metrics.monthly_returns.length}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default RunDetail

