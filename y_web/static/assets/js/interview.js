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
  const personaNameEl = document.getElementById('interview-persona-name')
  const personaSubtitleEl = document.getElementById('interview-persona-subtitle')
  const avatarEl = document.getElementById('interview-avatar')
  const interestsEl = document.getElementById('interview-interests')
  const memoryCardEl = document.getElementById('interview-memory-card')
  const memoryCollapseBtn = document.getElementById('interview-memory-collapse')
  const memoryStatusEl = document.getElementById('interview-memory-status')
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
  let currentAgentRecord = null
  let availableAgents = []

  function setStatus (msg, isError) {
    if (!statusEl) return
    statusEl.textContent = msg || ''
    statusEl.style.color = isError ? '#b00020' : ''
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

  function createAvatarDataUrl (label) {
    const text = String(label || '?').trim()
    const initials = (text.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0].toUpperCase()).join('') || '?').slice(0, 2)
    let hash = 0
    for (let i = 0; i < text.length; i++) hash = ((hash << 5) - hash) + text.charCodeAt(i)
    const hue = Math.abs(hash) % 360
    const bg = `hsl(${hue} 70% 92%)`
    const fg = `hsl(${hue} 72% 34%)`
    const svg = `
      <svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
        <rect width="96" height="96" rx="48" fill="${bg}"/>
        <text x="48" y="54" text-anchor="middle" font-family="Arial, sans-serif" font-size="34" font-weight="700" fill="${fg}">${initials}</text>
      </svg>
    `.trim()
    return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
  }

  function resolvePersonaAvatarUrl (agentRecord) {
    const selected = agentRecord || {}
    const explicit = String(selected.profile_pic || '').trim()
    if (explicit) return explicit
    return createAvatarDataUrl(selected.username || '?')
  }

  function renderPersonaHeader () {
    const selected = currentAgentRecord || {}
    const username = selected.username || 'No agent selected'
    const userType = selected.user_type || 'LLM agent'
    const leaning = selected.leaning || ''
    const profession = selected.profession || ''
    const profilePic = String(selected.profile_pic || '').trim()

    if (personaNameEl) personaNameEl.textContent = username
    if (personaSubtitleEl) {
      const bits = [userType, profession, leaning].filter(Boolean)
      personaSubtitleEl.textContent = bits.length ? bits.join(' · ') : 'Interview persona'
    }
    if (avatarEl) {
      avatarEl.innerHTML = ''
      const img = document.createElement('img')
      const fallback = createAvatarDataUrl(username)
      img.src = resolvePersonaAvatarUrl(selected)
      img.onerror = function () {
        if (img.dataset.fallbackApplied === '1') return
        img.dataset.fallbackApplied = '1'
        img.src = fallback
      }
      img.alt = `${username} avatar`
      avatarEl.appendChild(img)
    }
  }

  function normalizePersonaSnapshot (raw) {
    const hiddenLabels = new Set(['interests', 'language', 'community vibe'])
    const lines = String(raw || '')
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean)

    return lines.map((line) => {
      const idx = line.indexOf(':')
      if (idx === -1) return { label: 'Detail', value: line }
      const label = line.slice(0, idx).trim()
      return {
        label,
        value: line
          .slice(idx + 1)
          .trim()
          .replace(/\boe\/co\/ex\/ag\/ne\s*=\s*/i, '')
      }
    }).filter((row) => row.value && !hiddenLabels.has(String(row.label || '').toLowerCase()))
  }

  function renderPersonaDetails (rawSnapshot) {
    if (!personaEl) return
    const rows = normalizePersonaSnapshot(rawSnapshot)
    personaEl.innerHTML = ''
    if (!rows.length) {
      const empty = document.createElement('div')
      empty.className = 'interview-interest-empty'
      empty.textContent = 'No persona details loaded yet.'
      personaEl.appendChild(empty)
      return
    }

    rows.forEach((row) => {
      const line = document.createElement('div')
      line.className = 'interview-persona-row'

      const label = document.createElement('span')
      label.className = 'interview-persona-row-label'
      label.textContent = row.label

      const value = document.createElement('span')
      value.className = 'interview-persona-row-value'
      value.textContent = row.value

      line.appendChild(label)
      line.appendChild(value)
      personaEl.appendChild(line)
    })
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
    try {
      const parent = messagesEl.parentElement
      if (parent) parent.scrollTop = parent.scrollHeight
    } catch (e) {}
  }

  function renderInterests (interests) {
    if (!interestsEl) return
    interestsEl.innerHTML = ''
    const ints = Array.isArray(interests) ? interests : []
    if (!ints.length) {
      const empty = document.createElement('div')
      empty.className = 'interview-interest-empty'
      empty.textContent = 'No elicited interests available.'
      interestsEl.appendChild(empty)
      return
    }
    ints.forEach((interest) => {
      const tag = document.createElement('span')
      tag.className = 'interview-interest-tag'
      tag.textContent = String(interest)
      interestsEl.appendChild(tag)
    })
  }

  function formatJsonValue (value) {
    if (value === null || value === undefined) {
      return { cls: 'interview-json-null', text: 'null' }
    }
    if (typeof value === 'string') {
      return { cls: 'interview-json-string', text: `"${value}"` }
    }
    if (typeof value === 'number') {
      return { cls: 'interview-json-number', text: String(value) }
    }
    if (typeof value === 'boolean') {
      return { cls: 'interview-json-boolean', text: String(value) }
    }
    return { cls: '', text: String(value) }
  }

  function appendJsonLeaf (container, key, value, depth) {
    const line = document.createElement('div')
    line.className = 'interview-json-line interview-json-entry'
    line.style.setProperty('--json-depth', String(depth || 0))

    if (key != null) {
      const keyEl = document.createElement('span')
      keyEl.className = 'interview-json-key'
      keyEl.textContent = `${key}:`
      line.appendChild(keyEl)
    }

    const formatted = formatJsonValue(value)
    const valueEl = document.createElement('span')
    if (formatted.cls) valueEl.className = formatted.cls
    valueEl.textContent = formatted.text
    line.appendChild(valueEl)
    container.appendChild(line)
  }

  function appendJsonNode (container, key, value, depth) {
    const currentDepth = depth || 0
    if (value === null || typeof value !== 'object') {
      appendJsonLeaf(container, key, value, currentDepth)
      return
    }

    const isArray = Array.isArray(value)
    const entries = isArray
      ? value.map((item, index) => [index, item])
      : Object.entries(value)

    const details = document.createElement('details')
    details.className = 'interview-json-node interview-json-entry'
    details.style.setProperty('--json-depth', String(currentDepth))
    if (currentDepth < 1) details.open = true

    const summary = document.createElement('summary')

    if (key != null) {
      const keyEl = document.createElement('span')
      keyEl.className = 'interview-json-key'
      keyEl.textContent = `${key}:`
      summary.appendChild(keyEl)
    }

    const meta = document.createElement('span')
    meta.className = 'interview-json-meta'
    meta.textContent = isArray ? `Array(${entries.length})` : `Object(${entries.length})`
    summary.appendChild(meta)
    details.appendChild(summary)

    const children = document.createElement('div')
    children.className = 'interview-json-children'

    if (!entries.length) {
      children.style.setProperty('--json-depth', String(currentDepth + 1))
      appendJsonLeaf(children, null, isArray ? '[]' : '{}', currentDepth + 1)
    } else {
      entries.forEach(([childKey, childValue]) => {
        appendJsonNode(children, String(childKey), childValue, currentDepth + 1)
      })
    }

    details.appendChild(children)
    container.appendChild(details)
  }

  function renderJsonTree (value) {
    const tree = document.createElement('div')
    tree.className = 'interview-json-tree'
    appendJsonNode(tree, null, value, 0)
    return tree
  }

  function setMemorySnapshot (snap) {
    if (!memoryEl) return
    const snapshot = (snap && typeof snap === 'object') ? snap : {}
    memoryEl.innerHTML = ''
    const loadState = String(snapshot.load_state || '').toLowerCase()
    const memoryModeUsed = String(snapshot.memory_mode_used || '').toLowerCase()

    if (memoryStatusEl) {
      const modeRequested = snapshot.memory_mode_requested || 'n/a'
      const modeUsed = snapshot.memory_mode_used || 'n/a'
      const runId = snapshot.run_id || 'none'
      const extra = snapshot.note || snapshot.fallback_reason || snapshot.error || ''
      memoryStatusEl.innerHTML = `
        <strong>Run:</strong> ${escapeHtml(String(runId))}<br>
        <strong>Requested:</strong> ${escapeHtml(String(modeRequested))}<br>
        <strong>Used:</strong> ${escapeHtml(String(modeUsed))}
        ${extra ? `<div style="margin-top:0.45rem;">${escapeHtml(String(extra))}</div>` : ''}
      `
    }

    if (loadState === 'unavailable' || memoryModeUsed === 'unavailable') {
      const unavailable = document.createElement('div')
      unavailable.className = 'interview-memory-note'
      unavailable.style.marginBottom = '0'
      unavailable.textContent = 'No live memory payload is available from the forum server for this session.'
      memoryEl.appendChild(unavailable)
      return
    }

    if (loadState === 'deferred') {
      const deferred = document.createElement('div')
      deferred.className = 'interview-memory-note'
      deferred.style.marginBottom = '0'
      deferred.textContent = 'Memory retrieval for this session has not been loaded yet.'
      memoryEl.appendChild(deferred)
      return
    }

    const sections = [
      { key: 'retrieval_meta', title: 'Retrieval Meta', note: 'Search metadata and degraded-mode indicators.', primary: true },
      { key: 'semantic_items', title: 'Semantic Items', note: 'Retrieved memory items used to ground the current answer.', primary: true },
      { key: 'community_digest', title: 'Community Digest', note: 'High-level summary of the current community situation.', primary: true },
      { key: 'relationships', title: 'Relationships', note: 'Relationship summaries and pairwise interaction context.' },
      { key: 'threads', title: 'Threads', note: 'Thread-level context linked to the agent activity.' },
      { key: 'agent_events_tail', title: 'Agent Events', note: 'Recent events directly involving the interviewed agent.' },
      { key: 'recent_events_tail', title: 'Recent Event Tail', note: 'Recent raw event tail returned for context building.' }
    ]

    const primaryGrid = document.createElement('div')
    primaryGrid.className = 'interview-memory-primary-grid'
    const secondary = document.createElement('div')
    secondary.className = 'interview-memory-secondary'

    let renderedAny = false
    sections.forEach((section, index) => {
      const value = snapshot[section.key]
      const isEmptyArray = Array.isArray(value) && value.length === 0
      const isEmptyObject = value && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length === 0
      const isEmptyString = typeof value === 'string' && !value.trim()
      if (value == null || isEmptyArray || isEmptyObject || isEmptyString) return
      renderedAny = true

      const details = document.createElement('details')
      details.className = 'interview-memory-section'
      if (index === 0) details.open = true

      const summary = document.createElement('summary')
      summary.textContent = section.title
      details.appendChild(summary)

      const body = document.createElement('div')
      body.className = 'interview-memory-section-body'

      if (section.note) {
        const note = document.createElement('div')
        note.className = 'interview-memory-note'
        note.textContent = section.note
        body.appendChild(note)
      }

      body.appendChild(renderJsonTree(value))

      details.appendChild(body)
      if (section.primary) {
        primaryGrid.appendChild(details)
      } else {
        secondary.appendChild(details)
      }
    })

    if (!renderedAny) {
      const empty = document.createElement('div')
      empty.className = 'interview-memory-empty'
      empty.textContent = 'No structured memory sections were returned for this session.'
      memoryEl.appendChild(empty)
      return
    }

    if (primaryGrid.childNodes.length) memoryEl.appendChild(primaryGrid)
    if (secondary.childNodes.length) memoryEl.appendChild(secondary)
  }

  function renderContext (data) {
    if (!data) return
    renderPersonaHeader()
    renderPersonaDetails(data.persona_snapshot || '')
    renderInterests(data.interests)
    const snap = data.memory_snapshot || data.memory_snapshot_json || {}
    setMemorySnapshot(snap)
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

  async function loadAgents () {
    setStatus('Loading agents…')
    try {
      const res = await apiGet(`/api/interview/${expId}/agents`)
      if (!res || !res.success) {
        setStatus((res && res.error) ? res.error : 'Failed to load agents', true)
        return
      }
      availableAgents = Array.isArray(res.data) ? res.data : []
      agentSelect.innerHTML = availableAgents.map((a) => {
        const label = `${a.username} (${a.user_type || 'llm'})`
        return `<option value="${a.user_id}">${escapeHtml(label)}</option>`
      }).join('')
      if (!availableAgents.length) {
        agentSelect.innerHTML = '<option value="">(no LLM agents found)</option>'
        currentAgentRecord = null
      } else {
        currentAgentRecord = availableAgents[0]
      }
      renderPersonaHeader()
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
      currentAgentRecord = availableAgents.find(a => parseInt(a.user_id, 10) === agentUserId) || currentAgentRecord
      renderPersonaHeader()
      const runId = (runIdInput && runIdInput.value ? runIdInput.value.trim() : '')
      const res = await apiPost(`/api/interview/${expId}/session`, {
        agent_user_id: agentUserId,
        run_id: runId || null,
        backend_mode: backendMode(),
        preload_memory: true
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
      setStatus(`Session ${currentSessionId} started. run_id=${data.run_id || 'none'}.`)
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
      setStatus(options.failureStatus || `Failed to refresh memory: ${e}`, true)
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
  if (memoryCollapseBtn && memoryCardEl) {
    memoryCollapseBtn.addEventListener('click', function () {
      memoryCardEl.classList.toggle('is-collapsed')
      memoryCollapseBtn.textContent = memoryCardEl.classList.contains('is-collapsed') ? 'Expand' : 'Collapse'
    })
  }
  if (agentSelect) {
    agentSelect.addEventListener('change', function () {
      currentAgentRecord = availableAgents.find(a => String(a.user_id) === String(agentSelect.value)) || null
      renderPersonaHeader()
    })
  }
  if (inputEl) {
    inputEl.addEventListener('keydown', function (e) {
      if (e && e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        sendMessage()
      }
    })
  }

  renderPersonaHeader()
  loadAgents()
})()
