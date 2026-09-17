(function() {
    const populationsSteps = [
        {
            id: 'available-populations',
            selector: '#box-available-populations',
            title: '👥 Available Populations',
            description: `<p>View all <b>agent populations</b> in your system:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Name</b> - Click to edit population name</li>
                    <li><b>Agents</b> - Number of agents in the population</li>
                    <li><b>Demographics</b> - Education, political leanings, toxicity</li>
                    <li><b>Activity Profiles</b> - Activity patterns assigned</li>
                    <li><b>Actions</b> - View details or delete population</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'create-population',
            selector: '#box-create-population',
            title: '➕ Create Synthetic Population',
            description: `<p>Create a new <b>synthetic population</b> with automatically generated agents. Configure demographics, social attributes, and activity patterns.</p>`,
            position: 'overlay'
        },
        {
            id: 'basic-info',
            selector: '#section-basic-info',
            title: '📝 Basic Information',
            description: `<p>Define the <b>population identity</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Population Name</b> - Unique identifier (required)</li>
                    <li><b>Description</b> - Purpose or characteristics</li>
                    <li><b>Population Size</b> - Number of agents to generate</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'demographics',
            selector: '#section-demographics',
            title: '🌍 Demographics',
            description: `<p>Configure <b>basic demographic attributes</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Nationalities</b> - Origin countries of agents</li>
                    <li><b>Spoken Language</b> - Language for content generation</li>
                    <li><b>Age Classes</b> - Age distribution with percentages</li>
                    <li><b>Gender Distribution</b> - Male/female ratio</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'social-attributes',
            selector: '#section-social-attributes',
            title: '🎭 Social Attributes',
            description: `<p>Define <b>social characteristics</b> with percentage distributions:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Education Levels</b> - Select multiple levels with percentages</li>
                    <li><b>Political Leanings</b> - Political orientation distribution</li>
                    <li><b>Toxicity Levels</b> - Expected behavior patterns</li>
                </ul>
                <p style="margin-top: 8px; font-size: 0.9em; color: #888;">Percentages must sum to 100% for each category.</p>`,
            position: 'top'
        },
        {
            id: 'profession-categories',
            selector: '#section-profession-categories',
            title: '💼 Profession Categories',
            description: `<p>Select <b>profession backgrounds</b> for agent generation (optional):</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Click categories to activate/deactivate</li>
                    <li>Active categories shown in green</li>
                    <li>At least one category required</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'activity-engagement',
            selector: '#section-activity-engagement',
            title: '📊 Activity & Engagement',
            description: `<p>Configure <b>agent activity patterns</b> (optional):</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Activity Profiles</b> - Drag profiles to assign hourly patterns</li>
                    <li><b>Actions Per User</b> - Min/max actions when active</li>
                    <li><b>Distribution</b> - Uniform, Poisson, Geometric, or Zipf</li>
                </ul>`,
            position: 'top'
        },
        {
            id: 'load-population',
            selector: '#box-load-population',
            title: '📁 Load Population',
            description: `<p>Import a <b>previously exported population</b> from a JSON file.</p>`,
            position: 'left'
        },
        {
            id: 'empty-population',
            selector: '#box-empty-population',
            title: '📦 Create Empty Population',
            description: `<p>Create an <b>empty population container</b>. You can manually add agents to it later.</p>`,
            position: 'left'
        },
        {
            id: 'merge-populations',
            selector: '#box-merge-populations',
            title: '🔀 Merge Populations',
            description: `<p><b>Combine multiple populations</b> into one:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Drag populations from available list</li>
                    <li>Select at least 2 populations</li>
                    <li>Agents are combined without duplicates</li>
                </ul>`,
            position: 'left',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = populationsSteps.filter(step => {
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
                const tutorial = window.PageTutorialEngine.init('populations', filteredSteps);
                if (tutorial) {
                    window.startPopulationsTutorial = tutorial.start;
                }
            }
        }, 500);
    });
})();
