import React, { useState, useEffect } from 'react'
import axiosInstance from '../api/axiosInstance'
import { format } from 'date-fns'
import ConnectEmail from '../components/ConnectEmail'
import './Dashboard.css'

function Dashboard() {
  const [stats, setStats] = useState({
    totalEmails: 0,
    unreadEmails: 0,
    urgentEmails: 0,
    connectedAccounts: 0
  })
  const [recentEmails, setRecentEmails] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadDashboardData()
  }, [])

  const loadDashboardData = async () => {
    try {
      setLoading(true)

      const [emailData, accountData] = await Promise.all([
        axiosInstance.get('/email/list', {
          params: { limit: 10 }
        }),
        axiosInstance.get('/email/accounts')
      ])

      // 计算统计
      const total = emailData.total || 0
      const unread = emailData.items?.filter(e => e.status === 'unread').length || 0
      const urgent = emailData.items?.filter(e => e.category === 'urgent').length || 0
      const connectedAccounts = accountData?.length || 0

      setStats({
        totalEmails: total,
        unreadEmails: unread,
        urgentEmails: urgent,
        connectedAccounts
      })

      setRecentEmails(emailData.items || [])
    } catch (error) {
      console.error('加载数据失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const getCategoryBadgeClass = (category) => {
    if (!category) return 'badge-normal'
    return `badge-${category}`
  }

  if (loading) {
    return <div className="loading">加载中...</div>
  }

  const handleEmailConnected = () => {
    loadDashboardData()
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <div>
          <h1>总览</h1>
          <p className="dashboard-subtitle">实时掌握邮件流转与自动化效率</p>
        </div>
        <div className="dashboard-meta">
          <span className="badge badge-active">数据即时同步</span>
        </div>
      </div>

      <ConnectEmail onConnected={handleEmailConnected} />

      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-card-label">总邮件数</div>
          <p className="stat-value">{stats.totalEmails}</p>
          <span className="stat-trend stat-trend-neutral">累计收件总量</span>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">未读邮件</div>
          <p className="stat-value">{stats.unreadEmails}</p>
          <span className="stat-trend stat-trend-warning">待处理提醒</span>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">紧急邮件</div>
          <p className="stat-value">{stats.urgentEmails}</p>
          <span className="stat-trend stat-trend-danger">需优先响应</span>
        </div>
        <div className="stat-card">
          <div className="stat-card-label">已连接邮箱</div>
          <p className="stat-value">{stats.connectedAccounts}</p>
          <span className="stat-trend stat-trend-success">高效统一管理</span>
        </div>
      </div>

      <div className="card table-card">
        <div className="card-header">
          <div>
            <h2>最近邮件</h2>
            <p className="card-subtitle">最新同步的 10 封邮件，帮助你快速了解动态</p>
          </div>
        </div>
        {recentEmails.length === 0 ? (
          <div className="empty-state">
            <p>暂无邮件</p>
            <span>连接邮箱或等待系统同步后，将在此展示最新邮件。</span>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>发件人</th>
                  <th>主题</th>
                  <th>类别</th>
                  <th>时间</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {recentEmails.map((email) => (
                  <tr key={email.id}>
                    <td>{email.sender || email.sender_email}</td>
                    <td>{email.subject || '(无主题)'}</td>
                    <td>
                      {email.category && (
                        <span className={`badge ${getCategoryBadgeClass(email.category)}`}>
                          {email.category}
                        </span>
                      )}
                    </td>
                    <td>{format(new Date(email.received_at), 'yyyy-MM-dd HH:mm')}</td>
                    <td>
                      <span className={email.status === 'unread' ? 'status-unread' : ''}>
                        {email.status === 'unread' ? '未读' : '已读'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default Dashboard

