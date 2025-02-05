# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import time

from dash.orgs.models import Org
from dash.orgs.tasks import org_task
from dash.utils.sync import SyncOutcome

from django.core.cache import cache
from django.utils import timezone

from celery.utils.log import get_task_logger

from ureport.celery import app
from ureport.contacts.models import Contact
from ureport.utils import datetime_to_json_date, update_cache_org_contact_counts

logger = get_task_logger(__name__)


@app.task(name="contacts.rebuild_contacts_counts")
def rebuild_contacts_counts():
    orgs = Org.objects.filter(is_active=True)
    for org in orgs:
        Contact.recalculate_reporters_stats(org)


@org_task("update-org-contact-counts", 60 * 20)
def update_org_contact_count(org, ignored_since, ignored_until):
    update_cache_org_contact_counts(org)


@org_task("contact-pull", 60 * 60 * 12)
def pull_contacts(org, ignored_since, ignored_until):
    """
    Fetches updated contacts from RapidPro and updates local contacts accordingly
    """
    # from ureport.contacts.models import ReportersCounter

    results = dict()

    backends = org.backends.filter(is_active=True)
    for backend_obj in backends:
        backend = org.get_backend(backend_slug=backend_obj.slug)

        last_fetch_date_key = Contact.CONTACT_LAST_FETCHED_CACHE_KEY % (org.pk, backend_obj.slug)

        until = datetime_to_json_date(timezone.now())
        since = cache.get(last_fetch_date_key, None)

        if not since:
            logger.info("First time run for org #%d. Will sync all contacts" % org.pk)

        start = time.time()

        backend_fields_results = backend.pull_fields(org)

        fields_created = backend_fields_results[SyncOutcome.created]
        fields_updated = backend_fields_results[SyncOutcome.updated]
        fields_deleted = backend_fields_results[SyncOutcome.deleted]
        ignored = backend_fields_results[SyncOutcome.ignored]

        logger.info(
            "Fetched contact fields for org #%d. "
            "Created %s, Updated %s, Deleted %d, Ignored %d"
            % (org.pk, fields_created, fields_updated, fields_deleted, ignored)
        )
        logger.info("Fetch fields for org #%d took %ss" % (org.pk, time.time() - start))

        start_boundaries = time.time()

        backend_boundaries_results = backend.pull_boundaries(org)

        boundaries_created = backend_boundaries_results[SyncOutcome.created]
        boundaries_updated = backend_boundaries_results[SyncOutcome.updated]
        boundaries_deleted = backend_boundaries_results[SyncOutcome.deleted]
        ignored = backend_boundaries_results[SyncOutcome.ignored]

        logger.info(
            "Fetched boundaries for org #%d. "
            "Created %s, Updated %s, Deleted %d, Ignored %d"
            % (org.pk, boundaries_created, boundaries_updated, boundaries_deleted, ignored)
        )

        logger.info("Fetch boundaries for org #%d took %ss" % (org.pk, time.time() - start_boundaries))
        start_contacts = time.time()

        backend_contact_results, resume_cursor = backend.pull_contacts(org, since, until)

        contacts_created = backend_contact_results[SyncOutcome.created]
        contacts_updated = backend_contact_results[SyncOutcome.updated]
        contacts_deleted = backend_contact_results[SyncOutcome.deleted]
        ignored = backend_contact_results[SyncOutcome.ignored]

        cache.set(last_fetch_date_key, until, None)

        logger.info(
            "Fetched contacts for org #%d. "
            "Created %s, Updated %s, Deleted %d, Ignored %d"
            % (org.pk, contacts_created, contacts_updated, contacts_deleted, ignored)
        )

        logger.info("Fetch contacts for org #%d took %ss" % (org.pk, time.time() - start_contacts))

        # Squash reporters counts
        # ReportersCounter.squash_counts()

        results[backend_obj.slug] = {
            "fields": {"created": fields_created, "updated": fields_updated, "deleted": fields_deleted},
            "boundaries": {
                "created": boundaries_created,
                "updated": boundaries_updated,
                "deleted": boundaries_deleted,
            },
            "contacts": {"created": contacts_created, "updated": contacts_updated, "deleted": contacts_deleted},
        }

    return results
