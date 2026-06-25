"""
Agent population generation utilities.

Provides functions for generating realistic AI agent populations with diverse
demographic profiles, personality traits, and behavioral characteristics
based on population configuration parameters.
"""

import json
import math
import random
import re

import faker
import numpy as np
from sqlalchemy.sql import func

from y_web import db
from y_web.src.content.cover_images import random_cover_image_url
from y_web.src.models import (
    AgeClass,
    Agent,
    Agent_Ext,
    Agent_Population,
    Education,
    Leanings,
    Population,
    PopulationActivityProfile,
    Profession,
    Toxicity_Levels,
)


def __sample_round_actions(
    min_v: int,
    max_v: int,
    param: float,
    dist: str = "uniform",
) -> int:
    """
    Sample actions-per-active-slot (round_actions) using the configured distribution
    truncated to the integer support [min, max]. Falls back to uniform if invalid.
    """

    min_v = int(min_v)
    max_v = int(max_v)

    if min_v >= max_v:
        return max(min_v, 1)

    support = list(range(min_v, max_v + 1))
    R = len(support)

    # Map support to k in [1..R] for simpler formulas
    def to_value(k: int) -> int:
        return support[0] + (k - 1)

    # Uniform
    if dist == "uniform" or dist is None:
        return random.randint(min_v, max_v)

    if param is not None:
        param = float(param)

    # Build weights for k=1..R then sample
    weights = []
    if dist == "poisson":
        lam = float(param) if (param is not None) else 0.88
        if lam <= 0:
            return random.randint(min_v, max_v)
        # Unnormalized Poisson pmf over k=1..R (exclude zero)
        for k in range(1, R + 1):
            # compute poisson at k
            w = math.exp(-lam) * (lam**k) / math.factorial(k)
            weights.append(w)

    elif dist == "geometric":
        p = float(param) if (param is not None) else (2.0 / 3.0)
        if not (0 < p <= 1):
            return random.randint(min_v, max_v)
        for k in range(1, R + 1):
            w = p * ((1 - p) ** (k - 1))
            weights.append(w)
    elif dist == "zipf":
        s = float(param) if (param is not None) else 2.5
        if s <= 1:
            return random.randint(min_v, max_v)
        for k in range(1, R + 1):
            w = k ** (-s)
            weights.append(w)
    else:
        return random.randint(min_v, max_v)

    total = sum(weights)
    if total <= 0 or any(math.isnan(w) or math.isinf(w) for w in weights):
        return random.randint(min_v, max_v)

    # Sample k in [1..R] then map to support
    k = random.choices(range(1, R + 1), weights=weights, k=1)[0]
    return to_value(k)


def __sample_age(mean, std_dev, min_age, max_age):
    """
    Sample age from Gaussian distribution within specified bounds.

    Repeatedly samples from normal distribution until a value within the
    valid age range is obtained.

    Args:
        mean: Mean age for the distribution
        std_dev: Standard deviation for age distribution
        min_age: Minimum allowed age
        max_age: Maximum allowed age

    Returns:
        Integer age within [min_age, max_age]
    """
    while True:
        age = np.random.normal(mean, std_dev)  # Sample from Gaussian
        if min_age <= age <= max_age:  # Ensure it's within the range
            return int(round(age))


def __sample_age_degree_profession(age_class, edu_classes, profession_category=None):
    probs = [v[0] for v in age_class.values()]
    total = sum(probs)
    weights = [p / total for p in probs]

    # Extract the AgeClass objects
    classes = [v[1] for v in age_class.values()]

    # Sample one according to probability distribution
    age_class = random.choices(classes, weights=weights, k=1)[0]

    age = random.randint(age_class.age_start, age_class.age_end)

    if age < 18:
        profession = Profession.query.filter_by(profession="Student").first()
    else:
        # If a profession category is provided, sample from professions in that category
        if profession_category:
            # Get professions matching the category (background column)
            category_professions = Profession.query.filter_by(
                background=profession_category
            ).all()
            if category_professions:
                profession = random.choice(category_professions)
            else:
                # Fallback to random if no professions found for category
                profession = Profession.query.order_by(func.random()).first()
        else:
            profession = Profession.query.order_by(func.random()).first()

    sampled = random.choices(
        population=list(edu_classes.keys()), weights=list(edu_classes.values()), k=1
    )[0]
    education_level = int(sampled)
    # get education level object
    education_level = (
        Education.query.filter_by(id=education_level).first().education_level
    )

    return age, profession, education_level


