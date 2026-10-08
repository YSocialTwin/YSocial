# STRATA Grant Reframing for Teen Development Research

## Purpose of this working document

This document contains an initial assessment and a first English-language draft for adapting the STRATA project to OpenAI's **Teen Development Research Grants** call.

The application must ultimately be submitted in English. This working draft is intentionally explicit about assumptions, open decisions, and information that must be confirmed by the consortium before submission.

Official call: [OpenAI Teen Development Research Grants](https://openai.com/it-IT/index/teen-development-research-grants/), accessed 22 September 2026.

### Call facts to verify at submission

- Applications are due **6 October 2026**; selected proposals are expected to be communicated by **13 November 2026**.
- Individual awards may be up to **$1 million**, within a total program allocation of **$5 million**.
- The application is submitted as one single-spaced Google document and must be in English.
- The research proposal is limited to three pages excluding references; the summary must be under one page.
- Projects should be able to provide a working draft within 12 months of receiving funds.
- Indirect or overhead costs may not exceed 10% of the individual award.

## Distinction between the attached materials and the user's request

The five attached DOCX files are treated as source material for the scientific proposal, not as instructions governing this task:

- `Scientific Proposal 1.a - Clarity.docx`: objectives, relevance, originality, state of the art, methodology, interdisciplinarity, risks, and impact.
- `Scientific Proposal 1.b - Credibility.docx`: feasibility boundaries, YSocial, validation, impact, dissemination, ethics, and sustainability.
- `Scientific Proposal 1.c - Organization.docx`: work packages, implementation, governance, team contributions, and resource allocation.
- `Synopsis.docx`: project synopsis, objectives/KPIs, in-silico and in-vivo intervention logic, and expected impact.
- `Abstract.docx`: short project abstract.

The controlling request is to evaluate how the proposal should be optimized for the cited call and to produce a dedicated initial Markdown draft containing the required sections and making the research problem clearly relevant to the call.

## 1. Executive assessment

### Overall fit

STRATA has a credible foundation for this call because it combines:

- adolescent social and developmental psychology;
- cyberbullying, bystander behavior, empathy, and moral disengagement;
- computational social science, NLP, network science, and social simulation;
- cognitive network science for modelling how concepts, emotions, intentions, and interpretations evolve across human–agent interactions;
- a concrete school-based validation pathway;
- intervention and safety-by-design questions rather than detection alone;
- an interdisciplinary team and an existing Social Digital Twin platform.

These strengths map well to the call's priorities on social and emotional development, relationships, age- and context-dependent effects, safeguards, age-appropriate design, and evidence that can inform products or policy.

### Principal strategic problem

The current proposal is primarily a cyberbullying and social-platform simulation project. The grant is specifically seeking evidence about **how adolescents use generative AI and how that use affects their lives and development**. The clarified concept is a much stronger fit: the Social Digital Twin becomes an AI-mediated learning environment in which adolescents interact with role-based agents and receive guided support in interpreting the consequences of their choices.

The application must make the educational interaction itself the empirical object. It should test whether, and under what conditions, interacting with AI agents and an AI interpretation guide changes adolescents' understanding of cyberbullying, empathy, agency, bystander behavior, and awareness of network effects. The project should not assume that an engaging simulation is automatically beneficial; learning gains, confusion, over-reliance, emotional effects, and unintended behavioral effects must all be measured.

The application should therefore be reframed as follows:

> STRATA investigates whether and how an AI-powered Social Digital Twin can function as a supervised learning environment in which adolescents explore cyberbullying dynamics, understand the consequences of their own and others' actions, and develop empathy, agency, and safe bystander responses.

The Social Digital Twin should be presented as both the intervention and the controlled, auditable testbed that supports the empirical study. The AI has two distinct functions that must be separated analytically: (1) role-based agents that enact a controlled social scenario and (2) an AI learning guide that helps the adolescent interpret the scenario. The psychologist remains responsible for supervision, safeguarding, and the human debrief; the AI must not be presented as a therapist or autonomous authority.

### Main strengths to preserve

- the bully–victim–bystander framework;
- the focus on cumulative, relational, and networked behavior rather than isolated toxic messages;
- psychological validation of computational outputs;
- testing of proactive safeguards, cognitive friction, prosocial nudges, and safety by design;
- school access and practitioner involvement through UNIFI, the Regional School Office, and ELISA, subject to confirmation;
- open-science and reproducibility commitments;
- the consortium's technical baseline in YSocial and SoBigData.

### Main changes required before submission

1. Make supervised interaction with an OpenAI-powered, role-based learning environment—and its effects on 13–17-year-olds—the primary research object.
2. Tie outcomes to adolescent development: empathy, emotion regulation, autonomy, self-efficacy, identity, belonging, social competence, and help-seeking.
3. State precise research questions and testable hypotheses about AI use, not only about platform interventions.
4. Replace the current 36-month, six-work-package ambition with a focused project capable of producing a working draft within 12 months of funding.
5. Include a direct, bounded study with adolescents and a pre-specified analysis plan; use the SDT for safe counterfactual and stress-testing work.
6. Add a complete minor-participant ethics and safeguarding plan, including assent, parental consent where appropriate, privacy, sensitive-data handling, and response to disclosures or imminent risk.
7. Replace broad claims such as “causally verified,” “social vaccine,” “first,” and “permanently integrated” with claims proportional to the proposed evidence.
8. Complete the missing budget, named team biographies, institutional approvals, recruitment commitments, and independence/conflicts declaration.

## 2. Alignment audit against the call

| Call requirement or criterion | Current position in STRATA | Optimization needed |
|---|---|---|
| Project summary under one page | Abstract and Synopsis provide useful material | Rewrite around adolescent generative-AI use and developmental outcomes |
| Research questions | Objectives are broad and technology-led | Add 3–4 focused questions and hypotheses |
| Relevant prior research | Strong cyberbullying, social simulation, and AI-intervention basis | Add literature on adolescent generative-AI use, trust, agency, emotional support, and developmental differences |
| Methods and analysis | Rich pipeline, but diffuse and partly aspirational | Define participants, conditions, outcomes, primary analysis, power logic, preregistration, and model-safety evaluation |
| Population and recruitment | High-school RCT and school partners are proposed | Confirm age range, sites, access letters, inclusion, language, socioeconomic diversity, and feasibility evidence |
| Expected results | Strong technical and societal ambitions | Specify measurable developmental, behavioral, and safety outcomes |
| Limitations | Risks are discussed, but transfer limits are underdeveloped | State limits of synthetic agents, self-report, school samples, short follow-up, and platform generalization |
| Program relevance | Cyberbullying relevance is clear; generative-AI relevance is indirect | Make adolescent–AI interaction and safeguards the central contribution |
| Project plan and timeline | 36 months, WP0–WP5 | Propose a 12-month core study with milestones and a clear completion date relative to award |
| Budget and justification | Categories are described without amounts | Add requested amount, personnel, participant costs, compute, safeguarding, dissemination, and indirect-cost calculation; indirects must remain within the call limit |
| Dependencies | Technical and data risks are identified | Add school access, ethics approval, model availability, safeguarding, and recruitment dependencies |
| Ethics and safeguarding | General GDPR/ethics language is present | Provide a standalone minor-participant protocol and named safeguarding responsibility |
| Team information | Institutional strengths are described | Add short biographies, named roles, relevant adolescent-development competence, and CV links/attachments |
| Independence and conflicts | Not yet a complete declaration | Provide a factual statement covering AI-provider relationships, funding, data access, and publication independence |
| Evaluation criteria | Most criteria are potentially addressable | Improve focus, feasibility, inclusion/generalizability, and evidence-to-policy translation |

## 3. Recommended project architecture

### Recommended scientific repositioning

The revised project should answer one compact educational and developmental question:

> Under what conditions does supervised interaction with role-based generative-AI agents, combined with AI-supported interpretation and psychologist-led reflection, improve adolescents' understanding of cyberbullying and their capacity for empathic, safe, and constructive action?

The key contribution is not simply a simulation of cyberbullying. It is a controlled learning environment in which adolescents can safely enact or observe choices, see how agents respond, and reflect on how individual actions may contribute to escalation, diffusion of responsibility, victim impact, or prosocial intervention.

### Suggested 12-month design

- **Phase 1, months 1–3 — Co-design and baseline:** adolescent and practitioner consultation; refine scenarios, measures, safeguards, and language; ethics approval; preregistration and data-management plan.
- **Phase 2, months 3–8 — Controlled learning study:** randomized comparison of a standard psychologist-led learning activity, a passive SDT learning environment, and an active SDT learning environment in which adolescents interact with role-based AI agents and receive AI-supported interpretive prompts alongside a psychologist. UNITN will support the analysis of the evolving cognitive and interaction networks generated during these sessions. Target sample size and power must be confirmed by a statistician; an initial planning assumption is approximately 300–360 adolescents aged 13–17 across age and gender strata.
- **Phase 3, months 6–10 — SDT stress testing:** use de-identified and aggregate study findings to test counterfactual safety configurations and subgroup differences. Do not treat SDT outputs as direct evidence of adolescent effects without empirical validation.
- **Phase 4, months 9–12 — Follow-up, synthesis, and dissemination:** short follow-up where ethically and operationally feasible; mixed-method analysis; policy/product recommendations; public report and working-paper draft by month 12.

This is a recommended first-stage grant design. The existing 750-participant, three-arm school RCT may remain a follow-on study if the consortium can demonstrate the required power, access, budget, and 12-month feasibility.

## 4. Initial application draft

### Working title

**STRATA-AI: An AI-Powered Social Digital Twin for Adolescent Cyberbullying Learning and Awareness**

### Applicant status

- **Principal investigator:** [NAME, TITLE, INSTITUTION — TO CONFIRM]
- **Lead institutions:** CNR, UNIFI, and UNITN [formal roles and named investigators to confirm]; UNITN scientific lead: Massimo Stella.
- **Project duration:** 12 months from award for the core study; any extension or larger RCT should be described as a subsequent phase, not assumed in this application.
- **Requested amount:** [$ AMOUNT — TO CONFIRM]
- **Submission language:** English.

### Project summary

Generative AI is becoming part of how adolescents seek advice, interpret social situations, compose messages, and respond to conflict. Yet there is limited independent evidence about whether an AI-powered learning environment can help adolescents understand the social consequences of their choices without weakening empathy, agency, social connection, or safe help-seeking. This gap is especially urgent in online peer aggression and cyberbullying, where the effects of an AI-generated response can propagate through a wider social network and affect victims, aggressors, and bystanders.

STRATA-AI will study how adolescents aged 13–17 learn from controlled interaction with an AI-powered Social Digital Twin of a social platform. The environment will be populated by generative-AI agents that enact defined roles—such as target, aggressor, passive bystander, prosocial bystander, moderator, or trusted adult—within synthetic, developmentally appropriate scenarios. Adolescents will be able to observe or interact with the system, make choices, and see how those choices affect the simulated social process. An AI learning guide, operating under psychologist supervision, will support structured interpretation of the scenario through reflective prompts, explanations of network effects, and questions about alternative actions.

The empirical study will compare a standard psychologist-led learning activity, passive observation of the AI-powered environment, and active interaction with the environment plus AI-supported interpretation. Primary outcomes will include learning and awareness of cyberbullying mechanisms, empathy and perspective taking, bystander action, perceived agency, emotion regulation, social connectedness, and help-seeking. Analyses will test differences by age, prior experience of online aggression, AI literacy, language, and social context.

The Social Digital Twin will provide a safe environment for counterfactual stress testing of learning scenarios and safeguards before wider deployment. It will be calibrated only against de-identified empirical data and will be treated as a hypothesis-generating and safety-testing instrument, not as a replacement for evidence from adolescents. The project will produce an independent evidence report, a preregistered analysis record, a learning-environment and safeguarding toolkit, and recommendations for AI product design, educators, and policymakers.

### Research proposal

#### 1. Critical problem and relevance to adolescent development

Adolescence is a period in which identity, autonomy, emotional regulation, peer relationships, empathy, and social competence are still developing. Generative AI can enter these processes as an adviser, writing partner, conversational partner, or mediator of peer conflict. Its effects are unlikely to be uniformly positive or negative. They may depend on the adolescent's age and developmental stage, the purpose of use, the emotional context, the model's response, the presence of peers or adults, and the design of the surrounding platform.

Online peer aggression is a particularly important test case. Cyberbullying is relational and cumulative: the same adolescent may be a target in one interaction, a bystander in another, and an active participant elsewhere. Generative AI may help a young person interpret a harmful interaction, formulate a supportive response, or seek help. It may also produce overconfident advice, normalize retaliation, reduce personal agency, displace human support, or intensify a conflict when its limitations are not understood.

The critical evidence gap is therefore not simply whether an AI system detects harmful content. It is whether, how, and for whom interaction with generative AI changes developmental processes and social behavior in situations that matter to adolescents. STRATA-AI addresses this gap through a safe, mixed-method, theory-driven study that links individual responses to the social dynamics of the wider peer network.

#### 2. Research questions and hypotheses

**RQ1. Use and context:** How do adolescents aged 13–17 use generative AI when interpreting, discussing, or responding to online peer aggression, and how do use patterns vary by age, prior experience, AI literacy, language, and social context?

**RQ2. Learning and developmental effects:** Does interaction with the AI-powered learning environment improve adolescents' understanding of cyberbullying mechanisms, recognition of cumulative and networked harm, empathy, perspective taking, perceived agency, social connectedness, help-seeking, and willingness to act as a prosocial bystander?

**RQ3. Role of the AI guide and psychologist:** What is added by active interaction with role-based AI agents and AI-supported interpretive prompts, compared with passive observation and a standard psychologist-led learning activity? How do adolescents understand the respective roles and authority of the AI and the psychologist?

**RQ4. Safeguards and generalizability:** Do reflective friction, calibrated uncertainty, prosocial prompts, transparency about model limitations, and trusted-adult escalation reduce confusion, over-reliance, or harmful responses while preserving adolescent agency and social connection? Which findings are robust across age groups, languages, and school contexts?

The preregistered hypotheses will be finalized with the adolescent advisory group and statistician before data collection. The initial hypotheses are that: (H1) active, supervised interaction with the AI-powered learning environment will improve scenario-based learning and awareness more than passive observation alone; (H2) AI-supported interpretation will improve calibration, empathy, and constructive bystander action only when it is transparent, bounded, and integrated with psychologist-led reflection; (H3) learning gains will vary with age, prior victimization or bystander experience, AI literacy, and baseline social support; and (H4) over-reliance, confusion about AI authority, or emotional discomfort will be detectable and reducible through safeguards.

#### 3. Relevant prior research and contribution

The source proposal establishes a strong basis in cyberbullying psychology, the bully–victim–bystander triad, socio-linguistic and network analysis, agent-based modeling, LLM-based social simulation, and school-based prevention. It also identifies an important actionability gap: interventions are often tested either as psycho-educational programs or as reactive content moderation, with limited evidence about their interaction.

The revised proposal extends this foundation in three ways. First, it shifts the unit of inquiry from generic platform toxicity to adolescent interaction with generative AI. Second, it makes developmental outcomes and social relationships primary endpoints rather than secondary validation targets. Third, it uses the SDT to test plausible counterfactual safeguards without presenting synthetic behavior as proof of real-world developmental effects.

The project will update the bibliography before submission with recent independent work on adolescent generative-AI use, emotional reliance and trust, AI literacy, developmental differences, age-appropriate design, and safeguards. Existing references on cyberbullying, social simulation, network dynamics, and technology-based prevention will be retained selectively.

UNITN will add a cognitive network science layer to the existing computational and psychological framework. This layer will represent the interaction as a time-ordered, multilayer process linking conversational moves, concepts, affective states, perceived intentions, and social roles. It will help identify how adolescents' interpretations change across turns, how AI-agent responses reorganize the learner's cognitive landscape, and whether learning about escalation, victim impact, or bystander responsibility becomes more integrated after the session. These measures will complement, rather than replace, validated psychological scales and behavioral outcomes.

#### 4. Methods and analysis

The project will use a mixed-method design.

**Co-design and qualitative work.** Adolescents aged 13–17, educators, psychologists, and safeguarding professionals will review synthetic scenarios and proposed safeguards. Interviews and focus groups will examine perceived helpfulness, trust, agency, social belonging, emotional impact, and acceptable escalation pathways. Participation will not require disclosure of personal bullying experiences.

**Randomized controlled learning study.** Participants will be randomized to one of three conditions:

1. **Standard psychologist-led learning activity:** scenario-based reflection and existing age-appropriate educational material, facilitated by a psychologist without interaction with the Digital Twin.
2. **Passive AI learning environment:** adolescents observe controlled scenarios enacted by role-based AI agents and then discuss their observations with a psychologist.
3. **Active AI learning environment:** adolescents interact with the role-based AI agents, make decisions, and receive AI-supported interpretive prompts, followed by psychologist-led reflection and safeguarding support.

The role-based agents will operate within bounded scenarios and action spaces. Their roles may include aggressor, target, passive bystander, prosocial bystander, moderator, and trusted adult. The AI learning guide will not replace the psychologist: it will use pre-specified prompts and explanations to help participants connect their actions to simulated consequences, identify alternative responses, and distinguish observation from interpretation. All participant-facing AI outputs will be monitored and constrained.

The reference implementation will use OpenAI models, subject to access, institutional approvals, and applicable terms. Model versions, system prompts, safety settings, temperature or sampling parameters, tool access, and interaction logs will be versioned and reported. The scientific protocol will retain a controlled fallback configuration so that the study remains interpretable if a model version changes or access becomes unavailable.

The precise sample size, stratification, and power calculation will be confirmed before submission. The study will measure pre-intervention, immediate post-intervention, and—where approved and feasible—short follow-up outcomes. Primary outcomes will be selected a priori from validated measures of learning and awareness of cyberbullying mechanisms, empathy/perspective taking, bystander intentions and behavioral choices, perceived agency, emotion regulation, social connectedness, and help-seeking. Secondary measures will assess trust calibration, perceived usefulness, understanding of AI and psychologist roles, AI literacy, response quality, retention of learning, and unintended effects such as retaliation, withdrawal, confusion, emotional discomfort, or over-reliance.

**AI and scenario safety evaluation.** All scenarios will be synthetic or carefully de-identified. The system will not contact peers, post publicly, access private accounts, or provide unsupervised mental-health advice. Independent reviewers will code agent and guide outputs for harmfulness, escalation, stereotyping, overconfidence, inappropriate disclosure requests, confusion between simulation and reality, confusion about AI authority, and failure to recommend human support when needed. A psychologist will be able to pause the session and override the system at any time.

**Social Digital Twin.** YSocial will be used to create and reproduce aggregate social and interaction patterns observed in the study, to stress-test candidate learning scenarios and safeguards under controlled counterfactual conditions, and to make network consequences visible to learners. Model fidelity will be evaluated against held-out empirical measures and expert-coded interaction patterns. SDT results will be reported as simulations with uncertainty bounds; they will not be interpreted as direct estimates of population-level adolescent effects.

**Analysis.** The primary analysis will follow intention-to-treat principles. Mixed-effects regression models will estimate condition effects while accounting for school/site clustering and repeated measures. The primary contrasts will be active versus passive AI learning, passive AI learning versus standard psychologist-led learning, and active AI learning versus standard learning. UNITN will conduct preregistered cognitive network analyses of the interaction traces, subject to privacy and data-minimization constraints. Candidate measures may include the emergence and persistence of concepts related to harm, empathy, responsibility, and help-seeking; transitions between affective or interpretive states; and changes in the connectivity or integration of these concepts across the session. These measures will be evaluated against learning outcomes and expert-coded interaction quality, without treating network structure as a clinical diagnosis or a direct measure of mental state. Mediation analyses, if adequately powered, will examine whether perceived agency, empathy, understanding of network effects, or cognitive-network integration explain learning and behavioral outcomes. Pre-specified moderation analyses will test age, prior experience, AI literacy, language, gender, socioeconomic context, and baseline social support, subject to adequate sample size. Qualitative data will be analyzed thematically and integrated with quantitative results. All confirmatory outcomes, exclusions, missing-data handling, guide/agent safety criteria, cognitive-network metrics, and psychologist override rules will be preregistered.

#### 5. Population, recruitment, and feasibility

The target population is adolescents aged 13–17 recruited through participating secondary schools and established educational networks. Recruitment will seek variation in age, gender, language, socioeconomic context, and prior exposure to online peer aggression. No participant will be required to identify a perpetrator, victim, or specific private incident.

The consortium reports access pathways through UNIFI, the Regional School Office, and ELISA; these relationships, the number of reachable schools, and letters of support must be documented before submission. The application should include a recruitment table specifying sites, expected eligible participants, recruitment rate, attrition assumption, and contingency sites.

Feasibility is strengthened by the existing YSocial infrastructure, the consortium's computational and psychological expertise, and a staged design that separates a manageable empirical study from later scale-up. The reference implementation can use OpenAI models, but the project should not rely on access to restricted platform data or on an undocumented model version. A controlled fallback setup should be maintained; any comparison with another model or ChatGPT configuration should be optional, transparently documented, and analyzed independently.

#### 6. Expected results and applicability

The project will deliver:

- an empirical assessment of an AI-powered learning environment for adolescent cyberbullying awareness;
- estimates of learning, developmental, and social outcomes associated with passive observation versus active interaction with role-based AI agents;
- evidence on the added value and limits of AI-supported interpretation when it is combined with psychologist supervision;
- evidence on which safeguards improve safety without unnecessarily reducing agency or access to human support;
- a validated set of learning, scenario, and model-safety measures and a reproducibility checklist;
- an auditable SDT configuration for safe counterfactual testing and educator training;
- recommendations for model behavior, product design, school practice, and policy;
- a public report and a working-paper draft within 12 months of funding, subject to ethics, privacy, and publication review.

The results will be useful even if the hypotheses are not confirmed. Null or adverse findings will identify contexts in which AI assistance should be limited, require human oversight, or be redesigned.

#### 7. Limitations and uncertainty

The study will not establish the full long-term effects of everyday generative-AI use. Scenario-based interaction may differ from spontaneous use, school samples may not represent adolescents outside formal education, and self-report may be affected by demand characteristics. A short follow-up cannot establish durable developmental change. The SDT necessarily simplifies real social systems and cannot validate itself through synthetic realism alone. Model behavior may change across versions, languages, and deployment settings. Subgroup analyses will be treated as exploratory when sample size does not support reliable inference.

These limitations will be addressed through preregistration, multi-method measurement, adolescent co-design, held-out validation, transparent uncertainty reporting, model-agnostic safeguards, and a clear separation between empirical findings and simulation-based hypotheses.

#### 8. Pertinence to the Teen Development Research Grants program

STRATA-AI directly addresses the program's priorities on emotional well-being, social relationships, age- and context-dependent effects, and mitigation through age-appropriate design. It studies adolescents aged 13–17, examines the purposes and contexts of generative-AI use, and measures effects on empathy, agency, emotion regulation, belonging, help-seeking, and bystander behavior. It also evaluates safeguards that can be translated into model behavior, product features, educator support, and regulatory guidance.

The proposal is intentionally independent of any desired product outcome. It will report beneficial, null, and harmful effects, including cases where generative AI should not be used without human support. Its interdisciplinary design connects developmental psychology, computational social science, NLP, cognitive network science, human–computer interaction, and AI safety. Its inclusion strategy will make variation across age, language, culture, socioeconomic context, and prior experience an explicit analytic concern rather than an afterthought.

### Project plan and timeline

| Period | Main activities | Milestone or deliverable |
|---|---|---|
| M1–M2 | Ethics submission, safeguarding protocol, data-management plan, advisory-group formation, preregistration protocol | Ethics package and finalized study protocol |
| M2–M4 | Adolescent/practitioner co-design, scenario and measure refinement, technical safety testing | Co-designed scenario and safeguard set |
| M4–M7 | Recruitment, pilot, and main controlled study | Recruitment and data-quality report |
| M6–M10 | Quantitative and qualitative analysis; SDT calibration and counterfactual stress tests | Interim evidence and simulation report |
| M9–M12 | Follow-up where approved, synthesis, stakeholder review, public report, working-paper draft | Final report and working draft by M12 |

**Expected completion:** month 12 after receipt of funds, subject to ethics approval and school calendars.

### Budget and justification

The final budget must be prepared with institutional finance offices. The current source documents do not provide a submission-ready amount. The budget should prioritize:

| Category | Purpose | Amount |
|---|---|---:|
| Personnel | PI time, research staff, adolescent-development and safeguarding expertise, data/statistical support | [$ TBD] |
| Participant and school costs | Compensation where permitted, travel, accessibility, translation, school coordination | [$ TBD] |
| Ethics and safeguarding | Independent review, safeguarding training, clinical/child-protection consultation | [$ TBD] |
| Secure computing and infrastructure | Controlled model hosting, storage, audit logging, SDT execution, security review | [$ TBD] |
| Data and analysis | Transcription, coding, validated measures, statistical support | [$ TBD] |
| Dissemination and open science | Public report, workshops, open-access publication, practitioner toolkit | [$ TBD] |
| Indirect costs | Only within the call's stated limit | [$ TBD] |
| **Total request** | Must be consistent with the work plan and institutional rules | **[$ TBD]** |

The final justification should explain why each cost is necessary for a 12-month study and identify any confirmed co-funding, in-kind infrastructure, or other support. Do not budget for a 36-month program unless the application explicitly justifies the longer period and still meets the call's preference for a working draft within 12 months.

### Dependencies and risk management

| Dependency or risk | Consequence | Mitigation and decision point |
|---|---|---|
| Ethics approval or school calendar delay | Recruitment and data collection move beyond schedule | Submit early; use multiple sites; maintain a non-participant pilot; define a stop/go review at M2 |
| Insufficient recruitment or attrition | Low power and weak subgroup inference | Confirm letters of support; over-recruit within approved limits; predefine minimum analyzable sample |
| Model version or provider access changes | Non-reproducible AI condition | Use controlled, version-pinned models; archive prompts/configurations; retain a model-agnostic fallback |
| Harmful or overconfident model outputs | Participant distress or unsafe learning | Pre-screen outputs; real-time monitoring; human escalation; stop rules; no unsupervised deployment |
| Disclosure of current harm or imminent risk | Safeguarding obligation | Consent/assent briefing; trained safeguarding lead; predefined referral and emergency pathway; minimal data collection |
| Cognitive-network measures are overinterpreted | Interaction structure could be mistaken for a direct measure of cognition or mental state | Predefine constructs and limits; validate against behavioral and psychological measures; report network metrics as complementary indicators, not diagnoses |
| SDT does not reproduce observed dynamics | Simulation cannot support strong generalization | Treat SDT as hypothesis-generating; report mismatch; do not use simulation as a substitute for empirical evidence |
| Limited diversity of the school sample | Reduced generalizability | Recruit across sites and contexts; report composition and transportability limits; include subgroup uncertainty |
| Interdisciplinary fragmentation | Inconsistent technical and psychological decisions | Monthly steering committee; shared protocol; independent methods and safeguarding review |

### Ethics and safeguarding statement

This project involves minors and potentially sensitive experiences of online aggression. Before recruitment, the full protocol will be submitted to the relevant institutional or independent ethics review body and adapted to applicable national and institutional requirements. The application must name the reviewing body, approval status, responsible safeguarding lead, and data-protection contact.

Participation will require age-appropriate adolescent assent and parental/guardian consent where required or appropriate. Participants may skip questions or withdraw without penalty. The study will not require disclosure of personal victimization, access to private accounts, public posting, or contact with peers. Scenarios will be synthetic or de-identified and will be reviewed for developmental appropriateness.

Data collection will follow data minimization, pseudonymization, access control, retention limits, secure storage, and a documented data-management plan. No automated diagnosis or mental-health profiling will be performed. The AI system will not be presented as a therapist or emergency service. Researchers will explain model limitations and provide a human-support pathway.

The safeguarding protocol will specify how researchers respond to distress, disclosure of ongoing abuse, credible threats, or imminent risk. Responses will be led by trained human staff under the approved institutional protocol; the AI system will not make safeguarding decisions. The team must document relevant expertise in adolescent development, clinical or school psychology, child protection, privacy, and responsible AI.

### Information about the research team

The revised consortium combines three complementary institutional roles. The final application must replace the summaries below with named investigators and concise biographies.

- **CNR:** technical lead for YSocial and the Social Digital Twin; expertise in complex systems, AI, large-scale simulation, and social mining infrastructure. CNR will lead the design of the platform, the role-based agents, the controlled learning scenarios, and the technical safety layer.
- **UNIFI:** social and developmental psychology, bullying/cyberbullying prevention, school-based intervention, practitioner engagement, psychologist supervision, safeguarding, and in-vivo evaluation. UNIFI will lead the educational protocol, human debriefing, school implementation, and developmental outcome assessment.
- **UNITN — Massimo Stella:** cognitive network science and computational analysis of human–AI interaction. UNITN will lead the formalization and analysis of time-evolving cognitive and conversational networks, linking interaction traces to learning, interpretation, empathy, agency, and awareness outcomes. This role provides the methodological bridge between agent-level exchanges and adolescent-level developmental measures.

The final version must specify: PI and co-investigator names; percentage effort; Massimo Stella's formal role and relevant biography; prior work directly relevant to cognitive network science, adolescents, and generative AI; safeguarding and clinical/school-practice competence; statistical expertise; data-protection responsibility; and access to the named school networks.

### Independence and conflicts of interest

**Draft statement to verify and complete:**

> The investigators will conduct the study independently and will report beneficial, null, and adverse findings. The team will disclose all relevant financial relationships, current or pending funding, advisory roles, intellectual-property interests, commercial partnerships, model-access agreements, and institutional dependencies related to AI providers, social platforms, educational technology, or safeguarding products. No funder or technology provider will control the research questions, analysis, interpretation, publication, or decision to disseminate results. Any use of ChatGPT or another commercial model will be documented and compared with the independent protocol; its inclusion will not condition the conclusions.

This paragraph must be revised after a factual conflict-of-interest review by all investigators and institutions.

### References to carry forward and update

The bibliography in the attached Credibility and Clarity documents provides a starting point, including work on cyberbullying psychology, detection, social simulation, LLM-based agents, technology-based interventions, and YSocial. Before submission, the team should:

- verify every bibliographic record and publication status;
- add recent independent literature on adolescent generative-AI use and development;
- add evidence on trust, reliance, emotional support, agency, and AI literacy;
- add cognitive network science references and methodological evidence linking interaction traces to learning outcomes;
- add research on age-appropriate design, safeguards, and human escalation;
- keep the final bibliography selective because the research proposal page limit excludes references but the main text must remain focused.

## 5. Submission checklist and open decisions

- [ ] Confirm the PI's eligibility, age, affiliation, and relevant experience.
- [ ] Confirm the named ethics committee or independent review pathway.
- [ ] Confirm school sites, recruitment numbers, access letters, and languages.
- [ ] Complete a power analysis and lock the primary outcomes.
- [ ] Decide whether the empirical study is 300–360 participants or another defensible target.
- [ ] Decide whether a ChatGPT comparison is feasible and scientifically necessary; do not make the project depend on it.
- [ ] Define the exact AI systems, model versions, prompts, safety filters, logs, and retention policy.
- [ ] Complete the safeguarding escalation pathway and name responsible staff.
- [ ] Confirm the budget, indirect-cost calculation, co-funding, and in-kind infrastructure.
- [ ] Add full team biographies, including Massimo Stella's cognitive-network-science profile, and evidence of adolescent-development competence.
- [ ] Complete factual conflict-of-interest and independence disclosures.
- [ ] Rewrite the final application in English to fit: summary under one page, research proposal no more than three pages excluding references, plus the remaining required sections.
- [ ] Remove unsupported superlatives and ensure every causal claim is matched to the design and analysis.
