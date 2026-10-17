var AdminUsers = (function() {

    // ── Users Grid ─────────────────────────────────────────────────────────

    function initUsersGrid() {
        var config = window.YS_DATA_USERS || {};
        var currentUserRole = config.currentUserRole || '';

        var tableDiv = document.getElementById('table');
        if (!tableDiv) return;

        var updateUrl = function(prev, query) {
            return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
        };

        var editableCellAttributes = function(data, row, col) {
            if (row) {
                return { contentEditable: 'true', 'data-element-id': row.cells[0].data, 'data-column-id': col.id };
            }
            return {};
        };

        var roleEditableCellAttributes = function(data, row, col) {
            if (row && currentUserRole === 'admin') {
                var targetRole = row.cells[5].data;
                if (targetRole.toLowerCase() !== 'admin') {
                    return { contentEditable: 'true', 'data-element-id': row.cells[0].data, 'data-column-id': col.id };
                }
            }
            return {};
        };

        new gridjs.Grid({
            columns: [
                { id: 'id', hidden: true },
                { id: 'username', name: YI18n.t('Username'), attributes: editableCellAttributes },
                { id: 'email', name: YI18n.t('Email') },
                { id: 'password', name: YI18n.t('Password'), hidden: true, sort: false, attributes: editableCellAttributes },
                { id: 'last_seen', name: YI18n.t('Last Seen'), sort: false, hidden: true },
                { id: 'role', name: YI18n.t('Role'), sort: true, attributes: roleEditableCellAttributes },
                {
                    id: 'actions',
                    name: YI18n.t('Actions'),
                    sort: false,
                    formatter: function(cell, row) {
                        var id = row.cells[0].data;
                        var role = row.cells[5].data;
                        var isAdmin = role.toLowerCase() === 'admin';
                        var deleteButton = isAdmin
                            ? '<button disabled style="background-color: #ccc; color: #666; padding: 5px 10px; border-radius: 4px; border: none; font-size: 0.85rem;">' + YI18n.t('Delete') + '</button>'
                            : '<button class="delete-button" data-id="' + id + '" style="background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 4px; border: none; font-size: 0.85rem; cursor: pointer;">' + YI18n.t('Delete') + '</button>';
                        return gridjs.html(
                            '<div style="display: flex; gap: 8px; justify-content: center;"><a href="/admin/user_details/' + id + '" style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 0.9rem;">' + YI18n.t('Details') + '</a>' + deleteButton + '</div>'
                        );
                    }
                }
            ],
            server: {
                url: '/admin/user_data',
                then: function(results) { return results.data; },
                total: function(results) { return results.total; }
            },
            search: { enabled: true, server: { url: function(prev, search) { return updateUrl(prev, { search: search }); } } },
            sort: {
                enabled: true,
                multiColumn: true,
                server: {
                    url: function(prev, columns) {
                        var columnIds = ['id', 'username', 'email', 'password', 'last_seen', 'role'];
                        var sort = columns.map(function(col) { return (col.direction === 1 ? '+' : '-') + columnIds[col.index]; });
                        return updateUrl(prev, { sort: sort });
                    }
                }
            },
            pagination: {
                enabled: true,
                server: { url: function(prev, page, limit) { return updateUrl(prev, { start: page * limit, length: limit }); } }
            }
        }).render(tableDiv);

        var savedValue;

        tableDiv.addEventListener('focusin', function(ev) {
            if (ev.target.tagName === 'TD') savedValue = ev.target.textContent;
        });

        tableDiv.addEventListener('focusout', function(ev) {
            if (ev.target.tagName === 'TD') {
                if (savedValue !== ev.target.textContent) {
                    fetch('/admin/user_data', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: ev.target.dataset.elementId, [ev.target.dataset.columnId]: ev.target.textContent })
                    });
                }
                savedValue = undefined;
            }
        });

        tableDiv.addEventListener('keydown', function(ev) {
            if (ev.target.tagName === 'TD') {
                if (ev.key === 'Escape') { ev.target.textContent = savedValue; ev.target.blur(); }
                else if (ev.key === 'Enter') { ev.preventDefault(); ev.target.blur(); }
            }
        });

        tableDiv.addEventListener('click', function(event) {
            var target = event.target;
            if (target.classList.contains('delete-button')) {
                var id = target.getAttribute('data-id');
                if (confirm(YI18n.t('Are you sure you want to delete this user?'))) {
                    window.location.href = '/admin/delete_user/' + id;
                }
            }
        });
    }

    // ── Fetch Models (Add User form) ───────────────────────────────────────

    function fetchModelsForAddUser() {
        var urlInput = document.getElementById('custom_llm_url_add');
        var statusDiv = document.getElementById('fetch-status-add-user');
        var selectElement = document.getElementById('llm_model_select_add');
        var llmUrl = urlInput.value.trim();

        if (!llmUrl) {
            statusDiv.innerHTML = '<span style="color: #ff6b6b;">' + YI18n.t('Please enter an LLM URL') + '</span>';
            return;
        }
        statusDiv.innerHTML = '<span style="color: #4a90e2;">' + YI18n.t('Fetching models...') + '</span>';

        fetch('/admin/api/fetch_models?llm_url=' + encodeURIComponent(llmUrl))
            .then(function(response) {
                if (!response.ok) throw new Error(YI18n.t('Network response was not ok'));
                return response.json();
            })
            .then(function(data) {
                if (data.success && data.models && data.models.length > 0) {
                    selectElement.innerHTML = '';
                    var defaultOption = document.createElement('option');
                    defaultOption.value = '';
                    defaultOption.textContent = YI18n.t('Select a model');
                    selectElement.appendChild(defaultOption);
                    data.models.forEach(function(model) {
                        var option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        selectElement.appendChild(option);
                    });
                    statusDiv.innerHTML = '<span style="color: #28a745;">' + YI18n.t('✓ Loaded {length} models from {url}', {length: data.models.length, url: data.url || llmUrl}) + '</span>';
                } else {
                    statusDiv.innerHTML = '<span style="color: #ff6b6b;">\u2717 ' + (data.message || YI18n.t('No models found')) + '</span>';
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
                statusDiv.innerHTML = '<span style="color: #ff6b6b;">' + YI18n.t('✗ Error: Could not fetch models. Check if server is reachable.') + '</span>';
            });
    }

    // ── Fetch Models (User Details form) ──────────────────────────────────

    function fetchModelsForUser() {
        var urlInput = document.getElementById('custom_llm_url');
        var statusDiv = document.getElementById('fetch-status-user');
        var selectElement = document.getElementById('llm_model_select');
        var llmUrl = urlInput.value.trim();

        if (!llmUrl) {
            statusDiv.innerHTML = '<span style="color: #ff6b6b;">' + YI18n.t('Please enter an LLM URL') + '</span>';
            return;
        }
        statusDiv.innerHTML = '<span style="color: #4a90e2;">' + YI18n.t('Fetching models...') + '</span>';

        fetch('/admin/api/fetch_models?llm_url=' + encodeURIComponent(llmUrl))
            .then(function(response) {
                if (!response.ok) throw new Error(YI18n.t('Network response was not ok'));
                return response.json();
            })
            .then(function(data) {
                if (data.success && data.models && data.models.length > 0) {
                    selectElement.innerHTML = '';
                    data.models.forEach(function(model) {
                        var option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        selectElement.appendChild(option);
                    });
                    statusDiv.innerHTML = '<span style="color: #28a745;">' + YI18n.t('✓ Loaded {length} models', {length: data.models.length}) + '</span>';
                } else {
                    statusDiv.innerHTML = '<span style="color: #ff6b6b;">\u2717 ' + (data.message || YI18n.t('No models found')) + '</span>';
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
                statusDiv.innerHTML = '<span style="color: #ff6b6b;">' + YI18n.t('✗ Error: Could not fetch models. Check if server is reachable.') + '</span>';
            });
    }

    // ── Self-registration panel (administrators) ───────────────────────────

    function initSelfRegistration() {
        var box = document.getElementById('box-self-registration');
        if (!box || box.dataset.initialized) return;
        box.dataset.initialized = 'true';

        var toggle = document.getElementById('signup_enabled');
        var status = document.getElementById('signup-status');
        var message = document.getElementById('signup-message');
        var search = document.getElementById('signup-search');
        var count = document.getElementById('signup-count');
        var empty = document.getElementById('signup-empty');
        var rows = Array.prototype.slice.call(box.querySelectorAll('.sr-row'));
        var filter = 'all';

        function checked(cls) {
            return Array.prototype.map.call(box.querySelectorAll(cls + ':checked'), function(i) { return i.value; });
        }

        function refresh() {
            var q = (search.value || '').trim().toLowerCase();
            var shown = 0;
            rows.forEach(function(row) {
                var on = row.querySelector('input').checked;
                var match = (!q || row.dataset.text.indexOf(q) !== -1) &&
                    (filter === 'all' || (filter === 'selected' ? on : row.dataset.kind === filter));
                row.hidden = !match;
                if (match) shown++;
            });
            empty.hidden = shown !== 0;
            count.textContent = YI18n.t('{n} selected', {n: box.querySelectorAll('.sr-row input:checked').length});
        }

        function note(text, isError) {
            message.textContent = text;
            message.className = 'sr-message' + (isError ? ' is-error' : ' is-ok');
            setTimeout(function() { message.textContent = ''; }, 3000);
        }

        function save() {
            fetch('/admin/signup_settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled: toggle.checked,
                    experiments: checked('.signup-exp'),
                    modules: checked('.signup-mod')
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.success) { note(data.message || YI18n.t('Failed to update'), true); return; }
                status.textContent = toggle.checked && !data.open ? YI18n.t('On, but nothing is available to join yet') : '';
                note(YI18n.t('Self-registration settings saved'), false);
            })
            .catch(function() { note(YI18n.t('Error updating setting'), true); });
        }

        search.addEventListener('input', refresh);
        box.querySelector('#signup-filters').addEventListener('click', function(e) {
            var chip = e.target.closest('.sr-chip');
            if (!chip) return;
            filter = chip.dataset.filter;
            box.querySelectorAll('.sr-chip').forEach(function(c) { c.classList.toggle('is-active', c === chip); });
            refresh();
        });
        box.addEventListener('change', function(e) {
            if (e.target.matches('input[type=checkbox]')) {
                if (e.target !== toggle) refresh();
                save();
            }
        });
        refresh();
    }

    return {
        initUsersGrid: initUsersGrid,
        fetchModelsForAddUser: fetchModelsForAddUser,
        fetchModelsForUser: fetchModelsForUser,
        initSelfRegistration: initSelfRegistration
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    AdminUsers.initUsersGrid();
    AdminUsers.initSelfRegistration();
});

// Expose globally for use in HTML onclick attributes
window.fetchModelsForAddUser = AdminUsers.fetchModelsForAddUser;
window.fetchModelsForUser = AdminUsers.fetchModelsForUser;
