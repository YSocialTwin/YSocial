/**
 * AdminMiscellanea - Extracted from admin templates (Phase T6)
 * Auto-generated. Do not edit manually.
 */
var AdminMiscellanea = (function() {
  const bindById = (id, eventName, handler) => {
      const element = document.getElementById(id);
      if (element) {
          element.addEventListener(eventName, handler);
      }
      return element;
  };

  const tableDiv = document.getElementById('leaning_table');

  const updateUrl = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes = (data, row, col) => {
      if (row) {
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': 'leaning'
          };
      } else {
          return {};
      }
  };

  const grid = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'leaning',
              name: 'Name',
              attributes: editableCellAttributes
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_leaning/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid.forceRender();
                                      } else {
                                          alert("Failed to delete leaning.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/leanings_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'leaning'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrl(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid.render(tableDiv);

  // Inline edit tracking
  let savedValue;

  tableDiv.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue = ev.target.textContent;
      }
  });

  tableDiv.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue !== ev.target.textContent) {
              fetch('/admin/leanings_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue = undefined;
      }
  });

  tableDiv.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDiv5 = document.getElementById('edu_table');

  const updateUrl5 = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes5 = (data, row, col) => {
      if (row) {
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': 'education_level'
          };
      } else {
          return {};
      }
  };

  const grid5 = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'education_level',
              name: 'Name',
              attributes: editableCellAttributes5
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_education/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid5.forceRender();
                                      } else {
                                          alert("Failed to delete education level.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/educations_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl5(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'education_level'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl5(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrl5(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid5.render(tableDiv5);

  // Inline editing
  let savedValue5;

  tableDiv5.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue5 = ev.target.textContent;
      }
  });

  tableDiv5.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue5 !== ev.target.textContent) {
              fetch('/admin/educations_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue5 = undefined;
      }
  });

  tableDiv5.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue5;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDiv4 = document.getElementById('profession_table');

  const updateUrl4 = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes4 = (data, row, col) => {
      if (row) {
          const columnId = col.id;
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': columnId
          };
      } else {
          return {};
      }
  };

  const grid4 = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'profession',
              name: 'Name',
              attributes: editableCellAttributes4
          },
          {
              id: 'background',
              name: 'Category',
              attributes: editableCellAttributes4
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_profession/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid4.forceRender();
                                      } else {
                                          alert("Failed to delete profession.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/professions_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl4(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'profession', 'background'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl4(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrl4(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid4.render(tableDiv4);

  let savedValue4;

  tableDiv4.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue4 = ev.target.textContent;
      }
  });

  tableDiv4.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue4 !== ev.target.textContent) {
              fetch('/admin/professions_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue4 = undefined;
      }
  });

  tableDiv4.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue4;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDiv1 = document.getElementById('language_table');

  const updateUrl1 = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes1 = (data, row, col) => {
      if (row) {
          const columnId = col.id;
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': columnId
          };
      } else {
          return {};
      }
  };

  const grid1 = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'language',
              name: 'Name',
              attributes: editableCellAttributes1
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_language/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid1.forceRender();
                                      } else {
                                          alert("Failed to delete language.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/languages_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl1(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'language'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl1(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          limit: 5,
          server: {
              url: (prev, page, limit) => updateUrl1(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid1.render(tableDiv1);

  let savedValue1;

  tableDiv1.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue1 = ev.target.textContent;
      }
  });

  tableDiv1.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue1 !== ev.target.textContent) {
              fetch('/admin/languages_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue1 = undefined;
      }
  });

  tableDiv1.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue1;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDiv2 = document.getElementById('nationality_table');

  const updateUrl2 = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes2 = (data, row, col) => {
      if (row) {
          const columnId = col.id;
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': columnId
          };
      } else {
          return {};
      }
  };

  const grid2 = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'nationality',
              name: 'Name',
              attributes: editableCellAttributes2
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_nationality/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid2.forceRender();
                                      } else {
                                          alert("Failed to delete nationality.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/nationalities_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl2(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'nationality'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl2(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          limit: 5,
          server: {
              url: (prev, page, limit) => updateUrl2(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid2.render(tableDiv2);

  let savedValue2;

  tableDiv2.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue2 = ev.target.textContent;
      }
  });

  tableDiv2.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue2 !== ev.target.textContent) {
              fetch('/admin/nationalities_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue2 = undefined;
      }
  });

  tableDiv2.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue2;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDivAgeClasses = document.getElementById('age_classes_table');

  const updateUrlAgeClasses = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributesAgeClasses = (data, row, col) => {
      if (row) {
          const columnId = col.id;
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': columnId
          };
      } else {
          return {};
      }
  };

  const gridAgeClasses = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'name',
              name: 'Name',
              attributes: editableCellAttributesAgeClasses
          },
          {
              id: 'age_start',
              name: 'Age Start',
              attributes: editableCellAttributesAgeClasses
          },
          {
              id: 'age_end',
              name: 'Age End',
              attributes: editableCellAttributesAgeClasses
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_age_class/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          gridAgeClasses.forceRender();
                                      } else {
                                          alert("Failed to delete age class.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/age_classes_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrlAgeClasses(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'name', 'age_start', 'age_end'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrlAgeClasses(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrlAgeClasses(prev, { start: page * limit, length: limit }),
          },
      },
  });

  gridAgeClasses.render(tableDivAgeClasses);

  // Inline editing
  let savedValueAgeClasses;

  tableDivAgeClasses.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValueAgeClasses = ev.target.textContent;
      }
  });

  tableDivAgeClasses.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValueAgeClasses !== ev.target.textContent) {
              fetch('/admin/age_classes_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValueAgeClasses = undefined;
      }
  });

  tableDivAgeClasses.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValueAgeClasses;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDiv6 = document.getElementById('topics_table');

  const updateUrl6 = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes6 = (data, row, col) => {
      if (row) {
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': 'name'
          };
      } else {
          return {};
      }
  };

  const grid6 = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'name',
              name: 'Name',
              attributes: editableCellAttributes6
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_topic/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid6.forceRender(); // refresh table
                                      } else {
                                          alert("Failed to delete topic.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/topic_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl6(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'name'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl6(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrl6(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid6.render(tableDiv6);

  // Handle inline editing
  let savedValue6;

  tableDiv6.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue6 = ev.target.textContent;
      }
  });

  tableDiv6.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue6 !== ev.target.textContent) {
              fetch('/admin/topic_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue6 = undefined;
      }
  });

  tableDiv6.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue6;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDiv3 = document.getElementById('toxicity_table');

  const updateUrl3 = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributes3 = (data, row, col) => {
      if (row) {
          const columnId = col.id;
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': columnId
          };
      } else {
          return {};
      }
  };

  const grid3 = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'toxicity_level',
              name: 'Name',
              attributes: editableCellAttributes3
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_toxicity_level/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          grid3.forceRender();
                                      } else {
                                          alert("Failed to delete toxicity level.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/toxicity_levels_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrl3(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'toxicity_level'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrl3(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrl3(prev, { start: page * limit, length: limit }),
          },
      },
  });

  grid3.render(tableDiv3);

  let savedValue3;

  tableDiv3.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValue3 = ev.target.textContent;
      }
  });

  tableDiv3.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValue3 !== ev.target.textContent) {
              fetch('/admin/toxicity_levels_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValue3 = undefined;
      }
  });

  tableDiv3.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValue3;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDivActivity = document.getElementById('activity_profiles_table');

  const updateUrlActivity = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributesActivity = (data, row, col) => {
      if (row && col.id === 'name') {
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': col.id
          };
      } else {
          return {};
      }
  };

  const gridActivity = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'name',
              name: 'Name',
              attributes: editableCellAttributesActivity,
              width: '10%'
          },
          {
              id: 'hours',
              name: 'Activity Hours',
              width: '80%',
              formatter: (cell) => {
                  const hours = cell ? cell.split(',').map(h => parseInt(h.trim())) : [];
                  const barHtml = Array.from({length: 24}, (_, i) => {
                      const isActive = hours.includes(i);
                      const intensity = isActive ? 1 : 0;
                      const bgColor = isActive ? 'rgba(34, 197, 94, 0.8)' : 'rgba(229, 231, 235, 0.5)';
                      return `<div style="display: inline-block; width: 4%; height: 20px; background-color: ${bgColor}; border: 1px solid #e5e7eb; margin: 0; title='Hour ${i}'" title="Hour ${i}"></div>`;
                  }).join('');
                  return gridjs.html(`<div style="display: flex; width: 100%; gap: 0;">${barHtml}</div>`);
              }
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              width: '10%',
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_activity_profile/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          gridActivity.forceRender();
                                      } else {
                                          alert("Failed to delete activity profile.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/activity_profiles_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrlActivity(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'name', 'hours'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrlActivity(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrlActivity(prev, { start: page * limit, length: limit }),
          },
      },
  });

  gridActivity.render(tableDivActivity);

  let savedValueActivity;

  tableDivActivity.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValueActivity = ev.target.textContent;
      }
  });

  tableDivActivity.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValueActivity !== ev.target.textContent) {
              fetch('/admin/activity_profiles_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValueActivity = undefined;
      }
  });

  tableDivActivity.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValueActivity;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  // Collect selected hours when form is submitted
  const activityProfileForm = document.querySelector('form[action="/admin/create_activity_profile"]');
  if (activityProfileForm) {
      activityProfileForm.addEventListener('submit', function(e) {
          const checkboxes = document.querySelectorAll('input[name="hour"]:checked');
          const hours = Array.from(checkboxes).map(cb => cb.value);
          const hoursInput = document.getElementById('hours_input');
          if (hoursInput) {
              hoursInput.value = hours.join(',');
          }
      });
  }

  bindById('check-updates-btn', 'click', function() {
      const btn = this;
      const statusDiv = document.getElementById('update-status');
    
      btn.disabled = true;
      btn.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Checking...';
      statusDiv.innerHTML = '<span style="color: #4a90e2;">Checking for updates...</span>';
    
      fetch('/admin/check_for_updates', { method: 'POST' })
      .then(response => {
          btn.disabled = false;
          btn.innerHTML = '<i class="mdi mdi-update"></i> Check for Updates';
        
          if (response.redirected) {
              window.location.href = response.url;
          } else {
              statusDiv.innerHTML = '<span style="color: #22c55e;">✓ Check complete</span>';
              setTimeout(() => {
                  statusDiv.innerHTML = 'Click to check if a newer version of YSocial is available.';
              }, 3000);
          }
      })
      .catch(error => {
          btn.disabled = false;
          btn.innerHTML = '<i class="mdi mdi-update"></i> Check for Updates';
          statusDiv.innerHTML = '<span style="color: #dc3545;">✗ Error checking for updates</span>';
      });
  });

  function updateTelemetryStatus(enabled) {
      const status = document.getElementById('telemetry-status');
      if (enabled) {
          status.innerHTML = '<span style="color: #22c55e;">● Enabled</span>';
      } else {
          status.innerHTML = '<span style="color: #dc3545;">● Disabled</span>';
      }
  }

  function showTelemetryMessage(message, isError) {
      const msgDiv = document.getElementById('telemetry-message');
      msgDiv.textContent = message;
      msgDiv.style.display = 'block';
      msgDiv.style.backgroundColor = isError ? '#fee2e2' : '#dcfce7';
      msgDiv.style.color = isError ? '#dc3545' : '#16a34a';
      setTimeout(() => { msgDiv.style.display = 'none'; }, 3000);
  }

  bindById('telemetry_enabled', 'change', function() {
      const enabled = this.checked;
      updateTelemetryStatus(enabled);
    
      fetch('/admin/update_telemetry_preference_ajax', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ telemetry_enabled: enabled })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              showTelemetryMessage('Telemetry setting updated', false);
          } else {
              showTelemetryMessage(data.message || 'Failed to update', true);
          }
      })
      .catch(error => {
          console.error('Error:', error);
          showTelemetryMessage('Error updating setting', true);
      });
  });

  // Initialize status on load using data attribute to avoid duplicate initialization
  (function() {
      const telemetryCheckbox = document.getElementById('telemetry_enabled');
      if (telemetryCheckbox && !telemetryCheckbox.dataset.initialized) {
          telemetryCheckbox.dataset.initialized = 'true';
          updateTelemetryStatus(telemetryCheckbox.checked);
      }
  })();

  // Load current HPC monitor settings
  async function loadHpcMonitorSettings() {
      try {
          const response = await fetch('/admin/hpc_monitor_settings');
          const data = await response.json();
        
          document.getElementById('hpc_monitor_enabled').checked = data.enabled;
          document.getElementById('hpc_check_interval_seconds').value = data.check_interval_seconds;
        
          updateHpcMonitorStatusIndicator(data.enabled);
        
          if (data.last_check) {
              const lastCheck = new Date(data.last_check);
              document.getElementById('last-hpc-check-time').textContent = lastCheck.toLocaleString();
          } else {
              document.getElementById('last-hpc-check-time').textContent = 'Never';
          }
      } catch (error) {
          console.error('Error loading HPC monitor settings:', error);
      }
  }

  function updateHpcMonitorStatusIndicator(enabled) {
      const indicator = document.getElementById('hpc-monitor-status-indicator');
      if (enabled) {
          indicator.innerHTML = '<span style="color: #22c55e;">● Active</span>';
      } else {
          indicator.innerHTML = '<span style="color: #dc3545;">● Disabled</span>';
      }
  }

  function showHpcMonitorMessage(message, isError) {
      const msgDiv = document.getElementById('hpc-monitor-message');
      msgDiv.textContent = message;
      msgDiv.style.display = 'block';
      msgDiv.style.backgroundColor = isError ? '#fee2e2' : '#dcfce7';
      msgDiv.style.color = isError ? '#dc3545' : '#16a34a';
    
      setTimeout(() => {
          msgDiv.style.display = 'none';
      }, 5000);
  }

  // Save HPC monitor settings
  bindById('save-hpc-monitor-settings', 'click', async function() {
      const enabled = document.getElementById('hpc_monitor_enabled').checked;
      const intervalValue = document.getElementById('hpc_check_interval_seconds').value;
      const interval = Number(intervalValue);
    
      // Check for NaN or invalid values
      if (isNaN(interval) || interval < 1 || interval > 300) {
          showHpcMonitorMessage('Check interval must be a valid number between 1 and 300 seconds', true);
          return;
      }
    
      try {
          const response = await fetch('/admin/hpc_monitor_settings', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                  enabled: enabled,
                  check_interval_seconds: interval
              })
          });
        
          const data = await response.json();
        
          if (data.success) {
              updateHpcMonitorStatusIndicator(enabled);
              showHpcMonitorMessage('Settings saved successfully', false);
          } else {
              showHpcMonitorMessage(data.message || 'Failed to save settings', true);
          }
      } catch (error) {
          console.error('Error saving HPC monitor settings:', error);
          showHpcMonitorMessage('Error saving settings', true);
      }
  });

  // Update status indicator when toggle changes
  bindById('hpc_monitor_enabled', 'change', function() {
      updateHpcMonitorStatusIndicator(this.checked);
  });

  // Load settings on page load using data attribute to avoid duplicate initialization
  (function() {
      const hpcMonitorContainer = document.getElementById('hpc-monitor-settings-container');
      if (hpcMonitorContainer && !hpcMonitorContainer.dataset.initialized) {
          hpcMonitorContainer.dataset.initialized = 'true';
          if (document.readyState === 'loading') {
              document.addEventListener('DOMContentLoaded', loadHpcMonitorSettings);
          } else {
              // DOM is already loaded
              loadHpcMonitorSettings();
          }
      }
  })();

  // Update watchdog status indicator
  function updateWatchdogStatusIndicator(enabled) {
      const indicator = document.getElementById('watchdog-status-indicator');
      if (enabled) {
          indicator.innerHTML = '<span style="color: #22c55e;">● Active</span>';
      } else {
          indicator.innerHTML = '<span style="color: #dc3545;">● Disabled</span>';
      }
  }

  // Load watchdog status on page load
  async function loadWatchdogStatus() {
      try {
          const response = await fetch('/admin/watchdog_status');
          const data = await response.json();
        
          if (data.last_run) {
              const lastRun = new Date(data.last_run);
              document.getElementById('watchdog-last-run').textContent = lastRun.toLocaleString();
          } else {
              document.getElementById('watchdog-last-run').textContent = 'Never';
          }
        
          if (data.run_interval_minutes) {
              document.getElementById('watchdog_interval').value = data.run_interval_minutes;
          }
        
          // Update enabled status from scheduler_running
          const isEnabled = data.scheduler_running !== false;
          document.getElementById('watchdog_enabled').checked = isEnabled;
          updateWatchdogStatusIndicator(isEnabled);
      } catch (error) {
          console.error('Error loading watchdog status:', error);
      }
  }

  // Handle enable/disable toggle
  bindById('watchdog_enabled', 'change', function() {
      const enabled = this.checked;
      const statusDiv = document.getElementById('watchdog-status');
    
      updateWatchdogStatusIndicator(enabled);
    
      fetch('/admin/watchdog_toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: enabled })
      })
      .then(response => response.json())
      .then(data => {
          if (data.success) {
              statusDiv.innerHTML = '<span style="color: #22c55e;">✓ Watchdog ' + (enabled ? 'enabled' : 'disabled') + '</span>';
          } else {
              statusDiv.innerHTML = '<span style="color: #dc3545;">✗ ' + (data.message || 'Failed to update') + '</span>';
          }
          setTimeout(() => {
              statusDiv.innerHTML = 'Monitors server/client processes for hangs and auto-restarts them.';
          }, 3000);
      })
      .catch(error => {
          console.error('Error:', error);
          statusDiv.innerHTML = '<span style="color: #dc3545;">✗ Error updating setting</span>';
      });
  });

  bindById('save-watchdog-interval', 'click', function() {
      const interval = document.getElementById('watchdog_interval').value;
      const statusDiv = document.getElementById('watchdog-status');
    
      fetch('/admin/watchdog_set_interval', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: `watchdog_interval=${interval}`
      })
      .then(response => {
          if (response.ok) {
              statusDiv.innerHTML = '<span style="color: #22c55e;">✓ Interval updated successfully</span>';
          } else {
              statusDiv.innerHTML = '<span style="color: #dc3545;">✗ Failed to update interval</span>';
          }
          setTimeout(() => {
              statusDiv.innerHTML = 'Monitors server/client processes for hangs and auto-restarts them.';
          }, 3000);
      })
      .catch(error => {
          statusDiv.innerHTML = '<span style="color: #dc3545;">✗ Error: ' + error.message + '</span>';
      });
  });

  bindById('run-watchdog-now', 'click', function() {
      const btn = this;
      const statusDiv = document.getElementById('watchdog-status');
    
      btn.disabled = true;
      btn.innerHTML = 'Running...';
      statusDiv.innerHTML = '<span style="color: #4a90e2;">Running watchdog check...</span>';
    
      fetch('/admin/watchdog_run_now', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
      })
      .then(response => response.json())
      .then(data => {
          btn.disabled = false;
          btn.innerHTML = 'Run Now';
        
          if (data.error) {
              statusDiv.innerHTML = '<span style="color: #dc3545;">✗ Error: ' + data.error + '</span>';
          } else {
              const msg = 'Checked: ' + data.processes_checked + 
                         ', Restarted: ' + data.processes_restarted + 
                         ', Healthy: ' + data.processes_healthy;
              statusDiv.innerHTML = '<span style="color: #22c55e;">✓ ' + msg + '</span>';
              // Update last run time
              loadWatchdogStatus();
          }
      })
      .catch(error => {
          btn.disabled = false;
          btn.innerHTML = 'Run Now';
          statusDiv.innerHTML = '<span style="color: #dc3545;">✗ Error running watchdog</span>';
      });
  });

  // Initialize on page load using data attribute to avoid duplicate initialization
  (function() {
      const watchdogBox = document.getElementById('watchdog_interval');
      if (watchdogBox && !watchdogBox.dataset.initialized) {
          watchdogBox.dataset.initialized = 'true';
          if (document.readyState === 'loading') {
              document.addEventListener('DOMContentLoaded', loadWatchdogStatus);
          } else {
              loadWatchdogStatus();
          }
      }
  })();

  const tableDivOpinionGroups = document.getElementById('opinion_groups_table');

  const updateUrlOpinionGroups = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributesOpinionGroups = (data, row, col) => {
      if (row) {
          const columnId = col.id;
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': columnId
          };
      } else {
          return {};
      }
  };

  const gridOpinionGroups = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'name',
              name: 'Group Name',
              attributes: editableCellAttributesOpinionGroups
          },
          {
              id: 'lower_bound',
              name: 'Lower Bound',
              attributes: editableCellAttributesOpinionGroups
          },
          {
              id: 'upper_bound',
              name: 'Upper Bound',
              attributes: editableCellAttributesOpinionGroups
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_opinion_group/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          gridOpinionGroups.forceRender();
                                      } else {
                                          alert("Failed to delete opinion group.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/opinion_groups_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrlOpinionGroups(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'name', 'lower_bound', 'upper_bound'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrlOpinionGroups(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrlOpinionGroups(prev, { start: page * limit, length: limit }),
          },
      },
  });

  gridOpinionGroups.render(tableDivOpinionGroups);

  // Inline editing
  let savedValueOpinionGroups;

  tableDivOpinionGroups.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValueOpinionGroups = ev.target.textContent;
      }
  });

  tableDivOpinionGroups.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValueOpinionGroups !== ev.target.textContent) {
              fetch('/admin/opinion_groups_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValueOpinionGroups = undefined;
      }
  });

  tableDivOpinionGroups.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValueOpinionGroups;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const tableDivOpinionDistributions = document.getElementById('opinion_distributions_table');

  const updateUrlOpinionDistributions = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  const editableCellAttributesOpinionDistributions = (data, row, col) => {
      if (row && col.id === 'name') {
          return {
              contentEditable: 'true',
              'data-element-id': row.cells[0].data,
              'data-column-id': 'name'
          };
      } else {
          return {};
      }
  };

  const gridOpinionDistributions = new gridjs.Grid({
      columns: [
          { id: 'id', hidden: true },
          {
              id: 'name',
              name: 'Name',
              attributes: editableCellAttributesOpinionDistributions
          },
          {
              id: 'distribution_type',
              name: 'Distribution Type',
              width: '20%'
          },
          {
              id: 'parameters',
              name: 'Parameters',
              width: '40%',
              formatter: (cell) => {
                  try {
                      const params = JSON.parse(cell);
                      return gridjs.html(`<small><code>${JSON.stringify(params, null, 0)}</code></small>`);
                  } catch {
                      return cell;
                  }
              }
          },
          {
              name: 'Actions',
              attributes: () => ({ style: 'text-align: center;' }),
              formatter: (cell, row) => {
                  return gridjs.h(
                      'div',
                      { style: 'display: flex; justify-content: center;' },
                      gridjs.h(
                          'button',
                          {
                              className: 'btn btn-sm btn-danger',
                              onClick: () => {
                                  const id = row.cells[0].data;
                                  fetch(`/admin/delete_opinion_distribution/${id}`, {
                                      method: 'DELETE',
                                  }).then(res => {
                                      if (res.ok) {
                                          gridOpinionDistributions.forceRender();
                                      } else {
                                          alert("Failed to delete opinion distribution.");
                                      }
                                  });
                              }
                          },
                          'Delete'
                      )
                  );
              }
          }
      ],
      server: {
          url: '/admin/opinion_distributions_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => updateUrlOpinionDistributions(prev, { search }),
          },
      },
      sort: {
          enabled: true,
          multiColumn: true,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['id', 'name', 'distribution_type', 'parameters'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrlOpinionDistributions(prev, { sort });
              },
          },
      },
      pagination: {
          limit: 5,
          enabled: true,
          server: {
              url: (prev, page, limit) => updateUrlOpinionDistributions(prev, { start: page * limit, length: limit }),
          },
      },
  });

  gridOpinionDistributions.render(tableDivOpinionDistributions);

  // Inline editing for name only
  let savedValueOpinionDistributions;

  tableDivOpinionDistributions.addEventListener('focusin', ev => {
      if (ev.target.tagName === 'TD') {
          savedValueOpinionDistributions = ev.target.textContent;
      }
  });

  tableDivOpinionDistributions.addEventListener('focusout', ev => {
      if (ev.target.tagName === 'TD' && ev.target.dataset.elementId) {
          if (savedValueOpinionDistributions !== ev.target.textContent) {
              fetch('/admin/opinion_distributions_data', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({
                      id: ev.target.dataset.elementId,
                      [ev.target.dataset.columnId]: ev.target.textContent
                  }),
              });
          }
          savedValueOpinionDistributions = undefined;
      }
  });

  tableDivOpinionDistributions.addEventListener('keydown', ev => {
      if (ev.target.tagName === 'TD') {
          if (ev.key === 'Escape') {
              ev.target.textContent = savedValueOpinionDistributions;
              ev.target.blur();
          } else if (ev.key === 'Enter') {
              ev.preventDefault();
              ev.target.blur();
          }
      }
  });

  const distributionParams = {
      'uniform': [
          { name: 'low', label: 'Low', type: 'number', step: '0.01', default: '0' },
          { name: 'high', label: 'High', type: 'number', step: '0.01', default: '1' }
      ],
      'beta': [
          { name: 'a', label: 'Alpha (a)', type: 'number', step: '0.1', default: '2' },
          { name: 'b', label: 'Beta (b)', type: 'number', step: '0.1', default: '5' }
      ],
      'normal': [
          { name: 'loc', label: 'Mean (μ)', type: 'number', step: '0.01', default: '0.5' },
          { name: 'scale', label: 'Std Dev (σ)', type: 'number', step: '0.01', default: '0.1' }
      ],
      'exponential': [
          { name: 'scale', label: 'Scale (1/λ)', type: 'number', step: '0.01', default: '1' }
      ],
      'gamma': [
          { name: 'shape', label: 'Shape (k)', type: 'number', step: '0.1', default: '2' },
          { name: 'scale', label: 'Scale (θ)', type: 'number', step: '0.01', default: '1' }
      ],
      'binomial': [
          { name: 'n', label: 'Trials (n)', type: 'number', step: '1', default: '10' },
          { name: 'p', label: 'Probability (p)', type: 'number', step: '0.01', default: '0.5', min: '0', max: '1' }
      ],
      'poisson': [
          { name: 'lam', label: 'Lambda (λ)', type: 'number', step: '0.1', default: '3' }
      ],
      'lognormal': [
          { name: 'mean', label: 'Mean', type: 'number', step: '0.01', default: '0' },
          { name: 'sigma', label: 'Sigma (σ)', type: 'number', step: '0.01', default: '1' }
      ]
  };

  function updateDistributionParams() {
      const distType = document.getElementById('dist-type').value;
      const container = document.getElementById('dist-params-container');
    
      if (!distType || !distributionParams[distType]) {
          container.style.display = 'none';
          container.innerHTML = '';
          return;
      }
    
      container.style.display = 'block';
      container.innerHTML = '';
    
      const params = distributionParams[distType];
      params.forEach(param => {
          const line = document.createElement('div');
          line.className = 'box-line';
          line.innerHTML = `
              <span class="left">${param.label}</span>
              <span class="right">
                  <input type="${param.type}" 
                         class="input dist-param" 
                         data-param-name="${param.name}" 
                         step="${param.step}" 
                         value="${param.default}"
                         ${param.min !== undefined ? 'min="' + param.min + '"' : ''}
                         ${param.max !== undefined ? 'max="' + param.max + '"' : ''}
                         required>
              </span>
          `;
          container.appendChild(line);
      });
  }

  bindById('opinion-dist-form', 'submit', function(e) {
      const distType = document.getElementById('dist-type').value;
      const params = {};
      let hasError = false;
    
      document.querySelectorAll('.dist-param').forEach(input => {
          const paramName = input.dataset.paramName;
          const value = parseFloat(input.value);
          if (isNaN(value)) {
              alert(`Invalid value for ${paramName}: must be a valid number`);
              hasError = true;
              return;
          }
          params[paramName] = value;
      });
    
      if (hasError) {
          e.preventDefault();
          return false;
      }
    
      document.getElementById('dist-params-json').value = JSON.stringify(params);
  });

  function switchMiscTab(tabName) {
      // Hide all tabs
      document.querySelectorAll('.misc-tab-content').forEach(tab => {
          tab.classList.remove('active');
      });
      // Remove active from all buttons
      document.querySelectorAll('.misc-tab').forEach(btn => {
          btn.classList.remove('active');
      });
      // Show selected tab
      document.getElementById('tab-' + tabName).classList.add('active');
      // Set button as active
      event.target.classList.add('active');
  }

  $(document).ready(function () {
              if (!YS_DATA_MISCELLANEA.pullId) {
                  return;
              }
              // Start the background progress as soon as the page loads
              $.ajax({
                  url: `/admin/pull_progress/${YS_DATA_MISCELLANEA.pullId}`,
                  method: 'GET'
              });

              // Poll progress updates
              function pullProgress() {
                  $.ajax({
                      url: `/admin/pull_progress/${YS_DATA_MISCELLANEA.pullId}`,
                      method: 'GET',
                      dataType: 'json',
                      success: function (data) {
                          const modelName = data.model_name;
                          const percentage = data.progress;
                          const progressBar = $('#pull-progress-bar_' + YS_DATA_MISCELLANEA.pullId + '');
                          const textContainer = document.getElementById('model_pull_name_' + YS_DATA_MISCELLANEA.pullId + '');
                        
                          // Update model name display
                          if (textContainer) {
                              textContainer.textContent = modelName;
                          }

                          progressBar.css('width', percentage + '%');
                          progressBar.attr('aria-valuenow', percentage);
                          progressBar.text(percentage + '%');

                          if (percentage >= 100) {
                              setTimeout(function () {
                                  location.reload();
                              }, 1000);
                          } else {
                              setTimeout(pullProgress, 1000);
                          }
                      },
                      error: function () {
                          setTimeout(pullProgress, 1000);
                      }
                  });
              }

              pullProgress();
          });

  const llmModelsTableDiv = document.getElementById('llm-models-table');

  const updateUrlLLM = (prev, query) => {
      return prev + (prev.indexOf('?') >= 0 ? '&' : '?') + new URLSearchParams(query).toString();
  };

  if (llmModelsTableDiv) {
  new gridjs.Grid({
      columns: [
          { id: 'model_name', name: 'Model Name', sort: true },
          {
              id: 'actions',
              name: 'Actions',
              sort: false,
              formatter: (cell, row) => {
                  const modelName = row.cells[0].data;
                  const backend = (window.YS_DATA_MISCELLANEA && YS_DATA_MISCELLANEA.llmBackend) || '';

                  // Only show delete button for Ollama backend
                  if (backend === 'ollama') {
                      return gridjs.html(`
                          <div style="display: flex; gap: 8px; justify-content: center;">
                              <a href="/admin/delete_model/${encodeURIComponent(modelName)}"
                                 style="background-color: #dc3545; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-size: 0.85rem;">
                                  Delete
                              </a>
                          </div>
                      `);
                  } else {
                      return gridjs.html(`<div style="text-align: center;">-</div>`);
                  }
              }
          },
      ],
      server: {
          url: '/admin/models_data',
          then: results => results.data,
          total: results => results.total,
      },
      search: {
          enabled: true,
          server: {
              url: (prev, search) => {
                  return updateUrlLLM(prev, { search });
              },
          },
      },
      sort: {
          enabled: true,
          multiColumn: false,
          server: {
              url: (prev, columns) => {
                  const columnIds = ['model_name'];
                  const sort = columns.map(col => (col.direction === 1 ? '+' : '-') + columnIds[col.index]);
                  return updateUrlLLM(prev, { sort });
              },
          },
      },
      pagination: {
          enabled: true,
          limit: 10,
          server: {
              url: (prev, page, limit) => {
                  return updateUrlLLM(prev, { start: page * limit, length: limit });
              },
          },
      },
  }).render(llmModelsTableDiv);
  }

  Object.assign(window, {
      switchMiscTab,
      updateDistributionParams
  });
})();
