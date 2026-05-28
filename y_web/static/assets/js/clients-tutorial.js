(function() {
    const clientsSteps = [
        {
            id: 'new-client',
            selector: '#box-new-client',
            title: '🤖 Create Simulation Client',
            description: `<p>This form allows you to <b>create a new simulation client</b> that will run agents in your experiment.</p>
                <p style="margin-top: 8px;">Configure the following basic settings:</p>
                <ul style="margin: 8px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Name</b> - Unique identifier for this client</li>
                    <li><b>Description</b> - Brief explanation of the client's purpose</li>
                    <li><b>Population</b> - Select the agent population to simulate</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'simulation-params',
            selector: '#section-simulation-params',
            title: '⚙️ Simulation Parameters',
            description: `<p>Configure the <b>duration and behavioral settings</b> for the simulation:</p>
                <ul style="margin: 8px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Simulation Length</b> - Number of days (or "Run until stopped")</li>
                    <li><b>New Agents/Churn</b> - Daily agent creation and removal rates</li>
                    <li><b>Thread Context Length</b> - How much conversation history agents see</li>
                    <li><b>Timeline Follower Ratio</b> - Balance between follower and general content</li>
                    <li><b>Probability Daily Follow</b> - Chance for agents to connect with peers</li>
                    <li><b>Agents' Memory</b> - How long agents maintain interest in topics</li>
                    <li><b>Content Visibility</b> - How long content can be recommended</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'actions-relevance',
            selector: '#section-actions-relevance',
            title: '🎯 Agents\' Actions Relevance',
            description: `<p>Set <b>relative probabilities (0-10)</b> for each action type:</p>
                <ul style="margin: 8px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Post new content</b> - Create original posts</li>
                    <li><b>Share/comment images</b> - Visual content interactions</li>
                    <li><b>Comment on posts</b> - Reply to existing content</li>
                    <li><b>Read content</b> - Browse without interacting</li>
                    <li><b>Search hashtags</b> - Explore topics of interest</li>
                </ul>
                <p style="margin-top: 8px; font-size: 0.9em; color: #888;">Higher values = more frequent actions. Use 0 to disable an action.</p>`,
            position: 'top'
        },
        {
            id: 'recsys',
            selector: '#section-recsys',
            title: '🎲 Recommendation Systems',
            description: `<p>Select the <b>recommendation algorithms</b> that influence agent interactions:</p>
                <ul style="margin: 8px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Content RecSys</b> - Algorithm for suggesting posts to agents</li>
                    <li><b>Friendship RecSys</b> - Algorithm for suggesting users to follow</li>
                </ul>
                <p style="margin-top: 8px; font-size: 0.9em; color: #888;">These systems shape how information spreads in your simulation.</p>`,
            position: 'top'
        },
        {
            id: 'network',
            selector: '#section-network',
            title: '🌐 Social Network Structure',
            description: `<p>Configure the <b>initial connections</b> between agents (optional):</p>
                <ul style="margin: 8px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Synthetic Network</b> - Generate using Random or Scale-Free models</li>
                    <li><b>Custom Network</b> - Upload a CSV edge list file</li>
                </ul>
                <p style="margin-top: 8px; font-size: 0.9em; color: #888;">These options are mutually exclusive. Click to expand and configure.</p>`,
            position: 'top'
        },
        {
            id: 'activity-rates',
            selector: '#section-activity-rates',
            title: '📊 Hourly Activity Rates',
            description: `<p>Customize <b>agent activity patterns</b> by hour (optional):</p>
                <ul style="margin: 8px 0 0 18px; padding: 0; list-style: disc;">
                    <li>View a visualization of default activity rates</li>
                    <li>Override specific hours with custom values</li>
                    <li>Default values based on real Bluesky data</li>
                </ul>
                <p style="margin-top: 8px; font-size: 0.9em; color: #888;">Click to expand and configure. Leave empty to use defaults.</p>`,
            position: 'top',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = clientsSteps.filter(step => {
        return document.querySelector(step.selector) !== null;
    });
    
    // Mark last step
    if (filteredSteps.length > 0) {
        filteredSteps.forEach(s => s.isLast = false);
        filteredSteps[filteredSteps.length - 1].isLast = true;
    }
    
    // Initialize tutorial when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(() => {
            if (filteredSteps.length > 0) {
                const tutorial = window.PageTutorialEngine.init('clients', filteredSteps);
                if (tutorial) {
                    window.startClientsTutorial = tutorial.start;
                }
            }
        }, 500);
    });
})();
