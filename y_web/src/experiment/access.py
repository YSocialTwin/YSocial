"""Helpers for experiment visibility and management permissions."""

from y_web import db
from y_web.models import Exps, User_Experiment


def _get_shared_exp_ids(user_id):
    rows = User_Experiment.query.filter_by(user_id=user_id).all()
    return [row.exp_id for row in rows]


def get_shared_group_names(user_id):
    """Return group names reachable via at least one shared experiment."""
    shared_exp_ids = _get_shared_exp_ids(user_id)
    if not shared_exp_ids:
        return []

    groups = (
        db.session.query(Exps.exp_group)
        .filter(Exps.idexp.in_(shared_exp_ids))
        .filter(Exps.exp_group.isnot(None))
        .filter(Exps.exp_group != "")
        .distinct()
        .all()
    )
    return [group[0] for group in groups if group and group[0]]


def get_visible_experiment_query(admin_user):
    """Return query with experiments visible to current admin/researcher user."""
    if not admin_user:
        return Exps.query.filter(Exps.idexp == -1)

    if admin_user.role == "admin":
        return Exps.query

    if admin_user.role != "researcher":
        return Exps.query.filter(Exps.idexp == -1)

    shared_exp_ids = _get_shared_exp_ids(admin_user.id)
    shared_groups = get_shared_group_names(admin_user.id)

    filters = [Exps.owner == admin_user.username]
    if shared_exp_ids:
        filters.append(Exps.idexp.in_(shared_exp_ids))
    if shared_groups:
        filters.append(Exps.exp_group.in_(shared_groups))

    return Exps.query.filter(db.or_(*filters))


def user_can_view_experiment(admin_user, experiment):
    """Check if admin/researcher can view an experiment."""
    if not admin_user or not experiment:
        return False
    if admin_user.role == "admin":
        return True
    if admin_user.role != "researcher":
        return False
    if experiment.owner == admin_user.username:
        return True

    direct = User_Experiment.query.filter_by(
        user_id=admin_user.id, exp_id=experiment.idexp
    ).first()
    if direct:
        return True

    if experiment.exp_group and experiment.exp_group.strip():
        shared_groups = set(get_shared_group_names(admin_user.id))
        return experiment.exp_group in shared_groups

    return False


def user_can_manage_experiment(admin_user, experiment):
    """Check if user can stop/delete an experiment.

    Rules:
    - admin can always manage
    - owner can manage
    - researcher explicitly added to experiment can manage
    - researcher in a shared group can manage all experiments in that group
    """
    if not admin_user or not experiment:
        return False

    if admin_user.role == "admin":
        return True

    if experiment.owner == admin_user.username:
        return True

    if admin_user.role != "researcher":
        return False

    direct = User_Experiment.query.filter_by(
        user_id=admin_user.id, exp_id=experiment.idexp
    ).first()
    if direct:
        return True

    if experiment.exp_group and experiment.exp_group.strip():
        shared_groups = set(get_shared_group_names(admin_user.id))
        return experiment.exp_group in shared_groups

    return False
