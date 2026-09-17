(function() {
  'use strict';

  function refreshDynamicUi(container) {
    if (!container) {
      return;
    }

    container.querySelectorAll('[data-demo-src]').forEach(function(img) {
      var src = img.getAttribute('data-demo-src');
      if (src) {
        img.setAttribute('src', src);
      }
    });

    if (window.feather && typeof window.feather.replace === 'function') {
      window.feather.replace();
    }
  }

  function buildApiUrl(panel, targetUrl) {
    var baseApi = panel.getAttribute('data-friends-api');
    if (!baseApi || !targetUrl) {
      return null;
    }

    var parsed = new URL(targetUrl, window.location.origin);
    var pageMatch = parsed.pathname.match(/\/friends\/.+\/(\d+)$/);
    var page = pageMatch ? pageMatch[1] : '1';
    var tab = parsed.searchParams.get('tab') || 'followers';
    return baseApi + '/' + page + '?tab=' + encodeURIComponent(tab);
  }

  function setLoading(panel, isLoading) {
    panel.classList.toggle('is-loading', isLoading);
    panel.querySelectorAll('[data-friends-url]').forEach(function(link) {
      link.classList.toggle('is-disabled', isLoading);
      if (isLoading) {
        link.setAttribute('aria-busy', 'true');
      } else {
        link.removeAttribute('aria-busy');
      }
    });
  }

  function bindFriendsNavigation(panel) {
    panel.addEventListener('click', function(event) {
      var trigger = event.target.closest('[data-friends-url]');
      if (!trigger || trigger.classList.contains('is-disabled')) {
        return;
      }

      var targetUrl = trigger.getAttribute('data-friends-url');
      var apiUrl = buildApiUrl(panel, targetUrl);
      if (!apiUrl) {
        return;
      }

      event.preventDefault();
      setLoading(panel, true);

      fetch(apiUrl, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
        .then(function(response) {
          if (!response.ok) {
            throw new Error('Unable to load friends page.');
          }
          return response.json();
        })
        .then(function(payload) {
          panel.innerHTML = payload && payload.html ? payload.html : '';
          refreshDynamicUi(panel);
          if (window.history && typeof window.history.pushState === 'function') {
            window.history.pushState(
              {
                page: payload && payload.page ? payload.page : null,
                tab: payload && payload.active_tab ? payload.active_tab : null
              },
              '',
              targetUrl
            );
          }
        })
        .catch(function(error) {
          console.error(error);
          window.location.href = targetUrl;
        })
        .finally(function() {
          setLoading(panel, false);
        });
    });
  }

  document.addEventListener('DOMContentLoaded', function() {
    var panel = document.getElementById('friends-panel');
    if (!panel) {
      return;
    }
    refreshDynamicUi(panel);
    bindFriendsNavigation(panel);
  });
})();
