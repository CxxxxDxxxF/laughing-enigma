import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Overview from './pages/Overview'
import Experiments from './pages/Experiments'
import Runs from './pages/Runs'
import RunDetail from './pages/RunDetail'
import './App.css'

function App() {
  return (
    <div className="app">
      <nav className="navbar">
        <div className="container">
          <div className="nav-content">
            <h1 className="nav-title">Backtest Control Plane</h1>
            <div className="nav-links">
              <Link to="/" className="nav-link">Overview</Link>
              <Link to="/experiments" className="nav-link">Experiments</Link>
              <Link to="/runs" className="nav-link">Runs</Link>
            </div>
          </div>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/experiments" element={<Experiments />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/runs/:runId" element={<RunDetail />} />
        </Routes>
      </main>
    </div>
  )
}

export default App

