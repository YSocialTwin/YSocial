/* Scenario Design -- Fase 9 frontend (piano tecnico §14).
 *
 * Vanilla JS, no build step, no framework and no external library --
 * consistent with Fase 1's own placeholder note that a future
 * `plugin.js` would live here, and with this suite's own standalone
 * test requirement that the backend package stays importable/testable
 * without a frontend toolchain. Every call below hits an endpoint that
 * already exists and is already covered by this repo's own integration
 * tests (y_web/tests/test_scenario_design_fase*.py); this file adds no
 * new backend behaviour, only a client for it.
 *
 * Deliberately minimal styling (see the inline <style> in the page
 * shell) -- this closes the *functional* gap recorded in
 * docs/acceptance.md (criteria 3, 6, 7, 9, 10, 11, 12), not a pixel-
 * perfect rendering of scenario_design_mockup_*.svg.
 */
(function () {
  "use strict";

  const API = "/admin/scenario_design/api";

  const state = {
    exp: null,
    scenario: null,
    thread: null,
    roles: [],
    topics: [],
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "text") node.textContent = v;
      else if (k === "html") node.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    });
    (children || []).forEach((c) => c && node.appendChild(c));
    return node;
  }

  async function api(method, path, body) {
    const resp = await fetch(API + path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try {
      data = await resp.json();
    } catch (e) {
      data = null;
    }
    if (!resp.ok || (data && data.ok === false)) {
      const err = (data && data.error) || { code: "unknown_error", message: `HTTP ${resp.status}` };
      const e = new Error(err.message);
      e.code = err.code;
      e.status = resp.status;
      throw e;
    }
    return data;
  }

  function showError(container, err) {
    container.appendChild(
      el("div", { class: "sd-error", text: `${err.code || "error"}: ${err.message}` })
    );
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  // ------------------------------------------------------------------
  // Root layout
  // ------------------------------------------------------------------
  function mount() {
    const root = document.getElementById("sd-root");
    clear(root);
    root.appendChild(el("h1", { text: "Scenario Design" }));
    const expPicker = el("div", { class: "sd-panel", id: "sd-exp-picker" });
    root.appendChild(expPicker);
    const workspace = el("div", { id: "sd-workspace" });
    root.appendChild(workspace);
    loadExperiments(expPicker, workspace);
  }

  async function loadExperiments(container, workspace) {
    clear(container);
    container.appendChild(el("h2", { text: "Experiment" }));
    try {
      const { experiments } = await api("GET", "/experiments");
      if (!experiments.length) {
        container.appendChild(
          el("p", { text: "No eligible (microblogging) experiments found." })
        );
        return;
      }
      const select = el("select", { id: "sd-exp-select" });
      select.appendChild(el("option", { value: "", text: "-- choose an experiment --" }));
      experiments.forEach((exp) => {
        select.appendChild(
          el("option", {
            value: String(exp.id),
            text: `#${exp.id} ${exp.name} (${exp.simulator_type}${exp.running ? ", RUNNING" : ""})`,
          })
        );
      });
      select.addEventListener("change", () => {
        const exp = experiments.find((e) => String(e.id) === select.value);
        state.exp = exp || null;
        state.scenario = null;
        state.thread = null;
        renderWorkspace(workspace);
      });
      container.appendChild(select);
    } catch (err) {
      showError(container, err);
    }
  }

  // ------------------------------------------------------------------
  // Scenario list / create / duplicate / archive
  // ------------------------------------------------------------------
  async function renderWorkspace(workspace) {
    clear(workspace);
    if (!state.exp) return;

    const scenarioPanel = el("div", { class: "sd-panel" });
    workspace.appendChild(scenarioPanel);
    await renderScenarioList(scenarioPanel, workspace);
  }

  async function renderScenarioList(panel, workspace) {
    clear(panel);
    panel.appendChild(el("h2", { text: `Scenarios for experiment #${state.exp.id}` }));

    const createForm = el("form", { class: "sd-inline-form" });
    const nameInput = el("input", { type: "text", placeholder: "New scenario name", required: "required" });
    createForm.appendChild(nameInput);
    const createBtn = el("button", { type: "submit", text: "Create scenario" });
    createForm.appendChild(createBtn);
    createForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api("POST", `/experiments/${state.exp.id}/scenarios`, { name: nameInput.value });
        await renderScenarioList(panel, workspace);
      } catch (err) {
        showError(panel, err);
      }
    });
    panel.appendChild(createForm);

    try {
      const { scenarios } = await api("GET", `/experiments/${state.exp.id}/scenarios`);
      const list = el("ul", { class: "sd-list" });
      scenarios.forEach((sc) => {
        const openBtn = el("button", {
          text: `${sc.name} [${sc.status}]`,
          onclick: () => {
            state.scenario = sc;
            state.thread = null;
            renderScenarioWorkspace(workspace, panel);
          },
        });
        const dupBtn = el("button", {
          text: "Duplicate",
          onclick: async () => {
            try {
              await api("POST", `/experiments/${state.exp.id}/scenarios/${sc.id}/duplicate`);
              await renderScenarioList(panel, workspace);
            } catch (err) {
              showError(panel, err);
            }
          },
        });
        const archiveBtn = el("button", {
          text: "Archive",
          onclick: async () => {
            try {
              await api("POST", `/experiments/${state.exp.id}/scenarios/${sc.id}/archive`);
              await renderScenarioList(panel, workspace);
            } catch (err) {
              showError(panel, err);
            }
          },
        });
        const deleteBtn = el("button", {
          text: "Delete",
          onclick: async () => {
            try {
              await api("DELETE", `/experiments/${state.exp.id}/scenarios/${sc.id}`);
              await renderScenarioList(panel, workspace);
            } catch (err) {
              showError(panel, err);
            }
          },
        });
        list.appendChild(el("li", {}, [openBtn, dupBtn, archiveBtn, deleteBtn]));
      });
      panel.appendChild(list);
    } catch (err) {
      showError(panel, err);
    }
  }

  // ------------------------------------------------------------------
  // Scenario workspace: tabs (Threads, Validate/Publish, Audit, Real Content)
  // ------------------------------------------------------------------
  async function renderScenarioWorkspace(workspace, scenarioListPanel) {
    // Remove any previous scenario-detail panel (keep the scenario list
    // panel, which is workspace's first child).
    while (workspace.children.length > 1) workspace.removeChild(workspace.lastChild);
    if (!state.scenario) return;

    const detail = el("div", { class: "sd-panel" });
    workspace.appendChild(detail);
    detail.appendChild(
      el("h2", { text: `Scenario: ${state.scenario.name} (#${state.scenario.id})` })
    );

    const tabs = el("div", { class: "sd-tabs" });
    const body = el("div", { class: "sd-tab-body" });
    detail.appendChild(tabs);
    detail.appendChild(body);

    const tabDefs = [
      ["Threads", renderThreadsTab],
      ["Validate / Publish", renderPublishTab],
      ["Audit", renderAuditTab],
      ["Real Content", renderRealContentTab],
    ];
    tabDefs.forEach(([label, renderer]) => {
      tabs.appendChild(
        el("button", {
          text: label,
          onclick: () => {
            clear(body);
            renderer(body);
          },
        })
      );
    });
    // Default tab.
    renderThreadsTab(body);
  }

  // ------------------------------------------------------------------
  // Threads tab
  // ------------------------------------------------------------------
  async function renderThreadsTab(body) {
    clear(body);
    const layout = el("div", { class: "sd-two-col" });
    const threadsCol = el("div", { class: "sd-col" });
    const postsCol = el("div", { class: "sd-col" });
    layout.appendChild(threadsCol);
    layout.appendChild(postsCol);
    body.appendChild(layout);

    if (!state.roles.length) {
      try {
        state.roles = (await api("GET", "/roles")).roles;
      } catch (e) {
        state.roles = [{ key: "standard", label: "Standard" }];
      }
    }
    if (!state.topics.length) {
      try {
        state.topics = (await api("GET", "/vocab/topics")).topics;
      } catch (e) {
        state.topics = [];
      }
    }

    await renderThreadList(threadsCol, postsCol);
  }

  async function renderThreadList(threadsCol, postsCol) {
    clear(threadsCol);
    threadsCol.appendChild(el("h3", { text: "Threads" }));

    const createForm = el("form", { class: "sd-inline-form" });
    const tmpIdInput = el("input", { type: "text", placeholder: "thread tmp_id", required: "required" });
    createForm.appendChild(tmpIdInput);
    createForm.appendChild(el("button", { type: "submit", text: "Add thread" }));
    createForm.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api(
          "POST",
          `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/threads`,
          { tmp_id: tmpIdInput.value }
        );
        await renderThreadList(threadsCol, postsCol);
      } catch (err) {
        showError(threadsCol, err);
      }
    });
    threadsCol.appendChild(createForm);

    const bulkBtn = el("button", {
      text: "Bulk delete ALL threads",
      onclick: async () => {
        const confirmName = window.prompt(
          `Type the scenario's exact name ("${state.scenario.name}") to confirm bulk delete:`
        );
        if (confirmName === null) return;
        try {
          await api(
            "POST",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/bulk_delete_threads`,
            { confirm_name: confirmName }
          );
          state.thread = null;
          clear(postsCol);
          await renderThreadList(threadsCol, postsCol);
        } catch (err) {
          showError(threadsCol, err);
        }
      },
    });
    threadsCol.appendChild(bulkBtn);

    try {
      const { threads } = await api(
        "GET",
        `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/threads`
      );
      const list = el("ul", { class: "sd-list" });
      threads.forEach((t) => {
        const openBtn = el("button", {
          text: t.title ? `${t.tmp_id} - ${t.title}` : t.tmp_id,
          onclick: () => {
            state.thread = t;
            renderPostsTree(postsCol, threadsCol);
          },
        });
        const delBtn = el("button", {
          text: "Delete thread",
          onclick: async () => {
            try {
              await api(
                "DELETE",
                `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/threads/${t.id}`
              );
              if (state.thread && state.thread.id === t.id) {
                state.thread = null;
                clear(postsCol);
              }
              await renderThreadList(threadsCol, postsCol);
            } catch (err) {
              showError(threadsCol, err);
            }
          },
        });
        list.appendChild(el("li", {}, [openBtn, delBtn]));
      });
      threadsCol.appendChild(list);
    } catch (err) {
      showError(threadsCol, err);
    }
  }

  async function renderPostsTree(postsCol, threadsCol) {
    clear(postsCol);
    if (!state.thread) return;
    postsCol.appendChild(el("h3", { text: `Posts in thread "${state.thread.tmp_id}"` }));

    try {
      const { posts, orphan_tmp_ids } = await api(
        "GET",
        `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/threads/${state.thread.id}`
      );
      if (orphan_tmp_ids && orphan_tmp_ids.length) {
        postsCol.appendChild(
          el("div", {
            class: "sd-warning",
            text: `Orphan posts (missing parent): ${orphan_tmp_ids.join(", ")}`,
          })
        );
      }
      const byTmpId = {};
      posts.forEach((p) => (byTmpId[p.tmp_id] = p));

      posts.forEach((post) => {
        postsCol.appendChild(renderPostCard(post, postsCol, threadsCol));
      });

      postsCol.appendChild(renderAddPostForm(null, postsCol, threadsCol, "Add root post"));
    } catch (err) {
      showError(postsCol, err);
    }
  }

  function renderAddPostForm(parentTmpId, postsCol, threadsCol, label) {
    const form = el("form", { class: "sd-inline-form sd-add-post" });
    form.appendChild(el("h4", { text: label }));
    const tmpIdInput = el("input", { type: "text", placeholder: "post tmp_id", required: "required" });
    const authorInput = el("input", { type: "text", placeholder: "author_user_id" });
    const contentInput = el("textarea", { placeholder: "content", rows: "2" });
    const roleSelect = el("select", {});
    roleSelect.appendChild(el("option", { value: "", text: "(standard role)" }));
    state.roles.forEach((r) => roleSelect.appendChild(el("option", { value: r.key, text: r.label || r.key })));

    form.appendChild(tmpIdInput);
    form.appendChild(authorInput);
    form.appendChild(contentInput);
    form.appendChild(roleSelect);
    form.appendChild(el("button", { type: "submit", text: "Add" }));

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api(
          "POST",
          `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/threads/${state.thread.id}/posts`,
          {
            tmp_id: tmpIdInput.value,
            parent_tmp_id: parentTmpId,
            author_user_id: authorInput.value,
            content: contentInput.value,
            role_key: roleSelect.value || null,
          }
        );
        await renderPostsTree(postsCol, threadsCol);
      } catch (err) {
        showError(postsCol, err);
      }
    });
    return form;
  }

  function renderPostCard(post, postsCol, threadsCol) {
    const indent = post.parent_tmp_id ? "  " : "";
    const card = el("div", { class: "sd-post-card" });
    card.appendChild(
      el("div", {
        class: "sd-post-header",
        text: `${indent}[${post.tmp_id}] author=${post.author_user_id} role=${post.role_key || "standard"} status=${post.status}`,
      })
    );

    const contentArea = el("textarea", { rows: "2" });
    contentArea.value = post.content || "";
    card.appendChild(contentArea);

    const saveBtn = el("button", {
      text: "Save content",
      onclick: async () => {
        try {
          await api(
            "PUT",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/posts/${post.tmp_id}`,
            { content: contentArea.value }
          );
          await renderPostsTree(postsCol, threadsCol);
        } catch (err) {
          showError(postsCol, err);
        }
      },
    });
    card.appendChild(saveBtn);

    const replyBtn = el("button", {
      text: "Reply",
      onclick: () => {
        const existing = card.querySelector(".sd-reply-form");
        if (existing) {
          existing.remove();
          return;
        }
        const form = renderAddPostForm(post.tmp_id, postsCol, threadsCol, `Reply to ${post.tmp_id}`);
        form.classList.add("sd-reply-form");
        card.appendChild(form);
      },
    });
    card.appendChild(replyBtn);

    const deleteBtn = el("button", {
      text: "Delete (leaf only)",
      onclick: async () => {
        try {
          await api(
            "DELETE",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/posts/${post.tmp_id}`
          );
          await renderPostsTree(postsCol, threadsCol);
        } catch (err) {
          showError(postsCol, err);
        }
      },
    });
    card.appendChild(deleteBtn);

    const deleteSubtreeBtn = el("button", {
      text: "Delete subtree",
      onclick: async () => {
        if (!window.confirm(`Delete "${post.tmp_id}" and every reply to it?`)) return;
        try {
          await api(
            "POST",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/posts/${post.tmp_id}/delete_subtree`
          );
          await renderPostsTree(postsCol, threadsCol);
        } catch (err) {
          showError(postsCol, err);
        }
      },
    });
    card.appendChild(deleteSubtreeBtn);

    card.appendChild(renderLlmPanel(post, postsCol, threadsCol));
    return card;
  }

  function renderLlmPanel(post, postsCol, threadsCol) {
    const panel = el("details", { class: "sd-llm-panel" });
    panel.appendChild(el("summary", { text: "LLM generation (reuses /admin/api/fetch_models)" }));

    const hostInput = el("input", { type: "text", placeholder: "LLM endpoint host" });
    const fetchBtn = el("button", {
      type: "button",
      text: "Fetch models",
      onclick: async () => {
        try {
          const resp = await fetch(
            `/admin/api/fetch_models?llm_url=${encodeURIComponent(hostInput.value)}`
          );
          const data = await resp.json();
          clear(modelSelect);
          (data.models || []).forEach((m) => {
            const value = typeof m === "string" ? m : m.id || m.name || JSON.stringify(m);
            modelSelect.appendChild(el("option", { value, text: value }));
          });
        } catch (err) {
          showError(panel, err);
        }
      },
    });
    const modelSelect = el("select", {});
    const generateBtn = el("button", {
      type: "button",
      text: "Generate",
      onclick: async () => {
        try {
          const result = await api(
            "POST",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/posts/${post.tmp_id}/generate`,
            {
              llm_endpoint_host: hostInput.value,
              llm_endpoint_model: modelSelect.value,
            }
          );
          generatedBox.value = result.post.generated_text || "";
        } catch (err) {
          showError(panel, err);
        }
      },
    });
    const generatedBox = el("textarea", { rows: "2", placeholder: "(generated text appears here)" });
    const useBtn = el("button", {
      type: "button",
      text: "Use this draft as content",
      onclick: async () => {
        try {
          await api(
            "PUT",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/posts/${post.tmp_id}`,
            { content: generatedBox.value }
          );
          await renderPostsTree(postsCol, threadsCol);
        } catch (err) {
          showError(panel, err);
        }
      },
    });

    panel.appendChild(hostInput);
    panel.appendChild(fetchBtn);
    panel.appendChild(modelSelect);
    panel.appendChild(generateBtn);
    panel.appendChild(generatedBox);
    panel.appendChild(useBtn);
    return panel;
  }

  // ------------------------------------------------------------------
  // Validate / Preview / Publish tab
  // ------------------------------------------------------------------
  function renderPublishTab(body) {
    clear(body);
    const out = el("div", { class: "sd-output" });

    const validateBtn = el("button", {
      text: "Validate",
      onclick: async () => {
        clear(out);
        try {
          const result = await api(
            "POST",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/validate`
          );
          out.appendChild(
            el("pre", { text: JSON.stringify({ valid: result.valid, errors: result.errors }, null, 2) })
          );
        } catch (err) {
          showError(out, err);
        }
      },
    });
    const previewBtn = el("button", {
      text: "Preview",
      onclick: async () => {
        clear(out);
        try {
          const result = await api(
            "GET",
            `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/publish/preview`
          );
          out.appendChild(el("pre", { text: JSON.stringify(result.preview, null, 2) }));
        } catch (err) {
          showError(out, err);
        }
      },
    });
    const idempotencyInput = el("input", { type: "text", placeholder: "idempotency key (optional)" });
    const publishBtn = el("button", {
      text: "Publish",
      onclick: async () => {
        clear(out);
        try {
          const headers = {};
          const resp = await fetch(
            `${API}/experiments/${state.exp.id}/scenarios/${state.scenario.id}/publish`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...(idempotencyInput.value ? { "X-Idempotency-Key": idempotencyInput.value } : {}),
              },
              body: JSON.stringify({}),
            }
          );
          const data = await resp.json();
          if (!resp.ok || data.ok === false) {
            throw Object.assign(new Error((data.error && data.error.message) || "publish failed"), {
              code: data.error && data.error.code,
            });
          }
          out.appendChild(el("pre", { text: JSON.stringify(data, null, 2) }));
        } catch (err) {
          showError(out, err);
        }
      },
    });

    body.appendChild(el("div", { class: "sd-inline-form" }, [validateBtn, previewBtn, idempotencyInput, publishBtn]));
    body.appendChild(out);
  }

  // ------------------------------------------------------------------
  // Audit tab
  // ------------------------------------------------------------------
  async function renderAuditTab(body) {
    clear(body);
    try {
      const { publications, llm_generations } = await api(
        "GET",
        `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/audit`
      );
      body.appendChild(el("h3", { text: "Publications" }));
      body.appendChild(el("pre", { text: JSON.stringify(publications, null, 2) }));
      body.appendChild(el("h3", { text: "LLM generations" }));
      body.appendChild(el("pre", { text: JSON.stringify(llm_generations, null, 2) }));
    } catch (err) {
      showError(body, err);
    }
  }

  // ------------------------------------------------------------------
  // Real content tab
  // ------------------------------------------------------------------
  async function renderRealContentTab(body) {
    clear(body);
    body.appendChild(
      el("p", {
        text:
          "Browse already-published real posts from a publication run, and edit/delete them in place. Re-parenting is not supported.",
      })
    );

    let publications = [];
    try {
      publications = (
        await api("GET", `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/audit`)
      ).publications;
    } catch (err) {
      showError(body, err);
      return;
    }
    if (!publications.length) {
      body.appendChild(el("p", { text: "No publications yet for this scenario." }));
      return;
    }

    const select = el("select", {});
    select.appendChild(el("option", { value: "", text: "-- choose a publication --" }));
    publications.forEach((p) =>
      select.appendChild(el("option", { value: String(p.id), text: `#${p.id} (${p.status}, ${p.started_at})` }))
    );
    const mappingDiv = el("div", {});
    select.addEventListener("change", async () => {
      clear(mappingDiv);
      if (!select.value) return;
      try {
        const { id_mapping } = await api(
          "GET",
          `/experiments/${state.exp.id}/scenarios/${state.scenario.id}/publications/${select.value}/id_mapping`
        );
        id_mapping.forEach((m) => mappingDiv.appendChild(renderRealPostRow(m, mappingDiv)));
      } catch (err) {
        showError(mappingDiv, err);
      }
    });
    body.appendChild(select);
    body.appendChild(mappingDiv);
  }

  function renderRealPostRow(mapping, mappingDiv) {
    const row = el("div", { class: "sd-post-card" });
    row.appendChild(
      el("div", { text: `tmp_id=${mapping.tmp_id} -> real_id=${mapping.real_id}` })
    );
    const contentInput = el("textarea", { rows: "2", placeholder: "new content (leave blank to skip)" });
    const authorInput = el("input", { type: "text", placeholder: "new author_user_id (leave blank to skip)" });
    const saveBtn = el("button", {
      text: "Save edits",
      onclick: async () => {
        const body = {};
        if (contentInput.value) body.content = contentInput.value;
        if (authorInput.value) body.author_user_id = authorInput.value;
        try {
          await api("PUT", `/experiments/${state.exp.id}/real_posts/${mapping.real_id}`, body);
          row.appendChild(el("div", { class: "sd-ok", text: "Saved." }));
        } catch (err) {
          showError(row, err);
        }
      },
    });
    const deleteBtn = el("button", {
      text: "Delete (no replies only)",
      onclick: async () => {
        if (!window.confirm(`Delete real post ${mapping.real_id}?`)) return;
        try {
          await api("DELETE", `/experiments/${state.exp.id}/real_posts/${mapping.real_id}`);
          row.remove();
        } catch (err) {
          showError(row, err);
        }
      },
    });
    const deleteSubtreeBtn = el("button", {
      text: "Delete subtree",
      onclick: async () => {
        if (!window.confirm(`Delete real post ${mapping.real_id} and every real reply to it?`)) return;
        try {
          await api("POST", `/experiments/${state.exp.id}/real_posts/${mapping.real_id}/delete_subtree`);
          row.remove();
        } catch (err) {
          showError(row, err);
        }
      },
    });
    row.appendChild(contentInput);
    row.appendChild(authorInput);
    row.appendChild(saveBtn);
    row.appendChild(deleteBtn);
    row.appendChild(deleteSubtreeBtn);
    return row;
  }

  document.addEventListener("DOMContentLoaded", mount);
})();
