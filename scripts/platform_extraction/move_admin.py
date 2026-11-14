import ast, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_funcs import extract, imports_of, undefined
from rewrite_imports import convert

MANUAL = {
    "_hpc_prompts_filename": "hpc_prompts_filename",
    "_redirect_to_details_page": "redirect_to_details_page",
    "_opinion_configuration_internal": "opinion_configuration_internal",
    "_resolve_opinion_submission_context": "resolve_opinion_submission_context",
    "_apply_opinion_distributions_to_population": "apply_opinion_distributions_to_population",
    "_persist_non_hpc_opinion_dynamics": "persist_non_hpc_opinion_dynamics",
    "_invalidate_opinion_evolution_cache_for_experiment": "invalidate_opinion_evolution_cache_for_experiment",
    "_sync_initial_standard_opinions_to_experiment_db": "sync_initial_standard_opinions_to_experiment_db",
    "_update_client_simulation_internal": "update_client_simulation_internal",
    "_update_recsys_internal": "update_recsys_internal",
    "_update_client_llm_internal": "update_client_llm_internal",
    "_apply_population_attributes_to_client_config": "apply_population_attributes_to_client_config",
    "_provider_of": "provider_of",
    "_opinion_dynamics_enabled_for_client_creation": "opinion_dynamics_enabled_for_client_creation",
    "_memory_enabled_for_client_creation": "memory_enabled_for_client_creation",
    "_apply_structured_features_to_agent_payload": "apply_structured_features_to_agent_payload",
    "_build_client_creation_context": "build_client_creation_context",
    "_redirect_to_clients_page": "redirect_to_clients_page",
}


def move(src_path, names, dest_path, clients=False, header_doc="", keep=False):
    orig_imports, orig_defs = imports_of(src_path)
    code = extract(src_path, names, write_back=not keep)
    und = undefined(code)
    lines = []
    manual = []
    for n in und:
        if n in orig_imports:
            mod, name, asname = orig_imports[n]
            if mod is None:
                lines.append(f"import {name}" + (f" as {asname}" if asname else ""))
            else:
                lines.append(
                    f"from {mod} import {name}" + (f" as {asname}" if asname else "")
                )
        elif n in MANUAL:
            lines.append(f"from y_web.sdk.web import {MANUAL[n]} as {n}")
        elif n in orig_defs:
            manual.append(n)
        else:
            manual.append(n)
    body = "\n".join(sorted(set(lines)))
    text = f'"""{header_doc}"""\n\n{body}\n\n\n{code}\n'
    text = convert(text, "", clients_pkg=clients)
    return text, manual


if __name__ == "__main__":
    pass
