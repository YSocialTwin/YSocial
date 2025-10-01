"""
Page/news organization management routes.

Administrative routes for creating and managing institutional pages,
configuring RSS feeds, political leanings, topics, and associating
pages with populations.
"""

import json
import os

from flask import Blueprint, render_template, request, redirect, send_file, flash
from flask_login import login_required, current_user

from y_web.models import (
    Population,
    Page,
    Page_Population,
    Leanings, Topic_List, Page_Topic
)
from y_web.utils import (
    get_feed,
    get_ollama_models,
)

from y_web import db
from y_web.utils.miscellanea import check_privileges
from y_web.utils.miscellanea import ollama_status

pages = Blueprint("pages", __name__)


@pages.route("/admin/pages")
@login_required
def page_data():
    check_privileges(current_user.username)

    models = get_ollama_models()
    ollamas = ollama_status()
    leanings = Leanings.query.all()
    return render_template(
        "admin/pages.html", models=models, ollamas=ollamas, leanings=leanings
    )


@pages.route("/admin/create_page", methods=["POST"])
@login_required
def create_page():
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    page_type = request.form.get("page_type")
    feed = request.form.get("feed")
    keywords = request.form.get("tags")
    logo = request.form.get("logo")
    pg_type = request.form.get("pg_type")
    leaning = request.form.get("leaning")

    page = Page(
        name=name,
        descr=descr,
        page_type=page_type,
        feed=feed,
        keywords=keywords,
        logo=logo,
        pg_type=pg_type,
        leaning=leaning,
    )

    db.session.add(page)
    db.session.commit()

    return page_data()


@pages.route("/admin/pages_data")
@login_required
def pages_data():
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
            if name not in ["name", "descr", "keywords", "page_type", "logo", "leaning"]:
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

    # response
    res = query.all()

    return {
        "data": [
            {
                "id": page.id,
                "name": page.name,
                "descr": page.descr,
                "keywords": page.keywords,
                "page_type": page.page_type,
                "logo": page.logo,
                "leaning": page.leaning,
            }
            for page in res
        ],
        "total": total,
    }


@pages.route("/admin/delete_page/<int:uid>")
@login_required
def delete_page(uid):
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

    ollamas = ollama_status()

    return render_template(
        "admin/page_details.html",
        page=page,
        page_populations=pops,
        populations=populations,
        feeds=feed[:3],
        ollamas=ollamas,
        topics=topics,
        page_topics=page_topics,
    )


@pages.route("/admin/add_topic_to_page", methods=["POST"])
@login_required
def add_topic_to_page():
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
    check_privileges(current_user.username)

    collection = request.files["collection"]

    BASE = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    if collection:
        collection.save(
            f"{BASE}experiments{os.sep}temp_data{os.sep}{collection.filename}"
        )
        pages = json.load(
            open(f"{BASE}experiments{os.sep}temp_data{os.sep}{collection.filename}")
        )
        for page in pages:
            # check if the page already exists
            p = Page.query.filter_by(name=page["name"], feed=page["feed"]).first()
            if p:
                continue

            page = Page(
                name=page["name"],
                descr=page["descr"],
                page_type=page["page_type"],
                feed=page["feed"],
                keywords=page["keywords"],
                logo=page["logo"],
                pg_type=page["pg_type"],
                leaning=page["leaning"],
            )
            db.session.add(page)
            db.session.commit()

    # delete the file
    os.remove(f"{BASE}experiments{os.sep}temp_data{os.sep}{collection.filename}")

    return redirect(request.referrer)


@pages.route("/admin/download_pages")
@login_required
def download_pages():
    check_privileges(current_user.username)

    pages = Page.query.all()

    data = []
    for page in pages:
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
            }
        )

    BASE = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    with open(f"{BASE}experiments{os.sep}temp_data{os.sep}pages.json", "w") as f:
        json.dump(data, f)

    return send_file(
        f"{BASE}experiments{os.sep}temp_data{os.sep}pages.json", as_attachment=True
    )
