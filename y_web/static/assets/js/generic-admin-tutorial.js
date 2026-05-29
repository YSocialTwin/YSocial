(function() {
    function pickSteps() {
        const steps = [];

        if (document.querySelector('.dashboard-aside')) {
            steps.push({
                id: 'sidebar',
                selector: '.dashboard-aside',
                title: 'Sidebar Navigation',
                description: 'Use the sidebar to move between experiment setup, users, agents, and system tooling.',
                position: 'right'
            });
        }

        if (document.querySelector('.dashboard-toolbar')) {
            steps.push({
                id: 'toolbar',
                selector: '.dashboard-toolbar',
                title: 'Top Toolbar',
                description: 'The top toolbar hosts quick actions such as replay tutorial, account shortcuts, and active simulation access.',
                position: 'bottom'
            });
        }

        if (document.querySelector('.dashboard-body .dashboard-box')) {
            steps.push({
                id: 'main-content',
                selector: '.dashboard-body .dashboard-box',
                title: 'Main Content Panel',
                description: 'This panel contains the primary controls and outputs for the current admin page.',
                position: 'top'
            });
        }

        if (document.querySelector('form')) {
            steps.push({
                id: 'forms',
                selector: 'form',
                title: 'Form Actions',
                description: 'Most pages apply changes through forms. Review required fields before submitting to avoid partial updates.',
                position: 'top'
            });
        }

        if (document.querySelector('#tutorial-replay-btn')) {
            steps.push({
                id: 'replay',
                selector: '#tutorial-replay-btn',
                title: 'Replay Tutorial',
                description: 'You can reopen this guide at any time from the help button in the header.',
                position: 'bottom',
                isLast: true
            });
        }

        if (steps.length > 0) {
            steps.forEach((step) => { step.isLast = false; });
            steps[steps.length - 1].isLast = true;
        }
        return steps;
    }

    document.addEventListener('DOMContentLoaded', function() {
        const steps = pickSteps();
        if (!steps.length || !window.PageTutorialEngine) return;
        const tutorial = window.PageTutorialEngine.init('admin_generic', steps);
        if (tutorial) {
            window.startGenericAdminTutorial = tutorial.start;
        }
    });
})();
