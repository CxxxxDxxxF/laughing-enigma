import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { runsAPI } from '../api/client'
import { mockRuns } from '../utils/mockData'

const USE_MOCK_DATA = true // Set to false to use real API

function Runs() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadRuns()
  }, [])

  const loadRuns = async () => {
    try {
      if (USE_MOCK_DATA) {
        setRuns(mockRuns)
      } else {
        const data = await runsAPI.list()
        setRuns(data)
      }
    } catch (error) {
      console.error('Failed to load runs:', error)
      alert(`Failed to load runs: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="container">
        <div className="card">Loading...</div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">Runs</h1>
        <button className="btn btn-secondary" onClick={loadRuns}>
          Refresh
        </button>
      </div>

      <div className="card">
        {runs.length === 0 ? (
          <p>No runs yet. Run a backtest to get started.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Experiment</th>
                <th>Status</th>
                <th>Started At</th>
                <th>Completed At</th>
                <th>Error Message</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(run => (
                <tr key={run.id}>
                  <td>
                    <code>{run.id.substring(0, 8)}...</code>
                  </td>
                  <td>
                    {run.experiment_name} v{run.experiment_version}
                  </td>
                  <td>
                    <span className={`status-badge status-${run.status}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{new Date(run.started_at).toLocaleString()}</td>
                  <td>
                    {run.completed_at
                      ? new Date(run.completed_at).toLocaleString()
                      : '-'}
                  </td>
                  <td>{run.error_message || '-'}</td>
                  <td>
                    {run.status === 'success' && (
                      <Link to={`/runs/${run.id}`} className="link">
                        View Metrics
                      </Link>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default Runs

