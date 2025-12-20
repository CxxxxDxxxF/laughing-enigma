import React, { useState, useEffect } from 'react'
import { experimentsAPI } from '../api/client'
import { mockExperiments } from '../utils/mockData'

const USE_MOCK_DATA = true // Set to false to use real API

function Experiments() {
  const [experiments, setExperiments] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    name: '',
    version: '',
    config: '{}',
    description: '',
  })

  useEffect(() => {
    loadExperiments()
  }, [])

  const loadExperiments = async () => {
    try {
      if (USE_MOCK_DATA) {
        setExperiments(mockExperiments)
      } else {
        const data = await experimentsAPI.list()
        setExperiments(data)
      }
    } catch (error) {
      console.error('Failed to load experiments:', error)
      alert(`Failed to load experiments: ${error.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    
    try {
      const config = JSON.parse(formData.config)
      const experimentData = {
        name: formData.name,
        version: formData.version,
        config: config,
        description: formData.description || null,
      }

      if (USE_MOCK_DATA) {
        // Mock: just add to local state
        setExperiments([...experiments, {
          ...experimentData,
          created_at: new Date().toISOString(),
        }])
      } else {
        await experimentsAPI.create(experimentData)
        await loadExperiments()
      }

      setShowForm(false)
      setFormData({ name: '', version: '', config: '{}', description: '' })
    } catch (error) {
      console.error('Failed to create experiment:', error)
      alert(`Failed to create experiment: ${error.message}`)
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
        <h1 className="page-title">Experiments</h1>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : 'Create Experiment'}
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h2>Create New Experiment</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Name</label>
              <input
                type="text"
                className="form-input"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Version</label>
              <input
                type="text"
                className="form-input"
                value={formData.version}
                onChange={(e) => setFormData({ ...formData, version: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Config (JSON)</label>
              <textarea
                className="form-textarea"
                value={formData.config}
                onChange={(e) => setFormData({ ...formData, config: e.target.value })}
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label">Description (optional)</label>
              <input
                type="text"
                className="form-input"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>
            <button type="submit" className="btn btn-primary">
              Create
            </button>
          </form>
        </div>
      )}

      <div className="card">
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
                <th>Config</th>
              </tr>
            </thead>
            <tbody>
              {experiments.map(exp => (
                <tr key={`${exp.name}-${exp.version}`}>
                  <td>{exp.name}</td>
                  <td>{exp.version}</td>
                  <td>{new Date(exp.created_at).toLocaleString()}</td>
                  <td>{exp.description || '-'}</td>
                  <td>
                    <code>{JSON.stringify(exp.config)}</code>
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

export default Experiments

