var AdminClientDetails = (function() {

    function fetchModelsForClient() {
        var urlInput = document.getElementById('custom_llm_url_client');
        var select = document.getElementById('models_select_client');
        var status = document.getElementById('llm_url_status_client');
        var llmUrl = urlInput.value.trim();

        if (!llmUrl) {
            alert('Please enter an LLM server URL');
            return;
        }

        status.innerHTML = '<i class="mdi mdi-loading mdi-spin"></i> Fetching...';

        fetch('/admin/api/fetch_models?llm_url=' + encodeURIComponent(llmUrl))
            .then(function(response) { return response.json(); })
            .then(function(data) {
                if (data.error) {
                    status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> ' + data.error + '</span>';
                    setTimeout(function() { status.innerHTML = ''; }, 5000);
                } else {
                    select.innerHTML = '<option value="">Select a model</option>';
                    data.models.forEach(function(model) {
                        var option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        select.appendChild(option);
                    });
                    status.innerHTML = '<span style="color: green;"><i class="mdi mdi-check"></i> ' + data.models.length + ' models loaded</span>';
                    setTimeout(function() { status.innerHTML = ''; }, 3000);
                }
            })
            .catch(function() {
                status.innerHTML = '<span style="color: red;"><i class="mdi mdi-alert"></i> Connection failed</span>';
                setTimeout(function() { status.innerHTML = ''; }, 5000);
            });
    }

    function displayNetworkFileName(input) {
        var display = document.getElementById('network-file-name-display');
        if (input.files && input.files[0]) {
            display.textContent = '\u2713 ' + input.files[0].name;
        } else {
            display.textContent = '';
        }
    }

    function initActivityChart() {
        var config = window.YS_DATA_CLIENT || {};
        var rawData = config.activityData || [];
        var labels = config.activityLabels || [];

        var activityData = rawData.map(function(v) { return v * 100; });
        var maxValue = Math.max.apply(null, activityData);
        var yAxisMax = Math.ceil(maxValue * 1.1);

        new Chart('activity_rates', {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Activity %',
                    data: activityData,
                    backgroundColor: 'rgba(34, 197, 94, 0.6)',
                    borderColor: 'rgba(34, 197, 94, 1)',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 8,
                        titleFont: { size: 12 },
                        bodyFont: { size: 11 },
                        callbacks: {
                            label: function(context) {
                                return 'Active: ' + context.parsed.y.toFixed(2) + '%';
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        suggestedMax: yAxisMax,
                        ticks: {
                            font: { size: 10 },
                            callback: function(value) { return value + '%'; }
                        },
                        grid: { color: 'rgba(0, 0, 0, 0.05)' }
                    },
                    x: {
                        ticks: { font: { size: 9 } },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    function initNetworkModelSelector() {
        var sel = document.getElementById('options');
        if (!sel) return;

        sel.addEventListener('change', function() {
            var selectedValue = this.value;
            var allFields = [
                'option1-field', 'option2-field', 'option3-field', 'option3-field2',
                'option4-field', 'option4-field2', 'option6-field', 'option6-field2',
                'option6-field3', 'option7-field', 'option7-field2', 'option7-field3',
                'option7-field4'
            ];
            allFields.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) el.style.display = 'none';
            });

            var show = [];
            if (selectedValue === 'ER') {
                show = ['option1-field'];
            } else if (selectedValue === 'BA') {
                show = ['option2-field'];
            } else if (selectedValue === 'WS') {
                show = ['option3-field', 'option3-field2'];
            } else if (selectedValue === 'PLC') {
                show = ['option4-field', 'option4-field2'];
            } else if (selectedValue === 'SBM') {
                show = ['option6-field', 'option6-field2', 'option6-field3'];
            } else if (selectedValue === 'LFR') {
                show = ['option7-field', 'option7-field2', 'option7-field3', 'option7-field4'];
            }
            show.forEach(function(id) {
                var el = document.getElementById(id);
                if (el) el.style.display = 'inline-block';
            });
        });
    }

    return {
        fetchModelsForClient: fetchModelsForClient,
        displayNetworkFileName: displayNetworkFileName,
        initActivityChart: initActivityChart,
        initNetworkModelSelector: initNetworkModelSelector
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    AdminClientDetails.initActivityChart();
    AdminClientDetails.initNetworkModelSelector();
});

// Expose globally for use in HTML onclick/onchange attributes
window.fetchModelsForClient = AdminClientDetails.fetchModelsForClient;
window.displayNetworkFileName = AdminClientDetails.displayNetworkFileName;
