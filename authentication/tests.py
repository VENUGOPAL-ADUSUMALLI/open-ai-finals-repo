from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from authentication.services.resume.models import ParsedResume, PersonalInfo


class ResumeParseApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="resume-user",
            email="resume@example.com",
            password="password123",
            phone_number="9999999999",
            address="Already Set Address",
            location="Existing City",
        )
        self.url = reverse("authentication:parse_resume_v1")

    def test_unauthorized_returns_401(self):
        uploaded = SimpleUploadedFile("resume.pdf", b"dummy-data", content_type="application/pdf")
        response = self.client.post(self.url, data={"resume_file": uploaded}, format="multipart")
        self.assertEqual(response.status_code, 401)

    def test_invalid_extension_returns_400(self):
        self.client.force_authenticate(user=self.user)
        uploaded = SimpleUploadedFile("resume.txt", b"dummy-data", content_type="text/plain")
        response = self.client.post(self.url, data={"resume_file": uploaded}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "INVALID_REQUEST")

    @patch("authentication.interactors.resume_parser_interactor.LLMParser.parse", new_callable=AsyncMock)
    @patch("authentication.interactors.resume_parser_interactor.TextExtractor.extract_text", new_callable=AsyncMock)
    def test_success_returns_minimal_payload_and_saves_metadata(self, extract_mock, parse_mock):
        self.client.force_authenticate(user=self.user)
        extract_mock.return_value = ("Name: John Doe\nPython", "pdf")
        parse_mock.return_value = (
            ParsedResume(
                personal_info=PersonalInfo(
                    full_name="John Doe",
                    email="john@doe.com",
                    phone="8888888888",
                    address="Bangalore, India",
                    linkedin="https://linkedin.com/in/johndoe",
                    github="https://github.com/johndoe",
                    portfolio="https://johndoe.dev",
                ),
                summary="Backend developer",
                experience=[{"company": "Acme"}],
                education=[{"institution": "ABC"}],
                skills=[{"category": "Backend", "skills": ["Python"]}],
                certifications=[],
                projects=[],
                languages=[],
            ),
            0.82,
        )

        uploaded = SimpleUploadedFile("resume.pdf", b"dummy-data", content_type="application/pdf")
        response = self.client.post(self.url, data={"resume_file": uploaded}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"success": True})

        self.user.refresh_from_db()
        self.assertIn("personal_info", self.user.resume_metadata)
        self.assertIn("parsing_metadata", self.user.resume_metadata)
        self.assertIsNotNone(self.user.resume_last_parsed_at)

    @patch("authentication.interactors.resume_parser_interactor.LLMParser.parse", new_callable=AsyncMock)
    @patch("authentication.interactors.resume_parser_interactor.TextExtractor.extract_text", new_callable=AsyncMock)
    def test_existing_profile_fields_are_not_overwritten(self, extract_mock, parse_mock):
        self.client.force_authenticate(user=self.user)
        extract_mock.return_value = ("Name: Jane Doe", "pdf")
        parse_mock.return_value = (
            ParsedResume(
                personal_info=PersonalInfo(
                    full_name="Jane Doe",
                    phone="7777777777",
                    address="New City, India",
                ),
            ),
            0.71,
        )

        uploaded = SimpleUploadedFile("resume.pdf", b"dummy-data", content_type="application/pdf")
        response = self.client.post(self.url, data={"resume_file": uploaded}, format="multipart")

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.phone_number, "9999999999")
        self.assertEqual(self.user.address, "Already Set Address")
        self.assertEqual(self.user.location, "Existing City")

    @patch("authentication.interactors.resume_parser_interactor.TextExtractor.extract_text", new_callable=AsyncMock)
    def test_no_text_extracted_returns_400(self, extract_mock):
        self.client.force_authenticate(user=self.user)
        extract_mock.return_value = ("", "pdf")

        uploaded = SimpleUploadedFile("resume.pdf", b"dummy-data", content_type="application/pdf")
        response = self.client.post(self.url, data={"resume_file": uploaded}, format="multipart")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error_code"], "NO_TEXT_EXTRACTED")
