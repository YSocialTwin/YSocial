(function () {
  function debounce(fn, delay) {
    let timeoutId = null
    return function debounced(...args) {
      window.clearTimeout(timeoutId)
      timeoutId = window.setTimeout(() => fn.apply(this, args), delay)
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function initSearch(form) {
    const input = form.querySelector('.ys-mb-header-search__input')
    const resultsRoot = form.querySelector('[data-search-results]')
    const endpoint = form.dataset.searchEndpoint
    let suggestions = []
    let activeIndex = -1

    if (!input || !resultsRoot || !endpoint) {
      return
    }

    const renderResults = () => {
      if (!suggestions.length) {
        resultsRoot.innerHTML = '<div class="ys-mb-header-search__empty">No matching profiles, hashtags, or topics.</div>'
        resultsRoot.hidden = false
        return
      }

      resultsRoot.innerHTML = suggestions
        .map((item, index) => `
          <button type="button" class="ys-mb-header-search__option${index === activeIndex ? ' is-active' : ''}" data-search-url="${escapeHtml(item.url)}" data-search-index="${index}">
            <span class="ys-mb-header-search__copy">
              <span class="ys-mb-header-search__title">${escapeHtml(item.title)}</span>
              <span class="ys-mb-header-search__meta">${escapeHtml(item.subtitle)}</span>
            </span>
            <span class="ys-mb-header-search__tag">${escapeHtml(item.type)}</span>
          </button>
        `)
        .join('')
      resultsRoot.hidden = false
    }

    const closeResults = () => {
      activeIndex = -1
      resultsRoot.hidden = true
      resultsRoot.innerHTML = ''
    }

    const navigateToSelection = (index) => {
      const selected = suggestions[index]
      if (!selected || !selected.url) {
        return
      }
      window.location.href = selected.url
    }

    const performSearch = debounce(async () => {
      const query = input.value.trim()
      if (query.length < 2) {
        suggestions = []
        closeResults()
        return
      }

      try {
        const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`, {
          credentials: 'same-origin'
        })
        if (!response.ok) {
          throw new Error(`Search request failed with ${response.status}`)
        }
        const payload = await response.json()
        suggestions = Array.isArray(payload.results) ? payload.results : []
        activeIndex = suggestions.length ? 0 : -1
        renderResults()
      } catch (error) {
        console.error('Microblog header search failed', error)
        suggestions = []
        closeResults()
      }
    }, 180)

    input.addEventListener('input', performSearch)
    input.addEventListener('focus', () => {
      if (suggestions.length) {
        renderResults()
      }
    })

    input.addEventListener('keydown', (event) => {
      if (!suggestions.length && event.key !== 'Enter') {
        return
      }

      if (event.key === 'ArrowDown') {
        event.preventDefault()
        activeIndex = (activeIndex + 1) % suggestions.length
        renderResults()
      } else if (event.key === 'ArrowUp') {
        event.preventDefault()
        activeIndex = activeIndex <= 0 ? suggestions.length - 1 : activeIndex - 1
        renderResults()
      } else if (event.key === 'Enter') {
        event.preventDefault()
        if (suggestions.length) {
          navigateToSelection(activeIndex >= 0 ? activeIndex : 0)
        }
      } else if (event.key === 'Escape') {
        closeResults()
      }
    })

    resultsRoot.addEventListener('mousedown', (event) => {
      const button = event.target.closest('[data-search-url]')
      if (!button) {
        return
      }
      event.preventDefault()
      window.location.href = button.dataset.searchUrl
    })

    form.addEventListener('submit', (event) => {
      event.preventDefault()
      if (suggestions.length) {
        navigateToSelection(activeIndex >= 0 ? activeIndex : 0)
      }
    })

    form.addEventListener('focusout', () => {
      window.setTimeout(() => {
        if (!form.contains(document.activeElement)) {
          closeResults()
        }
      }, 120)
    })
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-mb-global-search]').forEach(initSearch)
  })
})()
