import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse
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


class PreferencesViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='pref-user',
            email='pref@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.url = reverse('preferences')

    def test_unauthenticated_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_get_empty_preference(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['preference'])

    def test_post_creates_preference(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('preference', response.data)
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_get_returns_saved_preference(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
        }
        self.client.post(self.url, data=payload, format='json')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['preference']['work_mode'], 'REMOTE')

    def test_delete_deactivates_preference(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
        }
        self.client.post(self.url, data=payload, format='json')
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 0)

    def test_delete_no_preference_returns_404(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 404)

    def test_missing_required_field_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {'work_mode': 'REMOTE'}
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_save_preference_false_does_not_persist(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'save_preference': False,
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 0)

    def test_experience_level_filter(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'experience_level': 'Entry level',
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['preference']['experience_level'], 'Entry level')

    def test_invalid_experience_level_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'experience_level': 'INVALID',
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('experience_level', response.data)

    def test_preferred_sectors(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'preferred_sectors': ['Technology', 'Finance'],
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)

    def test_overlapping_sectors_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'preferred_sectors': ['Technology'],
            'excluded_sectors': ['Technology'],
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_preferred_roles(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'preferred_roles': ['backend developer', 'python developer'],
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)

    def test_company_blacklist(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'excluded_companies': ['BadCo'],
            'preferred_companies': ['Google'],
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)

    def test_overlapping_companies_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'excluded_companies': ['Google'],
            'preferred_companies': ['Google'],
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_weights(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'weights': {'location': 0.9, 'skill_match': 0.8},
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 200)

    def test_invalid_weight_key_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'weights': {'invalid_key': 0.5},
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_weight_out_of_range_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'work_mode': 'REMOTE',
            'employment_type': 'FULL_TIME',
            'location': 'Bangalore',
            'company_size_preference': 'STARTUP',
            'weights': {'location': 1.5},
        }
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, AGENT_MATCHING_ENABLED=True)
class MatchingRunApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='run-user',
            email='run@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.url = reverse('matches-runs')

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
        response = self.client.post(self.url, data=self._payload(), format='json')

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
        self.client.post(self.url, data=self._payload(), format='json')
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(len(response.data['results']), 1)

    def test_get_run_detail_returns_top_jobs_when_completed(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        create_response = self.client.post(self.url, data=self._payload(), format='json')
        run_id = create_response.data['run_id']

        detail_url = reverse('matches-run-detail', kwargs={'run_id': run_id})
        detail_response = self.client.get(detail_url)

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(detail_response.data['status'], [MatchingRun.STATUS_COMPLETED, MatchingRun.STATUS_AGENT_RUNNING, MatchingRun.STATUS_FILTERING, MatchingRun.STATUS_PENDING])
        if detail_response.data['status'] == MatchingRun.STATUS_COMPLETED:
            self.assertGreater(len(detail_response.data['matched_jobs']['results']), 0)

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
        detail_url = reverse('matches-run-detail', kwargs={'run_id': run.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_create_run_returns_401(self):
        response = self.client.post(self.url, data=self._payload(), format='json')
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_list_run_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_create_run_saves_preference_when_enabled(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data=self._payload(), format='json')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(JobPreference.objects.filter(user=self.user, is_active=True).count(), 1)

    def test_create_run_with_no_matching_jobs_completes_with_empty_results(self):
        self._seed_jobs()
        self.client.force_authenticate(user=self.user)
        payload = self._payload()
        payload['preferences']['location'] = 'Chennai'
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 202)

        detail_url = reverse('matches-run-detail', kwargs={'run_id': response.data['run_id']})
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data['status'], MatchingRun.STATUS_COMPLETED)
        self.assertEqual(detail_response.data['filtered_jobs_count'], 0)
        self.assertEqual(detail_response.data['matched_jobs']['count'], 0)
        self.assertEqual(detail_response.data['matched_jobs']['results'], [])

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
        detail_url = reverse('matches-run-detail', kwargs={'run_id': run.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], MatchingRun.STATUS_FAILED)
        self.assertEqual(response.data['error']['code'], 'AGENT_PIPELINE_ERROR')
        self.assertEqual(response.data['error']['message'], 'Mock failure')


@override_settings(AGENT_MATCHING_ENABLED=False)
class MatchingRunFeatureFlagTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='flag-user',
            email='flag@example.com',
            password='password123',
        )
        self.client = APIClient()
        self.url = reverse('matches-runs')

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


