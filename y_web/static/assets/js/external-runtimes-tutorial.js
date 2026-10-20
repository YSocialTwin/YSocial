(function() {
    const steps = [
        {
            id: 'plugins-overview',
            selector: '#external-runtimes-main',
            title: 'Plugins',
            description: 'The list of plugins available to this installation, with what each one does and whether it is installed. Microblogging and Forum each stand for a server and a client.',
            position: 'top'
        },
        {
            id: 'plugins-status',
            selector: '#external-runtimes-list',
            title: 'Description and status',
            description: 'Each row shows the plugin, its description and its status: <strong>Installed</strong>, <strong>Not installed</strong> or <strong>Partially installed</strong> (only one of server and client). Plugins that can be switched on and off also show Enabled or Disabled.',
            position: 'top'
        },
        {
            id: 'plugins-install',
            selector: '[data-runtime-repo] .ext-row-actions a',
            title: 'Install or update',
            description: 'Opens the page of the plugin, where you choose the source (GitHub release or git branch), install or update it and read the output of the operation.',
            position: 'left'
        },
        {
            id: 'plugins-remove',
            selector: '[data-external-runtime-remove]',
            title: 'Remove',
            description: 'Deletes the local files of the plugin after a confirmation. For Microblogging and Forum it removes both server and client; to remove only one, use the plugin page.',
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
            const tutorial = window.PageTutorialEngine.init('external_runtimes', filtered);
            if (tutorial) {
                window.startExternalRuntimesTutorial = tutorial.start;
            }
        }, 500);
    });
})();
