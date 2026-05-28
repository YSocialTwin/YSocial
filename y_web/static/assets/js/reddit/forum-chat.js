;(function () {
  const panel = document.getElementById('forum-chat-panel')
  if (!panel || !window.redditFeedConfig) return

  const expId = panel.dataset.expId || window.redditFeedConfig.expId
  if (!expId) return

  const card = document.getElementById('forum-chat-card')
  const collapseHandle = document.getElementById('forum-chat-collapse-handle')
  const collapseBadge = document.getElementById('forum-chat-collapse-badge')
  const collapseBtn = document.getElementById('forum-chat-collapse')
  const refreshBtn = document.getElementById('forum-chat-refresh')
  const searchInput = document.getElementById('forum-chat-search')
  const listEl = document.getElementById('forum-chat-list')
  const browserEl = document.getElementById('forum-chat-browser')
  const threadEl = document.getElementById('forum-chat-thread')
  const backBtn = document.getElementById('forum-chat-back')
  const messagesEl = document.getElementById('forum-chat-messages')
  const composeForm = document.getElementById('forum-chat-compose')
  const inputEl = document.getElementById('forum-chat-input')
  const sendBtn = document.getElementById('forum-chat-send')
  const targetAvatarEl = document.getElementById('forum-chat-target-avatar')
  const targetNameEl = document.getElementById('forum-chat-target-name')
  const targetSubtitleEl = document.getElementById('forum-chat-target-subtitle')

  const state = {
    collapsed: false,
    agents: [],
    sessions: [],
    currentSession: null,
    loading: false
  }

  const storageKey = `ysocial:forum-chat:${expId}:collapsed`
  const readStateKey = `ysocial:forum-chat:${expId}:read-state`

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
      return `<div class="forum-chat-avatar-image" style="background-image:url('${profilePic.replace(/'/g, '%27')}')"></div>`
    }
    return `<div class="forum-chat-avatar-fallback">${escapeHtml(initials(name))}</div>`
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
    const sessionsByTarget = new Map(state.sessions.map(session => [Number(session.target_user_id), session]))

    const items = state.agents
      .filter(agent => !query || String(agent.username || '').toLowerCase().includes(query))
      .sort((a, b) => {
        const aTime = sessionsByTarget.get(Number(a.user_id))?.last_message_at || ''
        const bTime = sessionsByTarget.get(Number(b.user_id))?.last_message_at || ''
        return String(bTime).localeCompare(String(aTime))
      })

    if (!items.length) {
      listEl.innerHTML = '<div class="forum-chat-empty">No agents match this search.</div>'
      renderCollapsedBadge()
      return
    }

    listEl.innerHTML = items.map(agent => {
      const session = sessionsByTarget.get(Number(agent.user_id))
      const preview = session?.last_message_preview || agent.preview || agent.profession || 'Start a conversation'
      const stamp = session?.last_message_at ? new Date(session.last_message_at).toLocaleDateString() : ''
      return `
        <button class="forum-chat-list-item" type="button" data-agent-id="${agent.user_id}">
          <div class="forum-chat-list-avatar">${avatarMarkup(agent.username, agent.profile_pic)}</div>
          <div class="forum-chat-list-copy">
            <div class="forum-chat-list-head">
              <span class="forum-chat-list-name">${escapeHtml(agent.username)}</span>
              ${stamp ? `<span class="forum-chat-list-date">${escapeHtml(stamp)}</span>` : ''}
            </div>
            <div class="forum-chat-list-preview">${escapeHtml(preview)}</div>
          </div>
        </button>
      `
    }).join('')

    listEl.querySelectorAll('.forum-chat-list-item').forEach(btn => {
      btn.addEventListener('click', () => openSession(Number(btn.dataset.agentId)))
    })

    if (window.feather && typeof window.feather.replace === 'function') {
      window.feather.replace()
    }
    renderCollapsedBadge()
  }

  function renderMessages () {
    const messages = state.currentSession?.messages || []
    if (!messages.length) {
      messagesEl.innerHTML = '<div class="forum-chat-empty forum-chat-empty-thread">No messages yet. Start the conversation.</div>'
      return
    }
    messagesEl.innerHTML = messages.map(msg => (
      `<div class="forum-chat-bubble-row ${msg.role === 'user' ? 'is-user' : 'is-assistant'}">` +
      `<div class="forum-chat-bubble ${msg.role === 'user' ? 'is-user' : 'is-assistant'}">${formatMessageHtml(msg.content)}</div>` +
      `</div>`
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
    targetAvatarEl.innerHTML = avatarMarkup(session.target_username, session.target_profile_pic)
    targetNameEl.textContent = session.target_username
    targetSubtitleEl.textContent = 'Private chat'
    markSessionRead(session)
    renderMessages()
    renderCollapsedBadge()
    if (window.feather && typeof window.feather.replace === 'function') {
      window.feather.replace()
    }
  }

  async function loadBootstrap () {
    state.loading = true
    try {
      const data = await apiGet(`/api/reddit/${expId}/chat/bootstrap`)
      state.agents = Array.isArray(data.agents) ? data.agents : []
      state.sessions = Array.isArray(data.sessions) ? data.sessions : []
      renderList()
    } catch (err) {
      listEl.innerHTML = `<div class="forum-chat-empty">${err.message}</div>`
      renderCollapsedBadge()
    } finally {
      state.loading = false
    }
  }

  async function openSession (agentId) {
    try {
      const session = await apiPost(`/api/reddit/${expId}/chat/session`, { agent_user_id: agentId })
      const idx = state.sessions.findIndex(item => Number(item.id) === Number(session.id))
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
      const data = await apiPost(`/api/reddit/${expId}/chat/session/${state.currentSession.id}/message`, { content })
      const nextSession = Object.assign({}, state.currentSession, data.session)
      nextSession.messages = [...(state.currentSession.messages || []), data.user_message, data.assistant_message]
      state.currentSession = nextSession
      const idx = state.sessions.findIndex(item => Number(item.id) === Number(nextSession.id))
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
