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
            id: 'sidebar-users',
            selector: '#sidebar-users, #sidebar-profile',
            title: '👥 Users / My Profile',
            description: `<p>Manage <b>user accounts</b> (admin) or view your <b>profile settings</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Create and manage users</li>
                    <li>Configure LLM settings</li>
                    <li>Update profile information</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-experiments',
            selector: '#sidebar-experiments',
            title: '🧪 Experiments',
            description: `<p>Create and configure new <b>experiments</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Define experiment parameters</li>
                    <li>Schedule experiment execution</li>
                    <li>Copy or upload experiments</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-populations',
            selector: '#sidebar-populations',
            title: '🌍 Populations',
            description: `<p>Create and manage <b>agent populations</b> for your simulations:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Define demographic distributions</li>
                    <li>Configure agent behaviors</li>
                    <li>Set engagement patterns</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-agents',
            selector: '#sidebar-agents',
            title: '🤖 Synthetic Agents',
            description: `<p>Create <b>custom agents</b> with specific personalities:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Define Big Five personality traits</li>
                    <li>Set thematic interests</li>
                    <li>Configure social behaviors</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-pages',
            selector: '#sidebar-pages',
            title: '📄 Pages',
            description: `<p>Create and manage <b>news pages</b> for your simulations:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Define page themes and topics</li>
                    <li>Configure content generation</li>
                    <li>Set posting schedules</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'sidebar-miscellanea',
            selector: '#sidebar-miscellanea',
            title: '⚙️ Miscellanea',
            description: `<p>Access <b>system settings</b> and configurations:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>LLM server management</li>
                    <li>Demographics and content settings</li>
                    <li>System updates and logs</li>
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
