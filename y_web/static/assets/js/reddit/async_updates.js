(function ($, window, document) {
    "use strict";

    if (!$) {
        return;
    }

    var Api = window.RedditApi || null;
    if (!Api) {
        console.warn(
            "RedditApi client not found; Phase 3 interactions disabled.",
        );
        return;
    }

    var FEED_SELECTORS = {
        container: "#feed-container",
        loading: "#loading-indicator",
        endOfFeed: "#end-of-feed",
        refreshNotice: "#new-posts-indicator",
        refreshNoticeButton: "#new-posts-refresh-button",
        feedTypeSelect: "#feed-type-select",
        searchForm: "#feed-search-form",
        searchInput: "#feed-search-input",
        searchSummary: "#search-summary",
        searchSummaryResults: "#search-summary-results",
        searchSummaryEmpty: "#search-summary-empty",
        searchSummaryQuery: "#search-summary-query",
        searchSummaryTotal: "#search-summary-total",
        composeCard: "#compose-card",
        composeTrigger: "#create-post-trigger",
        publishButton: "#publish-button",
        postTitle: "#post-title",
        postBody: "#publish",
        linkUrl: "#link-url",
        linkUrlWrapper: "#link-url-wrapper",
        imageUrl: "#image-url",
        imageUrlWrapper: "#image-url-wrapper",
        imageUploadWrapper: "#image-upload-wrapper",
        imageSourceToggle: "#image-source-toggle",
        imageFile: "#image-file",
        feedUpload: "#feed-upload",
        annotation: "#activities",
        postTypeTabs: "[data-post-type-tab]",
        imageSourceInputs: 'input[name="image-source"]',
    };

    var VOTE_COLORS = {
        like: "#ff4500",
        dislike: "#7193ff",
        neutral: "#878a8c",
    };

    var DEFAULT_STATE = {
        currentPage: 1,
        perPage: 10,
        feedType: "new",
        searchQuery: "",
        viewMode: "feed",
        userId: null,
        hasMore: false,
        isLoading: false,
    };

    var VALID_FEED_TYPES = new Set(["new", "hot", "top", "most_commented"]);
    var AUTO_REFRESH_INTERVAL_MS = 30 * 1000;

    var feedState = $.extend({}, DEFAULT_STATE);
    var autoRefreshTimer = null;
    var voteInFlight = new Set();
    var articleEnrichInFlight = new Set();
    var imageEnrichInFlight = new Set();
    var commentSubmitInFlight = new Set();
    var composeState = {
        postType: "text", // text | link | image
        imageSource: "upload", // url | upload
        selectedFile: null,
        previewUrl: null,
    };

    function getActivePostTypeFromTabs() {
        var $active = $(FEED_SELECTORS.composeCard)
            .find(FEED_SELECTORS.postTypeTabs + ".is-active")
            .first();
        if ($active.length) {
            return $active.data("post-type-tab") || "text";
        }
        // Fallback: if template changed or class missing.
        var $first = $(FEED_SELECTORS.composeCard)
            .find(FEED_SELECTORS.postTypeTabs)
            .first();
        return ($first.data("post-type-tab") || "text");
    }

    function setActivePostTypeTab(value) {
        var $tabs = $(FEED_SELECTORS.composeCard).find(FEED_SELECTORS.postTypeTabs);
        $tabs.removeClass("is-active");
        $tabs
            .filter(function () {
                return $(this).data("post-type-tab") === value;
            })
            .addClass("is-active");
    }

    function getSelectedRadioValue(selector, fallback) {
        var $checked = $(selector + ":checked");
        if ($checked.length && $checked.val()) {
            return $checked.val();
        }
        return fallback;
    }

    function syncComposeStateFromInputs() {
        composeState.postType = getActivePostTypeFromTabs();
        composeState.imageSource = getSelectedRadioValue(
            FEED_SELECTORS.imageSourceInputs,
            "upload",
        );
    }

    function setRadioValue(selector, value) {
        $(selector).prop("checked", false);
        $(selector + '[value="' + value + '"]').prop("checked", true);
    }

    function clearUploadPreview() {
        if (composeState.previewUrl && window.URL && window.URL.revokeObjectURL) {
            window.URL.revokeObjectURL(composeState.previewUrl);
        }
        composeState.previewUrl = null;
        composeState.selectedFile = null;
        $(FEED_SELECTORS.feedUpload).empty();
        var $file = $(FEED_SELECTORS.imageFile);
        if ($file.length) {
            $file.val("");
        }
    }

    function isVideoFile(file) {
        if (!file) {
            return false;
        }
        if ((file.type || "").toLowerCase() === "video/mp4") {
            return true;
        }
        return (file.name || "").toLowerCase().endsWith(".mp4");
    }

    function renderUploadPreview(file) {
        var deleteIcon =
            window.feather && window.feather.icons && window.feather.icons.x
                ? window.feather.icons.x.toSvg()
                : "x";
        var video = isVideoFile(file);
        function renderWithUrl(src) {
            var previewNode = "";
            if (video) {
                previewNode =
                    '<video src="' +
                    src +
                    '" muted loop playsinline preload="metadata"></video>';
            } else {
                previewNode = '<img src="' + src + '" alt="">';
            }
            var template =
                '<div class="upload-wrap">' +
                previewNode +
                '<span class="remove-file" style="cursor: pointer;">' +
                deleteIcon +
                "</span>" +
                "</div>";

            $(FEED_SELECTORS.feedUpload).empty().append(template);
            $(FEED_SELECTORS.feedUpload)
                .find(".remove-file")
                .on("click", function () {
                    clearUploadPreview();
                    updateComposeUi();
                    updatePublishButtonState();
                });
        }

        var previewUrl = null;
        if (window.URL && window.URL.createObjectURL) {
            previewUrl = window.URL.createObjectURL(file);
        }
        composeState.previewUrl = previewUrl;
        if (previewUrl) {
            renderWithUrl(previewUrl);
            return;
        }

        var reader = new FileReader();
        reader.onload = function (event) {
            renderWithUrl(event.target.result);
        };
        reader.readAsDataURL(file);
    }

    function toggleHidden(selector, shouldShow) {
        var $el = $(selector);
        if (!$el.length) {
            return;
        }
        $el.toggleClass("is-hidden", !shouldShow);
    }

    function updateComposeUi() {
        syncComposeStateFromInputs();

        var isLink = composeState.postType === "link";
        var isImage = composeState.postType === "image";
        var isImageUrl = isImage && composeState.imageSource === "url";
        var isImageUpload = isImage && composeState.imageSource === "upload";

        toggleHidden(FEED_SELECTORS.linkUrlWrapper, isLink);
        toggleHidden(FEED_SELECTORS.imageSourceToggle, isImage);
        toggleHidden(FEED_SELECTORS.imageUrlWrapper, isImageUrl);
        toggleHidden(FEED_SELECTORS.imageUploadWrapper, isImageUpload);

        if (!isImageUpload) {
            clearUploadPreview();
        }
        if (!isLink) {
            $(FEED_SELECTORS.linkUrl).val("");
        }
        if (!isImageUrl) {
            $(FEED_SELECTORS.imageUrl).val("");
        }
    }

    function isComposeValid() {
        syncComposeStateFromInputs();
        var title = $(FEED_SELECTORS.postTitle).val().trim();
        if (!title) {
            return false;
        }

        if (composeState.postType === "link") {
            var linkUrl = ($(FEED_SELECTORS.linkUrl).val() || "").trim();
            return !!linkUrl;
        }

        if (composeState.postType === "image") {
            if (composeState.imageSource === "url") {
                var imageUrl = ($(FEED_SELECTORS.imageUrl).val() || "").trim();
                return !!imageUrl;
            }
            return !!composeState.selectedFile;
        }

        return true;
    }

    function updatePublishButtonState() {
        var $button = $(FEED_SELECTORS.publishButton);
        $button.prop("disabled", !isComposeValid());
    }

    function parseInitialState() {
        if (!window.redditFeedConfig) {
            return;
        }
        feedState.currentPage = window.redditFeedConfig.currentPage || 1;
        feedState.perPage = window.redditFeedConfig.perPage || 10;
        feedState.feedType = window.redditFeedConfig.feedType || "new";
        feedState.viewMode = window.redditFeedConfig.viewMode || "feed";
        feedState.searchQuery =
            feedState.viewMode === "search"
                ? (window.redditFeedConfig.searchQuery || "").trim()
                : "";
        feedState.userId = window.redditFeedConfig.userId || null;
        feedState.hasMore = !!window.redditFeedConfig.hasMore;

        var params = new URLSearchParams(window.location.search || "");
        var feedTypeFromUrl = (params.get("feed_type") || "").trim();
        if (VALID_FEED_TYPES.has(feedTypeFromUrl)) {
            feedState.feedType = feedTypeFromUrl;
        }
        if (feedState.viewMode === "search" && params.has("q")) {
            feedState.searchQuery = (params.get("q") || "").trim();
        }
    }

    function notify(message, type) {
        type = type || "error";
        if (window.toastr && window.toastr[type]) {
            window.toastr[type](message);
            return;
        }
        if (type === "error") {
            window.alert(message);
        } else {
            console.info(message);
        }
    }

    function getPostElement(target) {
        return $(target).closest("[data-reddit-post]");
    }

    function getExpId() {
        return (window.redditFeedConfig && window.redditFeedConfig.expId) || "";
    }

    function getCurrentFeedUrl() {
        var path = window.location.pathname || "";
        if (path.indexOf("/rfeed") === -1 && path.indexOf("/rsearch") === -1) {
            return "";
        }
        return path + (window.location.search || "");
    }

    function syncFeedUrlWithState() {
        var params = new URLSearchParams(window.location.search || "");
        params.set("feed_type", feedState.feedType);
        if (feedState.viewMode === "search") {
            if (feedState.searchQuery) {
                params.set("q", feedState.searchQuery);
            } else {
                params.delete("q");
            }
        } else {
            params.delete("q");
        }
        var query = params.toString();
        var url = window.location.pathname + (query ? "?" + query : "");
        window.history.replaceState({}, "", url);
    }

    function buildFeedRequestParams(page) {
        var params = {
            page: page,
            per_page: feedState.perPage,
            feed_type: feedState.feedType,
        };
        if (feedState.userId) {
            params.user_id = feedState.userId;
        }
        if (feedState.viewMode === "search" && feedState.searchQuery) {
            params.q = feedState.searchQuery;
        }
        return params;
    }

    function fetchFeedOrSearch(params) {
        if (feedState.viewMode === "search") {
            return Api.fetchSearch(params);
        }
        return Api.fetchFeed(params);
    }

    function applyFeedResponse(response, options) {
        options = options || {};
        var posts = response.data || [];
        renderPosts(posts, { replace: !!options.replace });
        var meta = response.meta || {};
        feedState.currentPage = meta.page || options.page || 1;
        feedState.hasMore = !!meta.has_more;
        $(FEED_SELECTORS.endOfFeed).toggle(!feedState.hasMore);
        if (feedState.viewMode === "search") {
            updateSearchSummary(meta);
        }
    }

    function updateSearchSummary(meta) {
        var $summary = $(FEED_SELECTORS.searchSummary);
        if (!$summary.length) {
            return;
        }
        var query = (meta && typeof meta.query === "string")
            ? meta.query.trim()
            : (feedState.searchQuery || "").trim();
        var totalValue = meta ? Number(meta.total) : NaN;
        var total = Number.isFinite(totalValue) ? totalValue : null;

        var $results = $(FEED_SELECTORS.searchSummaryResults);
        var $empty = $(FEED_SELECTORS.searchSummaryEmpty);
        var $query = $(FEED_SELECTORS.searchSummaryQuery);
        var $total = $(FEED_SELECTORS.searchSummaryTotal);

        if (!query) {
            $results.hide();
            $empty.show();
            return;
        }

        feedState.searchQuery = query;
        $query.text(query);
        if (total === null) {
            $total.text("");
        } else {
            $total.text(" (" + String(total) + ")");
        }
        $empty.hide();
        $results.show();
    }

    function fetchFeedPage(page, options) {
        options = options || {};
        var showLoading = !options.silent;

        if (feedState.isLoading) {
            return $.Deferred().resolve().promise();
        }

        feedState.isLoading = true;
        if (showLoading) {
            $(FEED_SELECTORS.loading).show();
        }

        return fetchFeedOrSearch(buildFeedRequestParams(page))
            .then(function (response) {
                applyFeedResponse(response, {
                    replace: !!options.replace,
                    page: page,
                });
                return response;
            })
            .fail(function (err) {
                if (options.showError !== false) {
                    notify(err.message || "Unable to refresh feed.", "error");
                }
            })
            .always(function () {
                feedState.isLoading = false;
                if (showLoading) {
                    $(FEED_SELECTORS.loading).hide();
                }
            });
    }

    function shouldAutoRefreshFeed() {
        if (feedState.viewMode !== "feed") {
            return false;
        }
        if (document.hidden) {
            return false;
        }
        if (feedState.isLoading) {
            return false;
        }
        // Keep refresh non-disruptive while user is actively reading deep in the feed.
        return window.scrollY < 220;
    }

    function getTopRenderedPostId() {
        var $first = $(FEED_SELECTORS.container).find("[data-post-id]").first();
        if (!$first.length) {
            return null;
        }
        var value = parseInt($first.attr("data-post-id"), 10);
        return Number.isFinite(value) ? value : null;
    }

    function showNewPostsNotice() {
        $(FEED_SELECTORS.refreshNotice).show();
    }

    function hideNewPostsNotice() {
        $(FEED_SELECTORS.refreshNotice).hide();
    }

    function probeForNewPosts() {
        if (feedState.viewMode !== "feed" || feedState.isLoading) {
            return;
        }
        fetchFeedOrSearch(buildFeedRequestParams(1))
            .then(function (response) {
                var posts = response.data || [];
                if (!posts.length) {
                    return;
                }
                var currentTop = getTopRenderedPostId();
                var nextTop = parseInt(posts[0].post_id, 10);
                if (!Number.isFinite(nextTop)) {
                    return;
                }
                if (currentTop === null) {
                    showNewPostsNotice();
                    return;
                }
                if (nextTop !== currentTop) {
                    showNewPostsNotice();
                }
            })
            .fail(function () {
                // Ignore silent probe failures.
            });
    }

    function startAutoRefresh() {
        if (feedState.viewMode !== "feed") {
            return;
        }
        if (autoRefreshTimer) {
            window.clearInterval(autoRefreshTimer);
        }
        autoRefreshTimer = window.setInterval(function () {
            if (!shouldAutoRefreshFeed()) {
                probeForNewPosts();
                return;
            }
            fetchFeedPage(1, { replace: true, silent: true, showError: false });
        }, AUTO_REFRESH_INTERVAL_MS);
    }

    function buildThreadUrl(postId) {
        var expId = getExpId();
        var back = getCurrentFeedUrl();
        var query = back ? ("?back=" + encodeURIComponent(back)) : "";
        if (expId) {
            return "/" + expId + "/rthread/" + postId + query;
        }
        return "/rthread/" + postId + query;
    }

    function buildProfileUrl(authorId) {
        var expId = getExpId();
        if (expId) {
            return "/" + expId + "/profile/" + authorId + "/recent/1";
        }
        return "/profile/" + authorId + "/recent/1";
    }

    function currentViewerCanDelete(authorId, loggedUserId) {
        var isAdmin = !!(window.redditContext && window.redditContext.isAdmin);
        return isAdmin || (loggedUserId && Number(authorId) === Number(loggedUserId));
    }

    function parseVoteState($post) {
        var likes = parseInt($post.attr("data-likes"), 10) || 0;
        var dislikes = parseInt($post.attr("data-dislikes"), 10) || 0;
        var score = parseInt($post.attr("data-score"), 10) || likes - dislikes;
        var vote = $post.attr("data-vote") || "neutral";
        return {
            postId: parseInt($post.attr("data-post-id"), 10),
            likes: likes,
            dislikes: dislikes,
            score: score,
            vote: vote,
        };
    }

    function setVoteState($post, state) {
        $post.attr("data-vote", state.vote);
        $post.attr("data-likes", state.likes);
        $post.attr("data-dislikes", state.dislikes);
        $post.attr("data-score", state.score);

        $post.find('[data-role="score"]').text(state.score);

        var $buttons = $post.find(".vote-button");
        $buttons.each(function () {
            var $btn = $(this);
            var action = $btn.data("action");
            var color = VOTE_COLORS.neutral;
            if (action === "like" && state.vote === "like") {
                color = VOTE_COLORS.like;
            } else if (action === "dislike" && state.vote === "dislike") {
                color = VOTE_COLORS.dislike;
            }
            $btn.css("color", color);
        });
    }

    function optimisticVoteUpdate(prevState, action) {
        var nextVote = action;
        var likes = prevState.likes;
        var dislikes = prevState.dislikes;

        if (prevState.vote === action) {
            nextVote = "neutral";
            if (action === "like" && likes > 0) {
                likes -= 1;
            } else if (action === "dislike" && dislikes > 0) {
                dislikes -= 1;
            }
        } else {
            if (action === "like") {
                likes += 1;
                if (prevState.vote === "dislike" && dislikes > 0) {
                    dislikes -= 1;
                }
            } else if (action === "dislike") {
                dislikes += 1;
                if (prevState.vote === "like" && likes > 0) {
                    likes -= 1;
                }
            }
        }

        var score = likes - dislikes;
        return {
            postId: prevState.postId,
            likes: likes,
            dislikes: dislikes,
            score: score,
            vote: nextVote,
        };
    }

    function handleVoteClick(event) {
        event.preventDefault();
        var $button = $(event.currentTarget);
        var action = $button.data("action");
        var $post = getPostElement($button);

        if (!$post.length || !action) {
            return;
        }

        var prevState = parseVoteState($post);
        if (voteInFlight.has(prevState.postId)) {
            return;
        }

        var effectiveAction = action;
        if (prevState.vote === action) {
            effectiveAction = "neutral";
        }

        var optimisticState = optimisticVoteUpdate(prevState, action);
        setVoteState($post, optimisticState);

        voteInFlight.add(prevState.postId);

        Api.vote(prevState.postId, effectiveAction)
            .then(function (data) {
                var confirmed = {
                    postId: data.post_id,
                    likes: data.likes,
                    dislikes: data.dislikes,
                    score: data.score,
                    vote: data.action,
                };
                setVoteState($post, confirmed);
                voteInFlight.delete(prevState.postId);
            })
            .fail(function (err) {
                setVoteState($post, prevState);
                voteInFlight.delete(prevState.postId);
                notify(
                    err.message || "Unable to update vote. Please try again.",
                );
            });
    }

    // Emotion and topic rendering removed for cleaner UI (Phase 4)
    // Data still available in database for analysis scripts

    function escapeHtml(str) {
        return $("<div>").text(str).html();
    }

    function formatDisplayTime(entity) {
        if (entity && entity.display_time) {
            return escapeHtml(String(entity.display_time));
        }
        var dayNum = entity && entity.day != null ? Number.parseInt(String(entity.day), 10) : NaN;
        var hourNum = entity && entity.hour != null ? Number.parseInt(String(entity.hour), 10) : NaN;
        if (!Number.isFinite(dayNum) || !Number.isFinite(hourNum)) {
            return "";
        }

        var dt = new Date();
        dt.setHours(0, 0, 0, 0);
        dt.setDate(dt.getDate() + Math.max(dayNum, 0));
        dt.setHours(Math.min(Math.max(hourNum, 0), 23), 0, 0, 0);

        var yy = String(dt.getFullYear()).slice(-2);
        var mm = String(dt.getMonth() + 1).padStart(2, "0");
        var dd = String(dt.getDate()).padStart(2, "0");
        var hh = String(dt.getHours()).padStart(2, "0");
        var mi = String(dt.getMinutes()).padStart(2, "0");
        return dd + "-" + mm + "-" + yy + " " + hh + ":" + mi;
    }

    function normalizeCommentTextForDedupe(text) {
        return String(text || "")
            .toLowerCase()
            .replace(/[^\w\s]/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    function simpleHash32(text) {
        var hash = 5381;
        var str = String(text || "");
        for (var i = 0; i < str.length; i += 1) {
            hash = ((hash << 5) + hash) + str.charCodeAt(i);
            hash = hash | 0;
        }
        return Math.abs(hash);
    }

    function buildClientCommentActionId(parentId, content) {
        // 10-second bucket allows retries for one user action, without forcing global permanence.
        var timeBucket = Math.floor(Date.now() / 10000);
        var normalized = normalizeCommentTextForDedupe(content);
        var seed = String(parentId) + "|" + normalized + "|" + String(timeBucket);
        var hash = simpleHash32(seed).toString(36);
        return "webc_" + String(parentId) + "_" + hash + "_" + String(timeBucket);
    }

    function buildPostNode(post, loggedUserId) {
        var vote = "neutral";
        if (post.is_liked) {
            vote = "like";
        } else if (post.is_disliked) {
            vote = "dislike";
        }
        var likes = post.likes || 0;
        var dislikes = post.dislikes || 0;
        var score = likes - dislikes;
        var threadId = post.thread_id || post.post_id;
        var hasDeletePrivilege = currentViewerCanDelete(post.author_id, loggedUserId);

        var articleSection = "";
        if (post.article && post.article !== 0) {
            var articleUrl = post.article.url || "#";
            var articleSummary = post.article.summary || "";
            var articleTitle = post.article.title || "";
            var articleIdAttr = post.article_id ? (' data-article-id="' + String(post.article_id) + '"') : "";

            var imagePreview = "";
            if (post.image && post.image.url) {
                var imageAlt = post.image.description
                    ? escapeHtml(post.image.description)
                    : "";
                if (post.image.media_type === "video") {
                    imagePreview =
                        '<div class="article-image" data-reddit-media="image" style="aspect-ratio: 16 / 9; overflow: hidden; background-color: #000;">' +
                        '<video data-reddit-media-video="1" autoplay loop muted playsinline preload="metadata" style="display: block; width: 100%; height: 100%; object-fit: cover;">' +
                        '<source src="' +
                        post.image.url +
                        '">' +
                        "</video>" +
                        "</div>";
                } else {
                    imagePreview =
                        '<div class="article-image" data-reddit-media="image" style="aspect-ratio: 16 / 9; overflow: hidden; background-color: #f8f9fa;">' +
                        '<img data-reddit-media-img="1" src="' +
                        post.image.url +
                        '" style="width: 100%; height: 100%; object-fit: cover;" alt="' +
                        imageAlt +
                        '"/>' +
                        "</div>";
                }
            }

            articleSection = [
                '<div class="article-preview" style="border: 1px solid #e1e8ed; border-radius: 12px; margin: 12px 0; overflow: hidden; background: #fff;">',
                '  <a href="' +
                    articleUrl +
                    '" target="_blank" rel="noopener" style="text-decoration: none; color: inherit; display: block;">',
                imagePreview,
                '    <div style="padding: 14px 14px 12px 14px;">',
                '      <h4 style="margin: 0 0 8px 0; font-size: 18px; font-weight: 650; color: #1c1c1c; line-height: 1.25;">' +
                    escapeHtml(articleTitle) +
                    "</h4>",
                '      <p data-role="article-summary"' + articleIdAttr + ' style="margin: 0 0 10px 0; color: #555; font-size: 15px; line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;">' +
                    escapeHtml(articleSummary) +
                    "</p>",
                '      <div style="display: flex; align-items: center; gap: 8px; color: #999; font-size: 12px;">' +
                    '<span style="display: inline-block; padding: 2px 8px; border: 1px solid #eef0f2; border-radius: 999px; color: #6b7280; background: #fafafa;">' +
                    escapeHtml(post.article.source || "Link") +
                    "</span>" +
                    '<span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">' +
                    escapeHtml(
                        (articleUrl || "")
                            .replace(/^https?:\/\//, "")
                            .replace(/^www\./, "")
                            .slice(0, 70),
                    ) +
                    "</span>" +
                    "</div>",
                "    </div>",
                "  </a>",
                "</div>",
            ].join("");
        }

        var imageSection = "";
        // Only show standalone image if there's no article (article now includes image)
        if (
            post.image &&
            post.image.url &&
            (!post.article || post.article === 0)
        ) {
            var imageAlt = post.image.description
                ? escapeHtml(post.image.description)
                : "";
            var imageIdAttr = post.image_id ? (' data-image-id="' + String(post.image_id) + '"') : "";
            if (post.image.media_type === "video") {
                imageSection =
                    '<div class="post-image" data-reddit-media="image" style="margin-bottom: 12px;">' +
                    '<video data-role="image-media"' + imageIdAttr + ' data-reddit-media-video="1" autoplay loop muted playsinline preload="metadata" style="display: block; width: 100%; height: auto; border-radius: 8px; background: #000;" title="' +
                    imageAlt +
                    '">' +
                    '<source src="' +
                    post.image.url +
                    '">' +
                    "</video>" +
                    "</div>";
            } else {
                imageSection =
                    '<div class="post-image" data-reddit-media="image" style="margin-bottom: 12px;"><img data-role="image-media"' +
                    imageIdAttr +
                    ' data-reddit-media-img="1" src="' +
                    post.image.url +
                    '" alt="' +
                    imageAlt +
                    '" style="display: block; width: 100%; height: auto; object-fit: contain; border-radius: 8px;"></div>';
            }
        }

        var sharedSection = "";
        if (post.shared_from && post.shared_from !== -1) {
            sharedSection =
                '<div style="text-align: right; border-bottom: 1px solid #f0f0f0; margin-bottom: 12px;"><p><small>Shared from: <a href="' +
                buildThreadUrl(post.shared_from[0]) +
                '">' +
                escapeHtml(post.shared_from[1] || "") +
                "</a></small></p></div>";
        }

        var deleteAction = "";
        if (hasDeletePrivilege) {
            deleteAction = [
                '<a class="dropdown-item delete-post-trigger" data-post-id="' +
                    post.post_id +
                    '" href="#">',
                '  <div class="media">',
                '    <i data-feather="trash-2"></i>',
                '    <div class="media-content">',
                "      <h3>Delete</h3>",
                "      <small>Remove this post</small>",
                "    </div>",
                "  </div>",
                "</a>",
            ].join("");
        }

        var postHtml = [
            '<div class="card is-post reddit-post" data-reddit-post data-post-id="' +
                post.post_id +
                '" data-thread-id="' +
                threadId +
                '" data-vote="' +
                vote +
                '" data-likes="' +
                likes +
                '" data-dislikes="' +
                dislikes +
                '" data-score="' +
                score +
                '" data-comment-count="' +
                (post.t_comments || 0) +
                '" data-thread-url="' +
                buildThreadUrl(post.post_id) +
                '">',
            '  <div class="content-wrap" style="padding: 0;">',
            '    <div class="card-heading" style="padding: 12px 16px 0 16px;">',
            '      <div class="user-block" style="display: flex; align-items: center; gap: 12px;">',
            '        <div class="image" style="width: 40px; height: 40px;">',
            '          <img src="https://via.placeholder.com/300x300" ' +
                'data-demo-src="' +
                escapeHtml(post.profile_pic || "https://via.placeholder.com/300x300") +
                '"' +
                ' alt="' +
                escapeHtml(post.author || "") +
                '" style="border-radius: 50%; width: 40px; height: 40px;">',
            "        </div>",
            '        <div class="user-info" style="display: flex; flex-direction: column;">',
            '          <a class="post-author-link" href="' +
                buildProfileUrl(post.author_id) +
                '" style="color: inherit; text-decoration: none; font-weight: 500;">' +
                escapeHtml(post.author || "") +
                "</a>",
            '          <span class="time">' +
                formatDisplayTime(post) +
                "</span>",
            "        </div>",
            "      </div>",
            '      <div class="dropdown is-spaced is-right is-neutral dropdown-trigger">',
            '        <div class="button"><i data-feather="more-vertical"></i></div>',
            '        <div class="dropdown-menu" role="menu">',
            '          <div class="dropdown-content">',
            '            <a href="' +
                buildThreadUrl(post.post_id) +
                '" class="dropdown-item">',
            '              <div class="media">',
            '                <i data-feather="bookmark"></i>',
            '                <div class="media-content">',
            "                  <h3>Discussion</h3>",
            "                  <small>See full discussion thread</small>",
            "                </div>",
            "              </div>",
            "            </a>",
            deleteAction,
            "          </div>",
            "        </div>",
            "      </div>",
            "    </div>",
            '    <div class="card-body" style="padding: 12px 16px;">',
            sharedSection,
            post.title
                ? '<h3 class="reddit-post-title"><a href="' +
                  buildThreadUrl(post.post_id) +
                  '" class="reddit-post-title-link">' +
                  escapeHtml(post.title) +
                  "</a></h3>"
                : "",
            post.post
                ? '<div class="post-text post-body" style="color: #1c1c1c; font-size: 16px; line-height: 1.5; margin-bottom: 12px; cursor: pointer;">' +
                  post.post +
                  "</div>"
                : "",
            articleSection,
            imageSection,
            "    </div>",
            "  </div>",
            '  <div class="post-footer" style="display: flex; align-items: center; gap: 12px; padding: 0 16px 12px 16px; border-top: 1px solid #e1e8ed;">',
            '    <div class="vote-stack" style="background: #f8f9fa; border-radius: 4px; display: flex; flex-direction: column; align-items: center; padding: 4px; min-width: 40px;">',
            '      <button class="vote-button" type="button" data-action="like" aria-label="Upvote" style="background: none; border: none; cursor: pointer; padding: 2px;"><i data-feather="arrow-up" style="width: 16px; height: 16px;"></i></button>',
            '      <span class="vote-score" data-role="score" style="font-size: 12px; font-weight: bold; color: #1c1c1c; margin: 2px 0;">' +
                score +
                "</span>",
            '      <button class="vote-button" type="button" data-action="dislike" aria-label="Downvote" style="background: none; border: none; cursor: pointer; padding: 2px;"><i data-feather="arrow-down" style="width: 16px; height: 16px;"></i></button>',
            "    </div>",
            '    <a class="open-thread-button" data-role="open-thread" href="' +
                buildThreadUrl(post.post_id) +
                '" style="background: none; border: none; cursor: pointer; padding: 6px 8px; border-radius: 4px; color: #878a8c; font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 4px; text-decoration: none;">',
            '      <i data-feather="message-square" style="width: 16px; height: 16px;"></i>',
            '      <span><span data-role="comment-count">' +
                (post.t_comments || 0) +
                "</span> Comments</span>",
            "    </a>",
            "  </div>",
            "</div>",
        ].join("");

        return $(postHtml);
    }

    function renderPosts(posts, options) {
        options = options || {};
        var $container = $(FEED_SELECTORS.container);
        if (!$container.length) {
            return;
        }

        var loggedUserId = window.redditContext
            ? window.redditContext.loggedUserId
            : null;
        var postById = {};
        (posts || []).forEach(function (p) {
            if (p && p.post_id != null) {
                postById[Number(p.post_id)] = p;
            }
        });

        // Collect existing post IDs to prevent duplicates
        var existingIds = {};
        if (!options.replace) {
            $container.find("[data-post-id]").each(function () {
                existingIds[$(this).attr("data-post-id")] = true;
            });
        }

        var fragment = $(document.createDocumentFragment());
        var appendedNodes = [];
        posts.forEach(function (post) {
            if (existingIds[post.post_id]) {
                return; // skip duplicate
            }
            existingIds[post.post_id] = true;
            var node = buildPostNode(post, loggedUserId);
            appendedNodes.push(node);
            fragment.append(node);
        });

        if (options.replace) {
            $container.empty();
            hideNewPostsNotice();
        }
        $container.append(fragment);

        appendedNodes.forEach(function ($post) {
            var state = parseVoteState($post);
            setVoteState($post, state);

            // Load profile images with data-demo-src
            $post.find("[data-demo-src]").each(function () {
                var newSrc = $(this).attr("data-demo-src");
                $(this).attr("src", newSrc);
            });

            enhanceRedditMedia($post);

            // Lazy enrichment for link summaries and image descriptions.
            var postId = Number($post.attr("data-post-id"));
            var postData = postById[postId] || null;
            if (postData) {
                maybeEnrichPost($post, postData);
            }
        });

        if (window.feather && window.feather.replace) {
            window.feather.replace();
        }
    }

    function maybeEnrichPost($post, post) {
        if (!post) {
            return;
        }

        if (
            post.article_needs_enrichment &&
            post.article_id &&
            !articleEnrichInFlight.has(post.article_id)
        ) {
            articleEnrichInFlight.add(post.article_id);
            Api.enrichArticle(post.article_id, false)
                .done(function (data) {
                    if (data && data.ok && data.summary) {
                        $post
                            .find('[data-role="article-summary"][data-article-id="' + post.article_id + '"]')
                            .text(data.summary);
                    }
                })
                .always(function () {
                    articleEnrichInFlight.delete(post.article_id);
                });
        }

        if (
            post.image_needs_enrichment &&
            post.image_id &&
            !imageEnrichInFlight.has(post.image_id)
        ) {
            imageEnrichInFlight.add(post.image_id);
            Api.enrichImage(post.image_id, false)
                .done(function (data) {
                    if (data && data.ok && data.description) {
                        // Update alt/title for the standalone media element if present.
                        var $media = $post.find('[data-role="image-media"][data-image-id="' + post.image_id + '"]');
                        if ($media.length) {
                            if ($media.is("img")) {
                                $media.attr("alt", data.description);
                            }
                            $media.attr("title", data.description);
                        }
                    }
                })
                .always(function () {
                    imageEnrichInFlight.delete(post.image_id);
                });
        }
    }

    function handleThreadOpen(event) {
        event.preventDefault();
        var $btn = $(event.currentTarget);
        var $post = getPostElement($btn);
        var url = $post.attr("data-thread-url");
        if (url) {
            window.location.href = url;
        }
    }

    function handleThreadOpenFromContent(event) {
        // Make post body behave like Reddit: click opens the thread.
        // Guard against clicks on links/buttons and against navigating while selecting text.
        if (
            $(event.target).closest("a, button, input, textarea, select, label")
                .length
        ) {
            return;
        }
        if (window.getSelection) {
            var selection = window.getSelection();
            if (
                selection &&
                selection.toString &&
                selection.toString().trim()
            ) {
                return;
            }
        }
        var $post = getPostElement(event.currentTarget);
        var url = $post.attr("data-thread-url");
        if (url) {
            window.location.href = url;
        }
    }

    function resetComposeForm() {
        $(FEED_SELECTORS.postTitle).val("");
        $(FEED_SELECTORS.postBody).val("");
        $(FEED_SELECTORS.linkUrl).val("");
        $(FEED_SELECTORS.imageUrl).val("");
        $(FEED_SELECTORS.annotation).val("");
        clearUploadPreview();
        setActivePostTypeTab("text");
        setRadioValue(FEED_SELECTORS.imageSourceInputs, "upload");
        updateComposeUi();
        $(FEED_SELECTORS.publishButton)
            .prop("disabled", true)
            .removeClass("is-loading");
    }

    function showComposeCard() {
        $(FEED_SELECTORS.composeTrigger).hide();
        $(FEED_SELECTORS.composeCard).show();
        $(FEED_SELECTORS.postTitle).focus();
    }

    function hideComposeCard() {
        $(FEED_SELECTORS.composeCard).hide();
        $(FEED_SELECTORS.composeTrigger).show();
        // Clear the app-wide overlay that compose.js activates when the compose
        // area is opened — it is only removed by .close-publish in compose.js,
        // so we must clear it here too when hiding after a successful submit.
        $(".app-overlay").removeClass("is-active");
        $(".is-new-content").removeClass("is-highlighted");
        resetComposeForm();
    }

    function combinePostContent(title, body) {
        var content = title || "";
        if (body) {
            content += "\n\n" + body;
        }
        return content.trim();
    }

    function gatherPostPayload() {
        syncComposeStateFromInputs();
        var title = $(FEED_SELECTORS.postTitle).val().trim();
        var body = $(FEED_SELECTORS.postBody).val().trim();
        var linkUrl = ($(FEED_SELECTORS.linkUrl).val() || "").trim();
        var imageUrl = ($(FEED_SELECTORS.imageUrl).val() || "").trim();
        var annotation = $(FEED_SELECTORS.annotation).val() || "";

        var content = combinePostContent(title, body);
        if (annotation) {
            if (body) {
                body += "\n\n" + annotation;
            } else {
                body = annotation;
            }
            content = combinePostContent(title, body);
        }
        var url = "";
        if (composeState.postType === "link") {
            url = linkUrl;
        } else if (composeState.postType === "image") {
            if (composeState.imageSource === "url") {
                url = imageUrl;
            }
        }

        return {
            content: content,
            title: title,
            body: body,
            url: url,
            postType: composeState.postType,
            imageSource: composeState.imageSource,
        };
    }

    function refreshFeedAfterPost() {
        fetchFeedPage(1, { replace: true, showError: true });
    }

    function handlePostSubmit(event) {
        event.preventDefault();
        var payload = gatherPostPayload();
        if (!payload.content) {
            notify("Title is required to publish a post.", "error");
            return;
        }

        var $button = $(FEED_SELECTORS.publishButton);
        $button.addClass("is-loading").prop("disabled", true);

        var postPromise;
        if (payload.postType === "image" && payload.imageSource === "upload") {
            if (!composeState.selectedFile) {
                $button.removeClass("is-loading");
                updatePublishButtonState();
                notify("Please choose a media file to upload.", "error");
                return;
            }
            postPromise = Api.uploadMedia(composeState.selectedFile).then(function (
                data,
            ) {
                return Api.createPost({
                    content: payload.content,
                    title: payload.title,
                    body: payload.body,
                    url: data.url,
                });
            });
        } else {
            if (payload.postType === "link" && !payload.url) {
                $button.removeClass("is-loading");
                updatePublishButtonState();
                notify("Link URL is required for link posts.", "error");
                return;
            }
            if (
                payload.postType === "image" &&
                payload.imageSource === "url" &&
                !payload.url
            ) {
                $button.removeClass("is-loading");
                updatePublishButtonState();
                notify("Media URL is required for media posts.", "error");
                return;
            }
            postPromise = Api.createPost({
                content: payload.content,
                title: payload.title,
                body: payload.body,
                url: payload.url,
            });
        }

        postPromise
            .then(function () {
                notify("Post published successfully!", "success");
                hideComposeCard();
                refreshFeedAfterPost();
            })
            .fail(function (err) {
                $button.removeClass("is-loading");
                updatePublishButtonState();
                notify(err.message || "Unable to publish post. Please try again.");
            })
            .always(function () {
                $button.removeClass("is-loading");
                updatePublishButtonState();
            });
    }

    function handleScroll() {
        if (feedState.isLoading || !feedState.hasMore) {
            return;
        }
        var threshold =
            document.documentElement.scrollHeight - window.innerHeight - 400;
        if (window.scrollY >= threshold) {
            loadMorePosts();
        }
    }

    function loadMorePosts() {
        if (feedState.isLoading || !feedState.hasMore) {
            return;
        }

        var nextPage = feedState.currentPage + 1;
        fetchFeedPage(nextPage, { replace: false, showError: true })
            .then(function (response) {
                var posts = response.data || [];
                if (!posts.length) {
                    feedState.hasMore = false;
                    $(FEED_SELECTORS.endOfFeed).show();
                    return;
                }
            });
    }

    function handleDeletePost(event) {
        event.preventDefault();
        var $btn = $(event.currentTarget);
        var postId = $btn.data("post-id");
        if (!postId) {
            return;
        }
        if (
            !window.confirm("Delete this post? This action cannot be undone.")
        ) {
            return;
        }

        var $post = getPostElement($btn);
        Api.deletePost(postId)
            .then(function () {
                $post.remove();
            })
            .fail(function (err) {
                notify(
                    (err && err.message) || "Unable to delete post right now.",
                    "error",
                );
            });
    }

    function bindComposeEvents() {
        var $title = $(FEED_SELECTORS.postTitle);
        var $publishButton = $(FEED_SELECTORS.publishButton);
        var $linkUrl = $(FEED_SELECTORS.linkUrl);
        var $imageUrl = $(FEED_SELECTORS.imageUrl);
        var $file = $(FEED_SELECTORS.imageFile);

        if (!$title.length) {
            return;
        }

        function handleComposeChange() {
            updateComposeUi();
            updatePublishButtonState();
        }

        // Keep button enabled/disabled based on selected post type requirements.
        $title.on("input", updatePublishButtonState);
        $(FEED_SELECTORS.postBody).on("input", updatePublishButtonState);
        $linkUrl.on("input", updatePublishButtonState);
        $imageUrl.on("input", updatePublishButtonState);
        $(FEED_SELECTORS.composeCard)
            .find(FEED_SELECTORS.postTypeTabs)
            .on("click", "a", function (e) {
                e.preventDefault();
                var $li = $(this).closest(FEED_SELECTORS.postTypeTabs);
                var v = $li.data("post-type-tab");
                if (!v) {
                    return;
                }
                setActivePostTypeTab(v);
                handleComposeChange();
            });
        $(FEED_SELECTORS.imageSourceInputs).on("change", handleComposeChange);

        if ($file.length) {
            $file.on("change", function () {
                var file = this.files && this.files[0] ? this.files[0] : null;
                clearUploadPreview();
                if (!file) {
                    updatePublishButtonState();
                    return;
                }

                composeState.selectedFile = file;
                // Avoid ambiguity: upload mode uses file, so clear URL.
                $imageUrl.val("");
                renderUploadPreview(file);
                updatePublishButtonState();
            });
        }

        $(FEED_SELECTORS.composeTrigger).on("click", function (e) {
            e.preventDefault();
            showComposeCard();
            updateComposeUi();
            updatePublishButtonState();
        });

        $(document).on("click", ".close-publish", function (e) {
            e.preventDefault();
            hideComposeCard();
        });

        $publishButton.on("click", handlePostSubmit);
    }

    function bindFeedEvents() {
        $(document).on("click", ".vote-button", handleVoteClick);
        $(document).on("click", ".open-thread-button", handleThreadOpen);
        $(document).on("click", ".post-text", handleThreadOpenFromContent);
        $(document).on("click", ".delete-post-trigger", handleDeletePost);
    }

    function bindFeedTypeSelector() {
        var $select = $(FEED_SELECTORS.feedTypeSelect);
        if (!$select.length) {
            return;
        }
        $select.val(feedState.feedType);
        $("#feed-search-feed-type").val(feedState.feedType);
        $select.on("change", function () {
            var selected = ($select.val() || "").trim();
            if (!VALID_FEED_TYPES.has(selected)) {
                return;
            }
            feedState.feedType = selected;
            $("#feed-search-feed-type").val(selected);
            syncFeedUrlWithState();
            fetchFeedPage(1, { replace: true, showError: true });
        });
    }

    function buildSearchPageUrl(query) {
        var expId = getExpId();
        var params = new URLSearchParams();
        params.set("q", query);
        params.set("feed_type", feedState.feedType);
        return "/" + expId + "/rsearch?" + params.toString();
    }

    function bindFeedSearch() {
        var $form = $(FEED_SELECTORS.searchForm);
        var $input = $(FEED_SELECTORS.searchInput);
        if (!$form.length || !$input.length) {
            return;
        }

        $input.val(feedState.searchQuery || "");
        $form.on("submit", function (event) {
            var query = ($input.val() || "").trim();
            if (feedState.viewMode === "feed") {
                event.preventDefault();
                if (!query) {
                    return;
                }
                window.location.href = buildSearchPageUrl(query);
                return;
            }

            event.preventDefault();
            feedState.searchQuery = query;
            syncFeedUrlWithState();
            fetchFeedPage(1, { replace: true, showError: true });
        });
    }

    function bindRefreshNotice() {
        var $button = $(FEED_SELECTORS.refreshNoticeButton);
        if (!$button.length) {
            return;
        }
        $button.on("click", function (event) {
            event.preventDefault();
            hideNewPostsNotice();
            fetchFeedPage(1, { replace: true, showError: true });
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }

    function initializeFeed() {
        var $container = $(FEED_SELECTORS.container);
        if (!$container.length) {
            return;
        }

        parseInitialState();
        bindComposeEvents();
        bindFeedEvents();
        bindFeedTypeSelector();
        bindFeedSearch();
        bindRefreshNotice();
        syncFeedUrlWithState();
        startAutoRefresh();

        $(window).on("scroll", handleScroll);
        document.addEventListener("visibilitychange", function () {
            if (document.hidden) {
                return;
            }
            if (!shouldAutoRefreshFeed()) {
                return;
            }
            fetchFeedPage(1, { replace: true, silent: true, showError: false });
        });

        $container.find("[data-reddit-post]").each(function () {
            var $post = $(this);
            var state = parseVoteState($post);
            setVoteState($post, state);
        });

        enhanceRedditMedia($container);

        if (window.feather && window.feather.replace) {
            window.feather.replace();
        }

        $(FEED_SELECTORS.endOfFeed).toggle(!feedState.hasMore);
        $(FEED_SELECTORS.loading).hide();
        hideNewPostsNotice();
    }

    function buildCommentNode(comment) {
        var loggedUserId = window.redditContext
            ? window.redditContext.loggedUserId
            : null;
        var hasDeletePrivilege = currentViewerCanDelete(comment.author_id, loggedUserId);
        var profilePicUrl = "https://via.placeholder.com/300x300";
        var profilePicSrc =
            comment.profile_pic || "https://via.placeholder.com/300x300";

        var dropdownHtml = "";
        if (hasDeletePrivilege) {
            dropdownHtml = [
                '<div class="dropdown is-spaced is-right is-neutral dropdown-trigger" onclick="event.stopPropagation()">',
                '  <div><div class="button"><i data-feather="more-vertical"></i></div></div>',
                '  <div class="dropdown-menu" role="menu">',
                '    <div class="dropdown-content">',
                '      <a class="dropdown-item delete-post-trigger" data-post-id="' + comment.post_id + '" href="#">',
                '        <div class="media">',
                '          <i data-feather="trash-2"></i>',
                '          <div class="media-content">',
                '            <h3>Delete</h3>',
                '            <small>Remove this comment</small>',
                "          </div>",
                "        </div>",
                "      </a>",
                "    </div>",
                "  </div>",
                "</div>",
            ].join("");
        }

        var html = [
            '<div class="reddit-comment post-detail-card" data-reddit-post data-post-id="' +
                comment.post_id +
                '" data-thread-id="' +
                comment.thread_id +
                '" data-vote="neutral" data-likes="0" data-dislikes="0" data-score="0" style="padding: 12px; margin-bottom: 8px; background: white; border-radius: 4px; border-left: 2px solid transparent;">',
            '  <div style="display: flex; align-items: center; margin-bottom: 4px;">',
            '    <div style="display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0;">',
            '    <img src="' +
                profilePicUrl +
                '" data-demo-src="' +
                profilePicSrc +
                '" style="width: 20px; height: 20px; border-radius: 50%; margin-right: 6px;" alt="">',
            '    <span class="comment-meta-author" style="font-weight: 500; color: #1c1c1c; margin-right: 6px; font-size: 12px;">',
            '      <a href="' +
                buildProfileUrl(comment.author_id) +
                '" style="color: inherit; text-decoration: none;">' +
                escapeHtml(comment.author) +
                "</a>",
            "    </span>",
            '    <span class="comment-meta-time" style="color: #7c7c7c; font-size: 11px;">' +
                formatDisplayTime(comment) +
                "</span>",
            "    </div>",
            dropdownHtml,
            "  </div>",
            '  <div class="post-body comment-body" style="color: #1c1c1c; font-size: 15px; line-height: 1.4; margin-bottom: 6px;">',
            '    <div class="comment-content" style="white-space: pre-wrap; word-wrap: break-word;">' +
                escapeHtml(comment.post) +
                "</div>",
            "  </div>",
            '  <div style="display: flex; align-items: center; gap: 8px; color: #7c7c7c; font-size: 11px; font-weight: 700; margin-bottom: 8px;">',
            '    <div class="vote-stack" style="display: flex; flex-direction: column; align-items: center; background: #f8f9fa; border-radius: 4px; padding: 4px;">',
            '      <button class="vote-button" type="button" data-action="like" aria-label="Upvote" style="background: none; border: none; cursor: pointer; padding: 2px;">',
            '        <i data-feather="arrow-up" style="width: 12px; height: 12px;"></i>',
            "      </button>",
            '      <span class="vote-score" data-role="score" style="font-size: 11px; font-weight: bold; color: #1c1c1c; margin: 2px 0;">0</span>',
            '      <button class="vote-button" type="button" data-action="dislike" aria-label="Downvote" style="background: none; border: none; cursor: pointer; padding: 2px;">',
            '        <i data-feather="arrow-down" style="width: 12px; height: 12px;"></i>',
            "      </button>",
            "    </div>",
            '    <button style="background: none; border: none; color: #7c7c7c; cursor: pointer; padding: 2px 6px; border-radius: 2px; font-size: 11px; font-weight: 700;" data-reply-target="' +
                comment.post_id +
                '" class="toggle-reply-button">Reply</button>',
            "  </div>",
            '  <div style="margin-bottom: 8px;">',
            '    <p id="message-' + comment.post_id + '"></p>',
            '    <form class="comment_form" id="comment_form-' +
                comment.post_id +
                '" style="display: none;">',
            '      <textarea rows="2" class="reply_comment" id="comment-' +
                comment.post_id +
                '" style="width: 100%; padding: 6px; border: 1px solid #ccc; border-radius: 4px; font-family: inherit; resize: vertical; margin-bottom: 6px; font-size: 12px;">@' +
                escapeHtml(comment.author) +
                " </textarea>",
            '      <button type="button" class="add-comment-button" style="background: #0079d3; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-weight: 600; font-size: 11px;" data-parent-id="' +
                comment.post_id +
                '">Reply</button>',
            "    </form>",
            "  </div>",
            "</div>",
        ].join("");

        return $(html);
    }

    function handleThreadCommentSubmit(event) {
        event.preventDefault();
        var button = event.currentTarget;
        var $button = $(button);
        if ($button.data("submitting")) {
            return;
        }

        var parentAttr = button.getAttribute("data-parent-id");
        var parentId = parentAttr ? parseInt(parentAttr, 10) : NaN;
        if (!parentId) {
            return;
        }
        if (commentSubmitInFlight.has(parentId)) {
            return;
        }

        var textarea = document.getElementById("comment-" + parentId);
        if (!textarea) {
            return;
        }

        var content = textarea.value.trim();
        if (!content) {
            notify("Please enter a comment before submitting.", "error");
            return;
        }

        $button.data("submitting", true);
        $button.prop("disabled", true);
        commentSubmitInFlight.add(parentId);
        $button.html(
            '<span style="display: inline-block; width: 12px; height: 12px; border: 2px solid #fff; border-top-color: transparent; border-radius: 50%; animation: spin 0.6s linear infinite;"></span>',
        );

        // Add CSS animation for spinner if not already present
        if (!document.getElementById("spinner-style")) {
            var style = document.createElement("style");
            style.id = "spinner-style";
            style.textContent =
                "@keyframes spin { to { transform: rotate(360deg); } }";
            document.head.appendChild(style);
        }

        var clientActionId = buildClientCommentActionId(parentId, content);
        Api.createComment(parentId, content, clientActionId)
            .then(function (response) {
                var commentData = response.data || response;
                var commentId = commentData && commentData.post_id ? String(commentData.post_id) : "";
                var alreadyInDom = commentId
                    ? $('[data-reddit-post][data-post-id="' + commentId + '"]').length > 0
                    : false;

                if (!alreadyInDom) {
                    // Build and insert the new comment
                    var $newComment = buildCommentNode(commentData);
                    var $parentContainer = $("#child-" + parentId);

                    if ($parentContainer.length) {
                        // Insert as first child with proper nesting
                        var $wrapper = $(
                            '<div style="padding-left: 24px; border-left: 1px solid #e1e8ed; margin-left: 12px;"></div>',
                        );
                        $wrapper.append($newComment);
                        $parentContainer.prepend($wrapper);
                    } else {
                        // Fallback: insert after parent post
                        var $parentPostFallback = $('[data-post-id="' + parentId + '"]');
                        if ($parentPostFallback.length) {
                            $parentPostFallback.after($newComment);
                        }
                    }

                    // Initialize vote state for new comment
                    var state = parseVoteState($newComment);
                    setVoteState($newComment, state);

                    // Load profile images with data-demo-src
                    $newComment.find("[data-demo-src]").each(function () {
                        var newSrc = $(this).attr("data-demo-src");
                        $(this).attr("src", newSrc);
                    });

                    // Reinitialize feather icons
                    if (window.feather && window.feather.replace) {
                        window.feather.replace();
                    }
                }

                // Clear the textarea
                textarea.value = "";

                // Hide the reply form
                var form = document.getElementById("comment_form-" + parentId);
                if (form) {
                    form.style.display = "none";
                }

                // Update comment count only when we actually inserted a new node.
                if (!alreadyInDom) {
                    var $parentPost = $('[data-post-id="' + parentId + '"]');
                    if ($parentPost.length) {
                        var currentCount = parseInt(
                            $parentPost.attr("data-comment-count") || "0",
                            10,
                        );
                        $parentPost.attr("data-comment-count", currentCount + 1);
                        var $countDisplay = $parentPost.find(
                            '[data-role="comment-count"]',
                        );
                        if ($countDisplay.length) {
                            $countDisplay.text(currentCount + 1);
                        }
                    }
                }

                if (alreadyInDom || commentData.deduped) {
                    notify("Comment already posted.", "info");
                } else {
                    notify("Comment posted successfully!", "success");
                }

                commentSubmitInFlight.delete(parentId);
                $button.data("submitting", false);
                $button.prop("disabled", false);
                $button.html("Reply");
            })
            .fail(function (err) {
                commentSubmitInFlight.delete(parentId);
                $button.data("submitting", false);
                $button.prop("disabled", false);
                $button.html("Reply");
                notify(
                    err.message || "Unable to post comment. Please try again.",
                );
            });
    }

    function initializeThreadHelpers() {
        var $threadRoot = $(".reddit-thread-post");
        if (!$threadRoot.length) {
            return;
        }

        // Bind vote buttons for thread view
        bindFeedEvents();

        $("[data-reddit-post]").each(function () {
            var $post = $(this);
            var state = parseVoteState($post);
            setVoteState($post, state);
        });

        enhanceRedditMedia($(document));

        // Lazy enrichment for server-rendered thread view.
        maybeEnrichThreadDom($threadRoot);

        $(document).on("click", ".toggle-reply-button", function (event) {
            event.preventDefault();
            var target = event.currentTarget.getAttribute("data-reply-target");
            if (!target) {
                return;
            }
            var form = document.getElementById("comment_form-" + target);
            var message = document.getElementById("message-" + target);
            if (!form) {
                return;
            }
            var isHidden =
                form.style.display === "none" || form.style.display === "";
            form.style.display = isHidden ? "block" : "none";
            if (message) {
                message.style.display = isHidden ? "none" : "block";
            }
            if (isHidden) {
                var textarea = document.getElementById("comment-" + target);
                if (textarea) {
                    textarea.focus();
                    // Move cursor to end (after @username)
                    var length = textarea.value.length;
                    textarea.setSelectionRange(length, length);
                }
            }
        });

        $(document).on(
            "click",
            ".add-comment-button",
            handleThreadCommentSubmit,
        );
    }

    function initializeProfileCards() {
        var $postsRoot = $("#posts-container");
        if (!$postsRoot.length) {
            return;
        }

        bindFeedEvents();

        $postsRoot.find("[data-reddit-post]").each(function () {
            var $post = $(this);
            var state = parseVoteState($post);
            setVoteState($post, state);
        });

        $postsRoot.find("[data-demo-src]").each(function () {
            var newSrc = $(this).attr("data-demo-src");
            if (newSrc) {
                $(this).attr("src", newSrc);
            }
        });

        enhanceRedditMedia($postsRoot);

        if (window.feather && window.feather.replace) {
            window.feather.replace();
        }
    }

    function maybeEnrichThreadDom($threadRoot) {
        if (!$threadRoot || !$threadRoot.length) {
            return;
        }

        var articleNeeds = $threadRoot.attr("data-article-needs-enrichment") === "1";
        var articleId = Number($threadRoot.attr("data-article-id") || 0) || 0;
        if (articleNeeds && articleId && !articleEnrichInFlight.has(articleId)) {
            articleEnrichInFlight.add(articleId);
            Api.enrichArticle(articleId, false)
                .done(function (data) {
                    if (data && data.ok && data.summary) {
                        $threadRoot
                            .find('[data-role="article-summary"][data-article-id="' + articleId + '"]')
                            .text(data.summary);
                    }
                })
                .always(function () {
                    articleEnrichInFlight.delete(articleId);
                });
        }

        var imageNeeds = $threadRoot.attr("data-image-needs-enrichment") === "1";
        var imageId = Number($threadRoot.attr("data-image-id") || 0) || 0;
        if (imageNeeds && imageId && !imageEnrichInFlight.has(imageId)) {
            imageEnrichInFlight.add(imageId);
            Api.enrichImage(imageId, false)
                .done(function (data) {
                    if (data && data.ok && data.description) {
                        var $media = $threadRoot.find('[data-role="image-media"][data-image-id="' + imageId + '"]');
                        if ($media.length) {
                            if ($media.is("img")) {
                                $media.attr("alt", data.description);
                            }
                            $media.attr("title", data.description);
                        }
                    }
                })
                .always(function () {
                    imageEnrichInFlight.delete(imageId);
                });
        }
    }

    $(document).ready(function () {
        initializeFeed();
        initializeThreadHelpers();
        initializeProfileCards();
    });

    var MEDIA_RULES = Object.freeze({
        // Many Reddit RSS thumbnails are small (e.g. 140x70). We still want to show them
        // rather than stripping the entire media block.
        minDim: 60,
        minPixels: 6000,
        maxCollapsedHeight: 520,
        tallAspect: 1.6,
    });

    function ensureMediaContainerStyling($container) {
        $container.css({
            position: $container.css("position") === "static" ? "relative" : $container.css("position"),
            overflow: "hidden",
            borderRadius: "8px",
            backgroundColor: "#f8f9fa",
            maxWidth: "100%",
        });
    }

    function removeMediaContainer($container) {
        $container.remove();
    }

    function isTinyImage(naturalWidth, naturalHeight) {
        if (!naturalWidth || !naturalHeight) {
            return false;
        }
        if (naturalWidth < MEDIA_RULES.minDim || naturalHeight < MEDIA_RULES.minDim) {
            return true;
        }
        if (naturalWidth * naturalHeight < MEDIA_RULES.minPixels) {
            return true;
        }
        return false;
    }

    function ensureExpandOverlay($container) {
        if ($container.find("[data-reddit-media-overlay]").length) {
            return;
        }
        var overlay = $(
            '<div data-reddit-media-overlay="1" style="position: absolute; left: 0; right: 0; bottom: 0; padding: 10px 12px; background: linear-gradient(to top, rgba(0,0,0,0.6), rgba(0,0,0,0)); color: white; font-size: 12px; font-weight: 700; letter-spacing: 0.2px;">View full image</div>',
        );
        $container.append(overlay);
    }

    function setCollapsed($container, collapsed) {
        if (collapsed) {
            ensureMediaContainerStyling($container);
            $container.css({
                maxHeight: MEDIA_RULES.maxCollapsedHeight + "px",
                cursor: "pointer",
            });
            ensureExpandOverlay($container);
            $container.attr("data-reddit-media-collapsed", "1");
        } else {
            $container.css({
                maxHeight: "none",
                cursor: "default",
            });
            $container.find("[data-reddit-media-overlay]").remove();
            $container.removeAttr("data-reddit-media-collapsed");
        }
    }

    function enhanceSingleMediaImage(img) {
        var $img = $(img);
        if ($img.attr("data-reddit-media-enhanced") === "1") {
            return;
        }
        $img.attr("data-reddit-media-enhanced", "1");

        var $container = $img.closest("[data-reddit-media='image']");
        if (!$container.length) {
            return;
        }

        function applyFromDimensions() {
            var w = img.naturalWidth || 0;
            var h = img.naturalHeight || 0;

            // Filter tiny images (e.g. very small local placeholders like image_15.jpg).
            if (isTinyImage(w, h)) {
                removeMediaContainer($container);
                return;
            }

            ensureMediaContainerStyling($container);
            $img.css({
                display: "block",
                width: "100%",
                height: "auto",
                maxWidth: "100%",
                maxHeight: "none",
                objectFit: "contain",
            });

            var aspect = w > 0 ? h / w : 0;
            if (aspect > MEDIA_RULES.tallAspect && h > MEDIA_RULES.maxCollapsedHeight) {
                setCollapsed($container, true);
                $container.off("click.redditMedia").on("click.redditMedia", function (event) {
                    // Don't interfere with link clicks.
                    if ($(event.target).closest("a").length) {
                        return;
                    }
                    var isCollapsed = $container.attr("data-reddit-media-collapsed") === "1";
                    setCollapsed($container, !isCollapsed);
                });
            } else {
                setCollapsed($container, false);
            }
        }

        $img.on("error", function () {
            removeMediaContainer($container);
        });

        if (img.complete) {
            applyFromDimensions();
        } else {
            $img.on("load", applyFromDimensions);
        }
    }

    function enhanceSingleMediaVideo(video) {
        var $video = $(video);
        if ($video.attr("data-reddit-media-enhanced") === "1") {
            return;
        }
        $video.attr("data-reddit-media-enhanced", "1");

        var $container = $video.closest("[data-reddit-media='image']");
        if (!$container.length) {
            return;
        }

        function applyFromDimensions() {
            var w = video.videoWidth || 0;
            var h = video.videoHeight || 0;

            // If we can't read dimensions, keep the media but don't collapse/filter.
            if (!w || !h) {
                ensureMediaContainerStyling($container);
                return;
            }

            // Filter tiny animations/clips as well.
            if (isTinyImage(w, h)) {
                removeMediaContainer($container);
                return;
            }

            ensureMediaContainerStyling($container);
            $video.css({
                display: "block",
                width: "100%",
                height: "auto",
                maxWidth: "100%",
                maxHeight: "none",
            });

            var aspect = h / w;
            if (aspect > MEDIA_RULES.tallAspect && h > MEDIA_RULES.maxCollapsedHeight) {
                setCollapsed($container, true);
                $container.off("click.redditMedia").on("click.redditMedia", function (event) {
                    if ($(event.target).closest("a").length) {
                        return;
                    }
                    var isCollapsed = $container.attr("data-reddit-media-collapsed") === "1";
                    setCollapsed($container, !isCollapsed);
                });
            } else {
                setCollapsed($container, false);
            }
        }

        $video.on("error", function () {
            removeMediaContainer($container);
        });

        if (video.readyState >= 1) {
            applyFromDimensions();
        } else {
            $video.on("loadedmetadata", applyFromDimensions);
        }
    }

    function enhanceRedditMedia($root) {
        var $scope = $root && $root.length ? $root : $(document);
        $scope.find("img[data-reddit-media-img]").each(function () {
            enhanceSingleMediaImage(this);
        });
        $scope.find("video[data-reddit-media-video]").each(function () {
            enhanceSingleMediaVideo(this);
        });
    }
})(window.jQuery, window, document);
