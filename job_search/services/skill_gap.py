import re
from collections import Counter

from job_search.services.skill_matching import extract_skills_from_resume

KNOWN_SKILLS = {
    # --- Programming & Tech ---
    'python', 'java', 'javascript', 'typescript', 'react', 'angular', 'vue',
    'node', 'nodejs', 'django', 'flask', 'fastapi', 'spring', 'sql', 'nosql',
    'mongodb', 'postgresql', 'mysql', 'redis', 'docker', 'kubernetes', 'aws',
    'azure', 'gcp', 'git', 'ci/cd', 'rest', 'graphql', 'html', 'css',
    'machine learning', 'deep learning', 'nlp', 'computer vision', 'tensorflow',
    'pytorch', 'pandas', 'numpy', 'scikit-learn', 'data analysis', 'data science',
    'excel', 'tableau', 'power bi', 'spark', 'hadoop', 'kafka', 'airflow',
    'linux', 'bash', 'c++', 'c#', 'rust', 'go', 'kotlin', 'swift', 'ruby',
    'php', 'scala', 'r', 'matlab', 'figma', 'photoshop', 'illustrator',
    'jira', 'agile', 'scrum',

    # --- Data & Analytics ---
    'a/b testing', 'etl', 'data warehousing', 'data modeling', 'data engineering',
    'data visualization', 'bigquery', 'redshift', 'snowflake', 'looker',
    'dbt', 'apache beam', 'apache flink', 'data governance', 'data quality',
    'statistical analysis', 'predictive modeling', 'time series analysis',

    # --- Finance / Accounting ---
    'financial modeling', 'valuation', 'bloomberg', 'sap', 'quickbooks',
    'financial analysis', 'budgeting', 'forecasting', 'accounts payable',
    'accounts receivable', 'general ledger', 'gaap', 'ifrs', 'audit',
    'tax preparation', 'risk management', 'portfolio management',
    'investment banking', 'equity research', 'derivatives', 'fixed income',
    'financial reporting', 'treasury', 'cost accounting', 'cpa', 'cfa',
    'xero', 'netsuite', 'oracle financials', 'hyperion',

    # --- Marketing ---
    'seo', 'sem', 'google analytics', 'content marketing', 'social media marketing',
    'email marketing', 'marketing automation', 'hubspot', 'mailchimp',
    'google ads', 'facebook ads', 'ppc', 'conversion rate optimization',
    'brand management', 'market research', 'copywriting', 'content strategy',
    'influencer marketing', 'affiliate marketing', 'marketing strategy',
    'public relations', 'media planning', 'demand generation', 'growth hacking',
    'adobe analytics', 'mixpanel', 'segment',

    # --- Design ---
    'ui/ux', 'ux design', 'ui design', 'sketch', 'indesign', 'after effects',
    'motion graphics', 'adobe xd', 'wireframing', 'prototyping', 'user research',
    'interaction design', 'visual design', 'typography', 'graphic design',
    'responsive design', 'design systems', 'accessibility', 'usability testing',
    'information architecture', 'cinema 4d', 'blender', 'premiere pro',
    'lightroom', 'canva', 'invision', 'zeplin', 'framer',

    # --- Healthcare ---
    'clinical research', 'hipaa', 'emr', 'ehr', 'patient care',
    'medical coding', 'medical billing', 'icd-10', 'cpt coding',
    'clinical trials', 'fda regulations', 'gcp compliance', 'pharmacovigilance',
    'healthcare analytics', 'epic', 'cerner', 'hl7', 'fhir',
    'nursing', 'phlebotomy', 'radiology', 'pharmacy', 'telemedicine',
    'public health', 'epidemiology', 'biostatistics',

    # --- Legal ---
    'contract drafting', 'compliance', 'intellectual property', 'litigation',
    'legal research', 'regulatory compliance', 'corporate law', 'mergers and acquisitions',
    'due diligence', 'contract management', 'gdpr', 'data privacy',
    'employment law', 'patent law', 'trademark', 'arbitration', 'mediation',
    'legal writing', 'westlaw', 'lexisnexis', 'case management',

    # --- HR / People ---
    'talent acquisition', 'hris', 'compensation', 'employee relations',
    'performance management', 'onboarding', 'benefits administration',
    'workforce planning', 'succession planning', 'employee engagement',
    'diversity and inclusion', 'labor relations', 'payroll', 'adp',
    'workday', 'bamboohr', 'greenhouse', 'lever', 'organizational development',
    'change management', 'training and development', 'learning management',

    # --- Operations / Supply Chain ---
    'lean', 'six sigma', 'logistics', 'procurement', 'supply chain management',
    'inventory management', 'warehouse management', 'demand planning',
    'vendor management', 'quality assurance', 'quality control',
    'process improvement', 'operations management', 'production planning',
    'iso 9001', 'kaizen', 'kanban', 'erp', 'sap mm', 'sap sd',

    # --- Sales ---
    'crm', 'salesforce', 'cold calling', 'lead generation', 'b2b sales',
    'b2c sales', 'account management', 'sales strategy', 'pipeline management',
    'negotiation', 'business development', 'territory management',
    'sales forecasting', 'customer success', 'upselling', 'cross-selling',
    'zoho crm', 'pipedrive', 'outreach', 'sales enablement',

    # --- Education ---
    'curriculum design', 'lms', 'instructional design', 'e-learning',
    'lesson planning', 'educational technology', 'moodle', 'canvas',
    'blackboard', 'assessment design', 'pedagogy', 'student engagement',
    'classroom management', 'special education', 'tutoring',
    'course development', 'training facilitation',

    # --- Soft Skills ---
    'communication', 'leadership', 'teamwork', 'problem solving',
    'critical thinking', 'time management', 'project management',
    'strategic planning', 'decision making', 'conflict resolution',
    'presentation skills', 'stakeholder management', 'cross-functional collaboration',
    'mentoring', 'coaching', 'adaptability', 'emotional intelligence',
    'analytical thinking', 'attention to detail', 'creativity',

    # --- Project Management ---
    'pmp', 'prince2', 'waterfall', 'resource planning', 'risk assessment',
    'gantt charts', 'ms project', 'asana', 'trello', 'monday.com',
    'confluence', 'notion', 'okr', 'kpi tracking', 'sprint planning',
    'backlog grooming',
}


