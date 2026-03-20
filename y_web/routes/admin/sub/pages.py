"""
Page/news organization management routes.

Administrative routes for creating and managing institutional pages,
configuring RSS feeds, political leanings, topics, and associating
pages with populations.
"""

import json
import os

from flask import Blueprint, flash, redirect, render_template, request
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    ActivityProfile,
    Leanings,
    Page,
    Page_Population,
    Page_Topic,
    Population,
    PopulationActivityProfile,
    Topic_List,
)
from y_web.utils import (
    get_feed,
    get_llm_models,
    get_ollama_models,
)
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status

pages = Blueprint("pages", __name__)


@pages.route("/admin/pages")
@login_required
def page_data():
    """
    Display page management interface.

    Returns:
        Rendered page data template with available models
    """
    check_privileges(current_user.username)

    models = get_llm_models()  # Use generic function for any LLM server
    llm_backend = llm_backend_status()
    leanings = Leanings.query.all()
    activity_profiles = ActivityProfile.query.all()
    return render_template(
        "admin/pages.html",
        models=models,
        llm_backend=llm_backend,
        leanings=leanings,
        activity_profiles=activity_profiles,
    )


@pages.route("/admin/create_page", methods=["POST"])
@login_required
def create_page():
    """Create page."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    page_type = request.form.get("page_type")
    feed = request.form.get("feed")
    keywords = request.form.get("tags")
    logo = request.form.get("logo")
    pg_type = request.form.get("pg_type")
    leaning = request.form.get("leaning")
    activity_profile_id = request.form.get("activity_profile")

    # Validate that page name is unique
    existing_page = Page.query.filter_by(name=name).first()
    if existing_page:
        flash(f"Page name '{name}' already exists. Please choose a different name.")
        return page_data()

    page = Page(
        name=name,
        descr=descr,
        page_type=page_type,
        feed=feed,
        keywords=keywords,
        logo=logo,
        pg_type=pg_type,
        leaning=leaning,
        activity_profile=activity_profile_id,
    )

    db.session.add(page)
    db.session.commit()

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        {
            "action": "create_page",
            "data": {
                "page_name": name,
                "feed": feed,
                "logo": logo,
            },
        }
    )

    return page_data()


@pages.route("/admin/pages_data")
@login_required
def pages_data():
    """Display pages data page."""
    query = Page.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                Page.name.like(f"%{search}%"),
                Page.descr.like(f"%{search}%"),
                Page.keywords.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in [
                "name",
                "descr",
                "keywords",
                "page_type",
                "logo",
                "leaning",
            ]:
                name = "name"
            col = getattr(Page, name)
            if direction == "-":
                col = col.desc()
            order.append(col)
        if order:
            query = query.order_by(*order)

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    # get host and port of the server
    host = request.host.split(":")[0]
    port = request.host.split(":")[1] if ":" in request.host else "80"

    # response
    res = query.all()
    return {
        "data": [
            {
                "id": page.id,
                "name": page.name,
                "keywords": page.keywords,
                "page_type": page.page_type,
                "logo": (
                    page.logo
                    if page.logo != ""
                    else f"http://{host}:{port}/static/assets/img/vector/logo/Ysocial_l.png"
                ),
                "leaning": page.leaning,
                "activity_profile": (
                    [
                        db.session.query(ActivityProfile)
                        .filter(ActivityProfile.id == int(page.activity_profile))
                        .first()
                        .name
                    ]
                    if page.activity_profile
                    else []
                ),
            }
            for page in res
        ],
        "total": total,
    }


@pages.route("/admin/delete_page/<int:uid>")
@login_required
def delete_page(uid):
    """Delete page."""
    check_privileges(current_user.username)

    page = Page.query.filter_by(id=uid).first()

    # check if page is assigned to any population
    page_pop = Page_Population.query.filter_by(page_id=uid).first()
    if page_pop:
        # show an error message
        flash("Page is assigned to a population. Cannot delete.")
        return page_data()

    db.session.delete(page)
    db.session.commit()

    # delete page_population entries
    page_population = Page_Population.query.filter_by(page_id=uid).all()
    for pp in page_population:
        db.session.delete(pp)
        db.session.commit()

    return page_data()


@pages.route("/admin/page_details/<int:uid>")
@login_required
def page_details(uid):
    """Handle page details operation."""
    check_privileges(current_user.username)

    # get page details
    page = Page.query.filter_by(id=uid).first()

    # get agent populations along with population names and ids
    page_populations = (
        db.session.query(Page_Population, Population)
        .join(Population)
        .filter(Page_Population.page_id == uid)
        .all()
    )

    pops = [(p[1].name, p[1].id) for p in page_populations]

    # get all populations
    populations = Population.query.all()

    topics = Topic_List.query.all()
    page_topics = Page_Topic.query.filter_by(page_id=uid).all()

    # get topic names for page_topics from Topic_List
    page_topics = [
        Topic_List.query.filter_by(id=pt.topic_id).first().name for pt in page_topics
    ]

    feed = get_feed(page.feed)

    llm_backend = llm_backend_status()

    return render_template(
        "admin/page_details.html",
        page=page,
        page_populations=pops,
        populations=populations,
        feeds=feed[:3],
        llm_backend=llm_backend,
        topics=topics,
        page_topics=page_topics,
    )


@pages.route("/admin/add_topic_to_page", methods=["POST"])
@login_required
def add_topic_to_page():
    """
    Associate a topic with a page.

    Returns:
        Redirect to page details
    """
    check_privileges(current_user.username)

    page_id = request.form.get("page_id")
    topic_id = request.form.get("topic_id")

    # check if the topic is already in the page
    pt = Page_Topic.query.filter_by(page_id=page_id, topic_id=topic_id).first()
    if pt:
        return page_details(page_id)

    pt = Page_Topic(page_id=page_id, topic_id=topic_id)

    db.session.add(pt)
    db.session.commit()

    return page_details(page_id)


@pages.route("/admin/add_page_to_population", methods=["POST"])
@login_required
def add_page_to_population():
    """Handle add page to population operation."""
    check_privileges(current_user.username)

    page_id = request.form.get("page_id")
    population_id = request.form.get("population_id")

    # check if the page is already in the population
    ap = Page_Population.query.filter_by(
        page_id=page_id, population_id=population_id
    ).first()
    if ap:
        return page_details(page_id)

    ap = Page_Population(page_id=page_id, population_id=population_id)

    db.session.add(ap)
    db.session.commit()

    return page_details(page_id)


@pages.route("/admin/upload_page_collection", methods=["POST"])
@login_required
def upload_page_collection():
    """Upload page collection."""
    check_privileges(current_user.username)

    collection = request.files["collection"]

    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE, f"experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    if collection:
        collection.save(os.path.join(temp_data_dir, collection.filename))
        pages_data = json.load(open(os.path.join(temp_data_dir, collection.filename)))
        for page_data in pages_data:
            # check if the page already exists (by name and feed)
            existing_page = Page.query.filter_by(
                name=page_data["name"], feed=page_data["feed"]
            ).first()
            if existing_page:
                continue

            # Handle name duplicates by adding incremental suffix
            base_name = page_data["name"]
            page_name = base_name
            suffix = 0
            while Page.query.filter_by(name=page_name).first():
                suffix += 1
                page_name = f"{base_name}_{suffix}"

            # Resolve activity_profile by name if provided
            activity_profile_id = None
            if page_data.get("activity_profile"):
                activity_profile_obj = ActivityProfile.query.filter_by(
                    name=page_data["activity_profile"]
                ).first()
                if activity_profile_obj:
                    activity_profile_id = activity_profile_obj.id

            page = Page(
                name=page_name,
                descr=page_data["descr"],
                page_type=page_data["page_type"],
                feed=page_data["feed"],
                keywords=page_data["keywords"],
                logo=page_data["logo"],
                pg_type=page_data["pg_type"],
                leaning=page_data["leaning"],
                activity_profile=activity_profile_id,
            )
            db.session.add(page)
            db.session.commit()

    # delete the file
    os.remove(os.path.join(temp_data_dir, collection.filename))

    return redirect(request.referrer)


@pages.route("/admin/download_pages")
@login_required
def download_pages():
    """
    Download pages data as JSON file.

    Returns:
        JSON file download response
    """
    check_privileges(current_user.username)

    pages = Page.query.all()

    data = []
    for page in pages:
        # Get activity profile name if set
        activity_profile_name = None
        if page.activity_profile:
            activity_profile_obj = ActivityProfile.query.get(page.activity_profile)
            if activity_profile_obj:
                activity_profile_name = activity_profile_obj.name

        data.append(
            {
                "name": page.name,
                "descr": page.descr,
                "page_type": page.page_type,
                "feed": page.feed,
                "keywords": page.keywords,
                "logo": page.logo,
                "pg_type": page.pg_type,
                "leaning": page.leaning,
                "activity_profile": activity_profile_name,
            }
        )

    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Ensure temp_data directory exists
    temp_data_dir = os.path.join(BASE, f"experiments{os.sep}temp_data")
    os.makedirs(temp_data_dir, exist_ok=True)

    with open(os.path.join(temp_data_dir, "pages.json"), "w") as f:
        json.dump(data, f)

    return send_file_desktop(
        os.path.join(temp_data_dir, "pages.json"), as_attachment=True
    )
