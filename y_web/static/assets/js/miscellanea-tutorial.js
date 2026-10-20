(function() {
    // Define all tutorial steps for each tab
    const allSteps = {
        // Tab navigation
        'tabs-navigation': {
            id: 'tabs-navigation',
            selector: '.misc-tabs',
            title: '📑 Configuration Tabs',
            description: `<p>Navigate between different <b>configuration sections</b>. Each tab contains related settings for your simulation platform.</p>`,
            position: 'bottom',
            tab: null
        },
        
        // System Settings tab
        'system-updates': {
            id: 'system-updates',
            selector: '#box-system-updates',
            title: '🔄 System Updates',
            description: `<p><b>Check for new YSocial releases</b> and stay up to date with the latest features and improvements.</p>`,
            position: 'right',
            tab: 'system-settings'
        },
        'telemetry-settings': {
            id: 'telemetry-settings',
            selector: '#box-telemetry-settings',
            title: '📊 Telemetry Settings',
            description: `<p>Control <b>anonymous usage data collection</b> to help improve YSocial. No personal data is collected.</p>`,
            position: 'left',
            tab: 'system-settings'
        },
        'log-sync': {
            id: 'log-sync',
            selector: '#box-log-sync',
            title: '📝 Automatic Log Synchronization',
            description: `<p><b>Periodic log reading</b> from running experiments keeps plot data updated and prevents data loss during log rotation.</p>`,
            position: 'right',
            tab: 'system-settings'
        },
        'watchdog': {
            id: 'watchdog',
            selector: '#box-watchdog',
            title: '🐕 Process Watchdog',
            description: `<p><b>Monitor and auto-restart</b> hung server/client processes to ensure continuous operation of your experiments.</p>`,
            position: 'overlay',
            tab: 'system-settings'
        },
        
        // LLM Management tab
        'llm-server': {
            id: 'llm-server',
            selector: '#box-llm-server',
            title: '🖥️ LLM Server Status',
            description: `<p>View the status of your <b>self-hosted LLM server</b>. Check if it's installed and running.</p>`,
            position: 'right',
            tab: 'llm-management'
        },
        'add-llm-model': {
            id: 'add-llm-model',
            selector: '#box-add-llm-model',
            title: '➕ Add LLM Model',
            description: `<p><b>Pull new AI models</b> from the Ollama directory to use in your simulations.</p>`,
            position: 'left',
            tab: 'llm-management'
        },
        'available-llms': {
            id: 'available-llms',
            selector: '#box-available-llms',
            title: '📋 Available LLMs',
            description: `<p>View all <b>installed language models</b> with their sizes and details. Delete models you no longer need.</p>`,
            position: 'overlay',
            tab: 'llm-management'
        },
        
        // Demographics tab
        'political-leanings': {
            id: 'political-leanings',
            selector: '#box-political-leanings',
            title: '🗳️ Political Leanings',
            description: `<p>Define <b>political orientations</b> that agents can have. Edit names directly in the table.</p>`,
            position: 'right',
            tab: 'demographics'
        },
        'education-levels': {
            id: 'education-levels',
            selector: '#box-education-levels',
            title: '🎓 Education Levels',
            description: `<p>Configure <b>education categories</b> for agent demographics (e.g., High School, Bachelor's, PhD).</p>`,
            position: 'left',
            tab: 'demographics'
        },
        'professions': {
            id: 'professions',
            selector: '#box-professions',
            title: '💼 Professions',
            description: `<p>Define <b>job categories</b> that agents can have in your simulations.</p>`,
            position: 'right',
            tab: 'demographics'
        },
        'languages': {
            id: 'languages',
            selector: '#box-languages',
            title: '🌐 Languages',
            description: `<p>Configure <b>supported languages</b> for agent communication in simulations.</p>`,
            position: 'left',
            tab: 'demographics'
        },
        'nationalities': {
            id: 'nationalities',
            selector: '#box-nationalities',
            title: '🌍 Nationalities',
            description: `<p>Define <b>agent nationalities</b> available for demographic configuration.</p>`,
            position: 'right',
            tab: 'demographics'
        },
        'age-classes': {
            id: 'age-classes',
            selector: '#box-age-classes',
            title: '📅 Age Classes',
            description: `<p>Configure <b>age group definitions</b> with minimum and maximum age ranges.</p>`,
            position: 'left',
            tab: 'demographics'
        },
        
        // Content & Behavior tab
        'topics': {
            id: 'topics',
            selector: '#box-topics',
            title: '💬 Topics',
            description: `<p>Define <b>content topics</b> that agents can discuss and post about.</p>`,
            position: 'right',
            tab: 'content-behavior'
        },
        'toxicity-levels': {
            id: 'toxicity-levels',
            selector: '#box-toxicity-levels',
            title: '⚠️ Toxicity Levels',
            description: `<p>Configure <b>toxicity categories</b> for content classification in simulations.</p>`,
            position: 'left',
            tab: 'content-behavior'
        },
        'hpc-monitor': {
            id: 'hpc-monitor',
            selector: '#box-hpc-monitor',
            title: '🖧 HPC Monitor',
            description: `<p><b>Automatic monitoring</b> of HPC client execution: it detects when a remote run has completed.</p>`,
            position: 'right',
            tab: 'system-settings'
        },
        'detoxify-model': {
            id: 'detoxify-model',
            selector: '#box-detoxify-model',
            title: '🧠 Local Toxicity Model',
            description: `<p>Download and manage the <b>local toxicity model</b> used to annotate content without calling external services.</p>`,
            position: 'left',
            tab: 'system-settings'
        },
        'about-system': {
            id: 'about-system',
            selector: '#box-about-system',
            title: 'ℹ️ About System Settings',
            description: `<p>A short reference of what each system setting does.</p>`,
            position: 'top',
            tab: 'system-settings'
        },
        'opinion-groups': {
            id: 'opinion-groups',
            selector: '#box-opinion-groups',
            title: '👥 Opinion Groups',
            description: `<p>Define the <b>opinion groups</b> (for example supporters, opponents, neutrals) and the opinion range of each one.</p>`,
            position: 'right',
            tab: 'opinion-dynamics'
        },
        'opinion-distributions': {
            id: 'opinion-distributions',
            selector: '#box-opinion-distributions',
            title: '📈 Opinion Distributions',
            description: `<p>Create the <b>statistical distributions</b> that assign starting opinions to the agents of an experiment.</p>`,
            position: 'left',
            tab: 'opinion-dynamics'
        },
        'activity-profiles': {
            id: 'activity-profiles',
            selector: '#box-activity-profiles',
            title: '📈 Activity Profiles',
            description: `<p>Define <b>agent activity patterns</b> including hourly activity levels throughout the day.</p>`,
            position: 'overlay',
            tab: 'content-behavior'
        }
    };
    
    function getActiveTab() {
        // Check which tab content is visible by looking for the 'active' class
        const tabContents = document.querySelectorAll('.misc-tab-content');
        for (const tabElement of tabContents) {
            if (tabElement.classList.contains('active')) {
                const tabId = tabElement.id;
                // Convert tab-system-settings to system-settings
                if (tabId.startsWith('tab-')) {
                    return tabId.substring(4);
                }
                return tabId;
            }
        }
        
        // Fallback: check button active state
        const activeTabBtn = document.querySelector('.misc-tab.active');
        if (activeTabBtn) {
            const onclick = activeTabBtn.getAttribute('onclick') || '';
            const match = onclick.match(/switchMiscTab\('([^']+)'\)/);
            if (match) return match[1];
        }
        
        return 'system-settings';
    }
    
    function buildStepsForCurrentTab() {
        const activeTab = getActiveTab();
        const steps = [];
        
        // Always start with tab navigation
        const tabsNav = allSteps['tabs-navigation'];
        if (document.querySelector(tabsNav.selector)) {
            steps.push({...tabsNav});
        }
        
        // Add steps for the current active tab
        for (const key in allSteps) {
            const step = allSteps[key];
            if (step.tab === activeTab) {
                const element = document.querySelector(step.selector);
                // Check if element exists AND is visible (in the active tab)
                if (element && element.offsetParent !== null) {
                    steps.push({...step});
                }
            }
        }
        
        // Mark last step
        if (steps.length > 0) {
            steps.forEach(s => s.isLast = false);
            steps[steps.length - 1].isLast = true;
        }
        
        return steps;
    }
    
    document.addEventListener('DOMContentLoaded', function() {
        if (!window.PageTutorialEngine) return;
        // One engine and one set of listeners: the shared array is refilled at every start
        // with the steps of the tab that is open at that moment.
        const shared = [];
        const tutorial = window.PageTutorialEngine.init('miscellanea', shared);
        if (!tutorial) return;
        window.startMiscellaneaTutorial = function() {
            shared.length = 0;
            buildStepsForCurrentTab().forEach(function(step) { shared.push(step); });
            if (shared.length > 0) tutorial.start();
        };
    });
})();
