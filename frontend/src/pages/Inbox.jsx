import React, { useState, useEffect } from 'react'
import axiosInstance from '../api/axiosInstance'
import { format } from 'date-fns'
import './Inbox.css'

function Inbox() {
  const [emails, setEmails] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({
    status: '',
    category: '',
    sender: ''
  })
  const [selectedEmail, setSelectedEmail] = useState(null)

  useEffect(() => {
    loadEmails()
  }, [filters])

  const loadEmails = async () => {
    try {
      setLoading(true)
      const params = {}
      if (filters.status) params.status = filters.status
      if (filters.category) params.category = filters.category
      if (filters.sender) params.sender = filters.sender
      
      const data = await axiosInstance.get('/email/list', { params })
      setEmails(data.items || [])
    } catch (error) {
      console.error('加载邮件失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleMarkRead = async (emailId) => {
    try {
      await axiosInstance.post(`/email/${emailId}/mark-read`)
      loadEmails()
    } catch (error) {
      console.error('标记已读失败:', error)
    }
  }

  const handleClassify = async (emailId) => {
    try {
      await axiosInstance.post('/email/classify', {
        email_id: emailId,
        force: true
      })
      alert('分类任务已提交')
      setTimeout(loadEmails, 2000)
    } catch (error) {
      console.error('分类失败:', error)
    }
  }

  const handleGenerateDraft = async (emailId) => {
    try {
      await axiosInstance.post('/email/draft', {
        email_id: emailId,
        tone: 'professional',
        length: 'medium'
      })
      alert('草稿生成任务已提交')
    } catch (error) {
      console.error('生成草稿失败:', error)
    }
  }

  const getCategoryBadgeClass = (category) => {
    if (!category) return 'badge-normal'
    return `badge-${category}`
  }

  if (loading) {
    return <div className="loading">加载中...</div>
  }

  return (
    <div className="inbox">
      <div className="inbox-header">
        <h1>收件箱</h1>
        <button className="button" onClick={loadEmails}>刷新</button>
      </div>

      <div className="card">
        <h2>筛选</h2>
        <div className="filters">
          <select
            className="select"
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="">全部状态</option>
            <option value="unread">未读</option>
            <option value="read">已读</option>
            <option value="archived">已归档</option>
          </select>
          
          <select
            className="select"
            value={filters.category}
            onChange={(e) => setFilters({ ...filters, category: e.target.value })}
          >
            <option value="">全部类别</option>
            <option value="urgent">紧急</option>
            <option value="important">重要</option>
            <option value="normal">普通</option>
            <option value="spam">垃圾</option>
            <option value="promotion">促销</option>
          </select>
          
          <input
            className="input"
            type="text"
            placeholder="搜索发件人..."
            value={filters.sender}
            onChange={(e) => setFilters({ ...filters, sender: e.target.value })}
          />
        </div>
      </div>

      <div className="card">
        <h2>邮件列表</h2>
        {emails.length === 0 ? (
          <p>暂无邮件</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>发件人</th>
                <th>主题</th>
                <th>类别</th>
                <th>时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {emails.map((email) => (
                <tr
                  key={email.id}
                  className={email.status === 'unread' ? 'row-unread' : ''}
                  onClick={() => setSelectedEmail(email)}
                  style={{ cursor: 'pointer' }}
                >
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
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="action-buttons">
                      {email.status === 'unread' && (
                        <button
                          className="button button-success"
                          onClick={() => handleMarkRead(email.id)}
                        >
                          标记已读
                        </button>
                      )}
                      <button
                        className="button"
                        onClick={() => handleClassify(email.id)}
                      >
                        分类
                      </button>
                      <button
                        className="button"
                        onClick={() => handleGenerateDraft(email.id)}
                      >
                        生成草稿
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedEmail && (
        <div className="modal" onClick={() => setSelectedEmail(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{selectedEmail.subject || '(无主题)'}</h2>
              <button className="button" onClick={() => setSelectedEmail(null)}>关闭</button>
            </div>
            <div className="modal-body">
              <p><strong>发件人:</strong> {selectedEmail.sender} ({selectedEmail.sender_email})</p>
              <p><strong>时间:</strong> {format(new Date(selectedEmail.received_at), 'yyyy-MM-dd HH:mm:ss')}</p>
              {selectedEmail.category && (
                <p>
                  <strong>类别:</strong>{' '}
                  <span className={`badge ${getCategoryBadgeClass(selectedEmail.category)}`}>
                    {selectedEmail.category}
                  </span>
                </p>
              )}
              <div className="email-body">
                <h3>正文:</h3>
                <div dangerouslySetInnerHTML={{ __html: selectedEmail.body_html || selectedEmail.body_text }} />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Inbox

