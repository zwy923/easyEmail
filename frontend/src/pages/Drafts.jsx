import React, { useState, useEffect } from 'react'
import axiosInstance from '../api/axiosInstance'
import { format } from 'date-fns'
import './Drafts.css'

function Drafts() {
  const [drafts, setDrafts] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedDraft, setSelectedDraft] = useState(null)

  useEffect(() => {
    loadDrafts()
  }, [])

  const loadDrafts = async () => {
    try {
      setLoading(true)
      const data = await axiosInstance.get('/drafts')
      setDrafts(data || [])
    } catch (error) {
      console.error('加载草稿失败:', error)
      setDrafts([])
    } finally {
      setLoading(false)
    }
  }

  const handleSend = async (draftId) => {
    if (!window.confirm('确定要发送这个草稿吗？')) {
      return
    }
    try {
      await axiosInstance.post(`/drafts/${draftId}/send`)
      alert('草稿已发送')
      loadDrafts()
    } catch (error) {
      console.error('发送草稿失败:', error)
      alert('发送失败: ' + (error.detail || '未知错误'))
    }
  }

  const handleDelete = async (draftId) => {
    if (!window.confirm('确定要删除这个草稿吗？')) {
      return
    }
    try {
      await axiosInstance.delete(`/drafts/${draftId}`)
      alert('草稿已删除')
      loadDrafts()
    } catch (error) {
      console.error('删除草稿失败:', error)
      alert('删除失败: ' + (error.detail || '未知错误'))
    }
  }

  if (loading) {
    return <div className="loading">加载中...</div>
  }

  return (
    <div className="drafts">
      <div className="drafts-header">
        <h1>草稿管理</h1>
        <button className="button" onClick={loadDrafts}>刷新</button>
      </div>

      <div className="card">
        <h2>草稿列表</h2>
        {drafts.length === 0 ? (
          <p>暂无草稿</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>主题</th>
                <th>收件人</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {drafts.map((draft) => (
                <tr
                  key={draft.id}
                  onClick={() => setSelectedDraft(draft)}
                  style={{ cursor: 'pointer' }}
                >
                  <td>{draft.subject || '(无主题)'}</td>
                  <td>{draft.to || '-'}</td>
                  <td>{format(new Date(draft.created_at), 'yyyy-MM-dd HH:mm')}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="action-buttons">
                      <button
                        className="button button-success"
                        onClick={() => handleSend(draft.id)}
                      >
                        发送
                      </button>
                      <button
                        className="button"
                        onClick={() => setSelectedDraft(draft)}
                      >
                        查看
                      </button>
                      <button
                        className="button button-danger"
                        onClick={() => handleDelete(draft.id)}
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

      {selectedDraft && (
        <div className="modal" onClick={() => setSelectedDraft(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{selectedDraft.subject || '(无主题)'}</h2>
              <button className="button" onClick={() => setSelectedDraft(null)}>关闭</button>
            </div>
            <div className="modal-body">
              <p><strong>收件人:</strong> {selectedDraft.to || selectedDraft.email?.sender_email || '-'}</p>
              <p><strong>创建时间:</strong> {format(new Date(selectedDraft.created_at), 'yyyy-MM-dd HH:mm:ss')}</p>
              <div className="draft-body">
                <h3>草稿内容:</h3>
                <div dangerouslySetInnerHTML={{ __html: selectedDraft.body }} />
              </div>
              <div className="draft-actions">
                <button className="button button-success" onClick={() => handleSend(selectedDraft.id)}>
                  发送
                </button>
                <button className="button button-danger" onClick={() => handleDelete(selectedDraft.id)}>
                  删除
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Drafts

