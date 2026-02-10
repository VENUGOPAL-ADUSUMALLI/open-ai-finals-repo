from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from job_search.models import (
    CandidateRankingResult,
    CandidateRankingRun,
    CompanyTaskJob,
    JobCandidate,
    RecruiterJobPreference,
)


class CandidateRankingApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='rank-user',
            email='rank@example.com',
            password='password123',
        )
        self.job = CompanyTaskJob.objects.create(job_description='Backend role')
        RecruiterJobPreference.objects.create(
            job=self.job,
            college_tiers=['TIER_1', 'TIER_2'],
            min_experience_years='0.0',
            max_experience_years='2.0',
            coding_platform_criteria=[],
            number_of_openings=2,
        )
        JobCandidate.objects.create(
            job=self.job,
            name='Alice',
            email='alice@example.com',
            resume_data='{}',
        )

        self.create_url = reverse('candidate-ranking-run-create')
        self.list_url = reverse('candidate-ranking-run-list', kwargs={'job_id': self.job.id})

    def test_create_requires_auth(self):
        response = self.client.post(self.create_url, data={'job_id': self.job.id}, format='json')
        self.assertEqual(response.status_code, 401)

    @patch('job_search.views.run_candidate_ranking_pipeline.delay')
    def test_create_returns_202(self, delay_mock):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            self.create_url,
            data={'job_id': self.job.id, 'batch_size': 10, 'force_recompute': True},
            format='json',
        )
        self.assertEqual(response.status_code, 202)
        self.assertIn('run_id', response.data)
        delay_mock.assert_called_once()

    @patch('job_search.views.run_candidate_ranking_pipeline.delay')
    def test_create_reuses_existing_completed_run(self, delay_mock):
        self.client.force_authenticate(user=self.user)
        existing = CandidateRankingRun.objects.create(
            job=self.job,
            status=CandidateRankingRun.STATUS_COMPLETED,
            total_candidates=1,
            processed_candidates=1,
            shortlisted_count=1,
        )
        response = self.client.post(
            self.create_url,
            data={'job_id': self.job.id, 'batch_size': 10, 'force_recompute': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['run_id'], str(existing.id))
        delay_mock.assert_not_called()

    def test_list_runs(self):
        self.client.force_authenticate(user=self.user)
        CandidateRankingRun.objects.create(job=self.job, status=CandidateRankingRun.STATUS_PENDING)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data['count'], 1)

    def test_run_detail_returns_results(self):
        self.client.force_authenticate(user=self.user)
        run = CandidateRankingRun.objects.create(job=self.job, status=CandidateRankingRun.STATUS_COMPLETED)
        candidate = JobCandidate.objects.filter(job=self.job).first()
        CandidateRankingResult.objects.create(
            run=run,
            candidate=candidate,
            rank=1,
            is_shortlisted=True,
            passes_hard_filter=True,
            final_score='88.10',
            sub_scores={'education_fit': 90},
            filter_reasons=[],
            summary='Strong candidate',
        )
        detail_url = reverse('candidate-ranking-run-detail', kwargs={'run_id': run.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['rank'], 1)


class RecruiterPreferenceValidationTests(TestCase):
    def setUp(self):
        self.job = CompanyTaskJob.objects.create(job_description='Validation role')

    def test_invalid_operator_rejected_by_model(self):
        pref = RecruiterJobPreference(
            job=self.job,
            college_tiers=['TIER_1'],
            min_experience_years='0.0',
            max_experience_years='3.0',
            coding_platform_criteria=[
                {'platform': 'codeforces', 'metric': 'rating', 'operator': 'gt', 'value': 1500}
            ],
            number_of_openings=1,
        )
        with self.assertRaises(Exception):
            pref.full_clean()
