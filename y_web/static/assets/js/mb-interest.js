var MB_INTEREST = (function() {
    function init() {
        var config = window.YS_DATA_MB_INTEREST || {};
        if (window.InfiniteScroll && config.page !== undefined) {
            InfiniteScroll.init({
                apiEndpoint: '/'+config.expId+'/api/interest/'+config.interestId,
                postsContainerId: 'posts-container',
                initialPage: config.page
            });
        }
    }

    document.addEventListener('DOMContentLoaded', init);

    return { init: init };
})();
