(function() {
  function escapeAttr(value) {
      return String(value)
          .replace(/&/g, '&amp;')
          .replace(/"/g, '&quot;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
  }

  function revokeVisibilityAssignment(expId, researcherId) {
      if (!confirm('Revoke this visibility assignment?')) {
          return;
      }

      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/admin/visibility_settings/revoke_assignment';
      form.style.display = 'none';

      const expInput = document.createElement('input');
      expInput.type = 'hidden';
      expInput.name = 'exp_id';
      expInput.value = String(expId);
      form.appendChild(expInput);

      const researcherInput = document.createElement('input');
      researcherInput.type = 'hidden';
      researcherInput.name = 'researcher_id';
      researcherInput.value = String(researcherId);
      form.appendChild(researcherInput);

      document.body.appendChild(form);
      form.submit();
  }

  document.addEventListener('DOMContentLoaded', function() {
      const tableDiv = document.getElementById('researcher-visibility-table');
      if (!tableDiv || typeof gridjs === 'undefined') {
          return;
      }

      const rows = (window.YS_DATA_VISIBILITY && Array.isArray(YS_DATA_VISIBILITY.rows))
          ? YS_DATA_VISIBILITY.rows
          : [];

      new gridjs.Grid({
          columns: [
              {
                  id: 'experiment_name',
                  name: 'Experiment',
                  sort: true,
                  formatter: function(_, row) {
                      const url = row.cells[4].data;
                      const name = row.cells[0].data;
                      return gridjs.html(`<a href="${escapeAttr(url)}">${escapeAttr(name)}</a>`);
                  }
              },
              { id: 'group_name', name: 'Group', sort: true },
              { id: 'researcher_name', name: 'Researcher', sort: true },
              {
                  id: 'actions',
                  name: 'Actions',
                  sort: false,
                  formatter: function(_, row) {
                      const expId = row.cells[3].data;
                      const researcherId = row.cells[5].data;
                      return gridjs.html(
                          `<button class="button is-small is-danger is-light" onclick="revokeVisibilityAssignment(${Number(expId)}, ${Number(researcherId)})">Revoke</button>`
                      );
                  }
              },
              { id: 'experiment_url', hidden: true },
              { id: 'researcher_id', hidden: true },
          ],
          data: rows.map(function(item) {
              return [
                  item.experiment_name,
                  item.group_name,
                  item.researcher_name,
                  item.exp_id,
                  item.experiment_url,
                  item.researcher_id,
              ];
          }),
          search: true,
          sort: true,
          pagination: {
              enabled: true,
              limit: 10
          }
      }).render(tableDiv);
  });

  window.revokeVisibilityAssignment = revokeVisibilityAssignment;
})();
