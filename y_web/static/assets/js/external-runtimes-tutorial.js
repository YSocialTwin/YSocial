(function() {
    const steps = [
        {
            id: 'runtime-overview',
            selector: '#external-runtimes-main',
            title: 'External Runtime Plugins',
            description: 'Use this page to install, update, validate, and remove external runtime repositories used by experiments.',
            position: 'top'
        },
        {
            id: 'github-session',
            selector: '#external-runtimes-github-session',
            title: 'GitHub Session',
            description: 'Connect a token to avoid anonymous API rate limits and to access private release assets when needed.',
            position: 'bottom'
        },
        {
            id: 'runtime-categories',
            selector: '[data-runtime-category]',
            title: 'Runtime Categories',
            description: 'Repositories are grouped by runtime families. Expand each group to inspect status, releases, branches, and maintenance actions.',
            position: 'top'
        },
        {
            id: 'runtime-repo-card',
            selector: '[data-runtime-repo]',
            title: 'Repository Actions',
            description: 'Inside each repository card you can choose installation source, install dependencies, validate entrypoints, or perform advanced git maintenance.',
            position: 'left'
        },
        {
            id: 'operation-output',
            selector: '#external-runtimes-operation-output',
            title: 'Operation Output',
            description: 'Review command output and failures here when dependency installs or validation actions do not complete as expected.',
            position: 'left'
        },
        {
            id: 'recent-ops',
            selector: '#external-runtimes-recent-ops',
            title: 'Recent Runtime Operations',
            description: 'This audit trail helps you quickly verify what was changed, by whom, and when.',
            position: 'left',
            isLast: true
        }
    ];

    const filtered = steps.filter((step) => document.querySelector(step.selector));
    if (filtered.length > 0) {
        filtered.forEach((step) => { step.isLast = false; });
        filtered[filtered.length - 1].isLast = true;
    }

    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            if (!filtered.length || !window.PageTutorialEngine) return;
            const tutorial = window.PageTutorialEngine.init('external_runtimes', filtered);
            if (tutorial) {
                window.startExternalRuntimesTutorial = tutorial.start;
            }
        }, 500);
    });
})();
