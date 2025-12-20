/**
 * API client for Backtest Control Plane API
 * 
 * This module provides functions to interact with the backend API.
 * All functions return Promises that resolve to the API response data.
 */

const API_BASE_URL = '/api'

async function request(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  }

  if (config.body && typeof config.body === 'object') {
    config.body = JSON.stringify(config.body)
  }

  const response = await fetch(url, config)
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

// Experiments API
export const experimentsAPI = {
  list: () => request('/experiments'),
  get: (name, version) => request(`/experiments/${encodeURIComponent(name)}/${encodeURIComponent(version)}`),
  create: (data) => request('/experiments', {
    method: 'POST',
    body: data,
  }),
}

// Runs API
export const runsAPI = {
  list: () => request('/runs'),
  getMetrics: (runId) => request(`/runs/${encodeURIComponent(runId)}/metrics`),
  getArtifacts: (runId) => request(`/runs/${encodeURIComponent(runId)}/artifacts`),
  create: (data) => request('/runs', {
    method: 'POST',
    body: data,
  }),
}

// Health check
export const healthCheck = () => request('/health')

