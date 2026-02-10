from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.test.utils import override_settings
from rest_framework.test import APIClient

from .models import Job, JobPreference, MatchingRun


class JobPreferenceModelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='model-user',
            email='model@example.com',
            password='password123',
        )

    def test_full_time_without_duration_is_valid(self):
        preference = JobPreference(
            user=self.user,
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            location='Bangalore',
            company_size_preference='STARTUP',
            stipend_currency='INR',
        )
        preference.full_clean()

    def test_internship_without_duration_is_invalid(self):
        preference = JobPreference(
            user=self.user,
            work_mode='REMOTE',
            employment_type='INTERNSHIP',
            location='Bangalore',
            company_size_preference='STARTUP',
            stipend_currency='INR',
        )
        with self.assertRaises(ValidationError):
            preference.full_clean()

    def test_internship_with_duration_is_valid(self):
        preference = JobPreference(
            user=self.user,
            work_mode='ONSITE',
            employment_type='INTERNSHIP',
            internship_duration_weeks=12,
            location='Mumbai',
            company_size_preference='MNC',
            stipend_currency='INR',
        )
        preference.full_clean()

    def test_stipend_min_greater_than_max_is_invalid(self):
        preference = JobPreference(
            user=self.user,
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            location='Delhi',
            company_size_preference='SME',
            stipend_min='20000.00',
            stipend_max='10000.00',
            stipend_currency='INR',
        )
        with self.assertRaises(ValidationError):
            preference.full_clean()

    def test_single_stipend_bound_is_invalid(self):
        preference = JobPreference(
            user=self.user,
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            location='Delhi',
            company_size_preference='SME',
            stipend_min='10000.00',
            stipend_currency='INR',
        )
        with self.assertRaises(ValidationError):
            preference.full_clean()


class MatchJobsEndpointTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='api-user',
            email='api@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.url = reverse('match-jobs-by-preference')

    def _create_jobs(self):
        Job.objects.create(
            job_id='job-1',
            title='Backend Intern',
            company_name='Acme Startup',
            location='Bangalore, India',
            job_url='https://example.com/job-1',
            work_mode='REMOTE',
            employment_type='INTERNSHIP',
            internship_duration_weeks=12,
            company_size='STARTUP',
            stipend_min='10000.00',
            stipend_max='15000.00',
            stipend_currency='INR',
        )
        Job.objects.create(
            job_id='job-2',
            title='Backend Engineer',
            company_name='Mega Corp',
            location='Bangalore, India',
            job_url='https://example.com/job-2',
            work_mode='ONSITE',
            employment_type='FULL_TIME',
            company_size='MNC',
            stipend_min='30000.00',
            stipend_max='40000.00',
            stipend_currency='INR',
        )
        Job.objects.create(
            job_id='job-3',
            title='Data Intern',
            company_name='Startup Lab',
            location='Bangalore, India',
            job_url='https://example.com/job-3',
            work_mode='REMOTE',
            employment_type='INTERNSHIP',
            internship_duration_weeks=12,
            company_size='STARTUP',
            stipend_min='20000.00',
            stipend_max='25000.00',
            stipend_currency='INR',
        )

    def test_unauthenticated_request_returns_401(self):
        response = self.client.post(self.url, data={}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_valid_request_returns_filtered_jobs_and_saves_preference(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'INTERNSHIP',
            'internship_duration_weeks': 12,
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'stipend_min': '12000.00',
            'stipend_max': '18000.00',
            'stipend_currency': 'INR',
            'save_preference': True,
        }
        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['job_id'], 'job-1')
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_missing_duration_for_internship_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'INTERNSHIP',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_save_preference_false_does_not_persist(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'INTERNSHIP',
            'internship_duration_weeks': 12,
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'save_preference': False,
        }
        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 0)

    def test_stipend_overlap_filter_excludes_non_overlapping_jobs(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'INTERNSHIP',
            'internship_duration_weeks': 12,
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'stipend_min': '16000.00',
            'stipend_max': '19000.00',
            'stipend_currency': 'INR',
        }
        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, AGENT_MATCHING_ENABLED=True)
class MatchingRunApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='run-user',
            email='run@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.create_url = reverse('matching-run-create')
        self.list_url = reverse('matching-run-list')

    def _seed_jobs(self):
        Job.objects.create(
            job_id='run-job-1',
            title='Data Intern',
            company_name='Startup One',
            location='bangalore, india',
            job_url='https://example.com/run-job-1',
            work_mode='REMOTE',
            employment_type='INTERNSHIP',
            internship_duration_weeks=12,
            company_size='STARTUP',
            stipend_min='10000.00',
            stipend_max='15000.00',
            stipend_currency='INR',
        )
        Job.objects.create(
            job_id='run-job-2',
            title='ML Intern',
            company_name='Startup Two',
            location='bangalore, india',
            job_url='https://example.com/run-job-2',
            work_mode='REMOTE',
            employment_type='INTERNSHIP',
            internship_duration_weeks=12,
            company_size='STARTUP',
            stipend_min='12000.00',
            stipend_max='18000.00',
            stipend_currency='INR',
        )

    def _payload(self):
        return {
            'preferences': {
                'work_mode': 'REMOTE',
                'employment_type': 'INTERNSHIP',
                'internship_duration_weeks': 12,
                'location': 'Bangalore',
                'company_size_preference': 'STARTUP',
                'stipend_min': '9000.00',
                'stipend_max': '20000.00',
                'stipend_currency': 'INR',
                'save_preference': True,
            },
            'candidate_profile': {
                'career_stage': 'EARLY',
                'risk_tolerance': 'LOW',
            },
        }

    def test_create_run_returns_202_and_persists(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.create_url, data=self._payload(), format='json')

        self.assertEqual(response.status_code, 202)
        self.assertIn('run_id', response.data)

        run = MatchingRun.objects.get(id=response.data['run_id'])
        self.assertEqual(run.user_id, self.user.id)
        self.assertIn(run.status, [MatchingRun.STATUS_PENDING, MatchingRun.STATUS_COMPLETED])

    def test_list_runs_returns_user_runs_only(self):
        self._seed_jobs()
        other = get_user_model().objects.create_user(
            username='other-user',
            email='other@example.com',
            password='password123',
        )
        MatchingRun.objects.create(
            user=other,
            preferences_snapshot={'work_mode': 'REMOTE'},
            candidate_profile_snapshot={},
        )

        self.client.force_authenticate(user=self.user)
        self.client.post(self.create_url, data=self._payload(), format='json')
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)

    def test_get_run_detail_returns_top_jobs_when_completed(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(self.create_url, data=self._payload(), format='json')
        run_id = create_response.data['run_id']

        detail_url = reverse('matching-run-detail', kwargs={'run_id': run_id})
        detail_response = self.client.get(detail_url)

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(detail_response.data['status'], [MatchingRun.STATUS_COMPLETED, MatchingRun.STATUS_AGENT_RUNNING, MatchingRun.STATUS_FILTERING, MatchingRun.STATUS_PENDING])
        if detail_response.data['status'] == MatchingRun.STATUS_COMPLETED:
            self.assertLessEqual(len(detail_response.data['top_5_jobs']), 5)

    def test_user_cannot_access_another_users_run(self):
        other = get_user_model().objects.create_user(
            username='forbidden-user',
            email='forbidden@example.com',
            password='password123',
        )
        run = MatchingRun.objects.create(
            user=other,
            preferences_snapshot={'work_mode': 'REMOTE'},
            candidate_profile_snapshot={},
        )
        self.client.force_authenticate(user=self.user)
        detail_url = reverse('matching-run-detail', kwargs={'run_id': run.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_create_run_returns_401(self):
        response = self.client.post(self.create_url, data=self._payload(), format='json')
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_list_run_returns_401(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_create_run_saves_preference_when_enabled(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.create_url, data=self._payload(), format='json')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_create_run_with_no_matching_jobs_completes_with_empty_results(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        payload = self._payload()
        payload['preferences']['location'] = 'Chennai'
        response = self.client.post(self.create_url, data=payload, format='json')
        self.assertEqual(response.status_code, 202)

        detail_url = reverse('matching-run-detail', kwargs={'run_id': response.data['run_id']})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['status'], MatchingRun.STATUS_COMPLETED)
        self.assertEqual(detail_response.data['filtered_jobs_count'], 0)
        self.assertEqual(detail_response.data['top_5_jobs'], [])

    def test_failed_run_detail_includes_error_block(self):
        run = MatchingRun.objects.create(
            user=self.user,
            status=MatchingRun.STATUS_FAILED,
            preferences_snapshot={'work_mode': 'REMOTE'},
            candidate_profile_snapshot={},
            error_code='AGENT_PIPELINE_ERROR',
            error_message='Mock failure',
        )
        self.client.force_authenticate(user=self.user)
        detail_url = reverse('matching-run-detail', kwargs={'run_id': run.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], MatchingRun.STATUS_FAILED)
        self.assertEqual(response.data['error']['code'], 'AGENT_PIPELINE_ERROR')
        self.assertEqual(response.data['error']['message'], 'Mock failure')


class JobRecommendationApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='rec-user',
            email='rec@example.com',
            password='password123',
            resume_metadata={
                'skills': [
                    {'category': 'Programming', 'skills': ['Python', 'Django', 'REST APIs']},
                    {'category': 'Data', 'skills': ['SQL', 'PostgreSQL']},
                ]
            },
        )
        self.user_no_resume = get_user_model().objects.create_user(
            username='no-resume-user',
            email='noresume@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.url = reverse('job-recommendations')

    def _create_jobs(self):
        Job.objects.create(
            job_id='rec-job-1',
            title='Python Backend Developer',
            description='We need a Python Django developer with REST API experience and SQL knowledge.',
            company_name='Tech Startup',
            location='Bangalore, India',
            job_url='https://example.com/rec-job-1',
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            company_size='STARTUP',
        )
        Job.objects.create(
            job_id='rec-job-2',
            title='Frontend Developer',
            description='React and JavaScript developer needed for UI work.',
            company_name='Web Corp',
            location='Mumbai, India',
            job_url='https://example.com/rec-job-2',
            work_mode='ONSITE',
            employment_type='FULL_TIME',
            company_size='MNC',
        )
        Job.objects.create(
            job_id='rec-job-3',
            title='Data Analyst Intern',
            description='SQL and Python skills required for data analysis internship.',
            company_name='Data Labs',
            location='Bangalore, India',
            job_url='https://example.com/rec-job-3',
            work_mode='REMOTE',
            employment_type='INTERNSHIP',
            internship_duration_weeks=12,
            company_size='STARTUP',
        )

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, data={}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_no_resume_returns_400(self):
        self.client.force_authenticate(user=self.user_no_resume)
        response = self.client.post(self.url, data={}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['code'], 'RESUME_NOT_FOUND')

    def test_minimal_request_returns_recommendations(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('recommendations', response.data)
        self.assertIn('total_jobs_considered', response.data)
        self.assertIn('resume_skills_count', response.data)
        self.assertEqual(response.data['total_jobs_considered'], 3)
        self.assertGreater(len(response.data['recommendations']), 0)

    def test_recommendations_have_correct_shape(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={}, format='json')

        self.assertEqual(response.status_code, 200)
        rec = response.data['recommendations'][0]
        expected_fields = [
            'id', 'job_id', 'title', 'company_name', 'location',
            'work_mode', 'employment_type', 'skill_match_score',
            'matched_skills', 'composite_score', 'match_reasons',
        ]
        for field in expected_fields:
            self.assertIn(field, rec, f'Missing field: {field}')

    def test_location_filter(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={'location': 'mumbai'}, format='json')

        self.assertEqual(response.status_code, 200)
        for rec in response.data['recommendations']:
            self.assertIn('Mumbai', rec['location'])

    def test_employment_type_filter(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, data={'employment_type': 'INTERNSHIP', 'internship_duration_weeks': 12}, format='json'
        )

        self.assertEqual(response.status_code, 200)
        for rec in response.data['recommendations']:
            self.assertEqual(rec['employment_type'], 'INTERNSHIP')

    def test_work_mode_filter(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={'work_mode': 'REMOTE'}, format='json')

        self.assertEqual(response.status_code, 200)
        for rec in response.data['recommendations']:
            self.assertEqual(rec['work_mode'], 'REMOTE')

    def test_invalid_work_mode_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={'work_mode': 'INVALID'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('work_mode', response.data)

    def test_top_n_limits_results(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={'top_n': 1}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data['recommendations']), 1)

    def test_python_jobs_ranked_higher(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={}, format='json')

        self.assertEqual(response.status_code, 200)
        recs = response.data['recommendations']
        # The Python Backend Developer job should rank higher than Frontend Developer
        # because the user has Python, Django, REST APIs, SQL skills
        python_job = next((r for r in recs if r['job_id'] == 'rec-job-1'), None)
        frontend_job = next((r for r in recs if r['job_id'] == 'rec-job-2'), None)
        self.assertIsNotNone(python_job)
        self.assertIsNotNone(frontend_job)
        self.assertGreater(python_job['skill_match_score'], frontend_job['skill_match_score'])

    def test_no_matching_jobs_returns_empty(self):
        self._create_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.url, data={'location': 'NonexistentCity'}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_jobs_considered'], 0)
        self.assertEqual(response.data['recommendations'], [])


@override_settings(AGENT_MATCHING_ENABLED=False)
class MatchingRunFeatureFlagTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='flag-user',
            email='flag@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.url = reverse('matching-run-create')

    def test_create_run_returns_503_when_feature_disabled(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'preferences': {
                'work_mode': 'REMOTE',
                'employment_type': 'FULL_TIME',
                'location': 'Bangalore',
                'company_size_preference': 'STARTUP',
            }
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 503)
