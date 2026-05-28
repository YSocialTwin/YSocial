(function() {
    const usersSteps = [
        {
            id: 'registered-users',
            selector: '#box-registered-users',
            title: '👤 Registered Users',
            description: `<p>This table displays all <b>registered users</b> who can access the platform:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Username</b> - User's login name (editable)</li>
                    <li><b>Email</b> - Contact email address</li>
                    <li><b>Role</b> - Access level (Admin, Researcher, User)</li>
                    <li><b>Actions</b> - View details or delete user</li>
                </ul>
                <p style="margin-top: 10px; font-size: 0.9em; color: #888;">Click column headers to sort. Admin users cannot be deleted.</p>`,
            position: 'overlay'
        },
        {
            id: 'add-user',
            selector: '#box-add-user',
            title: '➕ Add New User',
            description: `<p>Create a new <b>platform user</b> with the following settings:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Username</b> - Unique identifier for login</li>
                    <li><b>Password</b> - Secure password for the account</li>
                    <li><b>Email</b> - User's email address</li>
                    <li><b>Role</b> - Admin, Researcher, or User</li>
                    <li><b>LLM Configuration</b> - Custom LLM URL for text annotation</li>
                    <li><b>Profile Picture</b> - Optional avatar URL</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'bulk-create-users',
            selector: '#box-bulk-create-users',
            title: '📋 Bulk Create Users',
            description: `<p>Create <b>multiple users at once</b> using CSV format:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Format</b>: username,email,role,password</li>
                    <li>One user per line</li>
                    <li>Password is optional (auto-generated if omitted)</li>
                    <li>Roles: admin, researcher, or user</li>
                </ul>`,
            position: 'overlay'
        },
        {
            id: 'bulk-assign-users',
            selector: '#box-bulk-assign-users',
            title: '🔗 Bulk Assign Users',
            description: `<p>Assign <b>multiple users to an experiment</b>:</p>
                <ul style="margin: 10px 0 0 18px; padding: 0; list-style: disc;">
                    <li><b>Select Experiment</b> - Choose the target experiment</li>
                    <li><b>Select Users</b> - Hold Ctrl/Cmd to select multiple</li>
                    <li>Users will be able to access the experiment interface</li>
                </ul>`,
            position: 'overlay',
            isLast: true
        }
    ];
    
    // Filter steps to only include elements that exist
    const filteredSteps = usersSteps.filter(step => {
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
                const tutorial = window.PageTutorialEngine.init('users', filteredSteps);
                if (tutorial) {
                    window.startUsersTutorial = tutorial.start;
                }
            }
        }, 1000);
    });
})();
