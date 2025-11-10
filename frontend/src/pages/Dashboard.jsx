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
    activeRules: 0
  })
  const [recentEmails, setRecentEmails] = useState([])
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState([])

  useEffect(() => {
    loadDashboardData()
    loadAccounts()
  }, [])

  const loadAccounts = async () => {
    try {
      const data = await axiosInstance.get('/email/accounts')
      setAccounts(data || [])
    } catch (error) {
      console.error('加载账户失败:', error)
    }
  }

  const loadDashboardData = async () => {
    try {
      setLoading(true)
      
      // 获取邮件列表
      const emailData = await axiosInstance.get('/email/list', {
        params: { limit: 10 }
      })
      
      // 计算统计
      const total = emailData.total || 0
      const unread = emailData.items?.filter(e => e.status === 'unread').length || 0
      const urgent = emailData.items?.filter(e => e.category === 'urgent').length || 0
      
      // 获取规则
      const rules = await axiosInstance.get('/rules')
      const activeRules = rules.filter(r => r.is_active).length
      
      setStats({
        totalEmails: total,
        unreadEmails: unread,
        urgentEmails: urgent,
        activeRules: activeRules
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
    loadAccounts()
  }

  return (
    <div className="dashboard">
      <h1>总览</h1>
      
      <ConnectEmail onConnected={handleEmailConnected} />
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>总邮件数</h3>
          <p className="stat-value">{stats.totalEmails}</p>
        </div>
        <div className="stat-card">
          <h3>未读邮件</h3>
          <p className="stat-value">{stats.unreadEmails}</p>
        </div>
        <div className="stat-card">
          <h3>紧急邮件</h3>
          <p className="stat-value">{stats.urgentEmails}</p>
        </div>
        <div className="stat-card">
          <h3>活跃规则</h3>
          <p className="stat-value">{stats.activeRules}</p>
        </div>
      </div>

      <div className="card">
        <h2>最近邮件</h2>
        {recentEmails.length === 0 ? (
          <p>暂无邮件</p>
        ) : (
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
        )}
      </div>
    </div>
  )
}

export default Dashboard

