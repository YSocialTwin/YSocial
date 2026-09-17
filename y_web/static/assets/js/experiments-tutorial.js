(function() {
    const experimentsSteps = [
        {
            id: 'running-experiments',
            selector: '#box-active',
            title: '🟢 Running Experiments',
            description: `<p>View and manage <b>currently active experiments</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Progress Bars</b> - Real-time progress of each experiment</li>
                    <li><b>Status Indicators</b> - Web interface and JupyterLab status</li>
                    <li><b>Actions</b> - View details or delete experiments</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'completed-experiments',
            selector: '#box-completed',
            title: '🔵 Completed Experiments',
            description: `<p>Experiments that have <b>finished all simulations</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Download All</b> - Export all completed experiments at once</li>
                    <li><b>Download Selected</b> - Select specific experiments to export</li>
                    <li><b>Annotation Tags</b> - See which annotations were applied</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'stopped-experiments',
            selector: '#box-stopped',
            title: '⚫ Stopped/Scheduled Experiments',
            description: `<p>Experiments that are <b>paused or waiting</b> to run:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li>Resume stopped experiments</li>
                    <li>Start scheduled experiments manually</li>
                    <li>View and manage experiment queue</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'new-experiment',
            selector: '#box-new-experiment',
            title: '➕ Create New Experiment',
            description: `<p>Set up a <b>new simulation experiment</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Platform Type</b> - Choose microblogging or forum style</li>
                    <li><b>Name & Description</b> - Identify your experiment</li>
                    <li><b>LLM Agents</b> - Enable AI-driven agent behavior</li>
                    <li><b>Topics</b> - Define conversation topics for the simulation</li>
                    <li><b>Annotations</b> - Enable toxicity, sentiment, emotion detection</li>
                </ul>`,
            position: 'right'
        },
        {
            id: 'schedule',
            selector: '#box-schedule',
            title: '📅 Experiment Schedule',
            description: `<p>Organize and run <b>experiments in batches</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Groups</b> - Create groups of experiments to run together</li>
                    <li><b>Drag & Drop</b> - Move experiments between groups</li>
                    <li><b>Sequential Execution</b> - Groups run one after another</li>
                    <li><b>Parallel Execution</b> - Experiments in a group run simultaneously</li>
                    <li><b>Log</b> - Monitor schedule execution progress</li>
                </ul>`,
            position: 'bottom'
        },
        {
            id: 'copy-experiment',
            selector: '#box-copy-experiment',
            title: '📋 Copy Experiment',
            description: `<p>Create a <b>duplicate</b> of an existing experiment:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>New Name</b> - Give the copy a unique name</li>
                    <li><b>Source</b> - Select which experiment to copy</li>
                    <li><b>Multiple Copies</b> - Create several copies at once</li>
                    <li>Copied experiments start fresh (no simulation data)</li>
                </ul>`,
            position: 'left'
        },
        {
            id: 'upload-experiment',
            selector: '#box-upload-experiment',
            title: '📤 Upload Experiment',
            description: `<p>Import a <b>previously exported</b> experiment:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>ZIP File</b> - Upload experiment archive</li>
                    <li><b>Custom Name</b> - Optionally rename the imported experiment</li>
                    <li>Uploaded experiments retain their original status and data</li>
                </ul>`,
            position: 'left',
            isLast: true
        }
    ];
    
    function getVisibleSteps() {
        return experimentsSteps.filter(step => {
            const el = document.querySelector(step.selector);
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none';
        });
    }
    
    // Initialize tutorial when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        // Always register the tutorial function immediately
        window.startExperimentsTutorial = function() {
            // Get visible steps at the time of starting
            const visibleSteps = getVisibleSteps();
            
            if (visibleSteps.length > 0) {
                visibleSteps.forEach(s => s.isLast = false);
                visibleSteps[visibleSteps.length - 1].isLast = true;
                
                const tutorial = window.PageTutorialEngine.init('experiments', visibleSteps);
                if (tutorial) {
                    tutorial.start();
                }
            }
        };
    });
})();
