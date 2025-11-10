import React, { useState, useEffect, useRef } from 'react'
import axiosInstance from '../api/axiosInstance'
import { format } from 'date-fns'
import ConnectEmail from '../components/ConnectEmail'
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
  const [selectedEmailIds, setSelectedEmailIds] = useState(new Set())
  const [similarEmails, setSimilarEmails] = useState([])
  const [drafts, setDrafts] = useState([])
  const [loadingSimilar, setLoadingSimilar] = useState(false)
  const [ragQuery, setRagQuery] = useState('')
  const [ragResult, setRagResult] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [taskProgress, setTaskProgress] = useState(null)
  const taskIntervalRef = useRef(null)

  const clearTaskInterval = () => {
    if (taskIntervalRef.current) {
      clearInterval(taskIntervalRef.current)
      taskIntervalRef.current = null
    }
  }

  useEffect(() => {
    loadEmails()
  }, [filters])

  const loadEmails = async (syncDeleted = false) => {
    try {
      setLoading(true)
      const params = {}
      if (filters.status) params.status = filters.status
      if (filters.category) params.category = filters.category
      if (filters.sender) params.sender = filters.sender
      // 刷新时同步检查已删除的邮件
      if (syncDeleted) {
        params.sync_deleted = true
      }
      
      const data = await axiosInstance.get('/email/list', { params })
      
      // 如果返回了任务ID，说明触发了同步任务，需要等待完成
      if (data.task_id) {
        // 开始监控进度
        startTaskProgress(data.task_id)
        // 不立即设置邮件列表，等待任务完成后再刷新
        return
      }
      
      // 正常返回邮件列表
      if (data.items) {
        setEmails(data.items || [])
      }
    } catch (error) {
      console.error('加载邮件失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const checkTaskProgress = async (taskId) => {
    try {
      const response = await axiosInstance.get(`/email/task/${taskId}`)
      setTaskProgress(response)
      
      // 如果任务完成，刷新邮件列表
      if (response.state === 'SUCCESS') {
        // 清除轮询
        clearTaskInterval()
        // 立即刷新邮件列表（不传syncDeleted，避免再次触发同步）
        await loadEmails(false)
        // 3秒后清除进度提示
        setTimeout(() => {
          setTaskProgress(null)
        }, 3000)
      } else if (response.state === 'FAILURE' || response.state === 'REVOKED') {
        // 任务失败，清除轮询
        clearTaskInterval()
        // 即使失败也刷新邮件列表
        await loadEmails(false)
        setTimeout(() => {
          setTaskProgress(null)
        }, 5000)
      }
    } catch (error) {
      console.error('获取任务进度失败:', error)
    }
  }

  const startTaskProgress = (taskId) => {
    // 清除之前的轮询
    clearTaskInterval()
    
    // 立即检查一次
    checkTaskProgress(taskId)
    
    // 每2秒轮询一次
    const interval = setInterval(() => {
      checkTaskProgress(taskId)
    }, 2000)

    taskIntervalRef.current = interval
  }

  // 组件卸载时清除轮询
  useEffect(() => {
    return () => {
      clearTaskInterval()
    }
  }, [])

  const handleMarkRead = async (emailId) => {
    try {
      await axiosInstance.post(`/email/${emailId}/mark-read`)
      loadEmails()
      // 如果当前查看的是这封邮件，更新状态
      if (selectedEmail && selectedEmail.id === emailId) {
        loadEmailDetails(emailId)
      }
    } catch (error) {
      console.error('标记已读失败:', error)
      alert('标记已读失败: ' + (error.detail || '未知错误'))
    }
  }

  const handleMarkUnread = async (emailId) => {
    try {
      await axiosInstance.post(`/email/${emailId}/mark-unread`)
      loadEmails()
      // 如果当前查看的是这封邮件，更新状态
      if (selectedEmail && selectedEmail.id === emailId) {
        loadEmailDetails(emailId)
      }
    } catch (error) {
      console.error('标记未读失败:', error)
      alert('标记未读失败: ' + (error.detail || '未知错误'))
    }
  }

  const handleClassify = async (emailId = null) => {
    try {
      // 如果提供了emailId，分类指定邮件；否则分类最新的10封未分类邮件
      const requestData = emailId ? {
        email_id: emailId,
        force: true
      } : null
      
      const response = await axiosInstance.post('/email/classify', requestData)
      
      if (emailId) {
        alert('分类任务已提交')
        setTimeout(loadEmails, 2000)
      } else {
        // 批量分类
        if (response.classified_count > 0) {
          alert(`已提交 ${response.classified_count} 封邮件的分类任务`)
          // 如果有任务ID，开始监控进度
          if (response.task_id) {
            startTaskProgress(response.task_id)
          }
          // 2秒后刷新列表
          setTimeout(loadEmails, 2000)
        } else {
          alert('没有未分类的邮件')
        }
      }
    } catch (error) {
      console.error('分类失败:', error)
      alert('分类失败: ' + (error.detail || '未知错误'))
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
      if (selectedEmail && selectedEmail.id === emailId) {
        loadEmailDetails(emailId)
      }
    } catch (error) {
      console.error('生成草稿失败:', error)
    }
  }

  const handleGenerateDraftWithContext = async (emailId, tone = 'professional') => {
    try {
      const response = await axiosInstance.post(`/email/${emailId}/draft-with-context?tone=${tone}`)
      if (response.draft) {
        alert('带上下文的草稿已生成')
        loadEmailDetails(emailId)
      }
    } catch (error) {
      console.error('生成上下文草稿失败:', error)
      alert('生成失败: ' + (error.detail || '未知错误'))
    }
  }

  const loadEmailDetails = async (emailId) => {
    try {
      // 加载邮件详情
      const emailData = await axiosInstance.get(`/email/${emailId}`)
      setSelectedEmail(emailData)
      
      // 加载相似邮件
      setLoadingSimilar(true)
      try {
        const similarData = await axiosInstance.get(`/email/${emailId}/similar?limit=5`)
        setSimilarEmails(similarData.similar_emails || [])
      } catch (error) {
        console.error('加载相似邮件失败:', error)
        setSimilarEmails([])
      } finally {
        setLoadingSimilar(false)
      }
      
      // 加载草稿（如果有草稿API）
      // const draftsData = await axiosInstance.get(`/email/${emailId}/drafts`)
      // setDrafts(draftsData || [])
    } catch (error) {
      console.error('加载邮件详情失败:', error)
    }
  }

  const handleRAGQuery = async () => {
    if (!ragQuery.trim()) return
    try {
      const response = await axiosInstance.post('/email/rag/query', {
        question: ragQuery
      })
      setRagResult(response)
    } catch (error) {
      console.error('RAG查询失败:', error)
      alert('查询失败: ' + (error.detail || '未知错误'))
    }
  }

  const handleSelectEmail = (emailId, checked) => {
    const newSelected = new Set(selectedEmailIds)
    if (checked) {
      newSelected.add(emailId)
    } else {
      newSelected.delete(emailId)
    }
    setSelectedEmailIds(newSelected)
  }

  const handleSelectAll = (checked) => {
    if (checked) {
      setSelectedEmailIds(new Set(emails.map(e => e.id)))
    } else {
      setSelectedEmailIds(new Set())
    }
  }

  const handleDeleteEmail = async (emailId) => {
    if (!window.confirm('确定要删除这封邮件吗？')) {
      return
    }
    
    try {
      setDeleting(true)
      await axiosInstance.delete(`/email/${emailId}`)
      alert('删除任务已提交，邮件将在后台删除')
      // 从列表中移除
      setEmails(emails.filter(e => e.id !== emailId))
      setSelectedEmailIds(prev => {
        const newSet = new Set(prev)
        newSet.delete(emailId)
        return newSet
      })
      // 如果删除的是当前查看的邮件，关闭详情
      if (selectedEmail && selectedEmail.id === emailId) {
        setSelectedEmail(null)
      }
    } catch (error) {
      console.error('删除邮件失败:', error)
      alert('删除失败: ' + (error.detail || '未知错误'))
    } finally {
      setDeleting(false)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedEmailIds.size === 0) {
      alert('请先选择要删除的邮件')
      return
    }
    
    if (!window.confirm(`确定要删除选中的 ${selectedEmailIds.size} 封邮件吗？`)) {
      return
    }
    
    try {
      setDeleting(true)
      const emailIds = Array.from(selectedEmailIds)
      await axiosInstance.post('/email/batch-delete', {
        email_ids: emailIds
      })
      alert(`批量删除任务已提交，共 ${emailIds.length} 封邮件将在后台删除`)
      // 从列表中移除
      setEmails(emails.filter(e => !selectedEmailIds.has(e.id)))
      setSelectedEmailIds(new Set())
      // 如果删除的邮件中包含当前查看的邮件，关闭详情
      if (selectedEmail && selectedEmailIds.has(selectedEmail.id)) {
        setSelectedEmail(null)
      }
    } catch (error) {
      console.error('批量删除失败:', error)
      alert('批量删除失败: ' + (error.detail || '未知错误'))
    } finally {
      setDeleting(false)
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
    loadEmails()
  }

  return (
    <div className="inbox">
      <div className="inbox-header">
        <h1>收件箱</h1>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="button" onClick={() => loadEmails(true)}>刷新</button>
          <button 
            className="button button-primary" 
            onClick={() => handleClassify()}
            title="AI分类最新的10封未分类邮件"
          >
            AI分类
          </button>
          <button 
            className="button" 
            onClick={async () => {
              try {
                // 获取账户ID（假设只有一个账户，或者使用第一个）
                const accounts = await axiosInstance.get('/email/accounts')
                if (accounts && accounts.length > 0) {
                  const response = await axiosInstance.post('/email/sync-status', {
                    account_id: accounts[0].id
                  })
                  if (response.task_id) {
                    startTaskProgress(response.task_id)
                    alert('同步删除状态任务已提交，请等待完成')
                  }
                } else {
                  alert('没有找到邮箱账户')
                }
              } catch (error) {
                console.error('触发同步失败:', error)
                alert('触发同步失败: ' + (error.detail || '未知错误'))
              }
            }}
          >
            同步删除状态
          </button>
        </div>
      </div>
      
      {/* 任务进度提示 */}
      {taskProgress && (
        <div className="card" style={{ marginBottom: '1rem', backgroundColor: '#f0f0f0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <strong>{taskProgress.status || '处理中...'}</strong>
            <span>{taskProgress.percent || 0}%</span>
          </div>
          {taskProgress.total > 0 && (
            <>
              <div style={{ 
                width: '100%', 
                height: '8px', 
                backgroundColor: '#ddd', 
                borderRadius: '4px',
                overflow: 'hidden',
                marginBottom: '0.5rem'
              }}>
                <div style={{
                  width: `${taskProgress.percent || 0}%`,
                  height: '100%',
                  backgroundColor: taskProgress.state === 'SUCCESS' ? '#4caf50' : '#2196f3',
                  transition: 'width 0.3s ease'
                }}></div>
              </div>
              <div style={{ fontSize: '0.9rem', color: '#666' }}>
                {taskProgress.current || 0} / {taskProgress.total || 0}
                {taskProgress.new_count !== undefined && ` | 新增: ${taskProgress.new_count}`}
                {taskProgress.skipped_count !== undefined && ` | 跳过: ${taskProgress.skipped_count}`}
                {taskProgress.error_count !== undefined && ` | 错误: ${taskProgress.error_count}`}
                {taskProgress.deleted_count !== undefined && ` | 删除: ${taskProgress.deleted_count}`}
                {taskProgress.updated_count !== undefined && ` | 更新: ${taskProgress.updated_count}`}
              </div>
            </>
          )}
        </div>
      )}

      <ConnectEmail onConnected={handleEmailConnected} />

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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>邮件列表</h2>
          {selectedEmailIds.size > 0 && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <span>已选择 {selectedEmailIds.size} 封邮件</span>
              <button 
                className="button button-danger" 
                onClick={handleBatchDelete}
                disabled={deleting}
              >
                {deleting ? '删除中...' : `批量删除 (${selectedEmailIds.size})`}
              </button>
            </div>
          )}
        </div>
        {emails.length === 0 ? (
          <p>暂无邮件</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}>
                  <input
                    type="checkbox"
                    checked={selectedEmailIds.size === emails.length && emails.length > 0}
                    onChange={(e) => handleSelectAll(e.target.checked)}
                  />
                </th>
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
                  onClick={() => loadEmailDetails(email.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <td onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedEmailIds.has(email.id)}
                      onChange={(e) => {
                        e.stopPropagation()
                        handleSelectEmail(email.id, e.target.checked)
                      }}
                    />
                  </td>
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
                      {email.status === 'unread' ? (
                        <button
                          className="button button-success"
                          onClick={() => handleMarkRead(email.id)}
                        >
                          标记已读
                        </button>
                      ) : (
                        <button
                          className="button"
                          onClick={() => handleMarkUnread(email.id)}
                        >
                          标记未读
                        </button>
                      )}
                      <button
                        className="button"
                        onClick={() => handleClassify(email.id)}
                        title="分类这封邮件"
                      >
                        分类
                      </button>
                      <button
                        className="button"
                        onClick={() => handleGenerateDraft(email.id)}
                      >
                        生成草稿
                      </button>
                      <button
                        className="button button-danger"
                        onClick={() => handleDeleteEmail(email.id)}
                        disabled={deleting}
                      >
                        删除
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
        <div className="modal" onClick={() => { setSelectedEmail(null); setSimilarEmails([]); setRagResult(null) }}>
          <div className="modal-content email-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{selectedEmail.subject || '(无主题)'}</h2>
              <button className="button" onClick={() => { setSelectedEmail(null); setSimilarEmails([]); setRagResult(null) }}>关闭</button>
            </div>
            <div className="modal-body">
              <div className="email-detail-info">
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
                <div className="email-actions">
                  <button className="button" onClick={() => handleClassify(selectedEmail.id)}>重新分类</button>
                  <button className="button" onClick={() => handleGenerateDraft(selectedEmail.id)}>生成草稿</button>
                  <button className="button" onClick={() => handleGenerateDraftWithContext(selectedEmail.id, 'professional')}>智能草稿</button>
                  {selectedEmail.status === 'unread' ? (
                    <button className="button button-success" onClick={() => handleMarkRead(selectedEmail.id)}>标记已读</button>
                  ) : (
                    <button className="button" onClick={() => handleMarkUnread(selectedEmail.id)}>标记未读</button>
                  )}
                  <button 
                    className="button button-danger" 
                    onClick={() => {
                      if (window.confirm('确定要删除这封邮件吗？')) {
                        handleDeleteEmail(selectedEmail.id)
                      }
                    }}
                    disabled={deleting}
                  >
                    {deleting ? '删除中...' : '删除'}
                  </button>
                </div>
              </div>
              
              <div className="email-body">
                <h3>正文:</h3>
                <div dangerouslySetInnerHTML={{ __html: selectedEmail.body_html || selectedEmail.body_text }} />
              </div>

              <div className="email-tabs">
                <div className="tab-section">
                  <h3>相似邮件</h3>
                  {loadingSimilar ? (
                    <p>加载中...</p>
                  ) : similarEmails.length > 0 ? (
                    <ul className="similar-emails-list">
                      {similarEmails.map((similar, idx) => (
                        <li key={idx} className="similar-email-item">
                          <strong>{similar.subject || '(无主题)'}</strong>
                          <span className="similar-sender">{similar.sender}</span>
                          <p className="similar-content">{similar.similarity_content}...</p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>暂无相似邮件</p>
                  )}
                </div>

                <div className="tab-section">
                  <h3>RAG 智能问答</h3>
                  <div className="rag-query">
                    <input
                      className="input"
                      type="text"
                      placeholder="输入问题，基于历史邮件进行智能回答..."
                      value={ragQuery}
                      onChange={(e) => setRagQuery(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && handleRAGQuery()}
                    />
                    <button className="button" onClick={handleRAGQuery}>查询</button>
                  </div>
                  {ragResult && (
                    <div className="rag-result">
                      <h4>回答:</h4>
                      <p>{ragResult.answer}</p>
                      {ragResult.source_documents && ragResult.source_documents.length > 0 && (
                        <div className="rag-sources">
                          <h5>来源邮件:</h5>
                          <ul>
                            {ragResult.source_documents.map((doc, idx) => (
                              <li key={idx}>
                                <strong>{doc.metadata?.subject || '无主题'}</strong> - {doc.metadata?.sender}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Inbox

