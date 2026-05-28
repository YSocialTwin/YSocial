(function() {
    const pagesSteps = [
        {
            id: 'available-pages',
            selector: '#box-available-pages',
            title: '📄 Available Pages',
            description: `<p>This table shows all <b>content pages</b> in your simulations:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Name</b> - Page identifier (editable)</li>
                    <li><b>Type</b> - Media page, influencer, etc.</li>
                    <li><b>Keywords</b> - Content focus areas</li>
                    <li><b>Leaning</b> - Political orientation</li>
                    <li><b>Actions</b> - View details or delete page</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Click column headers to sort, or use search to filter.</p>`,
            position: 'overlay'
        },
        {
            id: 'create-page',
            selector: '#box-create-page',
            title: '➕ Create New Page',
            description: `<p>Add a new <b>content page</b> to your simulations:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Page Name</b> - Unique identifier</li>
                    <li><b>Description</b> - Brief page description</li>
                    <li><b>Type</b> - Media page or other</li>
                    <li><b>Political Leaning</b> - Content bias orientation</li>
                    <li><b>Keywords</b> - Topics this page covers</li>
                    <li><b>Logo</b> - Optional page image URL</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Pages serve as content sources in your simulations.</p>`,
            position: 'overlay',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = pagesSteps.filter(step => {
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
                const tutorial = window.PageTutorialEngine.init('pages', pagesSteps);
                if (tutorial) {
                    window.startPagesTutorial = tutorial.start;
                }
            }
        }, 1000);
    });
})();
