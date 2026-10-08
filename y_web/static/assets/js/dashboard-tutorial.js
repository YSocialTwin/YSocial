(function() {
    const dashboardSteps = [
        // Sidebar Navigation
        {
            id: 'sidebar-home',
            selector: '#sidebar-home',
            title: '🏠 Home',
            description: `<p>The <b>Home</b> link takes you to this dashboard view showing all experiments.</p>`,
            position: 'right'
        },
        {
            id: 'sidebar-group-toggle-experiments',
            selector: '#sidebar-group-toggle-experiments',
            title: '🧪 Experiments',
            description: `<p>Everything about running and configuring your <b>simulations</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Experiments</b> - define parameters, schedule and run them</li>
                    <li><b>Populations</b> - demographic distributions and agent behaviors</li>
                    <li><b>Agent Resources</b> - create synthetic agents, media and institutional pages</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-group-toggle-extensions',
            selector: '#sidebar-group-toggle-extensions',
            title: '🧩 Extensions',
            description: `<p>Plugin-contributed configuration and pages:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Frontend Settings</b> - enable and configure frontend plugin modules</li>
                    <li>Any installed plugin's own page (e.g. Scenario Design) appears here too</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-group-toggle-admin',
            selector: '#sidebar-group-toggle-admin',
            title: '🛠️ Admin',
            description: `<p>Platform-wide administration (visible to admins only):</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Users</b> - create and manage user accounts</li>
                    <li><b>Miscellanea</b> - system settings, LLM server, demographics vocabularies</li>
                    <li><b>Plugin Manager</b> - install and configure external plugin suites</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-about',
            selector: '#sidebar-about',
            title: 'ℹ️ About',
            description: `<p>Learn more about <b>YSocial</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Version information</li>
                    <li>Documentation links</li>
                    <li>License details</li>
                </ul>`,
            position: 'right'
        },
        // Header Buttons
        {
            id: 'tutorial-replay-btn',
            selector: '#tutorial-replay-btn',
            title: '❓ Tutorial Button',
            description: `<p>Click this button to <b>replay the tutorial</b> for any page.</p>
                <p style="margin-top: 10px;">The button appears on all pages that have tutorials available.</p>`,
            position: 'bottom'
        },
        {
            id: 'join-simulation-btn',
            selector: '.live-button',
            title: '🎬 Join Simulation',
            description: `<p>When experiments are running, click to <b>join the live simulation</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>View agent activity in real-time</li>
                    <li>Monitor social interactions</li>
                    <li>Watch content generation</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'logout-btn',
            selector: 'a[href="/logout"]',
            title: '🚪 Log Out',
            description: `<p>Click to <b>log out</b> of your YSocial session.</p>`,
            position: 'bottom'
        },
        // Dashboard Content
        {
            id: 'running-experiments',
            selector: '#box-running-experiments',
            title: '🟢 Running Experiments',
            description: `<p>This section shows all <b>currently active experiments</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Client Progress</b> - Real-time progress bars for each simulation client</li>
                    <li><b>Play/Pause/Stop</b> - Control individual clients or the entire experiment</li>
                    <li><b>JupyterLab</b> - Start analysis environment for data exploration</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'completed-experiments',
            selector: '#box-completed-experiments',
            title: '🔵 Completed Experiments',
            description: `<p>Experiments where <b>all clients have finished</b> their simulation runs:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>View experiment details and results</li>
                    <li>Download data or restart simulations</li>
                    <li>Delete experiments you no longer need</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'stopped-experiments',
            selector: '#box-stopped-experiments',
            title: '⚫ Stopped/Scheduled Experiments',
            description: `<p>Experiments that are <b>paused or scheduled</b> to run:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Resume stopped experiments</li>
                    <li>Manage scheduled experiment queues</li>
                    <li>Configure experiment timing</li>
                </ul>`,
            position: 'left'
        },
        {
            id: 'quick-reference',
            selector: '#box-quick-reference',
            title: '📚 Quick Reference Guide',
            description: `<p>A helpful <b>step-by-step guide</b> for running experiments:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>How to create populations and agents</li>
                    <li>Setting up simulation clients</li>
                    <li>Starting and monitoring experiments</li>
                </ul>`,
            position: 'left'
        },
        // Services Indicator
        {
            id: 'services-indicator',
            selector: '#services-indicator',
            title: '📊 Services Status',
            description: `<p>Monitor the status of <b>backend services</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Database</b> - Connection status to SQLite or PostgreSQL</li>
                    <li><b>LLM Server</b> - Status of the AI language model service</li>
                </ul>
                <p style="margin-top: 10px;">Green indicators show healthy connections.</p>`,
            position: 'top',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = dashboardSteps.filter(step => {
        // Handle multiple selectors separated by comma
        const selectors = step.selector.split(',').map(s => s.trim());
        return selectors.some(sel => document.querySelector(sel) !== null);
    });
    
    // Mark last step
    if (filteredSteps.length > 0) {
        filteredSteps.forEach(s => s.isLast = false);
        filteredSteps[filteredSteps.length - 1].isLast = true;
    }
    
    // Initialize tutorial when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        if (filteredSteps.length > 0) {
            const tutorial = window.PageTutorialEngine.init('dashboard', filteredSteps);
            if (tutorial) {
                window.startDashboardTutorial = tutorial.start;
            }
        }
    });
})();
