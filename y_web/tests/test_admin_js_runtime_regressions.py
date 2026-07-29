import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path("/Users/rossetti/PycharmProjects/YWeb")
STATIC_JS_DIR = REPO_ROOT / "y_web" / "static" / "assets" / "js"


def test_all_admin_js_files_parse_with_node():
    failures = []
    for path in sorted(STATIC_JS_DIR.glob("admin-*.js")):
        result = subprocess.run(
            ["node", "-c", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            failures.append((path, result.stderr))

    assert not failures, failures


def test_admin_experiments_has_no_literal_admin_placeholder_urls():
    content = (STATIC_JS_DIR / "admin-experiments.js").read_text(encoding="utf-8")
    bad_literals = [
        "fetch('/admin/experiment_trends/${YS_DATA_EXP.expId}')",
        "fetch('/admin/experiment_logs/${YS_DATA_EXP.expId}')",
        "fetch('/admin/experiment_trends/${YS_DATA_EXP_FORUM.expId}')",
        "fetch('/admin/experiment_logs/${YS_DATA_EXP_FORUM.expId}')",
        "url: '/admin/progress/${YS_DATA_EXP.clientId}'",
        "url: '/admin/progress/${YS_DATA_EXP_FORUM.clientId}'",
    ]
    for literal in bad_literals:
        assert literal not in content


def test_admin_shared_bundles_guard_optional_page_sections():
    populations = (STATIC_JS_DIR / "admin-populations.js").read_text(encoding="utf-8")
    miscellanea = (STATIC_JS_DIR / "admin-miscellanea.js").read_text(encoding="utf-8")
    settings = (STATIC_JS_DIR / "admin-settings.js").read_text(encoding="utf-8")
    dashboard = (STATIC_JS_DIR / "admin-dashboard.js").read_text(encoding="utf-8")
    experiments = (STATIC_JS_DIR / "admin-experiments.js").read_text(encoding="utf-8")

    assert "const popDetails = window.YS_DATA_POP_DETAILS;" in populations
    assert "if (popDetails) {" in populations
    assert "if (tableDiv) {" in populations
    assert "if (llmModelsTableDiv) {" in miscellanea
    assert "hpc_max_hpc_simulations_per_vllm_worker" not in miscellanea
    assert "save-hpc-monitor-settings-secondary" not in miscellanea
    assert "boxDiv.classList.remove('d-none');" in settings
    assert "boxDiv.classList.add('d-none');" in settings
    assert "function renderExperimentProgressBadge(exp, statusFilter)" in settings
    assert "EXP_STATUS.STOPPED_SCHEDULED" in settings
    assert "progress_label" in settings
    assert "NA" in settings
    assert "function pollClientProgress(" not in settings
    assert "setInterval(updateProgress, 2000)" not in settings
    assert "fetch(`/admin/experiment_clients/${expId}`)" in settings
    assert "function pollAllClientProgress(" not in dashboard
    assert "fetch(`/admin/progress/${clientId}`)" not in dashboard
    assert (
        "setInterval(refreshAllClientProgress, PROGRESS_REFRESH_INTERVAL)" in dashboard
    )
    assert 'data-exp-id="' in dashboard
    assert "async function pollAllClientProgress()" in experiments
    assert "const results = await Promise.all(" in experiments


def test_admin_clients_network_parameter_rows_toggle_bootstrap_visibility():
    clients = (STATIC_JS_DIR / "admin-clients.js").read_text(encoding="utf-8")

    # The shared bundle contains one network toggle implementation per client form
    # variant. Showing a row must remove Bootstrap's d-none; hiding must restore it.
    assert clients.count("function hideNetworkField(field) {") == 3
    assert clients.count("field.classList.add('d-none');") >= 3
    assert clients.count("function showNetworkField(field) {") == 3
    assert clients.count("field.classList.remove('d-none');") >= 3


def test_admin_populations_percentage_rows_toggle_bootstrap_visibility():
    populations = (STATIC_JS_DIR / "admin-populations.js").read_text(encoding="utf-8")

    assert "containerRow.classList.add('d-none');" in populations
    assert "containerRow.classList.remove('d-none');" in populations


def test_new_experiment_form_no_longer_contains_annotation_toggles():
    settings = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "settings.html"
    ).read_text(encoding="utf-8")

    assert "Generated Content Annotation" not in settings
    assert 'name="toxicity_annotation"' not in settings
    assert 'name="sentiment_annotation"' not in settings
    assert 'name="emotion_annotation"' not in settings
    assert 'name="opinion_annotation"' not in settings
    assert 'name="perspective_api"' not in settings


def test_new_experiment_form_hides_description_and_experiment_type_controls():
    settings = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "settings.html"
    ).read_text(encoding="utf-8")
    admin_settings_js = (STATIC_JS_DIR / "admin-settings.js").read_text(
        encoding="utf-8"
    )

    assert '<span class="left">Description</span>' not in settings
    assert 'name="exp_descr"' not in settings
    assert '<span class="left">Experiment Type</span>' not in settings
    assert 'id="remote_experiment_toggle"' not in settings
    assert 'name="is_remote" value="false"' in settings
    assert (
        "if (!simulatorTypeInput || !platformTypeSelect || !hpcToggle || !hpcToggleLabel || !hpcInfoInline || !redisConfigBox || !llmAgentsToggle) {"
        in admin_settings_js
    )


