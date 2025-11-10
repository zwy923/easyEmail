import React, { useState, useEffect } from 'react'
import axiosInstance from '../api/axiosInstance'
import { format } from 'date-fns'
import './Logs.css'

function Logs() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('')

  useEffect(() => {
    loadLogs()
  }, [filter])

  const loadLogs = async () => {
    try {
      setLoading(true)
      const params = {}
      if (filter) params.level = filter
      const data = await axiosInstance.get('/logs', { params })
      setLogs(data || [])
    } catch (error) {
      console.error('加载日志失败:', error)
      setLogs([])
    } finally {
      setLoading(false)
    }
  }

  const getLevelClass = (level) => {
    switch (level?.toLowerCase()) {
      case 'error':
        return 'log-error'
      case 'warning':
        return 'log-warning'
      case 'info':
        return 'log-info'
      default:
        return ''
    }
  }

  if (loading) {
    return <div className="loading">加载中...</div>
  }

  return (
    <div className="logs">
      <div className="logs-header">
        <h1>系统日志</h1>
        <div className="logs-filters">
          <select
            className="select"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="">全部级别</option>
            <option value="INFO">信息</option>
            <option value="WARNING">警告</option>
            <option value="ERROR">错误</option>
          </select>
          <button className="button" onClick={loadLogs}>刷新</button>
        </div>
      </div>

      <div className="card">
        {logs.length === 0 ? (
          <p>暂无日志（日志功能待实现）</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>时间</th>
                <th>级别</th>
                <th>模块</th>
                <th>操作</th>
                <th>消息</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id} className={getLevelClass(log.level)}>
                  <td>{format(new Date(log.created_at), 'yyyy-MM-dd HH:mm:ss')}</td>
                  <td>
                    <span className={`badge badge-${log.level?.toLowerCase()}`}>
                      {log.level}
                    </span>
                  </td>
                  <td>{log.module || '-'}</td>
                  <td>{log.action || '-'}</td>
                  <td>{log.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export default Logs