class ResumeSkillMatchingTests(TestCase):
    """Tests for resume-to-job skill matching in the orchestrator pipeline."""

    def setUp(self):
        Job.objects.create(
            job_id='skill-job-1',
            title='Python Backend Developer',
            company_name='TechCorp',
            location='bangalore, india',
            job_url='https://example.com/skill-1',
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            company_size='STARTUP',
            description='Looking for a Python developer with Django and REST API experience.',
        )
        Job.objects.create(
            job_id='skill-job-2',
            title='Marketing Manager',
            company_name='AdCorp',
            location='mumbai, india',
            job_url='https://example.com/skill-2',
            work_mode='ONSITE',
            employment_type='FULL_TIME',
            company_size='MNC',
            description='Need SEO expert with Google Analytics and content marketing skills.',
        )

    def test_skill_matching_activates_with_resume(self):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
            candidate_profile={
                'resume_metadata': {
                    'skills': [{'category': 'Backend', 'skills': ['Python', 'Django', 'REST APIs']}],
                },
            },
        )
        self.assertTrue(result['context']['skill_matching_active'])
        self.assertGreater(result['context']['user_skills_count'], 0)

    def test_no_resume_keeps_skill_matching_inactive(self):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
            candidate_profile={},
        )
        self.assertFalse(result['context']['skill_matching_active'])
        self.assertEqual(result['context']['user_skills_count'], 0)

    def test_none_candidate_profile_backward_compatible(self):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
        )
        self.assertFalse(result['context']['skill_matching_active'])
        self.assertGreater(result['total_ranked'], 0)

    def test_skill_match_appears_in_why(self):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
            candidate_profile={
                'resume_metadata': {
                    'skills': [{'category': 'Backend', 'skills': ['Python', 'Django']}],
                },
            },
        )
        skill_match_found = any('Skill match' in tj['why'] for tj in result['top_jobs'])
        self.assertTrue(skill_match_found)

    def test_relevant_job_ranked_higher_with_resume(self):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
            candidate_profile={
                'resume_metadata': {
                    'skills': [{'category': 'Backend', 'skills': ['Python', 'Django']}],
                },
            },
        )
        top_job = result['top_jobs'][0]
        job = Job.objects.get(id=top_job['job_id'])
        self.assertIn('Python', job.title)


@override_settings(GPT_JOB_SCORING_ENABLED=False)
class GPTScoringDisabledTests(TestCase):
    """Tests verifying GPT scoring is properly disabled by default."""

    def test_gpt_disabled_by_default(self):
        from job_search.services.openai_client import is_gpt_scoring_enabled
        self.assertFalse(is_gpt_scoring_enabled())

    def test_pipeline_returns_gpt_not_applied(self):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        Job.objects.create(
            job_id='gpt-off-job',
            title='Test Job',
            company_name='TestCo',
            location='bangalore',
            job_url='https://example.com/gpt-off',
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            company_size='STARTUP',
        )
        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
        )
        self.assertFalse(result['gpt_metrics']['applied'])


@override_settings(GPT_JOB_SCORING_ENABLED=True, OPENAI_API_KEY='test-key')
class GPTScoringEnabledTests(TestCase):
    """Tests for GPT scoring when enabled (with mocked OpenAI client)."""

    def setUp(self):
        Job.objects.create(
            job_id='gpt-job-1',
            title='Python Developer',
            company_name='TechCorp',
            location='bangalore, india',
            job_url='https://example.com/gpt-1',
            work_mode='REMOTE',
            employment_type='FULL_TIME',
            company_size='STARTUP',
            description='Python and Django developer needed.',
        )

    def test_gpt_enabled_flag(self):
        from job_search.services.openai_client import is_gpt_scoring_enabled
        self.assertTrue(is_gpt_scoring_enabled())

    @patch('job_search.services.agents.gpt_scorer.get_sync_openai_client')
    def test_gpt_scoring_blends_with_heuristic(self, mock_client_fn):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            'role_fit': 0.9,
            'skill_alignment': 0.85,
            'career_trajectory': 0.8,
            'culture_signals': 0.75,
            'overall_score': 0.85,
            'reasoning': 'Strong Python/Django match with relevant backend experience.',
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
            candidate_profile={'resume_metadata': {'skills': [{'category': 'Backend', 'skills': ['Python']}]}},
        )
        self.assertTrue(result['gpt_metrics']['applied'])
        self.assertEqual(result['gpt_metrics']['jobs_scored'], 1)
        top = result['top_jobs'][0]
        self.assertEqual(top['agent_trace']['scoring_method'], 'heuristic+gpt')

    @patch('job_search.services.agents.gpt_scorer.get_sync_openai_client')
    def test_gpt_failure_falls_back_gracefully(self, mock_client_fn):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception('API Error')
        mock_client_fn.return_value = mock_client

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
        )
        gpt = result['gpt_metrics']
        self.assertTrue(gpt['applied'])
        self.assertEqual(gpt['jobs_scored'], 0)
        top = result['top_jobs'][0]
        self.assertEqual(top['agent_trace']['scoring_method'], 'heuristic')

    @patch('job_search.services.agents.gpt_scorer.get_sync_openai_client')
    def test_gpt_reasoning_replaces_why(self, mock_client_fn):
        from job_search.services.agents.orchestrator import run_agent_pipeline

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            'role_fit': 0.7,
            'skill_alignment': 0.6,
            'career_trajectory': 0.5,
            'culture_signals': 0.4,
            'overall_score': 0.6,
            'reasoning': 'Moderate fit due to partial skill overlap.',
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = run_agent_pipeline(
            Job.objects.all(),
            {'work_mode': 'REMOTE', 'employment_type': 'FULL_TIME', 'location': 'bangalore', 'company_size_preference': 'STARTUP'},
        )
        top = result['top_jobs'][0]
        self.assertIn('Moderate fit', top['why'])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, AGENT_MATCHING_ENABLED=True)
