/* interview.js
 *
 * Admin-only interview module for live experiments.
 * Uses server-side persona + memory injection via /api/interview/*.
 */

(function () {
  'use strict'

  const expId = window.INTERVIEW_EXP_ID
  const agentSelect = document.getElementById('interview-agent-select')
  if (!expId || !agentSelect) return

  const runIdInput = document.getElementById('interview-run-id')
  const startBtn = document.getElementById('interview-start-session')
  const refreshBtn = document.getElementById('interview-refresh-memory')
  const statusEl = document.getElementById('interview-status')
  const messagesEl = document.getElementById('interview-messages')
  const inputEl = document.getElementById('interview-input')
  const sendBtn = document.getElementById('interview-send')
  const personaEl = document.getElementById('interview-persona')
  const interestsEl = document.getElementById('interview-interests')
  const memoryEl = document.getElementById('interview-memory')
  const debugMode = (function () {
    try {
      const v = new URLSearchParams(window.location.search).get('debug')
      if (!v) return false
      return ['1', 'true', 'yes', 'on'].includes(String(v).toLowerCase())
    } catch (e) {
      return false
    }
  })()

  let currentSessionId = null
  let busy = false
  let refreshBusy = false

  function setStatus (msg, isError) {
    if (!statusEl) return
    statusEl.textContent = msg || ''
    statusEl.style.color = isError ? '#b00020' : ''
  }

  function setMemorySnapshot (snap) {
    if (!memoryEl) return
    try {
      memoryEl.textContent = JSON.stringify(snap || {}, null, 2)
    } catch (e) {
      memoryEl.textContent = String(snap || '')
    }
  }

  async function apiGet (path) {
    const resp = await fetch(path, { credentials: 'same-origin' })
    const text = await resp.text()
    let data = null
    try {
      data = text ? JSON.parse(text) : {}
    } catch (e) {
      const ct = resp.headers.get('content-type') || ''
      const snippet = (text || '').slice(0, 120).replace(/\s+/g, ' ').trim()
      throw new Error(`HTTP ${resp.status} non-JSON response (${ct || 'unknown content-type'}): ${snippet || 'empty body'}`)
    }
    return data
  }

  async function apiPost (path, body) {
    const resp = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    })
    const text = await resp.text()
    let data = null
    try {
      data = text ? JSON.parse(text) : {}
    } catch (e) {
      const ct = resp.headers.get('content-type') || ''
      const snippet = (text || '').slice(0, 120).replace(/\s+/g, ' ').trim()
      throw new Error(`HTTP ${resp.status} non-JSON response (${ct || 'unknown content-type'}): ${snippet || 'empty body'}`)
    }
    return data
  }

  function backendMode () {
    const radios = document.querySelectorAll('input[name="backend_mode"]')
    for (const r of radios) {
      if (r && r.checked) return r.value
    }
    return 'agent_runtime'
  }

  function escapeHtml (s) {
    return (s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
  }

  function renderMessages (messages) {
    if (!messagesEl) return
    const msgs = Array.isArray(messages) ? messages : []
    const html = msgs.map((m) => {
      const role = (m.role || 'system').toUpperCase()
      const content = escapeHtml(m.content || '')
      const cls = role === 'ADMIN' ? 'has-text-link' : (role === 'AGENT' ? 'has-text-dark' : 'has-text-grey')
      return `
        <div style="margin-bottom: 10px;">
          <div style="font-size: 12px; font-weight: 700;" class="${cls}">${role}</div>
          <div style="white-space: pre-wrap;">${content}</div>
        </div>
      `
    }).join('')
    messagesEl.innerHTML = html
    // Scroll to bottom
    try {
      const parent = messagesEl.parentElement
      if (parent) parent.scrollTop = parent.scrollHeight
    } catch (e) {}
  }

  function renderContext (data) {
    if (!data) return
    if (personaEl) personaEl.textContent = data.persona_snapshot || ''
    if (interestsEl) {
      const ints = Array.isArray(data.interests) ? data.interests : []
      interestsEl.textContent = ints.length ? ints.join(', ') : '(none)'
    }
    const snap = data.memory_snapshot || data.memory_snapshot_json || data.memory_snapshot || {}
    setMemorySnapshot(snap)
  }

  async function loadAgents () {
    setStatus('Loading agents…')
    try {
      const res = await apiGet(`/api/interview/${expId}/agents`)
      if (!res || !res.success) {
        setStatus((res && res.error) ? res.error : 'Failed to load agents', true)
        return
      }
      const agents = Array.isArray(res.data) ? res.data : []
      agentSelect.innerHTML = agents.map((a) => {
        const label = `${a.username} (${a.user_type || 'llm'})`
        return `<option value="${a.user_id}">${escapeHtml(label)}</option>`
      }).join('')
      if (!agents.length) {
        agentSelect.innerHTML = '<option value="">(no LLM agents found)</option>'
      }
      setStatus('')
    } catch (e) {
      setStatus(`Failed to load agents: ${e}`, true)
    }
  }

  async function startSession () {
    if (busy) return
    const agentUserId = parseInt(agentSelect.value, 10)
    if (!agentUserId) {
      setStatus('Pick an agent first.', true)
      return
    }
    busy = true
    setStatus('Starting session…')
    try {
      const runId = (runIdInput && runIdInput.value ? runIdInput.value.trim() : '')
      const res = await apiPost(`/api/interview/${expId}/session`, {
        agent_user_id: agentUserId,
        run_id: runId || null,
        backend_mode: backendMode(),
        preload_memory: false
      })
      if (!res || !res.success) {
        setStatus((res && res.error) ? res.error : 'Failed to start session', true)
        return
      }
      const data = res.data || {}
      currentSessionId = data.session_id
      renderContext(data)
      renderMessages(data.messages || [])

      if (inputEl) inputEl.disabled = false
      if (sendBtn) sendBtn.disabled = false
      if (refreshBtn) refreshBtn.disabled = false
      const startedMsg = `Session ${currentSessionId} started. run_id=${data.run_id || 'none'}.`
      setStatus(startedMsg)
    } catch (e) {
      setStatus(`Failed to start session: ${e}`, true)
    } finally {
      busy = false
    }
  }

  async function refreshMemory (opts) {
    const options = opts || {}
    if (!currentSessionId || refreshBusy) return
    refreshBusy = true
    if (refreshBtn) refreshBtn.disabled = true
    if (!options.silent) setStatus('Refreshing memory…')
    try {
      const res = await apiPost(`/api/interview/${expId}/session/${currentSessionId}/refresh_context`, {})
      if (!res || !res.success) {
        const msg = (res && res.error) ? res.error : 'Failed to refresh memory'
        setStatus(options.failureStatus || msg, true)
        return
      }
      const snap = (res.data || {}).memory_snapshot || {}
      setMemorySnapshot(snap)
      setStatus(options.successStatus || 'Memory refreshed.')
    } catch (e) {
      const msg = `Failed to refresh memory: ${e}`
      setStatus(options.failureStatus || msg, true)
    } finally {
      refreshBusy = false
      if (refreshBtn) refreshBtn.disabled = !currentSessionId
    }
  }

  async function sendMessage () {
    if (!currentSessionId || busy) return
    const text = (inputEl && inputEl.value ? inputEl.value.trim() : '')
    if (!text) return
    busy = true
    setStatus('Sending…')
    if (sendBtn) sendBtn.disabled = true
    try {
      const res = await apiPost(`/api/interview/${expId}/session/${currentSessionId}/message`, {
        content: text,
        auto_refresh_memory: true,
        debug: debugMode
      })
      if (!res || !res.success) {
        setStatus((res && res.error) ? res.error : 'Failed to send message', true)
        return
      }
      const data = res.data || {}
      renderMessages(data.messages || [])
      setMemorySnapshot(data.memory_snapshot || {})
      if (inputEl) inputEl.value = ''
      setStatus('')
    } catch (e) {
      setStatus(`Failed to send: ${e}`, true)
    } finally {
      busy = false
      if (sendBtn) sendBtn.disabled = false
    }
  }

  if (startBtn) startBtn.addEventListener('click', startSession)
  if (refreshBtn) refreshBtn.addEventListener('click', refreshMemory)
  if (sendBtn) sendBtn.addEventListener('click', sendMessage)
  if (inputEl) {
    inputEl.addEventListener('keydown', function (e) {
      // Ctrl+Enter to send
      if (e && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        sendMessage()
      }
    })
  }

  loadAgents()
})()
