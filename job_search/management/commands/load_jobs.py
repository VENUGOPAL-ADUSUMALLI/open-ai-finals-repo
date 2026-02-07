import json
import re
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from job_search.models import Job


class Command(BaseCommand):
    help = 'Load jobs from a LinkedIn scraper JSON file'

    def add_arguments(self, parser):
        parser.add_argument(
            'json_file',
            type=str,
            help='Path to the JSON file containing job data'
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing jobs instead of skipping them'
        )

    def handle(self, *args, **options):
        json_file = options['json_file']
        update_existing = options['update']

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                jobs_data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'File "{json_file}" not found')
        except json.JSONDecodeError as e:
            raise CommandError(f'Invalid JSON file: {e}')

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for job_data in jobs_data:
            job_id = job_data.get('id')
            if not job_id:
                self.stdout.write(self.style.WARNING('Skipping job with no ID'))
                skipped_count += 1
                continue

            # Parse the published date
            published_at = None
            if job_data.get('publishedAt'):
                try:
                    published_at = datetime.strptime(
                        job_data['publishedAt'], '%Y-%m-%d'
                    ).date()
                except ValueError:
                    pass

            job_fields = {
                'title': job_data.get('title', ''),
                'description': job_data.get('description', ''),
                'description_html': job_data.get('descriptionHtml', ''),
                'company_name': job_data.get('companyName', ''),
                'company_id': job_data.get('companyId', ''),
                'company_url': job_data.get('companyUrl', ''),
                'location': job_data.get('location', ''),
                'contract_type': job_data.get('contractType', ''),
                'experience_level': job_data.get('experienceLevel', ''),
                'work_type': job_data.get('workType', ''),
                'sector': job_data.get('sector', ''),
                'employment_type': self._map_employment_type(job_data.get('contractType', '')),
                'work_mode': self._map_work_mode(job_data),
                'salary': job_data.get('salary', ''),
                'benefits': job_data.get('benefits', ''),
                'job_url': job_data.get('jobUrl', ''),
                'apply_url': job_data.get('applyUrl', ''),
                'apply_type': job_data.get('applyType', ''),
                'applications_count': job_data.get('applicationsCount', ''),
                'published_at': published_at,
                'posted_time': job_data.get('postedTime', ''),
                'poster_profile_url': job_data.get('posterProfileUrl', ''),
                'poster_full_name': job_data.get('posterFullName', ''),
            }
            stipend_min, stipend_max, stipend_currency = self._parse_stipend_range(
                job_data.get('salary', '')
            )
            job_fields.update(
                {
                    'stipend_min': stipend_min,
                    'stipend_max': stipend_max,
                    'stipend_currency': stipend_currency,
                }
            )

            try:
                job, created = Job.objects.get_or_create(
                    job_id=job_id,
                    defaults=job_fields
                )

                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Created: {job.title} at {job.company_name}')
                    )
                elif update_existing:
                    for field, value in job_fields.items():
                        setattr(job, field, value)
                    job.save()
                    updated_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'Updated: {job.title} at {job.company_name}')
                    )
                else:
                    skipped_count += 1
                    self.stdout.write(
                        f'Skipped (exists): {job.title} at {job.company_name}'
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error processing job {job_id}: {e}')
                )
                skipped_count += 1

        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS(f'Created: {created_count} jobs'))
        self.stdout.write(self.style.WARNING(f'Updated: {updated_count} jobs'))
        self.stdout.write(f'Skipped: {skipped_count} jobs')
        self.stdout.write(f'Total processed: {len(jobs_data)} jobs')

    def _map_employment_type(self, contract_type):
        normalized = (contract_type or '').strip().lower()
        mapping = {
            'full-time': 'FULL_TIME',
            'part-time': 'PART_TIME',
            'contract': 'CONTRACT',
            'temporary': 'TEMPORARY',
            'internship': 'INTERNSHIP',
            'freelance': 'FREELANCE',
        }
        return mapping.get(normalized)

    def _map_work_mode(self, job_data):
        signals = ' '.join(
            [
                str(job_data.get('title', '')),
                str(job_data.get('location', '')),
                str(job_data.get('description', '')),
            ]
        ).lower()

        if 'hybrid' in signals:
            return 'HYBRID'

        remote_keywords = [
            'remote',
            'work from home',
            'wfh',
            'anywhere in india',
        ]
        if any(keyword in signals for keyword in remote_keywords):
            return 'REMOTE'

        return 'ONSITE'

    def _parse_stipend_range(self, salary_text):
        if not salary_text:
            return None, None, None

        numbers = re.findall(r'\d[\d,]*(?:\.\d+)?', salary_text)
        if not numbers:
            return None, None, None

        values = [float(number.replace(',', '')) for number in numbers]
        if len(values) == 1:
            stipend_min = values[0]
            stipend_max = values[0]
        else:
            stipend_min = min(values[0], values[1])
            stipend_max = max(values[0], values[1])

        currency = 'INR' if ('₹' in salary_text or 'inr' in salary_text.lower()) else None
        return stipend_min, stipend_max, currency
