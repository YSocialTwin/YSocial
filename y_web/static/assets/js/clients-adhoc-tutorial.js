(function() {
    const steps = [
        {
            id: 'adhoc-form',
            selector: '#box-new-client',
            title: 'Ad Hoc Client Form',
            description: 'This form creates or updates plugin-backed ad hoc clients for a selected experiment.',
            position: 'top'
        },
        {
            id: 'adhoc-agent-type',
            selector: '#adhoc-agent-type-line',
            title: 'Agent Type',
            description: 'Pick the plugin family first. This drives which populations and optional settings become available.',
            position: 'bottom'
        },
        {
            id: 'adhoc-population',
            selector: '#adhoc-population-line',
            title: 'Population Mapping',
            description: 'Only compatible populations for the selected ad hoc type are shown to prevent invalid client configuration.',
            position: 'bottom'
        },
        {
            id: 'adhoc-simulation',
            selector: '#section-simulation-params',
            title: 'Simulation Parameters',
            description: 'Configure duration and clock behavior. These values control execution cadence and stop conditions.',
            position: 'top'
        },
        {
            id: 'adhoc-agent-settings',
            selector: '#adhoc_agent_settings_section',
            title: 'Agent-Specific Settings',
            description: 'Plugin-defined controls appear here when required by the selected ad hoc agent type.',
            position: 'top'
        },
        {
            id: 'adhoc-llm',
            selector: '#adhoc_llm_section',
            title: 'LLM Configuration',
            description: 'This section is displayed only for agent families that require LLM inference.',
            position: 'top'
        },
        {
            id: 'adhoc-reference',
            selector: '#adhoc-quick-reference',
            title: 'Quick Reference',
            description: 'Use this panel for constraints and defaults while configuring ad hoc clients.',
            position: 'left',
            isLast: true
        }
    ];

    const filtered = steps.filter((step) => {
        const element = document.querySelector(step.selector);
        return element && element.offsetParent !== null;
    });
    if (filtered.length > 0) {
        filtered.forEach((step) => { step.isLast = false; });
        filtered[filtered.length - 1].isLast = true;
    }

    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            if (!filtered.length || !window.PageTutorialEngine) return;
            const tutorial = window.PageTutorialEngine.init('clients_adhoc', filtered);
            if (tutorial) {
                window.startClientsAdhocTutorial = tutorial.start;
            }
        }, 500);
    });
})();
