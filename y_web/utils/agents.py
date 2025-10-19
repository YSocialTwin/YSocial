"""
Agent population generation utilities.

Provides functions for generating realistic AI agent populations with diverse
demographic profiles, personality traits, and behavioral characteristics
based on population configuration parameters.
"""

import random

import faker
import numpy as np
from sqlalchemy.sql import func

from y_web import db
from y_web.models import (
    Agent,
    Agent_Population,
    Population,
    PopulationActivityProfile,
    Profession,
)


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


def generate_population(population_name, percentages=None):
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

    for _ in range(population.size):

        # sample attributes based on provided percentages
        sampled = {
            attr: random.choices(
                population=list(values.keys()),
                weights=list(values.values()),
                k=1
            )[0]
            for attr, values in percentages.items()
        }

        education_level = int(sampled["education"])
        toxicity = int(sampled["toxicity_levels"])
        political_leaning = int(sampled["political_leanings"])

        try:
            nationality = random.sample(population.nationalities.split(","), 1)[
                0
            ].strip()
        except:
            nationality = "American"

        gender = random.sample(["male", "female"], 1)[0]

        fake = faker.Faker(__locales[nationality])

        if gender == "male":
            name = fake.name_male()
        else:
            name = fake.name_female()

        # Gaussian distribution for age
        age = __sample_age(
            np.mean([population.age_min, population.age_max]),
            int((population.age_max - population.age_min) / 2),
            population.age_min,
            population.age_max,
        )

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
            round_actions = fake.random_int(
                min=1,
                max=4,
            )
        except:
            round_actions = 3

        daily_activity_level = __sample_pareto([1, 2, 3, 4, 5])

        # get random profession from db
        profession = Profession.query.order_by(func.random()).first()

        # Assign activity profile based on population distribution
        rand_val = random.random()
        assigned_profile_id = None
        for cumulative_prob, profile_id in activity_profile_cdf:
            if rand_val <= cumulative_prob:
                assigned_profile_id = profile_id
                break

        agent = Agent(
            name=name.replace(" ", ""),
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
        )

        db.session.add(agent)
        db.session.commit()

        agent_population = Agent_Population(
            agent_id=agent.id, population_id=population.id
        )

        db.session.add(agent_population)
        db.session.commit()


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
