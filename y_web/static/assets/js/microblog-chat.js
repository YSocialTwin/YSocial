;(function () {
  const panel = document.getElementById('microblog-chat-panel')
  if (!panel) return

  const expId = panel.dataset.expId || window.EXP_ID
  if (!expId) return

  const card = document.getElementById('microblog-chat-card')
  const collapseHandle = document.getElementById('microblog-chat-collapse-handle')
  const collapseBadge = document.getElementById('microblog-chat-collapse-badge')
  const collapseBtn = document.getElementById('microblog-chat-collapse')
  const refreshBtn = document.getElementById('microblog-chat-refresh')
  const searchInput = document.getElementById('microblog-chat-search')
  const listEl = document.getElementById('microblog-chat-list')
  const browserEl = document.getElementById('microblog-chat-browser')
  const threadEl = document.getElementById('microblog-chat-thread')
  const backBtn = document.getElementById('microblog-chat-back')
  const messagesEl = document.getElementById('microblog-chat-messages')
  const composeForm = document.getElementById('microblog-chat-compose')
  const inputEl = document.getElementById('microblog-chat-input')
  const sendBtn = document.getElementById('microblog-chat-send')
  const targetAvatarEl = document.getElementById('microblog-chat-target-avatar')
  const targetNameEl = document.getElementById('microblog-chat-target-name')
  const targetSubtitleEl = document.getElementById('microblog-chat-target-subtitle')

  if (!card || !collapseHandle || !listEl || !browserEl || !threadEl || !composeForm) return

  const state = {
    collapsed: false,
    agents: [],
    sessions: [],
    currentSession: null
  }

  const storageKey = `ysocial:microblog-chat:${expId}:collapsed`
  const readStateKey = `ysocial:microblog-chat:${expId}:read-state`

  function apiGet (url) {
    return fetch(url, { credentials: 'same-origin' }).then(async (res) => {
      const payload = await res.json().catch(() => ({}))
      if (!res.ok || payload.success === false) {
        throw new Error(payload.error || 'Request failed')
      }
      return payload.data
    })
  }

  function apiPost (url, body) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }).then(async (res) => {
      const payload = await res.json().catch(() => ({}))
      if (!res.ok || payload.success === false) {
        throw new Error(payload.error || 'Request failed')
      }
      return payload.data
    })
  }

  function initials (name) {
    return String(name || '?')
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map(part => part[0].toUpperCase())
      .join('') || '?'
  }

  function escapeHtml (value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function formatMessageHtml (value) {
    return escapeHtml(String(value || '').replace(/^\s+/, '')).replace(/\n/g, '<br>')
  }

  function avatarMarkup (name, profilePic) {
    if (profilePic) {
      return `<div class="microblog-chat-avatar-image" style="background-image:url('${profilePic.replace(/'/g, '%27')}')"></div>`
    }
    return `<div class="microblog-chat-avatar-fallback">${escapeHtml(initials(name))}</div>`
  }

  function getAgentProfilePic (agent) {
    return String(
      agent?.profile_pic ||
      agent?.profile_picture_url ||
      agent?.avatar ||
      ''
    ).trim()
  }

  function getSessionProfilePic (session) {
    return String(
      session?.target_profile_pic ||
      session?.target_profile_picture_url ||
      session?.profile_pic ||
      session?.profile_picture_url ||
      ''
    ).trim()
  }

  function loadReadState () {
    try {
      const raw = localStorage.getItem(readStateKey)
      const parsed = raw ? JSON.parse(raw) : {}
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch (err) {
      return {}
    }
  }

  function saveReadState (value) {
    try {
      localStorage.setItem(readStateKey, JSON.stringify(value || {}))
    } catch (err) {}
  }

  function markSessionRead (session) {
    if (!session || !session.id) return
    const readState = loadReadState()
    readState[String(session.id)] = String(session.last_message_at || '')
    saveReadState(readState)
  }

  function isSessionUnread (session) {
    if (!session || !session.id || !session.last_message_at) return false
    const readState = loadReadState()
    return String(readState[String(session.id)] || '') !== String(session.last_message_at || '')
  }

  function getUnreadSessionCount () {
    if (!Array.isArray(state.sessions)) return 0
    return state.sessions.filter(isSessionUnread).length
  }

  function renderCollapsedBadge () {
    if (!collapseBadge) return
    const count = getUnreadSessionCount()
    if (count > 0) {
      collapseBadge.textContent = count > 99 ? '99+' : String(count)
      collapseBadge.classList.remove('is-hidden')
    } else {
      collapseBadge.textContent = ''
      collapseBadge.classList.add('is-hidden')
    }
  }

  function setCollapsed (collapsed) {
    state.collapsed = !!collapsed
    panel.classList.toggle('is-collapsed', state.collapsed)
    collapseHandle.setAttribute('aria-expanded', String(!state.collapsed))
    try {
      localStorage.setItem(storageKey, state.collapsed ? '1' : '0')
    } catch (err) {}
    if (window.feather && typeof window.feather.replace === 'function') {
      window.feather.replace()
    }
  }

  function renderList () {
    const query = String(searchInput.value || '').trim().toLowerCase()
    const sessionsByTarget = new Map(state.sessions.map(session => [String(session.target_user_id), session]))

    const items = state.agents
      .filter(agent => !query || String(agent.username || '').toLowerCase().includes(query))
      .sort((a, b) => {
        const aTime = sessionsByTarget.get(String(a.user_id))?.last_message_at || ''
        const bTime = sessionsByTarget.get(String(b.user_id))?.last_message_at || ''
        return String(bTime).localeCompare(String(aTime))
      })

    if (!items.length) {
      listEl.innerHTML = '<div class="microblog-chat-empty">No followed agents available for chat.</div>'
      renderCollapsedBadge()
      return
    }

    listEl.innerHTML = items.map(agent => {
      const session = sessionsByTarget.get(String(agent.user_id))
      const preview = session?.last_message_preview || agent.preview || agent.profession || 'Start a conversation'
      const stamp = session?.last_message_at ? new Date(session.last_message_at).toLocaleDateString() : ''
      return `
        <button class="microblog-chat-list-item" type="button" data-agent-id="${agent.user_id}">
          <div class="microblog-chat-list-avatar">${avatarMarkup(agent.username, getAgentProfilePic(agent))}</div>
          <div class="microblog-chat-list-copy">
            <div class="microblog-chat-list-head">
              <span class="microblog-chat-list-name">${escapeHtml(agent.username)}</span>
              ${stamp ? `<span class="microblog-chat-list-date">${escapeHtml(stamp)}</span>` : ''}
            </div>
            <div class="microblog-chat-list-preview">${escapeHtml(preview)}</div>
          </div>
        </button>
      `
    }).join('')

    listEl.querySelectorAll('.microblog-chat-list-item').forEach(btn => {
      btn.addEventListener('click', () => openSession(String(btn.dataset.agentId || '').trim()))
    })

    if (window.feather && typeof window.feather.replace === 'function') {
      window.feather.replace()
    }
    renderCollapsedBadge()
  }

  function renderMessages () {
    const messages = state.currentSession?.messages || []
    if (!messages.length) {
      messagesEl.innerHTML = '<div class="microblog-chat-empty microblog-chat-empty-thread">No messages yet. Start the conversation.</div>'
      return
    }
    messagesEl.innerHTML = messages.map(msg => (
      `<div class="microblog-chat-bubble-row ${msg.role === 'user' ? 'is-user' : 'is-assistant'}">` +
      `<div class="microblog-chat-bubble ${msg.role === 'user' ? 'is-user' : 'is-assistant'}">${formatMessageHtml(msg.content)}</div>` +
      '</div>'
    )).join('')
    messagesEl.scrollTop = messagesEl.scrollHeight
  }

  function setCurrentSession (session) {
    state.currentSession = session
    if (!session) {
      browserEl.classList.remove('is-hidden')
      threadEl.classList.add('is-hidden')
      return
    }

    browserEl.classList.add('is-hidden')
    threadEl.classList.remove('is-hidden')
    targetAvatarEl.innerHTML = avatarMarkup(session.target_username, getSessionProfilePic(session))
    targetNameEl.textContent = session.target_username
    targetSubtitleEl.textContent = 'Private message'
    markSessionRead(session)
    renderMessages()
    renderCollapsedBadge()
    if (window.feather && typeof window.feather.replace === 'function') {
      window.feather.replace()
    }
  }

  async function loadBootstrap () {
    try {
      const data = await apiGet(`/api/social/${expId}/chat/bootstrap`)
      state.agents = Array.isArray(data.agents) ? data.agents : []
      state.sessions = Array.isArray(data.sessions) ? data.sessions : []
      try {
        const readState = loadReadState()
        let changed = false
        state.sessions.forEach(session => {
          if (!session || !session.id) return
          const key = String(session.id)
          if (readState[key] == null) {
            readState[key] = String(session.last_message_at || '')
            changed = true
          }
        })
        if (changed) saveReadState(readState)
      } catch (err) {}
      renderList()
    } catch (err) {
      listEl.innerHTML = `<div class="microblog-chat-empty">${err.message}</div>`
      renderCollapsedBadge()
    }
  }

  async function openSession (agentId) {
    try {
      const session = await apiPost(`/api/social/${expId}/chat/session`, { agent_user_id: agentId })
      const idx = state.sessions.findIndex(item => String(item.id) === String(session.id))
      if (idx >= 0) state.sessions[idx] = session
      else state.sessions.unshift(session)
      setCurrentSession(session)
      renderList()
    } catch (err) {
      window.alert(err.message)
    }
  }

  async function sendMessage () {
    const content = String(inputEl.value || '').trim()
    if (!content || !state.currentSession || sendBtn.disabled) return

    sendBtn.disabled = true
    inputEl.disabled = true

    try {
      const data = await apiPost(`/api/social/${expId}/chat/session/${state.currentSession.id}/message`, { content })
      const nextSession = Object.assign({}, state.currentSession, data.session)
      nextSession.messages = [...(state.currentSession.messages || []), data.user_message, data.assistant_message]
      state.currentSession = nextSession
      const idx = state.sessions.findIndex(item => String(item.id) === String(nextSession.id))
      if (idx >= 0) state.sessions[idx] = nextSession
      else state.sessions.unshift(nextSession)
      markSessionRead(nextSession)
      inputEl.value = ''
      renderMessages()
      renderList()
    } catch (err) {
      window.alert(err.message)
    } finally {
      sendBtn.disabled = false
      inputEl.disabled = false
      inputEl.focus()
    }
  }

  backBtn.addEventListener('click', () => setCurrentSession(null))
  composeForm.addEventListener('submit', (event) => {
    event.preventDefault()
    sendMessage()
  })
  searchInput.addEventListener('input', renderList)
  refreshBtn.addEventListener('click', loadBootstrap)
  collapseBtn.addEventListener('click', () => setCollapsed(true))
  collapseHandle.addEventListener('click', () => setCollapsed(!state.collapsed))

  try {
    const persisted = localStorage.getItem(storageKey)
    setCollapsed(persisted === null ? true : persisted === '1')
  } catch (err) {
    setCollapsed(true)
  }

  loadBootstrap()
})()