class MatchedJobsPaginationTests(TestCase):
    """Tests for returning all matched jobs with pagination and enriched details."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='paginate-user',
            email='paginate@example.com',
            password='password123',
        )
        self.client = APIClient()
        # Create 8 jobs to verify we get more than 5
        for i in range(1, 9):
            Job.objects.create(
                job_id=f'paginate-job-{i}',
                title=f'Developer Role {i}',
                company_name=f'Company {i}',
                location='bangalore, india',
                job_url=f'https://example.com/paginate-job-{i}',
                apply_url=f'https://example.com/apply-{i}',
                work_mode='REMOTE',
                employment_type='FULL_TIME',
                company_size='STARTUP',
                description=f'Description for role {i} with Python and Django.',
            )

    def _create_run(self):
        self.client.force_authenticate(user=self.user)
        payload = {
            'preferences': {
                'work_mode': 'REMOTE',
                'employment_type': 'FULL_TIME',
                'location': 'bangalore',
                'company_size_preference': 'STARTUP',
            },
        }
        response = self.client.post(reverse('matches-runs'), data=payload, format='json')
        return response.data['run_id']

    def test_returns_all_matched_jobs_not_just_5(self):
        run_id = self._create_run()
        detail_url = reverse('matches-run-detail', kwargs={'run_id': run_id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        if response.data['status'] == MatchingRun.STATUS_COMPLETED:
            self.assertGreater(response.data['matched_jobs']['count'], 5)

    def test_matched_jobs_has_pagination_structure(self):
        run_id = self._create_run()
        detail_url = reverse('matches-run-detail', kwargs={'run_id': run_id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        if response.data['status'] == MatchingRun.STATUS_COMPLETED:
            matched = response.data['matched_jobs']
            self.assertIn('count', matched)
            self.assertIn('next', matched)
            self.assertIn('previous', matched)
            self.assertIn('results', matched)

    def test_job_details_included_in_results(self):
        run_id = self._create_run()
        detail_url = reverse('matches-run-detail', kwargs={'run_id': run_id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        if response.data['status'] == MatchingRun.STATUS_COMPLETED:
            results = response.data['matched_jobs']['results']
            self.assertGreater(len(results), 0)
            first = results[0]
            self.assertIn('title', first)
            self.assertIn('company_name', first)
            self.assertIn('location', first)
            self.assertIn('work_mode', first)
            self.assertIn('apply_url', first)
            self.assertIn('selection_probability', first)
            self.assertIn('why', first)

    def test_min_score_filter(self):
        run_id = self._create_run()
        detail_url = reverse('matches-run-detail', kwargs={'run_id': run_id})
        # Get all results first
        all_response = self.client.get(detail_url)
        if all_response.data['status'] != MatchingRun.STATUS_COMPLETED:
            return
        total_all = all_response.data['matched_jobs']['count']
        # Filter with a high min_score
        filtered_response = self.client.get(detail_url, {'min_score': '0.99'})
        total_filtered = filtered_response.data['matched_jobs']['count']
        self.assertLessEqual(total_filtered, total_all)
