(function() {
    const clientDetailsSteps = [
        {
            id: 'client-overview',
            selector: '#box-client-overview',
            title: '🤖 Client Overview',
            description: `<p>View <b>basic client information</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Name & Description</b> - Client identification</li>
                    <li><b>Population</b> - Assigned agent population</li>
                    <li><b>Content Pages</b> - News sources for agents</li>
                    <li><b>Actions</b> - Download agent list, delete client</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'simulation-params',
            selector: '#box-simulation-params',
            title: '⚙️ Simulation Parameters',
            description: `<p>Configure <b>simulation behavior</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Duration</b> - Simulation length in days</li>
                    <li><b>Agent Growth</b> - New agent and churn rates</li>
                    <li><b>Thread Context</b> - Conversation history depth</li>
                    <li><b>Timeline Ratio</b> - Follower vs. general content</li>
                    <li><b>Follow Probabilities</b> - Social connection rates</li>
                    <li><b>Memory</b> - How long agents remember topics</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'actions-likelihood',
            selector: '#box-actions-likelihood',
            title: '🎯 Actions Likelihood',
            description: `<p>View <b>action probability weights</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Post</b> - Creating new content</li>
                    <li><b>Comment</b> - Responding to posts</li>
                    <li><b>Read</b> - Consuming content</li>
                    <li><b>Share</b> - Redistributing news</li>
                    <li><b>Search</b> - Finding hashtags</li>
                    <li><b>Vote</b> - Casting votes on content</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'llm-config',
            selector: '#box-llm-config',
            title: '🧠 LLM Configuration',
            description: `<p>View <b>AI model settings</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Text LLM</b> - Model, URL, temperature</li>
                    <li><b>Vision LLM</b> - Image transcription settings</li>
                    <li><b>Max Tokens</b> - Response length limits</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'agent-config',
            selector: '#box-agent-config',
            title: '👥 Agent Configuration',
            description: `<p><b>Bulk update</b> all agents in this client:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Content RecSys</b> - How posts are recommended</li>
                    <li><b>Follow RecSys</b> - User suggestions</li>
                    <li><b>LLM Model</b> - AI model for agent behavior</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">⚠️ Load experiment before updating to preserve settings.</p>`,
            position: 'overlay'
        },
        {
            id: 'social-network',
            selector: '#box-social-network',
            title: '🔗 Social Network Structure',
            description: `<p>Configure the <b>initial social network</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Network Type</b> - Generated or custom</li>
                    <li><b>Upload Custom</b> - Use your own network file</li>
                    <li><b>Download Agent List</b> - Get names for custom networks</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'hourly-activity',
            selector: '#box-hourly-activity',
            title: '📊 Hourly Activity Rates',
            description: `<p>View the <b>daily activity pattern</b> for agents:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Shows activity distribution across 24 hours</li>
                    <li>Based on real Bluesky usage data</li>
                    <li>Affects when agents are most active</li>
                </ul>`,
            position: 'overlay',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = clientDetailsSteps.filter(step => {
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
                const tutorial = window.PageTutorialEngine.init('client_details', filteredSteps);
                if (tutorial) {
                    window.startClientDetailsTutorial = tutorial.start;
                }
            }
        }, 500);
    });
})();
