import React, { useState, useEffect } from 'react'
import axiosInstance from '../api/axiosInstance'
import './ConnectEmail.css'

function ConnectEmail({ onConnected }) {
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)

  useEffect(() => {
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

  const handleConnectGmail = async () => {
    try {
      setConnecting(true)
      // 获取OAuth授权URL
      const response = await axiosInstance.get('/email/auth-url/gmail')
      const { auth_url } = response
      
      // 打开新窗口进行OAuth授权
      const width = 600
      const height = 700
      const left = (window.screen.width - width) / 2
      const top = (window.screen.height - height) / 2
      
      const popup = window.open(
        auth_url,
        'Gmail授权',
        `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=yes`
      )

      // 监听来自弹出窗口的消息
      const handleMessage = (event) => {
        if (event.data && event.data.type === 'gmail_connected' && event.data.success) {
          setConnecting(false)
          // 重新加载账户列表
          loadAccounts()
          if (onConnected) onConnected()
          window.removeEventListener('message', handleMessage)
        }
      }
      window.addEventListener('message', handleMessage)

      // 备用：监听弹出窗口关闭
      const checkPopup = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkPopup)
          setConnecting(false)
          window.removeEventListener('message', handleMessage)
          // 重新加载账户列表（以防消息未收到）
          setTimeout(loadAccounts, 1000)
          if (onConnected) onConnected()
        }
      }, 500)
    } catch (error) {
      console.error('连接Gmail失败:', error)
      alert('连接失败: ' + (error.detail || '未知错误'))
      setConnecting(false)
    }
  }

  const handleDisconnect = async (accountId) => {
    if (!window.confirm('确定要断开连接吗？')) {
      return
    }
    try {
      // 注意：需要后端实现断开连接的API
      // await axiosInstance.delete(`/email/accounts/${accountId}`)
      alert('断开连接功能待实现')
      loadAccounts()
    } catch (error) {
      console.error('断开连接失败:', error)
    }
  }

  const handleRefresh = async (accountId) => {
    try {
      setLoading(true)
      // 触发获取邮件任务
      const response = await axiosInstance.post('/email/fetch', {
        account_id: accountId
      })
      alert(response.message || '邮件获取任务已提交')
    } catch (error) {
      console.error('获取邮件失败:', error)
      alert('获取失败: ' + (error.detail || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="connect-email">
      <div className="card">
        <h2>邮箱账户</h2>
        
        {accounts.length === 0 ? (
          <div className="no-accounts">
            <p>还没有连接任何邮箱账户</p>
            <button 
              className="button button-primary" 
              onClick={handleConnectGmail}
              disabled={connecting}
            >
              {connecting ? '连接中...' : '连接 Gmail'}
            </button>
          </div>
        ) : (
          <>
            <div className="accounts-list">
              {accounts.map((account) => (
                <div key={account.id} className="account-item">
                  <div className="account-info">
                    <strong>{account.email}</strong>
                    <span className={`badge ${account.is_active ? 'badge-active' : 'badge-inactive'}`}>
                      {account.is_active ? '已激活' : '未激活'}
                    </span>
                    <span className="badge badge-provider">{account.provider}</span>
                  </div>
                  <div className="account-actions">
                    <button
                      className="button"
                      onClick={() => handleRefresh(account.id)}
                      disabled={loading}
                    >
                      刷新邮件
                    </button>
                    <button
                      className="button button-danger"
                      onClick={() => handleDisconnect(account.id)}
                    >
                      断开
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <button 
              className="button button-primary" 
              onClick={handleConnectGmail}
              disabled={connecting}
            >
              {connecting ? '连接中...' : '+ 添加 Gmail 账户'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}

export default ConnectEmail

