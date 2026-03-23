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
                { id: 'username', name: 'Username', attributes: editableCellAttributes },
                { id: 'email', name: 'Email' },
                { id: 'password', name: 'Password', hidden: true, sort: false, attributes: editableCellAttributes },
                { id: 'last_seen', name: 'Last Seen', sort: false, hidden: true },
                { id: 'role', name: 'Role', sort: true, attributes: roleEditableCellAttributes },
                {
                    id: 'actions',
                    name: 'Actions',
                    sort: false,
                    formatter: function(cell, row) {
                        var id = row.cells[0].data;
                        var role = row.cells[5].data;
                        var isAdmin = role.toLowerCase() === 'admin';
                        var deleteButton = isAdmin
                            ? '<button disabled style="background-color: #ccc; color: #666; padding: 5px 10px; border-radius: 4px; border: none; font-size: 0.85rem;">Delete</button>'
                            : '<button class="delete-button" data-id="' + id + '" style="background-color: #dc3545; color: white; padding: 5px 10px; border-radius: 4px; border: none; font-size: 0.85rem; cursor: pointer;">Delete</button>';
                        return gridjs.html(
                            '<div style="display: flex; gap: 8px; justify-content: center;">' +
                            '<a href="/admin/user_details/' + id + '" style="background-color: #28a745; color: white; padding: 5px 10px; border-radius: 4px; text-decoration: none; font-size: 0.9rem;">Details</a>' +
                            deleteButton + '</div>'
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
                if (confirm('Are you sure you want to delete this user?')) {
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
            statusDiv.innerHTML = '<span style="color: #ff6b6b;">Please enter an LLM URL</span>';
            return;
        }
        statusDiv.innerHTML = '<span style="color: #4a90e2;">Fetching models...</span>';

        fetch('/admin/api/fetch_models?llm_url=' + encodeURIComponent(llmUrl))
            .then(function(response) {
                if (!response.ok) throw new Error('Network response was not ok');
                return response.json();
            })
            .then(function(data) {
                if (data.success && data.models && data.models.length > 0) {
                    selectElement.innerHTML = '';
                    var defaultOption = document.createElement('option');
                    defaultOption.value = '';
                    defaultOption.textContent = 'Select a model';
                    selectElement.appendChild(defaultOption);
                    data.models.forEach(function(model) {
                        var option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        selectElement.appendChild(option);
                    });
                    statusDiv.innerHTML = '<span style="color: #28a745;">\u2713 Loaded ' + data.models.length + ' models from ' + (data.url || llmUrl) + '</span>';
                } else {
                    statusDiv.innerHTML = '<span style="color: #ff6b6b;">\u2717 ' + (data.message || 'No models found') + '</span>';
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
                statusDiv.innerHTML = '<span style="color: #ff6b6b;">\u2717 Error: Could not fetch models. Check if server is reachable.</span>';
            });
    }

    // ── Fetch Models (User Details form) ──────────────────────────────────

    function fetchModelsForUser() {
        var urlInput = document.getElementById('custom_llm_url');
        var statusDiv = document.getElementById('fetch-status-user');
        var selectElement = document.getElementById('llm_model_select');
        var llmUrl = urlInput.value.trim();

        if (!llmUrl) {
            statusDiv.innerHTML = '<span style="color: #ff6b6b;">Please enter an LLM URL</span>';
            return;
        }
        statusDiv.innerHTML = '<span style="color: #4a90e2;">Fetching models...</span>';

        fetch('/admin/api/fetch_models?llm_url=' + encodeURIComponent(llmUrl))
            .then(function(response) {
                if (!response.ok) throw new Error('Network response was not ok');
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
                    statusDiv.innerHTML = '<span style="color: #28a745;">\u2713 Loaded ' + data.models.length + ' models</span>';
                } else {
                    statusDiv.innerHTML = '<span style="color: #ff6b6b;">\u2717 ' + (data.message || 'No models found') + '</span>';
                }
            })
            .catch(function(error) {
                console.error('Error:', error);
                statusDiv.innerHTML = '<span style="color: #ff6b6b;">\u2717 Error: Could not fetch models. Check if server is reachable.</span>';
            });
    }

    return {
        initUsersGrid: initUsersGrid,
        fetchModelsForAddUser: fetchModelsForAddUser,
        fetchModelsForUser: fetchModelsForUser
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    AdminUsers.initUsersGrid();
});
