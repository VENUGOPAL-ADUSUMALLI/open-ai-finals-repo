from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from job_search.models import CompanyTaskJob, RecruiterJobPreference


class RecruiterJobPreferenceModelTests(TestCase):
    def setUp(self):
        self.job = CompanyTaskJob.objects.create(job_description='Test job')

    def _valid_payload(self):
        return {
            'job': self.job,
            'college_tiers': ['TIER_1', 'TIER_2'],
            'min_experience_years': '0.0',
            'max_experience_years': '2.0',
            'coding_platform_criteria': [
                {'platform': 'codeforces', 'metric': 'rating', 'operator': 'gte', 'value': 1400}
            ],
            'number_of_openings': 2,
        }

    def test_valid_preference_saves(self):
        pref = RecruiterJobPreference(**self._valid_payload())
        pref.full_clean()
        pref.save()
        self.assertEqual(pref.job_id, self.job.id)

    def test_invalid_college_tier_fails(self):
        payload = self._valid_payload()
        payload['college_tiers'] = ['TIER_4']
        pref = RecruiterJobPreference(**payload)
        with self.assertRaises(ValidationError):
            pref.full_clean()

    def test_empty_tiers_fails(self):
        payload = self._valid_payload()
        payload['college_tiers'] = []
        pref = RecruiterJobPreference(**payload)
        with self.assertRaises(ValidationError):
            pref.full_clean()

    def test_min_greater_than_max_fails(self):
        payload = self._valid_payload()
        payload['min_experience_years'] = '3.0'
        payload['max_experience_years'] = '2.0'
        pref = RecruiterJobPreference(**payload)
        with self.assertRaises(ValidationError):
            pref.full_clean()

    def test_openings_zero_fails(self):
        payload = self._valid_payload()
        payload['number_of_openings'] = 0
        pref = RecruiterJobPreference(**payload)
        with self.assertRaises(ValidationError):
            pref.full_clean()

    def test_malformed_coding_criteria_fails(self):
        payload = self._valid_payload()
        payload['coding_platform_criteria'] = [{'platform': 'codeforces'}]
        pref = RecruiterJobPreference(**payload)
        with self.assertRaises(ValidationError):
            pref.full_clean()


class RecruiterJobPreferenceApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='pref-user',
            email='pref@example.com',
            password='password123',
        )
        self.job = CompanyTaskJob.objects.create(job_description='Test job')
        self.url = reverse('company-task-job-preference-upsert')

    def _payload(self):
        return {
            'job_id': self.job.id,
            'college_tiers': ['TIER_1', 'TIER_2'],
            'min_experience_years': 0,
            'max_experience_years': 2,
            'number_of_openings': 3,
            'coding_platform_criteria': [
                {'platform': 'codeforces', 'metric': 'rating', 'operator': 'gte', 'value': 1400}
            ],
        }

    def test_unauthenticated_returns_401(self):
        response = self.client.post(self.url, data=self._payload(), format='json')
        self.assertEqual(response.status_code, 401)

    def test_missing_required_fields_returns_400(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data={'job_id': self.job.id}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_invalid_job_id_type_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self._payload()
        payload['job_id'] = 'abc'
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)

    def test_job_not_found_returns_404(self):
        self.client.force_authenticate(user=self.user)
        payload = self._payload()
        payload['job_id'] = 999999
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 404)

    def test_create_preference_returns_201(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, data=self._payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['number_of_openings'], 3)

    def test_repeat_post_updates_and_returns_200(self):
        self.client.force_authenticate(user=self.user)
        self.client.post(self.url, data=self._payload(), format='json')

        payload = self._payload()
        payload['number_of_openings'] = 5
        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['number_of_openings'], 5)

    def test_invalid_coding_operator_returns_400(self):
        self.client.force_authenticate(user=self.user)
        payload = self._payload()
        payload['coding_platform_criteria'] = [
            {'platform': 'codeforces', 'metric': 'rating', 'operator': 'gt', 'value': 1400}
        ]
        response = self.client.post(self.url, data=payload, format='json')
        self.assertEqual(response.status_code, 400)
