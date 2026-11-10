# Station catalogue

<!-- Generated from data/catalogue/stations.yaml by `npm run catalogue:doc`; edit the
YAML, not this file. -->

Definitions for a full set of practice stations, from which detailed case files will be
written ([NEW-STATION-PROCESS.md](NEW-STATION-PROCESS.md)). All are original fiction and
not clinically validated. The set follows the pinned MRCPsych CASC Syllabus and Blueprint
(March 2023): **4 complete running orders of 16 stations** (64 stations). Each running order is valid on its own, with the exam's
proportions; together they meet every minimum frequency in the blueprint matrix.
`services/api/tests/test_station_catalogue.py` checks every rule below.

## How the set follows the blueprint

Every running order has 5 history, 5 examination and 6 management stations: in the
morning session 6 management, 1 history and 1 examination station (4 minutes' reading);
in the afternoon 4 history and 4 examination stations (90 seconds' reading). Each has
at least four general psychiatry stations and at least one in each other specialty;
at least one station of risk assessment or safety planning, of cognition or capacity,
and of physical health history or physical examination; and each communication
subdivision as the emphasis of at least one station.

### Skill subdivisions: running orders that test each, against the blueprint minimum

| Skill | Subdivision | Running orders | Stations | Minimum |
|---|---|---|---|---|
| History (5 per order) | Presenting complaint and psychiatric history | 4 of 4 (100%) | 7 | 100% |
| History (5 per order) | Physical health history | 2 of 4 (50%) | 2 | 50% |
| History (5 per order) | Developmental history | 3 of 4 (75%) | 3 | 50% |
| History (5 per order) | Personal and social history | 3 of 4 (75%) | 3 | 50% |
| History (5 per order) | Collateral history | 4 of 4 (100%) | 5 | 100% |
| Examination (5 per order) | Mental state (cognitive) | 3 of 4 (75%) | 3 | 75% |
| Examination (5 per order) | Mental state (psychotic) | 4 of 4 (100%) | 5 | 100% |
| Examination (5 per order) | Mental state (non-psychotic) | 4 of 4 (100%) | 5 | 100% |
| Examination (5 per order) | Capacity assessment | 2 of 4 (50%) | 2 | 25% |
| Examination (5 per order) | Physical examination | 2 of 4 (50%) | 2 | 50% |
| Examination (5 per order) | Risk assessment | 3 of 4 (75%) | 3 | 50% |
| Management (6 per order) | Formulation | 4 of 4 (100%) | 5 | 100% |
| Management (6 per order) | Management (biological) | 4 of 4 (100%) | 5 | 100% |
| Management (6 per order) | Management (psychological) | 3 of 4 (75%) | 3 | 50% |
| Management (6 per order) | Holistic management plan | 4 of 4 (100%) | 4 | 100% |
| Management (6 per order) | Safety planning | 3 of 4 (75%) | 3 | 50% |
| Management (6 per order) | Legal and ethical management | 4 of 4 (100%) | 4 | 100% |

### Specialties per running order

| Running order | General | Child and adolescent | Intellectual disability | Old age | Forensic | Medical psychotherapy | Addiction |
|---|---|---|---|---|---|---|---|
| A | 7 | 2 | 1 | 3 | 1 | 1 | 1 |
| B | 7 | 2 | 1 | 2 | 1 | 1 | 2 |
| C | 9 | 1 | 1 | 2 | 1 | 1 | 1 |
| D | 7 | 2 | 1 | 2 | 2 | 1 | 1 |
| Minimum | 4 | 1 | 1 | 1 | 1 | 1 | 1 |

### Range of clinical scenarios

Every disorder group the syllabus lists appears at least once:

| Condition group | Stations |
|---|---|
| Neurodevelopmental disorders | A08, A12, B04, B12, D05 (5) |
| Schizophrenia or other primary psychotic disorders | A01, A02, A06, A14, B08, B13, C03, C13, D11 (9) |
| Catatonia | C08 (1) |
| Mood disorders | A05, A10, A13, B03, B09, C01, D04, D12, D13, D16 (10) |
| Anxiety or fear-related disorders | A15, C06 (2) |
| Obsessive-compulsive or related disorders | B06, D09 (2) |
| Disorders specifically associated with stress | B15, D07, D10 (3) |
| Dissociative disorders | C14 (1) |
| Feeding or eating disorders | A07 (1) |
| Elimination disorders | D02 (1) |
| Disorders of bodily distress or bodily experience | B10 (1) |
| Disorders due to substance use or addictive behaviours | A09, B05, B14, C10, D03 (5) |
| Impulse control disorders | C15 (1) |
| Disruptive behaviour or dissocial disorders | B11 (1) |
| Personality disorders and related traits | A03, B01, B07, C05 (4) |
| Paraphilic disorders | D01 (1) |
| Factitious disorders | D15 (1) |
| Neurocognitive disorders | A04, A11, A16, B16, C04, C07, C16 (7) |
| Disorders associated with pregnancy, childbirth or the puerperium | B02, C11, D06 (3) |
| Psychological or behavioural factors affecting other conditions | D08 (1) |
| Secondary mental or behavioural syndromes | D14 (1) |
| Sleep-wake disorders | C09 (1) |
| Sexual dysfunctions | C02 (1) |
| Gender incongruence | C12 (1) |

**Settings:** inpatient 9; outpatient 23; community 13; emergency 4; criminal justice 5; general hospital 8; educational 2

**Patients' age bands:** adult 47; older adult 10; adolescent 4; child 3

**Who the candidate meets:** colleague 7; relative 11; patient 44; carer 2

**Already written as cases:** A01 (first-episode-psychosis-formulation), A02 (clozapine-explanation-relative), A03 (dbt-referral-discussion), A04 (dementia-distress-care-plan), A05 (adolescent-self-harm-safety-plan), A06 (prison-hospital-transfer-discussion), A07 (restrictive-eating-physical-history), A08 (dental-extraction-capacity), A09 (alcohol-history), A10 (elevated-mood-history), A11 (memory-collateral-history), A12 (child-attention-developmental-history), A13 (overdose-risk-assessment), A14 (persecutory-psychosis-mental-state), A15 (panic-avoidance-mental-state), A16 (acute-confusion-cognitive-examination), B01 (ward-team-self-harm-formulation), B02 (lithium-early-pregnancy-discussion), B03 (ect-explanation-husband), B04 (supported-living-behaviour-plan), B05 (alcohol-driving-confidentiality), B06 (child-ocd-family-treatment), B07 (remand-personal-social-history), B09 (redundancy-depression-history), B10 (persistent-pain-fatigue-history), B11 (school-aggression-teacher-collateral), B12 (adult-autism-developmental-collateral), B13 (jealousy-partner-risk), B14 (cannabis-voices-mental-state), B15 (asylum-trauma-mental-state), B16 (behavioural-change-cognitive-assessment), C01 (depression-app-trial-applicability), C02 (antidepressant-sexual-effects-discussion), C03 (rehabilitation-supported-housing-plan), C04 (dementia-disclosure-son), C05 (forensic-leave-safety-plan), C06 (social-anxiety-therapy-choice), C07 (down-syndrome-decline-collateral), C09 (adolescent-delayed-sleep-history), C10 (opioid-treatment-physical-health), C11 (postpartum-psychosis-husband-collateral), C12 (transgender-woman-social-history), C13 (late-life-intrusion-beliefs), C14 (functional-seizures-mental-state), C15 (explosive-outbursts-mental-state), C16 (alcohol-memory-cognitive-assessment), D01 (exposure-offending-formulation), D02 (child-wetting-soiling-family-formulation), D03 (alcohol-assisted-withdrawal-options), D04 (older-adult-depression-discharge-plan), D05 (learning-disability-relationship-rights), D06 (postnatal-depression-safety-plan), D07 (developmental-relationships-trauma-history), D08 (amputation-refusal-capacity), D09 (checking-rituals-ocd-history), D10 (bereavement-grief-depression-history), D11 (probation-psychosis-collateral), D12 (young-carer-social-history), D13 (first-arrest-suicide-risk), D14 (epilepsy-associated-psychosis), D15 (recurrent-infections-mental-state).

**Need a new simulator mechanism:** B08, D16 (physical examination: the candidate examines and asks for findings, which the
current voice simulator cannot yet provide).

## Running order A

| Code | Session | Skill: subdivision | Specialty | Emphasis | Setting | Meets | Scenario | Task |
|---|---|---|---|---|---|---|---|---|
| A01 ✱ | morning | Management: Formulation | General | Clear information | inpatient | consultant psychiatrist (colleague) | A 22-year-old man admitted with a first episode of psychosis after months of social withdrawal. | Present the history, mental state, differential diagnosis and an initial management plan to the consultant. |
| A02 ✱ | morning | Management: Management (biological) | General | Clear information | outpatient | mother (relative) | Mother of a man with treatment-resistant schizophrenia who is being offered clozapine. | Explain clozapine, its monitoring and side effects, and address her concerns. |
| A03 ✱ | morning | Management: Management (psychological) | Medical psychotherapy | Empathy | outpatient | woman with recurrent self-harm and unstable relationships (patient) | A 27-year-old woman referred for a structured psychological therapy after repeated crises. | Explain dialectical behaviour therapy and agree whether she wishes to be referred. |
| A04 ✱ | morning | Management: Holistic management plan | Old age | Cues | community | daughter (relative) | A man with Alzheimer's disease in a care home has become agitated in the evenings; staff have asked for sedation. | Agree a plan with his daughter for his distress, including non-drug approaches and the place of medication. |
| A05 ✱ | morning | Management: Safety planning | Child and adolescent | Empathy | emergency | 15-year-old girl (patient) | A 15-year-old seen in the emergency department after cutting herself more deeply than before. | Develop a safety plan with her before she goes home. |
| A06 ✱ | morning | Management: Legal and ethical management | Forensic | Personalisation and respect | criminal justice | man on remand in prison (patient) | A man on remand with worsening paranoid psychosis is to be transferred from prison to hospital. | Explain why, and the principles of compulsory treatment, and respond to his objections. |
| A07 ✱ | morning | History: Physical health history | General | Cues | outpatient | woman with an eating disorder (patient) | A 24-year-old woman with restrictive eating referred by her GP after fainting at work. | Take a physical health history. |
| A08 ✱ | morning | Examination: Capacity assessment | Intellectual disability | Personalisation and respect | general hospital | man with a mild intellectual disability (patient) | A man with a mild intellectual disability refuses a dental extraction under general anaesthetic. | Assess his capacity to decide, making reasonable adjustments. |
| A09 ✱ | afternoon | History: Presenting complaint and psychiatric history | Addiction | Personalisation and respect | outpatient | man referred about his drinking (patient) | A man referred after abnormal liver tests who minimises his drinking. | Take a history of his alcohol use. |
| A10 ✱ | afternoon | History: Presenting complaint and psychiatric history | General | Cues | outpatient | young adult brought by a sibling's concern (patient) | A young adult with reduced sleep, overspending and grand business plans. | Take a history of the presenting problem. |
| A11 ✱ | afternoon | History: Collateral history | Old age | Cues | outpatient | daughter (relative) | The daughter of a man referred to a memory clinic for forgetfulness and getting lost. | Take a collateral history. |
| A12 ✱ | afternoon | History: Developmental history | Child and adolescent | Personalisation and respect | outpatient | mother of a 7-year-old boy (relative) | A 7-year-old referred by school for inattention, restlessness and difficulty with friendships. | Take a developmental history from his mother. |
| A13 ✱ | afternoon | Examination: Risk assessment | General | Empathy | general hospital | adult admitted after an overdose (patient) | An adult medically fit for discharge after an overdose the night before. | Assess the risk of further self-harm and suicide. |
| A14 ✱ | afternoon | Examination: Mental state (psychotic) | General | Cues | inpatient | woman on an acute ward (patient) | A woman admitted after barricading herself in her flat, convinced that neighbours are watching her. | Examine her mental state for psychotic phenomena. |
| A15 ✱ | afternoon | Examination: Mental state (non-psychotic) | General | Empathy | outpatient | man with sudden attacks of fear (patient) | A man who has stopped using buses and supermarkets after repeated attacks of overwhelming fear. | Examine his mental state for anxiety and related symptoms. |
| A16 ✱ | afternoon | Examination: Mental state (cognitive) | Old age | Personalisation and respect | general hospital | older woman on a medical ward (patient) | An older woman on a medical ward who has become confused over two days. | Examine her cognition, with attention to delirium. |

✱ already written as a case.

## Running order B

| Code | Session | Skill: subdivision | Specialty | Emphasis | Setting | Meets | Scenario | Task |
|---|---|---|---|---|---|---|---|---|
| B01 ✱ | morning | Management: Formulation | Medical psychotherapy | Cues | inpatient | ward nurse (colleague) | A nurse is distressed and angry about a patient who repeatedly self-harms and divides the team. | Help the nurse make sense of the situation, including the feelings it evokes, and agree a team approach. |
| B02 ✱ | morning | Management: Management (biological) | General | Clear information | outpatient | pregnant woman with bipolar disorder (patient) | A woman with bipolar disorder, eight weeks pregnant, who takes a mood stabiliser with known risks in pregnancy. | Discuss her medication and the plan for pregnancy and after birth. |
| B03 ✱ | morning | Management: Management (biological) | Old age | Empathy | inpatient | husband (relative) | An older woman with severe depression who has stopped eating and drinking; ECT is being considered. | Explain ECT to her husband and address his fears. |
| B04 ✱ | morning | Management: Holistic management plan | Intellectual disability | Personalisation and respect | community | support worker (carer) | A young man with autism and a moderate intellectual disability has hit staff since moving to supported living. | Agree a plan with his support worker for the change in behaviour. |
| B05 ✱ | morning | Management: Legal and ethical management | Addiction | Personalisation and respect | outpatient | van driver with alcohol dependence (patient) | A man with alcohol dependence tells you he still drives for work and has driven after drinking. | Discuss his fitness to drive and your duties, including confidentiality. |
| B06 ✱ | morning | Management: Management (psychological) | Child and adolescent | Clear information | outpatient | father of a 14-year-old (relative) | A 14-year-old girl spends hours washing and checking; her father is drawn into her rituals. | Explain the recommended psychological treatment to her father. |
| B07 ✱ | morning | History: Personal and social history | Forensic | Personalisation and respect | criminal justice | man on remand (patient) | A man on remand for assault, referred by prison healthcare for a report. | Take a personal and social history. |
| B08 | morning | Examination: Physical examination | General | Clear information | inpatient | man recently started on an antipsychotic (patient) | A man on an acute ward, recently started on an antipsychotic, is stiff, sweating and confused. | Examine him for the relevant physical signs and say what investigations you would arrange. |
| B09 ✱ | afternoon | History: Presenting complaint and psychiatric history | General | Empathy | community | man seen at home by the crisis team (patient) | A man made redundant three months ago who has stopped going out and sleeps poorly. | Take a history of his low mood. |
| B10 ✱ | afternoon | History: Presenting complaint and psychiatric history | General | Cues | general hospital | woman with many unexplained physical symptoms (patient) | A woman referred from medical clinics after many investigations for pain and fatigue found no cause. | Take a history, exploring her symptoms and her understanding of them. |
| B11 ✱ | afternoon | History: Collateral history | Child and adolescent | Cues | educational | class teacher (colleague) | A 10-year-old boy excluded twice this term for aggression and defiance at school. | Take a collateral history from his teacher. |
| B12 ✱ | afternoon | History: Developmental history | General | Personalisation and respect | outpatient | mother of a 24-year-old (relative) | A 24-year-old referred for an adult autism assessment after difficulties at university. | Take a developmental history from his mother. |
| B13 ✱ | afternoon | Examination: Risk assessment | General | Empathy | emergency | man convinced his partner is unfaithful (patient) | A man brought to the emergency department after threatening his partner over fixed beliefs of infidelity. | Assess the risk he poses to others. |
| B14 ✱ | afternoon | Examination: Mental state (psychotic) | Addiction | Cues | emergency | young man who uses high-potency cannabis (patient) | A young man brought in by friends, frightened and hearing voices after heavy cannabis use. | Examine his mental state for psychotic phenomena. |
| B15 ✱ | afternoon | Examination: Mental state (non-psychotic) | General | Personalisation and respect | community | woman seeking asylum (patient) | A woman seeking asylum, seen at a community centre, with nightmares and intrusive memories. | Examine her mental state for symptoms related to trauma, sensitively. |
| B16 ✱ | afternoon | Examination: Mental state (cognitive) | Old age | Cues | outpatient | man in his sixties (patient) | A man in his sixties whose personality has changed, with disinhibited behaviour and poor planning. | Examine his cognition, including frontal and executive function. |

✱ already written as a case.

## Running order C

| Code | Session | Skill: subdivision | Specialty | Emphasis | Setting | Meets | Scenario | Task |
|---|---|---|---|---|---|---|---|---|
| C01 ✱ | morning | Management: Formulation | General | Clear information | outpatient | general practitioner (colleague) | A GP asks whether a published trial of an app-based therapy for depression applies to her older patients. | Discuss the study's design and findings and whether they generalise to her patients. |
| C02 ✱ | morning | Management: Management (biological) | General | Personalisation and respect | outpatient | man on an antidepressant (patient) | A man whose depression has improved wants to stop his antidepressant because of sexual side effects. | Discuss his options. |
| C03 ✱ | morning | Management: Holistic management plan | General | Personalisation and respect | inpatient | man on a rehabilitation ward (patient) | A man with long-standing schizophrenia preparing to move from a rehabilitation ward to supported housing. | Agree a plan for the move with him. |
| C04 ✱ | morning | Management: Legal and ethical management | Old age | Empathy | outpatient | son (relative) | A son asks that his mother is not told she has dementia, fearing it will upset her. | Respond to his request, explaining your duties to his mother. |
| C05 ✱ | morning | Management: Safety planning | Forensic | Cues | inpatient | man on a forensic step-down unit (patient) | A man with past violence when intoxicated is about to start unescorted community leave. | Agree a safety plan for his leave. |
| C06 ✱ | morning | Management: Management (psychological) | Medical psychotherapy | Empathy | outpatient | woman with longstanding social anxiety (patient) | A woman in her thirties who avoids colleagues and meetings and has never had psychological therapy. | Assess what she wants from therapy and explain the options. |
| C07 ✱ | morning | History: Collateral history | Intellectual disability | Cues | community | care home manager (carer) | A woman with Down syndrome, in her fifties, is losing skills and has become withdrawn. | Take a collateral history from the care home manager. |
| C08 | morning | Examination: Mental state (psychotic) | General | Cues | inpatient | man who has stopped speaking and moving (patient) | A man on an acute ward who has become mute, holds fixed postures and refuses food. | Examine his mental state, including catatonic features. |
| C09 ✱ | afternoon | History: Presenting complaint and psychiatric history | Child and adolescent | Personalisation and respect | outpatient | 17-year-old (patient) | A 17-year-old who cannot fall asleep until the early hours and is missing college mornings. | Take a history of the sleep problem. |
| C10 ✱ | afternoon | History: Physical health history | Addiction | Empathy | community | woman on opioid substitution treatment (patient) | A woman on opioid substitution treatment attending a drug service review. | Take a physical health history. |
| C11 ✱ | afternoon | History: Collateral history | General | Cues | community | husband (relative) | A woman two weeks after giving birth has become confused and frightened and hears voices. | Take a collateral history from her husband. |
| C12 ✱ | afternoon | History: Personal and social history | General | Personalisation and respect | outpatient | transgender woman referred with low mood (patient) | A transgender woman referred with low mood while waiting for gender services. | Take a personal and social history. |
| C13 ✱ | afternoon | Examination: Mental state (psychotic) | Old age | Empathy | community | older woman living alone (patient) | An older woman who believes her neighbours are entering her flat and moving her belongings. | Examine her mental state for psychotic phenomena. |
| C14 ✱ | afternoon | Examination: Mental state (non-psychotic) | General | Cues | general hospital | woman on a neurology ward (patient) | A woman with seizures that tests show are not epileptic, told the diagnosis yesterday. | Examine her mental state. |
| C15 ✱ | afternoon | Examination: Mental state (non-psychotic) | General | Personalisation and respect | outpatient | man with explosive outbursts (patient) | A man referred after losing his temper and damaging property several times. | Examine his mental state. |
| C16 ✱ | afternoon | Examination: Mental state (cognitive) | General | Clear information | general hospital | man with heavy alcohol use (patient) | A man on a medical ward with long heavy drinking, who cannot recall recent events. | Examine his cognition. |

✱ already written as a case.

## Running order D

| Code | Session | Skill: subdivision | Specialty | Emphasis | Setting | Meets | Scenario | Task |
|---|---|---|---|---|---|---|---|---|
| D01 ✱ | morning | Management: Formulation | Forensic | Clear information | criminal justice | consultant forensic psychiatrist (colleague) | A man on probation for indecent exposure is referred for assessment. | Present your formulation of his offending and risk, and a management plan. |
| D02 ✱ | morning | Management: Formulation | Child and adolescent | Empathy | outpatient | parents of a 9-year-old (relative) | A 9-year-old has started wetting and soiling since his parents separated. | Explain your understanding of the problem to his parents and the plan. |
| D03 ✱ | morning | Management: Management (biological) | Addiction | Clear information | community | woman who wants to stop drinking (patient) | A woman with alcohol dependence who wants to stop and asks about medication. | Discuss assisted withdrawal and medication to prevent relapse. |
| D04 ✱ | morning | Management: Holistic management plan | Old age | Cues | inpatient | ward nurse (colleague) | An older man admitted with depression and self-neglect is nearly ready to go home, where he lives alone. | Plan his discharge with the ward nurse. |
| D05 ✱ | morning | Management: Legal and ethical management | Intellectual disability | Personalisation and respect | community | mother of a young woman (relative) | The mother of a young woman with a moderate intellectual disability wants to stop her having a relationship. | Discuss her concerns, your duties and how decisions will be made. |
| D06 ✱ | morning | Management: Safety planning | General | Empathy | community | mother of a three-month-old (patient) | A mother with postnatal depression who has thoughts that she and the baby would be better off without her. | Agree a safety plan with her. |
| D07 ✱ | morning | History: Developmental history | Medical psychotherapy | Empathy | outpatient | woman referred for psychotherapy (patient) | A woman referred for psychotherapy with longstanding emotional numbness and difficult relationships. | Take a developmental history, including early relationships and adversity. |
| D08 ✱ | morning | Examination: Capacity assessment | General | Personalisation and respect | general hospital | man with diabetes and low mood (patient) | A man with a diabetic foot infection refuses the recommended amputation. | Assess his capacity to refuse the operation. |
| D09 ✱ | afternoon | History: Presenting complaint and psychiatric history | General | Personalisation and respect | outpatient | young man with checking rituals (patient) | A young man who spends hours each day checking locks and appliances and has stopped working. | Take a history of the presenting problem. |
| D10 ✱ | afternoon | History: Presenting complaint and psychiatric history | Old age | Empathy | community | widower seen at home (patient) | An older man seen at home a year after his wife's death, who is still unable to resume his life. | Take a history, distinguishing grief from depression. |
| D11 ✱ | afternoon | History: Collateral history | Forensic | Cues | criminal justice | probation officer (colleague) | A man with schizophrenia on probation has missed appointments and his probation officer is worried. | Take a collateral history from the probation officer. |
| D12 ✱ | afternoon | History: Personal and social history | Child and adolescent | Cues | educational | 16-year-old young carer (patient) | A 16-year-old who cares for a parent with a disabling illness, referred by the school nurse. | Take a personal and social history. |
| D13 ✱ | afternoon | Examination: Risk assessment | General | Empathy | criminal justice | man in a police custody suite (patient) | A man arrested for the first time who told a custody officer he wants to die. | Assess his risk of suicide. |
| D14 ✱ | afternoon | Examination: Mental state (psychotic) | General | Cues | community | woman with epilepsy (patient) | A woman with epilepsy who, after a cluster of seizures, believes her thoughts are being broadcast. | Examine her mental state for psychotic phenomena. |
| D15 ✱ | afternoon | Examination: Mental state (non-psychotic) | General | Personalisation and respect | general hospital | woman with repeated unexplained infections (patient) | A woman with repeated infections that the medical team suspect may be self-induced. | Examine her mental state, sensitively. |
| D16 | afternoon | Examination: Physical examination | General | Clear information | emergency | woman taking lithium (patient) | A woman taking lithium with a coarse tremor, vomiting and unsteadiness. | Examine her for signs of toxicity and say what investigations you would arrange. |

✱ already written as a case.
