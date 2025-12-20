import React, { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { experimentsAPI, runsAPI } from '../api/client'
import { mockExperiments, mockRuns } from '../utils/mockData'

const USE_MOCK_DATA = true // Set to false to use real API

function Overview() {
  const [experiments, setExperiments] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      if (USE_MOCK_DATA) {
        setExperiments(mockExperiments)
        setRuns(mockRuns)
      } else {
        const [experimentsData, runsData] = await Promise.all([
          experimentsAPI.list(),
          runsAPI.list(),
        ])
        setExperiments(experimentsData)
        setRuns(runsData)
      }
    } catch (error) {
      console.error('Failed to load data:', error)
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

  const successfulRuns = runs.filter(r => r.status === 'success').length
  const failedRuns = runs.filter(r => r.status === 'failed').length

  return (
    <div className="container">
      <div className="page-header">
        <h1 className="page-title">Overview</h1>
      </div>

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Experiments</div>
          <div className="stat-value">{experiments.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Total Runs</div>
          <div className="stat-value">{runs.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Successful Runs</div>
          <div className="stat-value">{successfulRuns}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Failed Runs</div>
          <div className="stat-value">{failedRuns}</div>
        </div>
      </div>

      <div className="card">
        <h2>Recent Runs</h2>
        {runs.length === 0 ? (
          <p>No runs yet. Create an experiment and run a backtest to get started.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Experiment</th>
                <th>Status</th>
                <th>Started At</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 5).map(run => (
                <tr key={run.id}>
                  <td>{run.id.substring(0, 8)}...</td>
                  <td>{run.experiment_name} v{run.experiment_version}</td>
                  <td>
                    <span className={`status-badge status-${run.status}`}>
                      {run.status}
                    </span>
                  </td>
                  <td>{new Date(run.started_at).toLocaleString()}</td>
                  <td>
                    <Link to={`/runs/${run.id}`} className="link">
                      View Details
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Experiments</h2>
        {experiments.length === 0 ? (
          <p>No experiments yet. Create one to get started.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Version</th>
                <th>Created At</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map(exp => (
                <tr key={`${exp.name}-${exp.version}`}>
                  <td>{exp.name}</td>
                  <td>{exp.version}</td>
                  <td>{new Date(exp.created_at).toLocaleString()}</td>
                  <td>{exp.description || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default Overview

