(function() {
    const agentsSteps = [
        {
            id: 'agents-table',
            selector: '#box-agents-table',
            title: '👥 Available Agents',
            description: `<p>This table displays all <b>AI agents</b> in your system:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Name</b> - Click to edit agent name inline</li>
                    <li><b>Age & Profession</b> - Sortable demographic info</li>
                    <li><b>Activity Level</b> - How active the agent is (1-5 stars)</li>
                    <li><b>Activity Profile</b> - Hourly activity pattern</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Click column headers to sort, or search to filter agents.</p>`,
            position: 'bottom'
        },
        {
            id: 'create-agent',
            selector: '#box-create-agent',
            title: '➕ Create New Agent',
            description: `<p>Create a new <b>synthetic agent</b> with customized characteristics. The form is divided into several sections for different aspects of the agent's profile.</p>`,
            position: 'overlay'
        },
        {
            id: 'simulation-config',
            selector: '#section-simulation-config',
            title: '🎯 Simulation Configuration',
            description: `<p>Assign the agent to a <b>target population</b>. This determines which simulation the agent will participate in.</p>`,
            position: 'top'
        },
        {
            id: 'demographic-info',
            selector: '#section-demographic-info',
            title: '👤 Demographic Information',
            description: `<p>Configure <b>basic demographics</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Name</b> - Agent's display name</li>
                    <li><b>Profile Picture</b> - Optional URL for avatar</li>
                    <li><b>Age, Gender, Language</b> - Basic attributes</li>
                    <li><b>Profession, Nationality</b> - Background info</li>
                    <li><b>Education Level</b> - Educational background</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'thematic-characterization',
            selector: '#section-thematic-characterization',
            title: '🗳️ Thematic Characterization',
            description: `<p>Define the agent's <b>political orientation</b>. This influences how the agent interacts with political content in the simulation.</p>`,
            position: 'top'
        },
        {
            id: 'big-five',
            selector: '#section-big-five',
            title: '🧠 Big Five Personality',
            description: `<p>Configure the <b>Big Five personality traits</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Openness</b> - Inventive/curious vs. consistent/cautious</li>
                    <li><b>Conscientiousness</b> - Efficient vs. extravagant</li>
                    <li><b>Extraversion</b> - Outgoing vs. reserved</li>
                    <li><b>Agreeableness</b> - Friendly vs. critical</li>
                    <li><b>Neuroticism</b> - Sensitive vs. resilient</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'social-behavior',
            selector: '#section-social-behavior',
            title: '⚠️ Expected Social Behavior',
            description: `<p>Define <b>behavioral patterns</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Toxicity Level</b> - How aggressive or kind the agent is</li>
                    <li><b>Expected Activity</b> - Posting frequency (Low to High)</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'advanced-roleplay',
            selector: '#section-advanced-roleplay',
            title: '🎭 Advanced Role-Playing',
            description: `<p>Override agent behavior with a <b>custom pre-prompt</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Specify alternative profile text</li>
                    <li>Overrides all other configuration variables</li>
                    <li>Use for highly customized agent behavior</li>
                </ul>`,
            position: 'top',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = agentsSteps.filter(step => {
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
                const tutorial = window.PageTutorialEngine.init('agents', filteredSteps);
                if (tutorial) {
                    window.startAgentsTutorial = tutorial.start;
                }
            }
        }, 1000);
    });
})();
