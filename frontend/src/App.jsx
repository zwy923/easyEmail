import React from 'react'
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Rules from './pages/Rules'
import Inbox from './pages/Inbox'
import Logs from './pages/Logs'
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
            <Route path="/rules" element={<Rules />} />
            <Route path="/inbox" element={<Inbox />} />
            <Route path="/drafts" element={<Drafts />} />
            <Route path="/logs" element={<Logs />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}

function NavBar() {
  const location = useLocation()
  
  const navItems = [
    { path: '/', label: '总览' },
    { path: '/inbox', label: '收件箱' },
    { path: '/drafts', label: '草稿' },
    { path: '/rules', label: '规则' },
    { path: '/logs', label: '日志' },
  ]
  
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <h1>AI邮件编排系统</h1>
      </div>
      <div className="navbar-links">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={location.pathname === item.path ? 'active' : ''}
          >
            {item.label}
          </Link>
        ))}
      </div>
    </nav>
  )
}

export default App

