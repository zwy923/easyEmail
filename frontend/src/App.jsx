import React, { useState } from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Inbox from './pages/Inbox'
import Drafts from './pages/Drafts'
import './App.css'

function App() {
  return (
    <Router>
      <div className="app">
        <NavBar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/drafts" element={<Drafts />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

function NavBar() {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  const navItems = [
    { path: '/', label: '总览' },
    { path: '/inbox', label: '收件箱' },
    { path: '/drafts', label: '草稿' }
  ]

  return (
    <nav className={`navbar ${menuOpen ? 'navbar-open' : ''}`}>
      <div className="navbar-inner">
        <div className="navbar-brand">
          <div className="brand-icon" aria-hidden="true">📨</div>
          <div className="brand-copy">
            <h1>EZmail</h1>
            <p>智能化邮件运营工作台</p>
          </div>
        </div>
        <button
          className="navbar-toggle"
          aria-label="切换导航"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <span />
          <span />
          <span />
        </button>
        <div className="navbar-links">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-link ${location.pathname === item.path ? 'active' : ''}`}
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
      {menuOpen && <div className="navbar-overlay" onClick={() => setMenuOpen(false)} />}
    </nav>
  )
}

export default App