def test_new_experiment_form_uses_repo_availability_bridge():
    settings = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "settings.html"
    ).read_text(encoding="utf-8")
    admin_settings_js = (STATIC_JS_DIR / "admin-settings.js").read_text(
        encoding="utf-8"
    )

    assert "repoAvailability:" in settings
    assert "const repoAvailability =" in admin_settings_js
    assert (
        "const microbloggingAvailable = !!repoAvailability.microblogging;"
        in admin_settings_js
    )
    assert "const hpcAvailable = !!repoAvailability.hpc;" in admin_settings_js
    assert "const forumAvailable = !!repoAvailability.forum;" in admin_settings_js
    assert "hpcToggleLabel.textContent = 'Required';" in admin_settings_js
    assert (
        "microbloggingOption.disabled = !microbloggingAvailable && !hpcAvailable;"
        in admin_settings_js
    )


def test_copy_group_box_is_present_in_admin_settings():
    settings = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "settings.html"
    ).read_text(encoding="utf-8")

    assert "Copy Rules" not in settings
    assert "ROW 4: Copy Experiment + Copy Group + Experiment Matrix" in settings
    assert 'id="box-copy-group"' in settings
    assert 'action="/admin/copy_experiment_group"' in settings
    assert 'name="source_group"' in settings
    assert 'id="copy_source_group"' in settings
    assert 'name="target_group"' in settings
    assert 'id="copy_target_group"' in settings
    assert "Copy Group" in settings
    assert settings.count("is-12-tablet is-4-desktop ys-flex-col") == 3
    assert settings.index('id="box-copy-experiment"') < settings.index(
        'id="box-copy-group"'
    ) < settings.index('id="box-experiment-matrix"')


def test_experiment_matrix_box_filters_source_experiments_by_group():
    settings = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "settings.html"
    ).read_text(encoding="utf-8")
    matrix_template = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "experiment_matrix.html"
    ).read_text(encoding="utf-8")
    admin_settings_js = (STATIC_JS_DIR / "admin-settings.js").read_text(
        encoding="utf-8"
    )

    assert 'id="matrix_exp_group_select"' in settings
    assert 'id="matrix_source_exp_id"' in settings
    assert "Select a group first..." in settings
    assert "Choose a source experiment from the selected group." in settings
    assert "Target Group" in (
        REPO_ROOT / "y_web" / "templates" / "admin" / "experiment_matrix.html"
    ).read_text(encoding="utf-8")
    assert "function syncTargetGroupFields()" in matrix_template
    assert (
        "targetGroupInput.addEventListener('input', syncTargetGroupFields)"
        in matrix_template
    )
    assert (
        "matrixForm.addEventListener('submit', syncTargetGroupFields)"
        in matrix_template
    )
    assert "matrixExperiments:" in settings
    assert "function initializeMatrixExperimentSelector()" in admin_settings_js
    assert "matrix_exp_group_select" in admin_settings_js
    assert "matrix_source_exp_id" in admin_settings_js
    assert "String(item.group || '').trim() === groupName" in admin_settings_js
    assert "option.textContent = exp.name;" in admin_settings_js


def test_experiment_matrix_page_separates_source_group_and_target_group():
    matrix_template = (
        REPO_ROOT / "y_web" / "templates" / "admin" / "experiment_matrix.html"
    ).read_text(encoding="utf-8")
    matrix_crud = (
        REPO_ROOT / "y_web" / "routes" / "admin" / "sub" / "experiments" / "_crud.py"
    ).read_text(encoding="utf-8")

    assert 'id="matrix-source-group"' in matrix_template
    assert 'name="source_group"' in matrix_template
    assert 'id="matrix-target-group"' in matrix_template
    assert 'name="target_group"' in matrix_template
    assert "Choose an existing group or type a new one" in matrix_template
    assert (
        "You can assign the generated experiments to an existing group or create a new one here."
        in matrix_template
    )
    assert "selected_source_group" in matrix_template
    assert "selected_source_group" in matrix_crud
    assert (
        'source_group = (request.values.get("source_group") or "").strip()'
        in matrix_crud
    )
    assert "grouped_experiments = _matrix_filter_experiments_by_group(" in matrix_crud
