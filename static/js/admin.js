// Admin panel JS - placeholder for future functionality
(function () {
    // Auto-refresh logs if on the logs page
    const logsTable = document.querySelector('[data-auto-refresh]');
    if (logsTable) {
        setInterval(function () {
            window.location.reload();
        }, 30000); // Refresh every 30 seconds
    }
})();
