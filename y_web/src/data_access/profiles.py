"""
Profile picture data-access helpers.

Contains ``get_safe_profile_pic`` — the single function in this module —
which resolves a display picture URL for any user or page in the system.
"""

from y_web.src.models import Admin_users, Agent, Page


def get_safe_profile_pic(username, is_page=0):
    """
    Safely retrieve profile picture URL for a user or page.

    Attempts to find profile picture from multiple sources with fallbacks.

    Args:
        username: Username to get profile picture for
        is_page: 1 if username refers to a page, 0 for regular user

    Returns:
        Profile picture URL string, or empty string if not found
    """
    if is_page == 1:
        try:
            pg = Page.query.filter_by(name=username).first()
            if pg is not None and hasattr(pg, "logo") and pg.logo:
                return pg.logo
        except:
            pass
    else:
        try:
            ag = Agent.query.filter_by(name=username).first()
            if ag is not None and hasattr(ag, "profile_pic") and ag.profile_pic:
                return ag.profile_pic
        except:
            pass

        try:
            admin_user = Admin_users.query.filter_by(username=username).first()
            if (
                admin_user is not None
                and hasattr(admin_user, "profile_pic")
                and admin_user.profile_pic
            ):
                return admin_user.profile_pic
        except:
            pass

    return ""