def __sample_pareto(values, alpha=2.0):
    """
    Sample a value from a discrete set using Pareto distribution.

    Uses Pareto distribution to model power-law behavior, normalized to
    map onto discrete value set (e.g., for activity levels).

    Args:
        values: List of discrete values to sample from
        alpha: Pareto distribution shape parameter (default 2.0)

    Returns:
        One value from the input list
    """
    pareto_sample = np.random.pareto(alpha)  # Shifted Pareto sample
    normalized_sample = pareto_sample / (pareto_sample + 1)  # Normalize to (0,1)

    # Map the continuous value to the discrete set
    return values[int(np.floor(normalized_sample * len(values)))]


def _normalize_generated_username(raw_name: str, username_type: str) -> str:
    value = str(raw_name or "").strip()
    if username_type == "forum":
        lowered = value.lower()
        lowered = re.sub(r"[^a-z0-9_]+", "_", lowered)
        lowered = re.sub(r"_+", "_", lowered).strip("_")
        return lowered or "forum_user"
    return value.replace(" ", "")


def _generate_unique_name(
    fake,
    gender,
    used_names,
    username_type="microblogging",
    max_attempts=100,
):
    """
    Generate a unique name that hasn't been used yet.

    Username creation is platform-aware:
    - microblogging keeps the legacy full-name-without-spaces behavior
    - forum uses a dedicated forum-safe username path
    """

    username_type = (username_type or "microblogging").strip().lower()

    def _fake_attr(preferred, fallback):
        if hasattr(fake, preferred):
            return getattr(fake, preferred)()
        return getattr(fake, fallback)()

    def generate_name(gender_type):
        if username_type == "forum":
            if hasattr(fake, "user_name"):
                return _normalize_generated_username(fake.user_name(), username_type)

            if gender_type == "male":
                first_name = _fake_attr("first_name_male", "first_name")
            elif gender_type == "female":
                first_name = _fake_attr("first_name_female", "first_name")
            else:
                first_name = _fake_attr("first_name", "name")
            last_name = _fake_attr("last_name", "last_name")
            return _normalize_generated_username(
                f"{first_name}_{last_name}", username_type
            )

        if gender_type == "male":
            raw_name = fake.name_male()
        elif gender_type == "female":
            raw_name = fake.name_female()
        else:
            raw_name = fake.name_male()
        return _normalize_generated_username(raw_name, username_type)

    last_name = None
    for _ in range(max_attempts):
        name = generate_name(gender)
        last_name = name
        if name not in used_names:
            return name

    base_name = last_name if last_name else generate_name(gender)
    counter = 1
    unique_name = f"{base_name}{counter}"

    while unique_name in used_names:
        counter += 1
        unique_name = f"{base_name}{counter}"

    return unique_name


