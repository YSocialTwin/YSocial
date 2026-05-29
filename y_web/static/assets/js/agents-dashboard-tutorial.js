(function() {
    const steps = [
        {
            id: 'agents-dashboard-hero',
            selector: '#agents-dashboard-hero',
            title: 'Agent Workspace Overview',
            description: 'This dashboard is the entry point for creating user agents, pages, and plugin-backed resources.',
            position: 'bottom'
        },
        {
            id: 'resource-groups',
            selector: '[data-agent-resource-group]',
            title: 'Resource Groups',
            description: 'Resources are organized by group to separate standard flows and plugin-provided capabilities.',
            position: 'top'
        },
        {
            id: 'resource-cards',
            selector: '[data-agent-resource-card]',
            title: 'Resource Cards',
            description: 'Each card opens the dedicated creation interface for that resource type.',
            position: 'right',
            isLast: true
        }
    ];

    const filtered = steps.filter((step) => document.querySelector(step.selector));
    if (filtered.length > 0) {
        filtered.forEach((step) => { step.isLast = false; });
        filtered[filtered.length - 1].isLast = true;
    }

    document.addEventListener('DOMContentLoaded', function() {
        if (!filtered.length || !window.PageTutorialEngine) return;
        const tutorial = window.PageTutorialEngine.init('agents_dashboard', filtered);
        if (tutorial) {
            window.startAgentsDashboardTutorial = tutorial.start;
        }
    });
})();
