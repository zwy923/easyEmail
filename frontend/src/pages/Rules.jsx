import React, { useState, useEffect } from 'react'
import axiosInstance from '../api/axiosInstance'
import { format } from 'date-fns'
import './Rules.css'

function Rules() {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingRule, setEditingRule] = useState(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    is_active: true,
    priority: 0,
    conditions: {
      sender: {},
      subject: {},
      body: {},
      date_range: {}
    },
    actions: {
      type: 'classify',
      category: '',
      mark_important: false,
      generate_draft: false,
      forward_to: '',
      remind_after_hours: null
    }
  })

  useEffect(() => {
    loadRules()
  }, [])

  const loadRules = async () => {
    try {
      setLoading(true)
      const data = await axiosInstance.get('/rules')
      setRules(data || [])
    } catch (error) {
      console.error('加载规则失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      if (editingRule) {
        await axiosInstance.put(`/rules/${editingRule.id}`, formData)
      } else {
        await axiosInstance.post('/rules', formData)
      }
      setShowForm(false)
      setEditingRule(null)
      resetForm()
      loadRules()
    } catch (error) {
      console.error('保存规则失败:', error)
      alert('保存失败: ' + (error.detail || '未知错误'))
    }
  }

  const handleDelete = async (ruleId) => {
    if (!window.confirm('确定要删除这条规则吗？')) {
      return
    }
    try {
      await axiosInstance.delete(`/rules/${ruleId}`)
      loadRules()
    } catch (error) {
      console.error('删除规则失败:', error)
    }
  }

  const handleToggle = async (ruleId) => {
    try {
      await axiosInstance.post(`/rules/${ruleId}/toggle`)
      loadRules()
    } catch (error) {
      console.error('切换规则状态失败:', error)
    }
  }

  const handleEdit = (rule) => {
    setEditingRule(rule)
    setFormData({
      name: rule.name,
      description: rule.description || '',
      is_active: rule.is_active,
      priority: rule.priority,
      conditions: rule.conditions || {
        sender: {},
        subject: {},
        body: {},
        date_range: {}
      },
      actions: rule.actions || {
        type: 'classify',
        category: '',
        mark_important: false,
        generate_draft: false,
        forward_to: '',
        remind_after_hours: null
      }
    })
    setShowForm(true)
  }

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      is_active: true,
      priority: 0,
      conditions: {
        sender: {},
        subject: {},
        body: {},
        date_range: {}
      },
      actions: {
        type: 'classify',
        category: '',
        mark_important: false,
        generate_draft: false,
        forward_to: '',
        remind_after_hours: null
      }
    })
  }

  if (loading) {
    return <div className="loading">加载中...</div>
  }

  return (
    <div className="rules">
      <div className="rules-header">
        <h1>规则管理</h1>
        <button className="button" onClick={() => { setShowForm(true); setEditingRule(null); resetForm() }}>
          新建规则
        </button>
      </div>

      {showForm && (
        <div className="card">
          <h2>{editingRule ? '编辑规则' : '新建规则'}</h2>
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>规则名称</label>
              <input
                className="input"
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
              />
            </div>

            <div className="form-group">
              <label>描述</label>
              <textarea
                className="input"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows="3"
              />
            </div>

            <div className="form-group">
              <label>优先级</label>
              <input
                className="input"
                type="number"
                value={formData.priority}
                onChange={(e) => setFormData({ ...formData, priority: parseInt(e.target.value) })}
              />
            </div>

            <div className="form-group">
              <label>发件人条件（包含）</label>
              <input
                className="input"
                type="text"
                placeholder="example.com"
                value={formData.conditions.sender?.contains || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  conditions: {
                    ...formData.conditions,
                    sender: { contains: e.target.value }
                  }
                })}
              />
            </div>

            <div className="form-group">
              <label>主题条件（包含）</label>
              <input
                className="input"
                type="text"
                placeholder="urgent"
                value={formData.conditions.subject?.contains || ''}
                onChange={(e) => setFormData({
                  ...formData,
                  conditions: {
                    ...formData.conditions,
                    subject: { contains: e.target.value }
                  }
                })}
              />
            </div>

            <div className="form-group">
              <label>动作类型</label>
              <select
                className="select"
                value={formData.actions.type}
                onChange={(e) => setFormData({
                  ...formData,
                  actions: { ...formData.actions, type: e.target.value }
                })}
              >
                <option value="classify">分类</option>
                <option value="draft">生成草稿</option>
                <option value="mark">标记</option>
                <option value="forward">转发</option>
                <option value="remind">提醒</option>
              </select>
            </div>

            {formData.actions.type === 'classify' && (
              <div className="form-group">
                <label>分类类别</label>
                <select
                  className="select"
                  value={formData.actions.category}
                  onChange={(e) => setFormData({
                    ...formData,
                    actions: { ...formData.actions, category: e.target.value }
                  })}
                >
                  <option value="">选择类别</option>
                  <option value="urgent">紧急</option>
                  <option value="important">重要</option>
                  <option value="normal">普通</option>
                  <option value="spam">垃圾</option>
                  <option value="promotion">促销</option>
                </select>
              </div>
            )}

            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.actions.mark_important}
                  onChange={(e) => setFormData({
                    ...formData,
                    actions: { ...formData.actions, mark_important: e.target.checked }
                  })}
                />
                标记为重要
              </label>
            </div>

            <div className="form-group">
              <label>
                <input
                  type="checkbox"
                  checked={formData.actions.generate_draft}
                  onChange={(e) => setFormData({
                    ...formData,
                    actions: { ...formData.actions, generate_draft: e.target.checked }
                  })}
                />
                生成草稿
              </label>
            </div>

            <div className="form-actions">
              <button type="submit" className="button button-success">保存</button>
              <button type="button" className="button" onClick={() => { setShowForm(false); setEditingRule(null); resetForm() }}>
                取消
              </button>
            </div>
          </form>
        </div>
      )}

      <div className="card">
        <h2>规则列表</h2>
        {rules.length === 0 ? (
          <p>暂无规则</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>名称</th>
                <th>描述</th>
                <th>优先级</th>
                <th>匹配次数</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.id}>
                  <td>{rule.name}</td>
                  <td>{rule.description || '-'}</td>
                  <td>{rule.priority}</td>
                  <td>{rule.match_count || 0}</td>
                  <td>
                    <span className={`badge ${rule.is_active ? 'badge-active' : 'badge-inactive'}`}>
                      {rule.is_active ? '启用' : '禁用'}
                    </span>
                  </td>
                  <td>
                    <div className="action-buttons">
                      <button
                        className="button"
                        onClick={() => handleToggle(rule.id)}
                      >
                        {rule.is_active ? '禁用' : '启用'}
                      </button>
                      <button
                        className="button"
                        onClick={() => handleEdit(rule)}
                      >
                        编辑
                      </button>
                      <button
                        className="button button-danger"
                        onClick={() => handleDelete(rule.id)}
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
    </div>
  )
}

export default Rules

