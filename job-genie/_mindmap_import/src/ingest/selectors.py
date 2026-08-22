"""LinkedIn CSS Selectors for job search and extraction."""

# --- SEARCH PAGE SELECTORS ---

# Selectors for the main results list container
SEARCH_RESULTS_LIST_SELECTORS = [
    ".jobs-search-results-list",
    "ul.jobs-search__results-list",
    ".scaffold-layout__list-container",
    "ul.scaffold-layout__list-container",
    ".jobs-search-two-pane__job-section",
    "section.jobs-search-results-list",
]

# Selectors for individual job cards within the search results
SEARCH_JOB_CARD_SELECTORS = [
    ".jobs-search-results-list__item",
    "li",
    ".job-card-container",
    ".base-card",
    ".job-search-card",
    ".base-search-card",
]

# Field selectors within a search job card
SEARCH_CARD_TITLE_SELECTORS = [
    ".job-card-list__title",
    ".base-search-card__title",
    ".job-search-card__title",
    "h3",
    "h4",
    "a",
]

SEARCH_CARD_COMPANY_SELECTORS = [
    ".job-card-container__primary-description",
    ".base-search-card__subtitle",
    ".job-search-card__subtitle",
    ".topcard__org-name-link",
    ".job-card-container__company-name",
    ".base-card__subtitle",
    ".job-card-list__company-name",
    "button[class*='company']",
]

SEARCH_CARD_LOCATION_SELECTORS = [
    ".job-card-container__metadata-item",
    ".job-search-card__location",
    ".base-search-card__metadata",
    ".job-card-container__metadata-wrapper",
]

# --- JOB PAGE SELECTORS ---

# Selectors to wait for when loading a job page
JOB_PAGE_WAIT_SELECTORS = [
    ".jobs-description",
    ".top-card-layout",
    ".main-content",
    ".description__text",
    ".job-details-jobs-unified-top-card",
    ".jobs-unified-top-card",
]

JOB_TITLE_SELECTORS = [
    ".job-details-jobs-unified-top-card__job-title",
    ".top-card-layout__title",
    ".jobs-unified-top-card__job-title",
    "h1.top-card-layout__title",
    "h1",
    ".topcard__title",
    "h2.top-card-layout__title",
]

JOB_COMPANY_SELECTORS = [
    ".job-details-jobs-unified-top-card__company-name",
    ".topcard__org-name-link",
    ".topcard__flavor a",
    ".top-card-layout__first-subline a",
    ".job-details-jobs-unified-top-card__company-name a",
    ".jobs-unified-top-card__company-name",
    ".app-shared-outline--company-name",
]

JOB_LOCATION_SELECTORS = [
    ".job-details-jobs-unified-top-card__bullet",
    ".topcard__flavor--bullet",
    ".top-card-layout__first-subline span:nth-child(2)",
    ".jobs-unified-top-card__bullet",
    ".job-details-jobs-unified-top-card__primary-description-container span:last-child",
]

JOB_DESCRIPTION_SELECTORS = [
    ".jobs-description__container",
    ".show-more-less-html__markup",
    ".description__text",
    ".jobs-description-content__text",
    ".description__text--rich",
    "#job-details",
    ".jobs-box__html-content",
]

JOB_POSTED_DATE_SELECTORS = [
    ".job-details-jobs-unified-top-card__posted-date",
    ".topcard__flavor--metadata",
    "span.posted-time-ago__text",
    ".topcard__flavor--metadata.posted-time-ago__text",
]

# --- MODAL, AUTHWALL & ERROR SELECTORS ---

JOB_ERROR_SELECTORS = [
    ".jobs-details-error",
    ".artdeco-empty-state",
    ".error-container",
    "text=No longer accepting applications",
    "text=Security Check",
]

LOGIN_MODAL_SELECTORS = [
    ".modal--contextual-sign-in",
    ".authwall-modal",
    ".login-modal",
    ".sign-in-modal",
]

# Selectors for job insights (top card metadata)
JOB_INSIGHT_SELECTORS = [
    ".job-details-jobs-unified-top-card__job-insight",
    ".jobs-unified-top-card__job-insight",
    ".topcard__flavor--metadata",
]

# Selectors for job criteria (bottom section metadata)
JOB_CRITERIA_ITEM_SELECTORS = [
    ".description__job-criteria-item",
    ".jobs-description-details__list-item",
]

JOB_CRITERIA_HEADER_SELECTORS = [
    ".description__job-criteria-subheader",
    ".jobs-description-details__list-item-group-title",
]

JOB_CRITERIA_VALUE_SELECTORS = [
    ".description__job-criteria-text",
    ".jobs-description-details__list-item-text",
]

# Selectors for salary information
JOB_SALARY_SELECTORS = [
    ".job-details-jobs-unified-top-card__job-insight:has-text('$')",
    ".jobs-unified-top-card__job-insight:has-text('$')",
    ".salary-field",
    ".compensation-insight",
]

# Selectors for apply buttons/links
JOB_APPLY_SELECTORS = [
    ".jobs-apply-button",
    ".jobs-s-apply",
    "button[class*='apply']",
    "a[class*='apply']",
]
