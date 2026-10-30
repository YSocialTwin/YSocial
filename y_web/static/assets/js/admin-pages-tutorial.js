/**
 * Per-page guided tours for the admin pages that have no dedicated tutorial script.
 *
 * Each admin template marks its main boxes with ``data-tut="<slug>"`` and its
 * container with ``data-tutorial-page="<page>"``. ``generic-admin-tutorial.js`` reads
 * the entry of the page, adds the boxes it does not describe (taking the text from the
 * box itself) and runs the usual tutorial engine. Texts are English keys of the
 * ``tutorials`` JS catalog; box titles come from the (already translated) page headings.
 */
(function () {
    // texts used for boxes the tour does not describe
    window.YS_PAGE_TUTORIAL_FALLBACK = { title: 'Overview', description: 'Review and edit the values in this section.' };

    var pages = {
        about: [
            { selector: '[data-tut="about-us"]', title: '@heading', description: 'What YSocial is, its goals and the team that develops it.', position: 'auto' },
            { selector: '[data-tut="supporting-institutions"]', title: '@heading', description: 'The institutions that host and support the project.', position: 'auto' },
            { selector: '[data-tut="supporting-projects"]', title: '@heading', description: 'Research projects and funding programmes that contributed to YSocial.', position: 'auto' },
            { selector: '[data-tut="get-in-touch"]', title: '@heading', description: 'Contact channels and the code repository: use them for questions, bug reports and contributions.', position: 'auto' },
            { selector: '[data-tut="scientific-papers"]', title: '@heading', description: 'Publications describing the platform. Please cite them when you use YSocial in your research.', position: 'auto' }
        ],
        agent_details: [
            { selector: '[data-tut="agent-profile"]', title: '@heading', description: 'Full profile of the agent: identity, demographics, interests, personality traits and the behaviour settings it was generated with.', position: 'auto' },
            { selector: '[data-tut="population-memberships"]', title: '@heading', description: 'The populations this agent belongs to. Click a population to open it.', position: 'auto' },
            { selector: '[data-tut="add-to-population"]', title: '@heading', description: 'Add this agent to another population: choose the population and confirm.', position: 'auto' }
        ],
        annotation_analytics: [
            { selector: '[data-tut="temporal-controls"]', title: '@heading', description: 'Replay the simulation over time: press play, change the speed, and every chart follows the selected moment.', position: 'auto' },
            { selector: '#annotation-stats-row', title: 'Summary indicators', description: 'Headline figures for the selected annotation, updated as the simulated time moves.', position: 'auto' },
            { selector: '#annotationDistributionChartContainer', title: 'Distribution', description: 'How the annotation values are distributed over the content produced so far.', position: 'auto' },
            { selector: '#annotationTrendChartContainer', title: 'Trend over time', description: 'How the annotation evolves round after round.', position: 'auto' },
            { selector: '[data-tut="moderator-target-drill-down"]', title: '@heading', description: 'Pick a target to see how moderators intervened on it: toxicity trend and the list of interventions.', position: 'auto' },
            { selector: '[data-tut="author-recommendation-drill-down"]', title: '@heading', description: 'Pick an author to see how the recommender system exposed their posts: reach, receiver diversity and recommended posts.', position: 'auto' }
        ],
        custom_agent: [
            { selector: '[data-tut="available-populations"]', title: '@heading', description: 'Populations of this agent type already defined for the experiment platform. Open one to inspect its agents and deployments.', position: 'auto' },
            { selector: '[data-tut="available-agents"]', title: '@heading', description: 'Agents of this type that are already available. Open one to see its profile.', position: 'auto' },
            { selector: '[data-tut="create"]', title: '@heading', description: 'Create a new population or agent of this type. The fields come from the plugin that provides the agent type.', position: 'auto' }
        ],
        custom_population_details: [
            { selector: '[data-tut="custom-population-overview"]', title: '@heading', description: 'Name, description and key attributes of this population.', position: 'auto' },
            { selector: '[data-tut="experiment-deployments"]', title: '@heading', description: 'The experiments where this population is deployed.', position: 'auto' },
            { selector: '[data-tut="assigned-agents"]', title: '@heading', description: 'The agents that belong to the population.', position: 'auto' }
        ],
        dating_analytics: [
            { selector: '[data-tut="analytics-state"]', title: 'Analytics data', description: 'When the derived data were last built. Refresh them to read the latest rounds of a running experiment; the run itself is never modified.', position: 'auto' },
            { selector: '[data-tut="run-totals"]', title: '@heading', description: 'Headline figures of the run: agents, matches, date proposals, exits and paused profiles.', position: 'auto' },
            { selector: '[data-tut="recommenders"]', title: '@heading', description: 'Exposure and outcome of each recommender model: like rate, matches per stack and how unequal the exposure is.', position: 'auto' },
            { selector: '[data-tut="day-by-day"]', title: '@heading', description: 'The run day by day: swipes, matches, messages and dates.', position: 'auto' },
            { selector: '[data-tut="date-funnel"]', title: '@heading', description: 'From proposal to outcome: how many dates were proposed, accepted, declined or expired.', position: 'auto' },
            { selector: '[data-tut="exits"]', title: '@heading', description: 'Who left and why: success (a couple formed) or frustration (churn).', position: 'auto' },
            { selector: '[data-tut="export"]', title: '@heading', description: 'Download any derived table as CSV, or everything in one ZIP together with the field map.', position: 'auto' },
            { selector: '[data-tut="compare"]', title: '@heading', description: 'Compare this run with another dating experiment. The comparison is clean when population and seed are the same and only the recommender differs.', position: 'auto' }
        ],
        dating_analytics_compare: [
            { selector: '#dating-compare', title: 'Comparison', description: 'The two experiments side by side, metric by metric.', position: 'auto' }
        ],
        dating_participants: [
            { selector: '#dating-gateway-status', title: 'Gateway', description: 'Whether the local gateway that carries the actions of the people to the run is answering.', position: 'auto' },
            { selector: '#dating-humans', title: 'Participants', description: 'The users assigned to this experiment who can play: whether they have entered and what they have done so far.', position: 'auto' }
        ],
        dating_settings: [
            { selector: '#box-dating-settings', title: '@heading', description: 'The rules shared by every client of the experiment: recommender, quotas, chats, dates and human participation. They are locked once the experiment has started.', position: 'auto' }
        ],
        clients_dating: [
            { selector: '#box-new-client', title: '@heading', description: 'Choose the population and how long the client runs, then adjust how its agents behave. Every setting has the default of the dating runtime.', position: 'auto' }
        ],
        client_details_dating: [
            { selector: '#box-extend-simulation', title: '@heading', description: 'Add days to the total length of the client, then start it again: it continues from where it stopped.', position: 'auto' },
            { selector: '#box-client-settings', title: '@heading', description: 'The settings of the agents of this client. They can be changed while the client is stopped.', position: 'auto' }
        ],
        prompts_dating: [
            { selector: '[data-tut="dating-prompts"]', title: '@heading', description: 'The prompts the agents use. You can reword them for this experiment; the hash of each prompt is recorded with the run.', position: 'auto' }
        ],
        dating_populations: [
            { selector: '#dating-populations-table', title: 'Dating populations', description: 'The dating populations available. Open one to inspect its agents and preview their profile cards.', position: 'auto' },
            { selector: '#box-upload-dating-population', title: '@heading', description: 'Upload a population file. It is validated against the schema of the dating runtime and refused, with the path of the problem, if it does not fit.', position: 'auto' },
            { selector: '#box-generate-dating-population', title: '@heading', description: 'Generate a synthetic population from a seed: the same seed always gives the same agents.', position: 'auto' }
        ],
        dating_population_details: [
            { selector: '[data-tut="population-overview"]', title: '@heading', description: 'Name, size and summary of the population: ages, genders, intents and photos.', position: 'auto' },
            { selector: '#dating-card-preview', title: '@heading', description: 'See a profile card as another user would see it; hidden attributes are not shown.', position: 'auto' }
        ],
        download_notifications: [
            { selector: '[data-tut="notifications"]', title: '@heading', description: 'History of exports and background jobs: status, download links and the experiments involved. Mark entries as read or remove them.', position: 'auto' }
        ],
        embedding_settings: [
            { selector: '[data-tut="memory-embeddings"]', title: '@heading', description: 'Choose the Ollama host and the embedding model that agents use for semantic memory. Without it, memory falls back to lexical retrieval.', position: 'auto' },
            { selector: '#fetch_embedding_models', title: 'Load models', description: 'Query the host for the embedding-capable models installed on it, then pick one before saving.', position: 'auto' },
            { selector: '[data-tut="quick-reference-guide"]', title: '@heading', description: 'Short reminders about supported backends and model selection.', position: 'auto' }
        ],
        experiment_matrix: [
            { selector: '[data-tut="experiment-matrix"]', title: '@heading', description: 'Generate many experiments at once: pick a source experiment, unlock the parameters to vary and list their values.', position: 'auto' },
            { selector: '#matrix-form', title: 'Parameters', description: 'Nested configuration of the source experiment. Unlock a value to vary it, then add the values to combine.', position: 'auto' },
            { selector: '#matrix-warning', title: 'Combination count', description: 'Shows how many experiments the chosen values will produce, so you can spot huge matrices before creating them.', position: 'auto' },
            { selector: '#matrix-submit-btn', title: 'Generate experiments', description: 'Creates one experiment for every combination, optionally assigned to a project group.', position: 'auto' }
        ],
        external_runtime_logs: [
            { selector: '[data-tut="operation-log"]', title: '@heading', description: 'Output of the install, update and validation operations run on this component. Check it when an operation fails.', position: 'auto' }
        ],
        feed_limits: [
            { selector: '[data-tut="feed-retrieval-limits"]', title: '@heading', description: 'Limits on how much content is retrieved from RSS feeds, Reddit and the database fallback during forum simulations.', position: 'auto' },
            { selector: '[data-tut="quick-reference-guide"]', title: '@heading', description: 'Advice on when to raise or keep the defaults.', position: 'auto' }
        ],
        forum_image_resources: [
            { selector: '[data-tut="reusable-forum-image-resources"]', title: '@heading', description: 'Add image sources (feeds or subreddits) once and reuse them in every forum experiment. Validate a source before saving it.', position: 'auto' },
            { selector: '[data-tut="usage"]', title: '@heading', description: 'How the saved image resources are used by forum experiments.', position: 'auto' },
            { selector: '[data-tut="saved-image-resources"]', title: '@heading', description: 'The image resources already saved. Remove the ones you no longer need.', position: 'auto' }
        ],
        forum_rss_resources: [
            { selector: '[data-tut="reusable-forum-rss-resources"]', title: '@heading', description: 'Add RSS or Reddit feeds once and reuse them in every forum experiment. Validate a feed before saving it.', position: 'auto' },
            { selector: '[data-tut="usage"]', title: '@heading', description: 'How the saved feeds are used by forum experiments.', position: 'auto' },
            { selector: '[data-tut="saved-rss-resources"]', title: '@heading', description: 'The feeds already saved. Remove the ones you no longer need.', position: 'auto' }
        ],
        frontend_settings: [
            { selector: '[data-tut="user-interactions"]', title: '@heading', description: 'Choose which interactions the web interface offers to users: reactions, sharing, comments and more.', position: 'auto' },
            { selector: '[data-tut="annotations"]', title: '@heading', description: 'Control which annotations and statistics are shown next to the content.', position: 'auto' },
            { selector: '[data-tut="feed-profile"]', title: '@heading', description: 'Settings for the feed and the profile pages, such as posts per page.', position: 'auto' },
            { selector: '[id^="box-suite-"]', title: 'Plugin settings', description: 'Settings added by the installed plugins. They only apply when the plugin is active.', position: 'auto' }
        ],
        image_feeds: [
            { selector: '[data-tut="forum-image-feed-assignment"]', title: '@heading', description: 'Select which reusable image resources this forum experiment may use.', position: 'auto' },
            { selector: '[data-tut="assignment-notes"]', title: '@heading', description: 'Notes about how resources are shared across experiments.', position: 'auto' }
        ],
        jupyter: [
            { selector: '.jupyter-container', title: 'Analytical environment', description: 'JupyterLab embedded in the dashboard: open the notebooks of the experiment and analyse its data without leaving the page.', position: 'auto' }
        ],
        opinion_configuration: [
            { selector: '[data-tut="opinion-distribution-configuration"]', title: '@heading', description: 'Configure how opinions are initialised and how they evolve in this experiment.', position: 'auto' },
            { selector: '#dimensions-container', title: 'Dimensions', description: 'The opinion dimensions the agents hold. Add or remove dimensions as needed.', position: 'auto' },
            { selector: '#topic-configuration', title: 'Topics', description: 'Associate each topic with the dimensions it affects.', position: 'auto' },
            { selector: '#distributions-grid', title: 'Initial distributions', description: 'Choose the distribution that assigns the starting opinions to the agents.', position: 'auto' },
            { selector: '#update-rule-configuration', title: 'Update rule', description: 'Pick the rule that changes opinions after interactions and set its parameters.', position: 'auto' },
            { selector: '#submit-btn', title: 'Save', description: 'Store the configuration. Changes apply to the next run of the experiment.', position: 'auto' }
        ],
        opinion_evolution: [
            { selector: '[data-tut="temporal-controls"]', title: '@heading', description: 'Replay the simulation over time: press play, change the speed, and every chart follows the selected moment.', position: 'auto' },
            { selector: '[data-tut="opinion-distribution"]', title: '@heading', description: 'Distribution of the agents\' opinions at the selected moment.', position: 'auto' },
            { selector: '[data-tut="opinion-group-trends"]', title: '@heading', description: 'Average opinion of every opinion group over time.', position: 'auto' },
            { selector: '[data-tut="agent-opinion-evolution"]', title: '@heading', description: 'The opinion trajectory of individual agents.', position: 'auto' },
            { selector: '[data-tut="propaganda-target-drill-down"]', title: '@heading', description: 'Select a target to see how propagandists influenced its opinion.', position: 'auto' },
            { selector: '[data-tut="master-of-puppets-target-drill-down"]', title: '@heading', description: 'Select a target to see how coordinated actors influenced its opinion.', position: 'auto' }
        ],
        page_details: [
            { selector: '[data-tut="page-overview"]', title: '@heading', description: 'Identity of the page (name, feed, leaning) and the figures collected for it.', position: 'auto' },
            { selector: '[data-tut="add-to-population"]', title: '@heading', description: 'Add the page to a population so that it is deployed in experiments.', position: 'auto' },
            { selector: '[data-tut="add-topic-to-page"]', title: '@heading', description: 'Link a topic to the page: it will post content about it.', position: 'auto' },
            { selector: '[data-tut="recent-news"]', title: '@heading', description: 'The latest articles retrieved from the page\'s feed.', position: 'auto' }
        ],
        population_details: [
            { selector: '[data-tut="population-overview"]', title: '@heading', description: 'Description of the population: size, platform and the main attributes of its agents.', position: 'auto' },
            { selector: '[data-tut="experiment-deployments"]', title: '@heading', description: 'The experiments where this population is deployed.', position: 'auto' }
        ],
        prompts: [
            { selector: '[data-tut="llm-prompts-configuration"]', title: '@heading', description: 'The system prompts that guide agents and pages. They are sent to the LLM before every action.', position: 'auto' },
            { selector: '[data-tut="quick-reference-guide"]', title: '@heading', description: 'How the conversation with the LLM is composed and what each prompt controls.', position: 'auto' }
        ],
        prompts_hpc: [
            { selector: '[data-tut="hpc-llm-prompts-configuration"]', title: '@heading', description: 'The prompts used by HPC clients for every action: persona, post, reaction, comment, read and search.', position: 'auto' },
            { selector: '[data-tut="hpc-prompts-guide"]', title: '@heading', description: 'Reminders on placeholders and how the prompts are combined.', position: 'auto' }
        ],
        rss_feeds: [
            { selector: '[data-tut="forum-rss-feed-assignment"]', title: '@heading', description: 'Select which reusable RSS resources this forum experiment may use.', position: 'auto' },
            { selector: '[data-tut="assignment-notes"]', title: '@heading', description: 'Notes about how feeds are shared across experiments.', position: 'auto' }
        ],
        stress_reward_evolution: [
            { selector: '[data-tut="temporal-controls"]', title: '@heading', description: 'Replay the simulation over time: press play, change the speed, and every chart follows the selected moment.', position: 'auto' },
            { selector: '[data-tut="stress-distribution"]', title: '@heading', description: 'Distribution of the agents\' stress at the selected moment.', position: 'auto' },
            { selector: '[data-tut="reward-distribution"]', title: '@heading', description: 'Distribution of the agents\' reward at the selected moment.', position: 'auto' },
            { selector: '[data-tut="average-aggregate-trends"]', title: '@heading', description: 'Average stress and reward across the population over time.', position: 'auto' },
            { selector: '[data-tut="stress-attacker-target-drill-down"]', title: '@heading', description: 'Select a target to see which attackers raised its stress and when.', position: 'auto' }
        ],
        stress_reward_settings: [
            { selector: '[data-tut="stress-reward-settings"]', title: '@heading', description: 'Weights of the events that move stress and reward, coupling between the two and the optional churn rule.', position: 'auto' },
            { selector: '[data-tut="quick-reference-guide"]', title: '@heading', description: 'What each group of values controls.', position: 'auto' }
        ],
        select_experiment: [
            { selector: '#main-section', title: 'Choose an experiment', description: 'Pick the experiment to join: the interface then opens as one of its simulated users.', position: 'auto' }
        ],
        visibility_settings: [
            { selector: '[data-tut="share-experiments"]', title: '@heading', description: 'Grant or revoke experiment visibility to researcher users. Shared researchers can view the experiments and stop or delete them.', position: 'auto' },
            { selector: '[data-tut="share-single-experiment"]', title: '@heading', description: 'Share one experiment with the selected researchers.', position: 'auto' },
            { selector: '[data-tut="share-entire-group"]', title: '@heading', description: 'Share all the experiments of a project group at once.', position: 'auto' },
            { selector: '[data-tut="current-researcher-visibility"]', title: '@heading', description: 'Who can currently see what. Revoke a grant from this table.', position: 'auto' }
        ]
    };

    // pages built from the same template family share one tour
    var aliases = {
        opinion_configuration_forum: 'opinion_configuration',
        opinion_configuration_hpc: 'opinion_configuration',
        opinion_configuration_im: 'opinion_configuration',
        prompts_forum: 'prompts'
    };
    Object.keys(aliases).forEach(function (k) { pages[k] = pages[aliases[k]]; });

    window.YS_PAGE_TUTORIALS = pages;
})();
