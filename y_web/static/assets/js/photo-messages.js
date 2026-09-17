;(function () {
  const root = document.getElementById('photo-messages-page')
  if (!root) return

  const config = window.YS_DATA_PHOTO_MESSAGES || {}
  const expId = root.dataset.expId || config.expId
  if (!expId) return

  const searchInput = document.getElementById('photo-messages-search')
  const listEl = document.getElementById('photo-messages-list')
  const messagesEl = document.getElementById('photo-messages-messages')
  const composeForm = document.getElementById('photo-messages-compose')
  const inputEl = document.getElementById('photo-messages-input')
  const sendBtn = document.getElementById('photo-messages-send')
  const targetAvatarEl = document.getElementById('photo-messages-target-avatar')
  const targetNameEl = document.getElementById('photo-messages-target-name')
  const targetSubtitleEl = document.getElementById('photo-messages-target-subtitle')
  const newBtn = document.querySelector('[data-photo-messages-new]')

  if (!searchInput || !listEl || !messagesEl || !composeForm || !inputEl || !sendBtn || !targetAvatarEl || !targetNameEl || !targetSubtitleEl) {
    return
  }

  const state = {
    agents: [],
    sessions: [],
    currentSession: null,
    loading: false
  }

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
      return `<div class="photo-messages-avatar-image" style="background-image:url('${profilePic.replace(/'/g, '%27')}')"></div>`
    }
    return `<div class="photo-messages-avatar-fallback">${escapeHtml(initials(name))}</div>`
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
      const raw = localStorage.getItem(`ysocial:photo-messages-read-state:${expId}`)
      const parsed = raw ? JSON.parse(raw) : {}
      return parsed && typeof parsed === 'object' ? parsed : {}
    } catch (err) {
      return {}
    }
  }

  function saveReadState (value) {
    try {
      localStorage.setItem(`ysocial:photo-messages-read-state:${expId}`, JSON.stringify(value || {}))
    } catch (err) {}
  }

  function normalizeSessionTargetId (session) {
    return String(session && session.target_user_id != null ? session.target_user_id : '')
  }

  function renderList () {
    const query = String(searchInput.value || '').trim().toLowerCase()
    const sessionsByTarget = new Map(state.sessions.map(session => [normalizeSessionTargetId(session), session]))

    const items = state.agents
      .filter(agent => !query || String(agent.username || '').toLowerCase().includes(query))
      .sort((a, b) => {
        const aTime = sessionsByTarget.get(String(a.user_id))?.last_message_at || ''
        const bTime = sessionsByTarget.get(String(b.user_id))?.last_message_at || ''
        return String(bTime).localeCompare(String(aTime))
      })

    if (!items.length) {
      listEl.innerHTML = '<div class="photo-messages-empty">No conversations match your search.</div>'
      return
    }

    listEl.innerHTML = items.map(agent => {
      const session = sessionsByTarget.get(String(agent.user_id))
      const preview = session?.last_message_preview || agent.preview || agent.profession || 'Start a conversation'
      const stamp = session?.last_message_at ? new Date(session.last_message_at).toLocaleDateString() : ''
      const active = state.currentSession && String(state.currentSession.target_user_id) === String(agent.user_id)
      return `
        <button class="photo-messages-list-item ${active ? 'is-active' : ''}" type="button" data-agent-id="${escapeHtml(agent.user_id)}">
          <div class="photo-messages-avatar">${avatarMarkup(agent.username, getAgentProfilePic(agent))}</div>
          <div class="photo-messages-list-copy">
            <div class="photo-messages-list-name-row">
              <span class="photo-messages-list-name">${escapeHtml(agent.username)}</span>
              ${stamp ? `<span class="photo-messages-list-date">${escapeHtml(stamp)}</span>` : ''}
            </div>
            <div class="photo-messages-list-preview">${escapeHtml(preview)}</div>
          </div>
        </button>
      `
    }).join('')

    listEl.querySelectorAll('.photo-messages-list-item').forEach(btn => {
      btn.addEventListener('click', () => openSession(String(btn.dataset.agentId || '').trim()))
    })
  }

  function renderMessages () {
    const session = state.currentSession
    const messages = session?.messages || []
    if (!session) {
      messagesEl.innerHTML = '<div class="photo-messages-empty">Select a conversation to start chatting.</div>'
      return
    }

    if (!messages.length) {
      messagesEl.innerHTML = '<div class="photo-messages-empty">No messages yet. Start the conversation.</div>'
      return
    }

    const fmtDate = (iso) => {
      try {
        const date = new Date(iso)
        return new Intl.DateTimeFormat(undefined, {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
          hour: 'numeric',
          minute: '2-digit'
        }).format(date)
      } catch (err) {
        return String(iso || '')
      }
    }

    let lastDateKey = ''
    const chunks = []
    messages.forEach(msg => {
      const createdAt = msg.created_at || ''
      const dateKey = createdAt ? new Date(createdAt).toDateString() : ''
      if (dateKey && dateKey !== lastDateKey) {
        chunks.push(`<div class="photo-messages-date-separator">${escapeHtml(fmtDate(createdAt))}</div>`)
        lastDateKey = dateKey
      }
      chunks.push(
        `<div class="photo-messages-bubble-row ${msg.role === 'user' ? 'is-user' : 'is-assistant'}">` +
        `<div class="photo-messages-bubble ${msg.role === 'user' ? 'is-user' : 'is-assistant'}">${formatMessageHtml(msg.content)}</div>` +
        `</div>`
      )
    })

    messagesEl.innerHTML = chunks.join('')
    messagesEl.scrollTop = messagesEl.scrollHeight
  }

  function setCurrentSession (session) {
    state.currentSession = session
    if (!session) {
      targetAvatarEl.innerHTML = ''
      targetNameEl.textContent = 'Select a conversation'
      targetSubtitleEl.textContent = ''
      renderMessages()
      renderList()
      return
    }

    targetAvatarEl.innerHTML = avatarMarkup(session.target_username, getSessionProfilePic(session))
    targetNameEl.textContent = session.target_username || 'Agent'
    targetSubtitleEl.textContent = session.target_username || ''
    renderMessages()
    renderList()
  }

  async function loadBootstrap () {
    state.loading = true
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

      const initialSession = state.sessions[0]
      const initialAgent = state.agents[0]
      if (initialSession) {
        const openTarget = String(initialSession.target_user_id || '')
        if (openTarget) {
          await openSession(openTarget)
          return
        }
      } else if (initialAgent) {
        await openSession(String(initialAgent.user_id || ''))
        return
      }

      setCurrentSession(null)
    } catch (err) {
      listEl.innerHTML = `<div class="photo-messages-empty">${escapeHtml(err.message || 'Unable to load conversations.')}</div>`
      messagesEl.innerHTML = `<div class="photo-messages-empty">${escapeHtml(err.message || 'Unable to load messages.')}</div>`
    } finally {
      state.loading = false
    }
  }

  async function openSession (agentId) {
    if (!agentId) return
    try {
      const session = await apiPost(`/api/social/${expId}/chat/session`, { agent_user_id: agentId })
      const idx = state.sessions.findIndex(item => String(item.id) === String(session.id))
      if (idx >= 0) state.sessions[idx] = session
      else state.sessions.unshift(session)
      setCurrentSession(session)
      renderList()
    } catch (err) {
      window.alert(err.message || 'Unable to open conversation.')
    }
  }

  async function sendMessage () {
    const session = state.currentSession
    const content = String(inputEl.value || '').trim()
    if (!session || !content || sendBtn.disabled) return

    sendBtn.disabled = true
    inputEl.disabled = true

    try {
      const data = await apiPost(`/api/social/${expId}/chat/session/${session.id}/message`, { content })
      const nextSession = Object.assign({}, session, data.session)
      nextSession.messages = [...(session.messages || []), data.user_message, data.assistant_message]
      state.currentSession = nextSession
      const idx = state.sessions.findIndex(item => String(item.id) === String(nextSession.id))
      if (idx >= 0) state.sessions[idx] = nextSession
      else state.sessions.unshift(nextSession)
      inputEl.value = ''
      renderMessages()
      renderList()
    } catch (err) {
      window.alert(err.message || 'Unable to send message.')
    } finally {
      sendBtn.disabled = false
      inputEl.disabled = false
      inputEl.focus()
    }
  }

  searchInput.addEventListener('input', renderList)
  composeForm.addEventListener('submit', (event) => {
    event.preventDefault()
    sendMessage()
  })
  newBtn && newBtn.addEventListener('click', () => {
    inputEl.focus()
    searchInput.focus()
  })

  loadBootstrap()
})()