def extract_skills_from_job(job):
    """Extract potential skill keywords from a job's title and description."""
    text_parts = []
    if job.title:
        text_parts.append(job.title)
    if job.description:
        text_parts.append(job.description)
    if job.work_type:
        text_parts.append(job.work_type)

    text = ' '.join(text_parts).lower()

    found = set()
    for skill in KNOWN_SKILLS:
        if len(skill) <= 2:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, text):
                found.add(skill)
        else:
            if skill in text:
                found.add(skill)

    return found


def analyze_skill_gaps(matching_results, resume_metadata):
    """
    Compare user's resume skills against skills found in top matched jobs.

    Returns a dict with skill_gaps, user_skills_count, and jobs_analyzed.
    """
    user_skills = extract_skills_from_resume(resume_metadata)
    user_skills_lower = {s.lower() for s in user_skills}

    job_skill_counter = Counter()
    jobs_analyzed = 0

    for result in matching_results:
        job = result.job
        job_skills = extract_skills_from_job(job)
        for skill in job_skills:
            if skill not in user_skills_lower:
                job_skill_counter[skill] += 1
        jobs_analyzed += 1

    if jobs_analyzed == 0:
        return {
            'skill_gaps': [],
            'user_skills_count': len(user_skills),
            'jobs_analyzed': 0,
        }

    skill_gaps = [
        {
            'skill': skill,
            'frequency': count,
            'percentage': round(count / jobs_analyzed * 100, 1),
        }
        for skill, count in job_skill_counter.most_common()
    ]

    return {
        'skill_gaps': skill_gaps,
        'user_skills_count': len(user_skills),
        'jobs_analyzed': jobs_analyzed,
    }