def generate_population(
    population_name, percentages=None, actions_config=None, profession_backgrounds=None
):
    """
    Generate a population of AI agents with realistic profiles.

    Creates agents based on population configuration including demographics
    (age, nationality, gender), Big Five personality traits (OCEAN model),
    political leaning, toxicity level, education, language, profession,
    and activity profiles based on specified distribution percentages.
    Uses statistical distributions to ensure realistic diversity.

    Args:
        population_name: Name of the population configuration to use
        percentages: Optional dict specifying percentage distributions for
                     certain attributes
        actions_config : Optional dict specifying configuration for round_actions
                         sampling (min, max, distribution type, parameter)
        profession_backgrounds: Optional list of profession background categories
                                to sample from when assigning professions

    Side effects:
        Creates and persists Agent and Agent_Population records in database
    """

    # get population by name
    population = Population.query.filter_by(name=population_name).first()

    # Get activity profile distribution for this population
    profile_distributions = PopulationActivityProfile.query.filter_by(
        population=population.id
    ).all()

    # Build cumulative distribution for activity profile assignment
    activity_profile_cdf = []
    cumulative = 0
    for dist in profile_distributions:
        cumulative += dist.percentage / 100.0
        activity_profile_cdf.append((cumulative, dist.activity_profile))

    # If no profiles assigned, use None
    if not activity_profile_cdf:
        activity_profile_cdf = [(1.0, None)]

    age_classes = {
        int(k): [float(v), db.session.query(AgeClass).filter_by(id=int(k)).first()]
        for k, v in percentages["age_classes"].items()
    }

    edu_classes = percentages["education"]

    # Get all existing agent names from the database to avoid duplicates
    existing_agents = db.session.query(Agent.name).all()
    used_names = {agent.name for agent in existing_agents}

    # Collect agents to insert in bulk
    agents_to_insert = []

    for _ in range(population.size):
        # Sample a profession category if provided
        profession_category = None
        if profession_backgrounds:
            profession_category = random.choice(profession_backgrounds)

        age, profession, education_level = __sample_age_degree_profession(
            age_classes, edu_classes, profession_category
        )

        # sample attributes based on provided percentages
        sampled = {
            attr: random.choices(
                population=list(values.keys()), weights=list(values.values()), k=1
            )[0]
            for attr, values in percentages.items()
        }

        toxicity = int(sampled["toxicity_levels"])
        # get toxicity level object
        toxicity = (
            db.session.query(Toxicity_Levels)
            .filter_by(id=toxicity)
            .first()
            .toxicity_level
        )

        political_leaning = int(sampled["political_leanings"])
        # get political leaning object
        political_leaning = (
            db.session.query(Leanings).filter_by(id=political_leaning).first().leaning
        )

        try:
            nationality = random.sample(population.nationalities.split(","), 1)[
                0
            ].strip()
        except:
            nationality = "American"

        # Use weighted gender sampling based on provided percentages
        if percentages and "gender" in percentages:
            gender_dist = percentages["gender"]
            genders = list(gender_dist.keys())
            weights = list(gender_dist.values())
            gender = random.choices(genders, weights=weights, k=1)[0]
        else:
            # Default to equal probability if no gender distribution provided
            gender = random.sample(["male", "female"], 1)[0]

        fake = faker.Faker(__locales[nationality])

        # Generate a unique name
        name = _generate_unique_name(
            fake,
            gender,
            used_names,
            getattr(population, "username_type", "microblogging"),
        )
        # Add the name to used_names to prevent duplicates within this population
        used_names.add(name)

        language = fake.random_element(
            elements=(population.languages.split(","))
        ).strip()
        ag_type = population.llm

        oe = fake.random_element(elements=("inventive/curious", "consistent/cautious"))
        co = fake.random_element(
            elements=("efficient/organized", "extravagant/careless")
        )
        ex = fake.random_element(elements=("outgoing/energetic", "solitary/reserved"))
        ag = fake.random_element(
            elements=("friendly/compassionate", "critical/judgmental")
        )
        ne = fake.random_element(elements=("sensitive/nervous", "resilient/confident"))

        try:
            round_actions = __sample_round_actions(
                actions_config["min"],
                actions_config["max"],
                (
                    actions_config[actions_config["distribution"]]
                    if actions_config["distribution"] in actions_config
                    else None
                ),
                actions_config["distribution"],
            )
        except:
            round_actions = 3

        daily_activity_level = __sample_pareto([1, 2, 3, 4, 5])

        # Assign activity profile based on population distribution
        rand_val = random.random()
        assigned_profile_id = None
        for cumulative_prob, profile_id in activity_profile_cdf:
            if rand_val <= cumulative_prob:
                assigned_profile_id = profile_id
                break

        agent = Agent(
            name=name,
            age=age,
            ag_type=ag_type,
            leaning=political_leaning,
            ag=ag,
            co=co,
            oe=oe,
            ne=ne,
            ex=ex,
            language=language,
            education_level=education_level,
            round_actions=round_actions,
            gender=gender,
            nationality=nationality,
            toxicity=toxicity,
            frecsys=population.frecsys,
            crecsys=population.crecsys,
            daily_activity_level=daily_activity_level,
            profession=profession.profession,
            activity_profile=assigned_profile_id,
            cover_image=random_cover_image_url(),
        )

        agents_to_insert.append(agent)

    # Bulk insert all agents in a single transaction
    db.session.bulk_save_objects(agents_to_insert, return_defaults=True)
    db.session.flush()

    # Now create Agent_Population relationships in bulk
    agent_populations_to_insert = []
    agent_exts_to_insert = []
    for agent in agents_to_insert:
        agent_population = Agent_Population(
            agent_id=agent.id, population_id=population.id
        )
        agent_populations_to_insert.append(agent_population)

        if getattr(population, "username_type", "microblogging") == "photo_sharing":
            favorite_filters = random.sample(
                ["warm", "vintage", "mono", "grain", "bright", "clean"],
                k=random.randint(0, 3),
            )
            story_visibility = random.choices(
                ["public", "followers", "private"], weights=[20, 65, 15], k=1
            )[0]
            creator_tier = random.choices(
                ["standard", "pro", "influencer"], weights=[60, 25, 15], k=1
            )[0]
            bio_text = " | ".join(
                [
                    part
                    for part in [
                        agent.profession,
                        agent.nationality,
                        agent.language,
                    ]
                    if part
                ]
            )
            ext_values = [
                ("bio", bio_text),
                ("is_private", random.random() < 0.2),
                ("is_verified", random.random() < 0.1),
                ("attention_budget", 100),
                ("favorite_filters", favorite_filters),
                ("story_visibility", story_visibility),
                ("creator_tier", creator_tier),
            ]
            for feature_name, feature_value in ext_values:
                if feature_value in (None, "", []):
                    continue
                agent_exts_to_insert.append(
                    Agent_Ext(
                        agent_id=agent.id,
                        feature_name=feature_name,
                        feature_value=(
                            json.dumps(feature_value)
                            if isinstance(feature_value, (list, dict, bool))
                            else str(feature_value)
                        ),
                    )
                )

    # Bulk insert all agent-population relationships
    db.session.bulk_save_objects(agent_populations_to_insert)
    if agent_exts_to_insert:
        db.session.bulk_save_objects(agent_exts_to_insert)
    db.session.commit()


