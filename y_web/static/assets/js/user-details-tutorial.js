(function() {
    const userDetailsSteps = [
        {
            id: 'user-profile',
            selector: '#box-user-profile',
            title: '👤 User Profile',
            description: `<p>View <b>user account information</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Username & Email</b> - Account identifiers</li>
                    <li><b>Role</b> - Admin, Researcher, or User</li>
                    <li><b>LLM Configuration</b> - Model and server URL</li>
                    <li><b>Perspective API</b> - Toxicity analysis status</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'update-llm',
            selector: '#box-update-llm',
            title: '🧠 Update LLM Configuration',
            description: `<p>Configure the <b>LLM server and model</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Server URL</b> - Custom LLM endpoint</li>
                    <li><b>Fetch Models</b> - Discover available models</li>
                    <li><b>Select Model</b> - Choose for text tasks</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'update-password',
            selector: '#box-update-password',
            title: '🔐 Update Password',
            description: `<p>Change the user's <b>password</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Minimum 8 characters</li>
                    <li>Requires uppercase, number, special symbol</li>
                    <li>Must confirm password twice</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'update-email',
            selector: '#box-update-email',
            title: '📧 Update Email',
            description: `<p>Change the user's <b>email address</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Must be a valid email format</li>
                    <li>Must be unique across all users</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'perspective-api',
            selector: '#box-perspective-api',
            title: '🔬 Perspective API',
            description: `<p>Configure <b>toxicity analysis</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Google's Perspective API key</li>
                    <li>Enables text toxicity evaluation</li>
                    <li>Used in hybrid simulations</li>
                </ul>`,
            position: 'left'
        },
        {
            id: 'experiment-participation',
            selector: '#box-experiment-participation',
            title: '📊 Experiment Participation',
            description: `<p>View user's <b>experiment involvement</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Owned</b> - Experiments user created</li>
                    <li><b>Joined</b> - Experiments user participates in</li>
                    <li>Click experiment name to view details</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'add-to-experiment',
            selector: '#box-add-to-experiment',
            title: '➕ Add to Experiment',
            description: `<p>Grant user <b>experiment access</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Select an experiment from dropdown</li>
                    <li>User will be able to participate</li>
                    <li>Admin-only feature</li>
                </ul>`,
            position: 'overlay',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = userDetailsSteps.filter(step => {
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
                const tutorial = window.PageTutorialEngine.init('user_details', filteredSteps);
                if (tutorial) {
                    window.startUserDetailsTutorial = tutorial.start;
                }
            }
        }, 500);
    });
})();
