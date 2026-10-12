(function() {
    const steps = [
        {
            id: 'detail-header',
            selector: '#external-runtime-detail',
            title: 'Plugin page',
            description: 'Install, update or remove this plugin and follow what happens. The badges at the top say whether it is installed, enabled, or needs a restart.',
            position: 'top'
        },
        {
            id: 'detail-state',
            selector: '.ext-members',
            title: 'What is installed',
            description: 'For each repository: whether it is installed, the version (release archive, or git branch and commit), the latest published release and the dependency and validation checks.',
            position: 'top'
        },
        {
            id: 'detail-component',
            selector: '.ext-component-title',
            title: 'Server and client are independent',
            description: 'Microblogging and Forum have a server and a client. Each has its own block below: install, update or remove one without touching the other.',
            position: 'top'
        },
        {
            id: 'detail-source',
            selector: '.ext-options',
            title: 'Choose the source',
            description: '<strong>GitHub release</strong> is the standard option and works without git. <strong>Git checkout</strong> follows a branch and is meant for development: an installed checkout is updated in place.',
            position: 'top'
        },
        {
            id: 'detail-actions',
            selector: '.ext-sync-form .ext-actions',
            title: 'Install or update',
            description: 'Runs the operation, then installs the dependencies, validates the plugin and migrates its schema. Dependencies and Validate can be run again on their own; Remove deletes the local files. Operations are blocked while experiments that use the plugin are running.',
            position: 'top'
        },
        {
            id: 'detail-github',
            selector: 'details.ext-section',
            title: 'GitHub session',
            description: 'Optionally connect a token for this session to avoid GitHub rate limits or to reach private releases.',
            position: 'top'
        },
        {
            id: 'detail-output',
            selector: '#external-runtime-output',
            title: 'Operation output',
            description: 'The terminal output of the latest operations, newest first. When something fails, the reason is here. The page reloads when an operation finishes.',
            position: 'left'
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
            const tutorial = window.PageTutorialEngine.init('external_runtime_detail', filtered);
            if (tutorial) {
                window.startExternalRuntimeDetailTutorial = tutorial.start;
            }
        }, 500);
    });
})();