def generate_population_from_config(
    population_name, percentages=None, actions_config=None, profession_backgrounds=None
):
    """Configuration-oriented entrypoint for population generation."""
    return generate_population(
        population_name,
        percentages=percentages,
        actions_config=actions_config,
        profession_backgrounds=profession_backgrounds,
    )


__locales = {
    "American": "en_US",
    "Argentine": "es_AR",
    "Armenian": "hy_AM",
    "Austrian": "de_AT",
    "Azerbaijani": "az_AZ",
    "Bangladeshi": "bn_BD",
    "Belgian": "nl_BE",
    "Brazilian": "pt_BR",
    "British": "en_GB",
    "Bulgarian": "bg_BG",
    "Chilean": "es_CL",
    "Chinese": "zh_CN",
    "Colombian": "es_CO",
    "Croatian": "hr_HR",
    "Czech": "cs_CZ",
    "Danish": "da_DK",
    "Dutch": "nl_NL",
    "Estonian": "et_EE",
    "Finnish": "fi_FI",
    "French": "fr_FR",
    "Georgian": "ka_GE",
    "German": "de_DE",
    "Greek": "el_GR",
    "Hungarian": "hu_HU",
    "Indian": "en_IN",
    "Indonesian": "id_ID",
    "Iranian": "fa_IR",
    "Irish": "ga_IE",
    "Israeli": "he_IL",
    "Italian": "it_IT",
    "Japanese": "ja_JP",
    "Latvian": "lv_LV",
    "Lithuanian": "lt_LT",
    "Mexican": "es_MX",
    "Nepalese": "ne_NP",
    "New Zealander": "en_NZ",
    "Norwegian": "no_NO",
    "Palestinian": "ar_PS",
    "Polish": "pl_PL",
    "Portuguese": "pt_PT",
    "Romanian": "ro_RO",
    "Russian": "ru_RU",
    "Saudi": "ar_SA",
    "Slovak": "sk_SK",
    "Slovenian": "sl_SI",
    "South African": "zu_ZA",
    "South Korean": "ko_KR",
    "Spanish": "es_ES",
    "Swedish": "sv_SE",
    "Swiss": "de_CH",
    "Taiwanese": "zh_TW",
    "Thai": "th_TH",
    "Turkish": "tr_TR",
    "Ukrainian": "uk_UA",
}
