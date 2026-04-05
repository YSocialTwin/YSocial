var AdminPages = (function() {

    function readAgentGridConfig(tableDiv) {
        return {
            kind: tableDiv.dataset.gridKind || 'standard',
            listEndpoint: tableDiv.dataset.listEndpoint || '/admin/agents_data',
            detailsUrlPrefix: tableDiv.dataset.detailsUrlPrefix || '/admin/agent_details/',
            deleteUrlPrefix: tableDiv.dataset.deleteUrlPrefix || '/admin/delete_agent/'
        };
    }

    function buildAgentActionsHtml(id, config) {
        return '<div style="display: flex; gap: 8px; justify-content: center;"><a href="'+config.detailsUrlPrefix+id+'" style="background-color: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Details</a><a href="'+config.deleteUrlPrefix+id+'" style="background-color: #dc3545; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Delete</a></div>';
    }

    function buildActivityProfileFormatter(cell) {
        if (!cell || !cell.hours) return gridjs.html('<span style="color: #999; font-size: 0.85em;">Not assigned</span>');
        var hours = cell.hours.split(',').map(function(h) { return parseInt(h.trim()); });
        var barHtml = Array.from({length: 24}, function(_, i) {
            var isActive = hours.includes(i);
            var bgColor = isActive ? 'rgba(34, 197, 94, 0.8)' : 'rgba(229, 231, 235, 0.5)';
            return '<div style="display: inline-block; width: 3.5%; height: 12px; background-color: '+bgColor+'; border: 0.5px solid #e5e7eb; margin: 0;" title="Hour '+i+'"></div>';
        }).join('');
        return gridjs.html('<div style="display: flex; flex-direction: column; gap: 3px;"><div style="font-size: 0.8em; font-weight: 500;">'+cell.name+'</div><div style="display: flex; width: 100%; gap: 0;">'+barHtml+'</div></div>');
    }

    function buildActivityProfileTagsHtml(values) {
        if (!values || values.length === 0) {
            return '<span style="color: #999; font-size: 0.85em;">Not assigned</span>';
        }
        var tags = values.map(function(value) {
            return '<span style="display: inline-block; background-color: #039be5; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.75rem; margin: 2px;">'+value+'</span>';
        }).join(' ');
        return '<div style="display: flex; flex-wrap: wrap; gap: 4px;">'+tags+'</div>';
    }

    function buildActivityProfileTagFormatter(cell) {
        var names = [];
        if (Array.isArray(cell)) {
            names = cell.filter(Boolean);
        } else if (cell && typeof cell === 'object') {
            if (Array.isArray(cell.names)) {
                names = cell.names.filter(Boolean);
            } else if (cell.name) {
                names = [cell.name];
            }
        } else if (typeof cell === 'string' && cell) {
            names = [cell];
        }
        return gridjs.html(buildActivityProfileTagsHtml(names));
    }

    function initAgentsGrid() {
        var tableDiv = document.getElementById('table');
        if (!tableDiv) return;
        var config = readAgentGridConfig(tableDiv);
        var updateUrl = function(prev, query) {
            return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
        };
        var editableCellAttributes = function(data, row, col) {
            if (row) return { contentEditable: 'true', 'data-element-id': row.cells[0].data, 'data-column-id': col.id };
            return {};
        };
        var getStarRatingHtml = function(level) {
            var filled = Math.max(0, Math.min(5, parseInt(level)));
            var empty = 5 - filled;
            var colors = ['#ccc', '#aaa', '#f0ad4e', '#f0ad4e', '#f39c12', '#d9534f'];
            var color = colors[filled] || '#ccc';
            return '<div style="text-align: center; color: ' + color + '; font-size: 1.1rem;">'+'★'.repeat(filled)+'☆'.repeat(empty)+'</div>';
        };
        var columns;
        var columnIds;
        if (config.kind === 'hello') {
            columns = [
                { id: 'id', hidden: true },
                { id: 'name', name: 'Name', attributes: editableCellAttributes },
                { id: 'daily_budget', name: 'Daily Budget', sort: true },
                { id: 'activity_profile', name: 'Activity Profile', sort: true, width: '250px', formatter: function(cell) { return buildActivityProfileTagFormatter(cell); } },
                { id: 'actions', name: 'Actions', sort: false, formatter: function(cell, row) {
                    var id = row.cells[0].data;
                    return gridjs.html(buildAgentActionsHtml(id, config));
                }}
            ];
            columnIds = ['id', 'name', 'daily_budget', 'activity_profile'];
        } else {
            columns = [
                { id: 'id', hidden: true },
                { id: 'name', name: 'Name', attributes: editableCellAttributes },
                { id: 'age', name: 'Age', sort: true },
                { id: 'profession', name: 'Profession', sort: true },
                { id: 'daily_activity_level', name: 'Activity Level', sort: true, formatter: function(cell) { return gridjs.html(getStarRatingHtml(cell)); } },
                { id: 'activity_profile', name: 'Activity Profile', sort: true, width: '250px', formatter: function(cell) { return buildActivityProfileFormatter(cell); } },
                { id: 'actions', name: 'Actions', sort: false, formatter: function(cell, row) {
                    var id = row.cells[0].data;
                    return gridjs.html(buildAgentActionsHtml(id, config));
                }}
            ];
            columnIds = ['id', 'name', 'age', 'profession', 'daily_activity_level', 'activity_profile'];
        }

        new gridjs.Grid({
            columns: columns,
            server: { url: config.listEndpoint, then: function(r) { return r.data; }, total: function(r) { return r.total; } },
            search: { enabled: true, server: { url: function(prev, search) { return updateUrl(prev, { search: search }); } } },
            sort: { enabled: true, multiColumn: true, server: { url: function(prev, columns) {
                var sort = columns.map(function(col) { return (col.direction === 1 ? '+' : '-') + columnIds[col.index]; });
                return updateUrl(prev, { sort: sort });
            }}},
            pagination: { enabled: true, server: { url: function(prev, page, limit) { return updateUrl(prev, { start: page * limit, length: limit }); } } }
        }).render(tableDiv);

        var savedValue;
        tableDiv.addEventListener('focusin', function(ev) { if (ev.target.tagName === 'TD') savedValue = ev.target.textContent; });
        tableDiv.addEventListener('focusout', function(ev) {
            if (ev.target.tagName === 'TD') {
                if (savedValue !== ev.target.textContent) {
                    fetch(config.listEndpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: ev.target.dataset.elementId, [ev.target.dataset.columnId]: ev.target.textContent }) });
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
                if (confirm('Are you sure you want to delete this agent?')) {
                    fetch(config.deleteUrlPrefix + id, { method: 'DELETE' })
                        .then(function(r) { if (!r.ok) throw new Error('Failed to delete'); location.reload(); })
                        .catch(function(err) { alert('Error deleting agent.'); console.error(err); });
                }
            }
        });
    }

    function initPagesGrid() {
        var tableDiv = document.getElementById('table');
        if (!tableDiv) return;
        var updateUrl = function(prev, query) {
            return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
        };
        var editableCellAttributes = function(data, row, col) {
            if (row) return { contentEditable: 'true', 'data-element-id': row.cells[1].data, 'data-column-id': col.id };
            return {};
        };
        new gridjs.Grid({
            columns: [
                { id: 'logo', name: '', formatter: function(cell) {
                    return gridjs.html('<div style="display: flex; justify-content: center; align-items: center; height: 100%; width: 100%;"><img src="'+cell+'" alt="logo" style="height: 25px; object-fit: contain; margin: 0; padding: 0; display: block;"></div>');
                }, sort: false, searchable: false, width: '60px' },
                { id: 'id', hidden: true },
                { id: 'name', name: 'Name', attributes: editableCellAttributes },
                { id: 'page_type', name: 'Type' },
                { id: 'leaning', name: 'Political Leaning' },
                { id: 'activity_profile', name: 'Activity Profile', sort: false, formatter: function(cell) {
                    return gridjs.html(buildActivityProfileTagsHtml(cell || []));
                }},
                { id: 'actions', name: 'Actions', formatter: function(cell, row) {
                    var id = row.cells[1].data;
                    return gridjs.html('<div style="display: flex; gap: 8px; justify-content: center;"><a href="/admin/page_details/'+id+'" style="background-color: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Details</a><a href="/admin/delete_page/'+id+'" style="background-color: #dc3545; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Delete</a></div>');
                }}
            ],
            server: { url: '/admin/pages_data', then: function(r) { return r.data; }, total: function(r) { return r.total; } },
            search: { enabled: true, server: { url: function(prev, search) { return updateUrl(prev, { search: search }); } } },
            sort: { enabled: true, multiColumn: true, server: { url: function(prev, columns) {
                var columnIds = ['logo', 'id', 'name', 'page_type', 'leaning', 'activity_profiles'];
                var sort = columns.map(function(col) { return (col.direction === 1 ? '+' : '-') + columnIds[col.index]; });
                return updateUrl(prev, { sort: sort });
            }}},
            pagination: { enabled: true, server: { url: function(prev, page, limit) { return updateUrl(prev, { start: page * limit, length: limit }); } } }
        }).render(tableDiv);

        var savedValue;
        tableDiv.addEventListener('focusin', function(ev) { if (ev.target.tagName === 'TD') savedValue = ev.target.textContent; });
        tableDiv.addEventListener('focusout', function(ev) {
            if (ev.target.tagName === 'TD') {
                if (savedValue !== ev.target.textContent) {
                    fetch('/admin/pages_data', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: ev.target.dataset.elementId, [ev.target.dataset.columnId]: ev.target.textContent }) });
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
                if (confirm('Are you sure you want to delete this page?')) {
                    fetch('/admin/delete_page/' + id, { method: 'DELETE' })
                        .then(function(r) { if (!r.ok) throw new Error('Failed to delete'); location.reload(); })
                        .catch(function(err) { alert('Error deleting page.'); console.error(err); });
                }
            }
        });
    }

    function displayPageCollectionFileName(input) {
        var display = document.getElementById('collection-file-name-display');
        if (input.files && input.files[0]) display.textContent = '\u2713 ' + input.files[0].name;
        else display.textContent = '';
    }

    function initHelloPopulationToggle() {
        var select = document.getElementById('hello_target_population');
        var fields = document.getElementById('hello-new-population-fields');
        if (!select || !fields) return;
        var sync = function() {
            fields.style.display = select.value === '__new__' ? 'block' : 'none';
        };
        select.addEventListener('change', sync);
        sync();
    }

    function initHelloPopulationsGrid() {
        var tableDiv = document.getElementById('hello-populations-table');
        if (!tableDiv || typeof gridjs === 'undefined') return;

        var raw = tableDiv.dataset.populations || '[]';
        var populations = [];
        try {
            populations = JSON.parse(raw);
        } catch (err) {
            console.error('Failed to parse hello populations payload', err);
            return;
        }

        new gridjs.Grid({
            columns: [
                { id: 'id', hidden: true },
                { id: 'name', name: 'Name' },
                { id: 'descr', name: 'Description' },
                { id: 'agent_count', name: 'Size' },
                {
                    id: 'actions',
                    name: 'Actions',
                    sort: false,
                    formatter: function(cell, row) {
                        var id = row.cells[0].data;
                        return gridjs.html('<div style="display: flex; gap: 8px; justify-content: center;"><a href="/admin/population_details/'+id+'" style="background-color: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Details</a></div>');
                    }
                }
            ],
            data: populations.map(function(pop) {
                return [pop.id, pop.name, pop.descr || '', pop.agent_count || 0];
            }),
            pagination: { enabled: true, limit: 5 },
            search: { enabled: true },
            sort: true
        }).render(tableDiv);
    }

    function initCustomPopulationAgentsGrid() {
        var tableDiv = document.getElementById('custom-population-agents-table');
        if (!tableDiv || typeof gridjs === 'undefined' || !window.YS_CUSTOM_POP_AGENTS) return;

        var agents = window.YS_CUSTOM_POP_AGENTS;
        new gridjs.Grid({
            columns: [
                { id: 'id', hidden: true },
                { id: 'name', name: 'Name' },
                { id: 'ag_type', name: 'Agent Type' },
                { id: 'activity_profile', name: 'Activity Profile', formatter: function(cell) { return buildActivityProfileTagFormatter(cell); } },
                { id: 'daily_activity_level', name: 'Activity Level' },
                { id: 'ext_fields', name: 'Extension Fields', formatter: function(cell) {
                    if (!cell || Object.keys(cell).length === 0) {
                        return gridjs.html('<span style="color: #999; font-size: 0.85em;">None</span>');
                    }
                    var items = Object.entries(cell).map(function(entry) {
                        return '<div><b>'+entry[0]+'</b>: '+entry[1]+'</div>';
                    }).join('');
                    return gridjs.html(items);
                }},
                { id: 'actions', name: 'Actions', sort: false, formatter: function(cell, row) {
                    var id = row.cells[0].data;
                    return gridjs.html('<div style="display: flex; gap: 8px; justify-content: center;"><a href="/admin/agent_details/'+id+'" style="background-color: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Details</a></div>');
                }}
            ],
            data: agents.map(function(agent) {
                return [
                    agent.id,
                    agent.name,
                    agent.ag_type || 'standard',
                    agent.activity_profile || 'Not assigned',
                    agent.daily_activity_level == null ? 'N/A' : agent.daily_activity_level,
                    agent.ext_fields || {}
                ];
            }),
            pagination: { enabled: true, limit: 10 },
            search: { enabled: true },
            sort: true
        }).render(tableDiv);
    }

    function initCustomPopulationsGrid() {
        var tableDiv = document.getElementById('custom-populations-table');
        if (!tableDiv || typeof gridjs === 'undefined') return;
        var raw = tableDiv.dataset.populations || '[]';
        var populations = [];
        try {
            populations = JSON.parse(raw);
        } catch (err) {
            console.error('Failed to parse custom populations payload', err);
            return;
        }

        new gridjs.Grid({
            columns: [
                { id: 'id', hidden: true },
                { id: 'name', name: 'Name' },
                { id: 'descr', name: 'Description' },
                { id: 'agent_count', name: 'Size' },
                { id: 'actions', name: 'Actions', sort: false, formatter: function(cell, row) {
                    var id = row.cells[0].data;
                    return gridjs.html('<div style="display: flex; gap: 8px; justify-content: center;"><a href="/admin/population_details/'+id+'" style="background-color: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Details</a></div>');
                }}
            ],
            data: populations.map(function(pop) {
                return [pop.id, pop.name, pop.descr || '', pop.agent_count || 0];
            }),
            pagination: { enabled: true, limit: 5 },
            search: { enabled: true },
            sort: true
        }).render(tableDiv);
    }

    function initCustomAgentsGrid() {
        var tableDiv = document.getElementById('custom-agents-table');
        if (!tableDiv || typeof gridjs === 'undefined') return;
        var rawAgents = tableDiv.dataset.agents || '[]';
        var rawColumns = tableDiv.dataset.columns || '[]';
        var agents = [];
        var columns = [];
        try {
            agents = JSON.parse(rawAgents);
            columns = JSON.parse(rawColumns);
        } catch (err) {
            console.error('Failed to parse custom agents payload', err);
            return;
        }

        var gridColumns = [{ id: 'id', hidden: true }];
        columns.forEach(function(column) {
            if (column.id === 'activity_profile') {
                gridColumns.push({
                    id: column.id,
                    name: column.name,
                    formatter: function(cell) { return buildActivityProfileTagFormatter(cell); }
                });
            } else {
                gridColumns.push({ id: column.id, name: column.name });
            }
        });
        gridColumns.push({
            id: 'actions',
            name: 'Actions',
            sort: false,
            formatter: function(cell, row) {
                var id = row.cells[0].data;
                return gridjs.html('<div style="display: flex; gap: 8px; justify-content: center;"><a href="/admin/agent_details/'+id+'" style="background-color: #28a745; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">Details</a></div>');
            }
        });

        new gridjs.Grid({
            columns: gridColumns,
            data: agents.map(function(agent) {
                var row = [agent.id];
                columns.forEach(function(column) {
                    row.push(agent[column.id] == null || agent[column.id] === '' ? 'N/A' : agent[column.id]);
                });
                return row;
            }),
            pagination: { enabled: true, limit: 10 },
            search: { enabled: true },
            sort: true
        }).render(tableDiv);
    }

    return {
        initAgentsGrid: initAgentsGrid,
        initPagesGrid: initPagesGrid,
        displayPageCollectionFileName: displayPageCollectionFileName,
        initHelloPopulationToggle: initHelloPopulationToggle,
        initHelloPopulationsGrid: initHelloPopulationsGrid,
        initCustomPopulationAgentsGrid: initCustomPopulationAgentsGrid,
        initCustomPopulationsGrid: initCustomPopulationsGrid,
        initCustomAgentsGrid: initCustomAgentsGrid
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    var agentTable = document.querySelector('#table[data-list-endpoint]');
    if (agentTable) {
        AdminPages.initAgentsGrid();
    }
    AdminPages.initHelloPopulationToggle();
    AdminPages.initHelloPopulationsGrid();
    AdminPages.initCustomPopulationAgentsGrid();
    AdminPages.initCustomPopulationsGrid();
    AdminPages.initCustomAgentsGrid();
    if (document.querySelector('#table') && window.location.pathname.includes('/admin/pages')) {
        AdminPages.initPagesGrid();
    }
});

// Expose globally for use in HTML onchange attributes
window.displayPageCollectionFileName = AdminPages.displayPageCollectionFileName;
