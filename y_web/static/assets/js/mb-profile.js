var MB_PROFILE = (function() {
    function init() {
        var config = window.YS_DATA_MB_PROFILE || {};
        if (window.InfiniteScroll && config.page !== undefined) {
            InfiniteScroll.init({
                apiEndpoint: '/'+config.expId+'/api/profile/'+config.userId+'/'+config.mode,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    return { init: init };
})();
