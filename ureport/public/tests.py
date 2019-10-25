# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

import json
from datetime import timedelta

import mock
import pytz
from dash.categories.models import Category
from dash.dashblocks.models import DashBlock, DashBlockType
from dash.orgs.models import Org, OrgBackend
from dash.stories.models import Story, StoryImage
from six.moves.urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils.http import urlquote

from ureport.countries.models import CountryAlias
from ureport.locations.models import Boundary
from ureport.news.models import NewsItem, Video
from ureport.polls.models import PollQuestion
from ureport.tests import MockTembaClient, UreportJobsTest, UreportTest


class PublicTest(UreportTest):
    def setUp(self):
        super(PublicTest, self).setUp()
        self.uganda = self.create_org("uganda", pytz.timezone("Africa/Kampala"), self.admin)
        self.nigeria = self.create_org("nigeria", pytz.timezone("Africa/Lagos"), self.admin)

        self.health_uganda = Category.objects.create(
            org=self.uganda, name="Health", created_by=self.admin, modified_by=self.admin
        )

        self.education_nigeria = Category.objects.create(
            org=self.nigeria, name="Education", created_by=self.admin, modified_by=self.admin
        )

    def test_org_config_fields(self):
        edit_url = reverse("orgs.org_edit")

        # make sure we only have one backend configured
        self.nigeria.backends.exclude(slug="rapidpro").delete()

        response = self.client.get(edit_url, SERVER_NAME="nigeria.ureport.io")
        self.assertLoginRedirect(response)

        self.login(self.admin)
        response = self.client.get(edit_url, SERVER_NAME="nigeria.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 39)

        self.login(self.superuser)
        response = self.client.get(edit_url, SERVER_NAME="nigeria.ureport.io")
        self.assertTrue("form" in response.context)
        self.assertEqual(len(response.context["form"].fields), 60)

    def test_count(self):
        count_url = reverse("public.count")

        response = self.client.get(count_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertTrue("count" in response.context)
        self.assertEqual(response.context["count"], self.nigeria.get_reporters_count())
        self.assertEqual(response.context["view"].template_name, "public/count")

        response = self.client.get(count_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org"], self.uganda)
        self.assertTrue("count" in response.context)
        self.assertEqual(response.context["count"], self.uganda.get_reporters_count())
        self.assertEqual(response.context["view"].template_name, "public/count")

    def test_chooser(self):
        chooser_url = reverse("public.home")

        settings_sites_count = len(list(getattr(settings, "COUNTRY_FLAGS_SITES", [])))

        # remove all orgs
        OrgBackend.objects.all().delete()
        Category.objects.all().delete()
        Org.objects.all().delete()

        response = self.client.get(chooser_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["orgs"]), settings_sites_count)

        # if no empty subdomain org give a tempate response
        response = self.client.get(chooser_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue("orgs" in response.context)
        self.assertContains(response, "welcome-flags")

        # if we have empty subdomain org we should show its index
        self.global_org = Org.objects.create(
            subdomain="", name="global", created_by=self.admin, modified_by=self.admin
        )
        response = self.client.get(chooser_url, SERVER_NAME="blabla.ureport.io")
        self.assertEqual(response.status_code, 301)
        response = self.client.get(chooser_url, follow=True, SERVER_NAME="blabla.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertFalse("orgs" in response.context)
        self.assertContains(response, "welcome-flags")

        self.global_org.set_config("common.is_global", True)

        # if the empty org in global the template tag should show the flags
        response = self.client.get(chooser_url, SERVER_NAME="blabla.ureport.io")
        self.assertEqual(response.status_code, 301)
        response = self.client.get(chooser_url, follow=True, SERVER_NAME="blabla.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertFalse("orgs" in response.context)
        self.assertContains(response, "welcome-flags")

        self.assertEqual(response.request["SERVER_NAME"], "ureport.io")
        self.assertEqual(response.request["wsgi.url_scheme"], "http")

        with self.settings(SESSION_COOKIE_SECURE=True):
            response = self.client.get(chooser_url, follow=True, SERVER_NAME="blabla.ureport.io")
            self.assertEqual(response.status_code, 200)

            self.assertEqual(response.request["SERVER_NAME"], "ureport.io")
            self.assertEqual(response.request["wsgi.url_scheme"], "http")

    def test_has_better_domain_processors(self):
        home_url = reverse("public.index")

        # using subdomain wihout domain on org, login is shown and indexing should be allow
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertNotContains(response, "<meta name='robots' content='noindex'")
        self.assertContains(response, "nigeria.ureport.io/users/login/")

        self.nigeria.domain = "ureport.ng"
        self.nigeria.save()

        # using subdomain without domain on org, indexing is disallowed but login should be shown
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertContains(response, "<meta name='robots' content='noindex'")
        self.assertContains(response, "nigeria.ureport.io/users/login/")

        # using custom domain, login is hidden  and indexing should be allow
        response = self.client.get(home_url, HTTP_HOST="ureport.ng")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertNotContains(response, "<meta name='robots' content='noindex'")
        self.assertNotContains(response, "nigeria.ureport.io/users/login/")

    def test_org_lang_params_processors(self):
        home_url = reverse("public.index")

        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertFalse(response.context["is_rtl_org"])
        self.assertEqual(response.context["org_lang"], "en_US")

        self.nigeria.language = "ar"
        self.nigeria.save()

        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertTrue(response.context["is_rtl_org"])
        self.assertEqual(response.context["org_lang"], "ar_AR")

        self.nigeria.language = "es"
        self.nigeria.save()

        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertFalse(response.context["is_rtl_org"])
        self.assertEqual(response.context["org_lang"], "es_ES")

    def test_set_story_widget_url(self):
        home_url = reverse("public.index")
        response = self.client.get(home_url, HTTP_HOST="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertTrue(response.context["story_widget_url"])

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    @mock.patch("django.core.cache.cache.get")
    def test_index(self, mock_cache_get):
        mock_cache_get.return_value = None
        home_url = reverse("public.index")

        response = self.client.get(home_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/index.html")

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertIsNone(response.context["latest_poll"])
        self.assertFalse("trending_words" in response.context)
        self.assertTrue("recent_polls" in response.context)
        self.assertTrue("gender_stats" in response.context)
        self.assertTrue("age_stats" in response.context)
        self.assertTrue("reporters" in response.context)
        self.assertTrue("most_active_regions" in response.context)

        self.assertFalse(response.context["recent_polls"])

        self.assertFalse(response.context["stories"])
        self.assertFalse(response.context["videos"])
        self.assertFalse(response.context["news"])

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertIsNone(response.context["latest_poll"])
        self.assertFalse("trending_words" in response.context)
        self.assertTrue("recent_polls" in response.context)
        self.assertFalse(response.context["recent_polls"])

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(poll1, response.context["latest_poll"])
        self.assertTrue("trending_words" in response.context)
        self.assertTrue("recent_polls" in response.context)
        self.assertFalse(response.context["recent_polls"])

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll2, title="question poll 2", ruleset_uuid="uuid-202", created_by=self.admin, modified_by=self.admin
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(poll1, response.context["latest_poll"])
        self.assertTrue("trending_words" in response.context)
        self.assertTrue("recent_polls" in response.context)
        self.assertFalse(response.context["recent_polls"])

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll3, title="question poll 3", ruleset_uuid="uuid-303", created_by=self.admin, modified_by=self.admin
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(poll3, response.context["latest_poll"])
        self.assertTrue("trending_words" in response.context)
        self.assertTrue("recent_polls" in response.context)
        self.assertTrue(response.context["recent_polls"])
        self.assertTrue(poll1 in response.context["recent_polls"])

        story1 = Story.objects.create(
            title="story 1",
            featured=True,
            content="body contents 1",
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["stories"])
        self.assertTrue(story1 in response.context["stories"])

        story2 = Story.objects.create(
            title="story 2",
            featured=True,
            content="body contents 2",
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["stories"])
        self.assertTrue(story1 in response.context["stories"])

        story3 = Story.objects.create(
            title="story 3",
            featured=False,
            content="body contents 3",
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["stories"])
        self.assertTrue(story1 in response.context["stories"])

        story4 = Story.objects.create(
            title="story 4",
            featured=True,
            content="body contents 4",
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["stories"])
        self.assertFalse(story2 in response.context["stories"])
        self.assertFalse(story3 in response.context["stories"])
        self.assertEqual(response.context["stories"][0].pk, story4.pk)
        self.assertEqual(response.context["stories"][1].pk, story1.pk)

        story4.featured = False
        story4.save()

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        video1 = Video.objects.create(
            title="video 1",
            video_id="video_1",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 in response.context["videos"])

        video2 = Video.objects.create(
            title="video 2",
            video_id="video_2",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 in response.context["videos"])
        self.assertTrue(video2 not in response.context["videos"])

        video3 = Video.objects.create(
            title="video 3",
            video_id="video_3",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 in response.context["videos"])
        self.assertTrue(video2 not in response.context["videos"])
        self.assertTrue(video3 in response.context["videos"])

        video1.is_active = False
        video1.save()

        response = self.client.get(home_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 not in response.context["videos"])
        self.assertTrue(video2 not in response.context["videos"])
        self.assertTrue(video3 in response.context["videos"])

        self.nigeria.set_config("common.custom_html", "<div>INCLUDE MY CUSTOM HTML</div>")
        response = self.client.get(home_url, SERVER_NAME="nigeria.ureport.io")
        self.assertContains(response, "<div>INCLUDE MY CUSTOM HTML</div>")

    def test_additional_menu(self):
        additional_menu_url = reverse("public.added")
        response = self.client.get(additional_menu_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/added/")
        self.assertEqual(response.context["org"], self.nigeria)

    def test_about(self):
        about_url = reverse("public.about")

        response = self.client.get(about_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/about.html")

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        video1 = Video.objects.create(
            title="video 1",
            video_id="video_1",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 in response.context["videos"])

        video2 = Video.objects.create(
            title="video 2",
            video_id="video_2",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 in response.context["videos"])
        self.assertTrue(video2 not in response.context["videos"])

        video3 = Video.objects.create(
            title="video 3",
            video_id="video_3",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 in response.context["videos"])
        self.assertTrue(video2 not in response.context["videos"])
        self.assertTrue(video3 in response.context["videos"])

        video1.is_active = False
        video1.save()

        response = self.client.get(about_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/about/")
        self.assertEqual(response.context["org"], self.uganda)

        self.assertTrue(response.context["videos"])
        self.assertTrue(video1 not in response.context["videos"])
        self.assertTrue(video2 not in response.context["videos"])
        self.assertTrue(video3 in response.context["videos"])

    def test_join_engage(self):
        join_engage_url = reverse("public.join")

        response = self.client.get(join_engage_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/join/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/join_engage.html")

        response = self.client.get(join_engage_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/join/")
        self.assertEqual(response.context["org"], self.uganda)

        # add shortcode and a join dashblock
        self.uganda.set_config("common.shortcode", "3000")
        join_dashblock_type = DashBlockType.objects.filter(slug="join_engage").first()

        DashBlock.objects.create(
            title="Join",
            content="Join",
            dashblock_type=join_dashblock_type,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(join_engage_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/join/")
        self.assertEqual(response.context["org"], self.uganda)
        self.assertContains(response, "All U-Report services (all msg on 3000) are free.")

    def test_ureporters(self):
        ureporters_url = reverse("public.ureporters")

        response = self.client.get(ureporters_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/ureporters/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["view"].template_name, "public/ureporters.html")

        self.assertTrue("months" in response.context)
        self.assertTrue("gender_stats" in response.context)
        self.assertTrue("age_stats" in response.context)
        self.assertTrue("registration_stats" in response.context)
        self.assertTrue("occupation_stats" in response.context)

        self.assertTrue("show_maps" in response.context)
        self.assertTrue("district_zoom" in response.context)
        self.assertTrue("ward_zoom" in response.context)
        self.assertTrue("show_age_stats" in response.context)
        self.assertTrue("show_gender_stats" in response.context)
        self.assertTrue("show_occupation_stats" in response.context)

        response = self.client.get(ureporters_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/ureporters/")
        self.assertEqual(response.context["org"], self.uganda)

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_polls_list(self):
        polls_url = reverse("public.polls")

        response = self.client.get(polls_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/polls/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["tab"], "list")
        self.assertEqual(response.context["view"].template_name, "public/polls.html")
        self.assertFalse(response.context["latest_poll"])
        self.assertFalse(response.context["polls"])
        self.assertFalse(response.context["related_stories"])

        self.assertEqual(len(response.context["categories"]), 1)
        self.assertTrue(self.education_nigeria in response.context["categories"])
        self.assertTrue(self.health_uganda not in response.context["categories"])

        education_uganda = Category.objects.create(
            org=self.uganda, name="Education", created_by=self.admin, modified_by=self.admin
        )

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        poll2 = self.create_poll(self.uganda, "Poll 2", "uuid-2", education_uganda, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll2, title="question poll 2", ruleset_uuid="uuid-102", created_by=self.admin, modified_by=self.admin
        )

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll3, title="question poll 3", ruleset_uuid="uuid-103", created_by=self.admin, modified_by=self.admin
        )

        poll4 = self.create_poll(self.nigeria, "Poll 4", "uuid-4", self.education_nigeria, self.admin, has_synced=True)

        PollQuestion.objects.create(
            poll=poll4, title="question poll 4", ruleset_uuid="uuid-104", created_by=self.admin, modified_by=self.admin
        )

        response = self.client.get(polls_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/polls/")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(response.context["tab"], "list")
        self.assertEqual(response.context["view"].template_name, "public/polls.html")
        self.assertEqual(response.context["latest_poll"], poll4)

        self.assertEqual(len(response.context["categories"]), 1)
        self.assertTrue(self.education_nigeria in response.context["categories"])
        self.assertTrue(self.health_uganda not in response.context["categories"])
        self.assertTrue(education_uganda not in response.context["categories"])

        self.assertEqual(len(response.context["polls"]), 1)
        self.assertTrue(poll4 in response.context["polls"])
        self.assertTrue(poll1 not in response.context["polls"])
        self.assertTrue(poll2 not in response.context["polls"])
        self.assertTrue(poll3 not in response.context["polls"])

        self.assertFalse(response.context["related_stories"])

        story1 = Story.objects.create(
            title="story 1",
            content="body contents 1",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story2 = Story.objects.create(
            title="story 2",
            content="body contents 2",
            category=education_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story3 = Story.objects.create(
            title="story 3",
            content="body contents 3",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story4 = Story.objects.create(
            title="story 4",
            content="body contents 4",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(polls_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(len(response.context["related_stories"]), 1)
        self.assertTrue(story4 in response.context["related_stories"])
        self.assertTrue(story1 not in response.context["related_stories"])
        self.assertTrue(story2 not in response.context["related_stories"])
        self.assertTrue(story3 not in response.context["related_stories"])

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.request["PATH_INFO"], "/polls/")
        self.assertEqual(response.context["org"], self.uganda)
        self.assertEqual(response.context["latest_poll"], poll3)

        self.assertEqual(len(response.context["categories"]), 2)
        self.assertTrue(self.education_nigeria not in response.context["categories"])
        self.assertTrue(self.health_uganda in response.context["categories"])
        self.assertTrue(education_uganda in response.context["categories"])
        self.assertEqual(response.context["categories"][0], education_uganda)
        self.assertEqual(response.context["categories"][1], self.health_uganda)

        self.assertEqual(len(response.context["polls"]), 3)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 in response.context["polls"])
        self.assertTrue(poll3 in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll3)
        self.assertEqual(response.context["polls"][1], poll2)
        self.assertEqual(response.context["polls"][2], poll1)

        self.assertEqual(len(response.context["related_stories"]), 2)
        self.assertTrue(story4 not in response.context["related_stories"])
        self.assertTrue(story1 in response.context["related_stories"])
        self.assertTrue(story2 not in response.context["related_stories"])
        self.assertTrue(story3 in response.context["related_stories"])
        self.assertEqual(response.context["related_stories"][0], story3)
        self.assertEqual(response.context["related_stories"][1], story1)

        story1.featured = True
        story1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["related_stories"]), 2)
        self.assertTrue(story4 not in response.context["related_stories"])
        self.assertTrue(story1 in response.context["related_stories"])
        self.assertTrue(story2 not in response.context["related_stories"])
        self.assertTrue(story3 in response.context["related_stories"])
        self.assertEqual(response.context["related_stories"][0], story1)
        self.assertEqual(response.context["related_stories"][1], story3)

        story1.is_active = False
        story1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(len(response.context["related_stories"]), 1)
        self.assertTrue(story4 not in response.context["related_stories"])
        self.assertTrue(story1 not in response.context["related_stories"])
        self.assertTrue(story2 not in response.context["related_stories"])
        self.assertTrue(story3 in response.context["related_stories"])
        self.assertEqual(response.context["related_stories"][0], story3)

        poll1.is_featured = True
        poll1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["latest_poll"], poll1)

        self.assertEqual(len(response.context["categories"]), 2)
        self.assertTrue(self.education_nigeria not in response.context["categories"])
        self.assertTrue(self.health_uganda in response.context["categories"])
        self.assertTrue(education_uganda in response.context["categories"])
        self.assertEqual(response.context["categories"][0], education_uganda)
        self.assertEqual(response.context["categories"][1], self.health_uganda)

        self.assertEqual(len(response.context["polls"]), 3)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 in response.context["polls"])
        self.assertTrue(poll3 in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll3)
        self.assertEqual(response.context["polls"][1], poll2)
        self.assertEqual(response.context["polls"][2], poll1)

        poll1.poll_date = poll3.poll_date + timedelta(days=1)
        poll1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["polls"][0], poll1)
        self.assertEqual(response.context["polls"][1], poll3)
        self.assertEqual(response.context["polls"][2], poll2)

        poll1.poll_date = poll1.created_on
        poll1.save()

        poll3.is_active = False
        poll3.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["latest_poll"], poll1)

        self.assertEqual(len(response.context["polls"]), 2)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 in response.context["polls"])
        self.assertTrue(poll3 not in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll2)
        self.assertEqual(response.context["polls"][1], poll1)

        education_uganda.is_active = False
        education_uganda.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["latest_poll"], poll1)

        self.assertEqual(len(response.context["polls"]), 1)
        self.assertTrue(poll4 not in response.context["polls"])
        self.assertTrue(poll1 in response.context["polls"])
        self.assertTrue(poll2 not in response.context["polls"])
        self.assertTrue(poll3 not in response.context["polls"])
        self.assertEqual(response.context["polls"][0], poll1)

        poll1.has_synced = False
        poll1.save()

        response = self.client.get(polls_url, SERVER_NAME="uganda.ureport.io")
        self.assertFalse(response.context["polls"])

    @mock.patch("dash.orgs.models.TembaClient", MockTembaClient)
    def test_polls_read(self):
        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)

        uganda_poll_read_url = reverse("public.poll_read", args=[poll1.pk])
        nigeria_poll_read_url = reverse("public.poll_read", args=[poll2.pk])

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll1.has_synced = True
        poll1.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["object"], poll1)

        response = self.client.get(nigeria_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll2.has_synced = True
        poll2.save()

        response = self.client.get(nigeria_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll1.is_active = False
        poll1.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        poll1.is_active = False
        poll1.save()

        response = self.client.get(uganda_poll_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

    def test_boundary_view(self):
        country_boundary_url = reverse("public.boundaries")
        state_boundary_url = reverse("public.boundaries", args=["R23456"])

        self.country = Boundary.objects.create(
            org=self.uganda,
            osm_id="R12345",
            name="Uganda",
            level=0,
            parent=None,
            geometry='{"type":"MultiPolygon", "coordinates":[[1, 2]]}',
        )

        self.kampala = Boundary.objects.create(
            org=self.uganda,
            osm_id="R23456",
            name="Kampala",
            level=1,
            parent=self.country,
            geometry='{"type":"MultiPolygon", "coordinates":[[3, 4]]}',
        )

        self.lugogo = Boundary.objects.create(
            org=self.uganda,
            osm_id="R34567",
            name="Lugogo",
            level=2,
            parent=self.kampala,
            geometry='{"type":"MultiPolygon", "coordinates":[[5, 6]]}',
        )

        self.mbarara = Boundary.objects.create(
            org=self.uganda,
            osm_id="R987",
            name="Mbarara",
            level=1,
            parent=self.country,
            geometry='{"type":"MultiPolygon", "coordinates":[[9, 9]]}',
        )

        self.kasese = Boundary.objects.create(
            org=self.uganda,
            osm_id="R999",
            name="Kasese",
            level=1,
            parent=self.country,
            geometry='{"type":"MultiPolygon", "coordinates":[[10, 10]]}',
        )

        self.falcons = Boundary.objects.create(
            org=self.uganda,
            osm_id="R9988",
            name="Falcons",
            level=2,
            parent=self.mbarara,
            geometry='{"type":"MultiPolygon", "coordinates":[[8, 8]]}',
        )

        self.kabare = Boundary.objects.create(
            org=self.uganda, osm_id="R9989", name="Kabare", level=1, parent=self.country, geometry="{}"
        )

        response = self.client.get(country_boundary_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        output = dict(
            type="FeatureCollection",
            features=[
                dict(
                    type="Feature",
                    properties=dict(id="R999", level=1, name="Kasese"),
                    geometry=dict(type="MultiPolygon", coordinates=[[10, 10]]),
                ),
                dict(
                    type="Feature",
                    properties=dict(id="R987", level=1, name="Mbarara"),
                    geometry=dict(type="MultiPolygon", coordinates=[[9, 9]]),
                ),
                dict(
                    type="Feature",
                    properties=dict(id="R23456", level=1, name="Kampala"),
                    geometry=dict(type="MultiPolygon", coordinates=[[3, 4]]),
                ),
            ],
        )
        self.assertEqual(json.dumps(json.loads(response.content), sort_keys=True), json.dumps(output, sort_keys=True))

        response = self.client.get(state_boundary_url, SERVER_NAME="uganda.ureport.io")

        output = dict(
            type="FeatureCollection",
            features=[
                dict(
                    type="Feature",
                    properties=dict(id="R34567", level=2, name="Lugogo"),
                    geometry=dict(type="MultiPolygon", coordinates=[[5, 6]]),
                )
            ],
        )

        self.assertEqual(json.dumps(json.loads(response.content), sort_keys=True), json.dumps(output, sort_keys=True))

        self.uganda.set_config("common.is_global", True)

        response = self.client.get(country_boundary_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        output = dict(
            type="FeatureCollection",
            features=[
                dict(
                    type="Feature",
                    properties=dict(id="R12345", level=0, name="Uganda"),
                    geometry=dict(type="MultiPolygon", coordinates=[[1, 2]]),
                )
            ],
        )

        self.assertEqual(json.dumps(json.loads(response.content), sort_keys=True), json.dumps(output, sort_keys=True))

        self.uganda.set_config("common.limit_states", "Kampala")
        self.uganda.set_config("common.is_global", False)

        response = self.client.get(country_boundary_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        output = dict(
            type="FeatureCollection",
            features=[
                dict(
                    type="Feature",
                    properties=dict(id="R23456", level=1, name="Kampala"),
                    geometry=dict(type="MultiPolygon", coordinates=[[3, 4]]),
                )
            ],
        )
        self.assertEqual(json.dumps(json.loads(response.content), sort_keys=True), json.dumps(output, sort_keys=True))

        self.uganda.set_config("common.limit_states", "Kampala, Kasese")

        response = self.client.get(country_boundary_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        output = dict(
            type="FeatureCollection",
            features=[
                dict(
                    type="Feature",
                    properties=dict(id="R999", level=1, name="Kasese"),
                    geometry=dict(type="MultiPolygon", coordinates=[[10, 10]]),
                ),
                dict(
                    type="Feature",
                    properties=dict(id="R23456", level=1, name="Kampala"),
                    geometry=dict(type="MultiPolygon", coordinates=[[3, 4]]),
                ),
            ],
        )
        self.assertEqual(json.dumps(json.loads(response.content), sort_keys=True), json.dumps(output, sort_keys=True))

    def test_stories_list(self):
        stories_url = reverse("public.stories")

        education_uganda = Category.objects.create(
            org=self.uganda, name="Education", created_by=self.admin, modified_by=self.admin
        )

        story1 = Story.objects.create(
            title="story 1",
            content="body contents 1",
            category=self.health_uganda,
            featured=True,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story2 = Story.objects.create(
            title="story 2",
            content="body contents 2",
            category=education_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story3 = Story.objects.create(
            title="story 3",
            content="body contents 3",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story4 = Story.objects.create(
            title="story 4",
            content="body contents 4",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(stories_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.context["org"], self.nigeria)
        self.assertEqual(len(response.context["categories"]), 1)
        self.assertEqual(response.context["categories"][0], self.education_nigeria)
        self.assertEqual(len(response.context["other_stories"]), 1)
        self.assertEqual(response.context["other_stories"][0], story4)
        self.assertFalse(response.context["featured"])

        response = self.client.get(stories_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.context["org"], self.uganda)
        self.assertEqual(len(response.context["categories"]), 2)
        self.assertEqual(response.context["categories"][0], education_uganda)
        self.assertEqual(response.context["categories"][1], self.health_uganda)

        self.assertEqual(len(response.context["other_stories"]), 2)
        self.assertEqual(response.context["other_stories"][0], story3)
        self.assertEqual(response.context["other_stories"][1], story2)
        self.assertEqual(len(response.context["featured"]), 1)
        self.assertEqual(response.context["featured"][0], story1)

        story2.is_active = False
        story2.save()

        response = self.client.get(stories_url, SERVER_NAME="uganda.ureport.io")

        self.assertEqual(len(response.context["other_stories"]), 1)
        self.assertEqual(response.context["other_stories"][0], story3)

        story2.is_active = True
        story2.save()
        education_uganda.is_active = False
        education_uganda.save()

        self.assertEqual(len(response.context["other_stories"]), 1)
        self.assertEqual(response.context["other_stories"][0], story3)

    def test_story_read(self):

        education_uganda = Category.objects.create(
            org=self.uganda, name="Education", created_by=self.admin, modified_by=self.admin
        )

        story1 = Story.objects.create(
            title="story 1",
            content="body contents 1",
            category=self.health_uganda,
            featured=True,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story2 = Story.objects.create(
            title="story 2",
            content="body contents 2",
            category=education_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story3 = Story.objects.create(
            title="story 3",
            content="body contents 3",
            category=self.health_uganda,
            featured=True,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        story4 = Story.objects.create(
            title="story 4",
            content="body contents 4",
            category=self.education_nigeria,
            org=self.nigeria,
            created_by=self.admin,
            modified_by=self.admin,
        )

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin, has_synced=True)

        self.create_poll(self.uganda, "Poll 2", "uuid-2", education_uganda, self.admin)

        poll3 = self.create_poll(self.uganda, "Poll 3", "uuid-3", self.health_uganda, self.admin)

        uganda_story_read_url = reverse("public.story_read", args=[story1.pk])
        nigeria_story_read_url = reverse("public.story_read", args=[story4.pk])

        response = self.client.get(nigeria_story_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 404)

        response = self.client.get(uganda_story_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org"], self.uganda)

        self.assertEqual(response.context["object"], story1)
        self.assertEqual(len(response.context["categories"]), 2)
        self.assertEqual(response.context["categories"][0], education_uganda)
        self.assertEqual(response.context["categories"][1], self.health_uganda)

        self.assertEqual(len(response.context["other_stories"]), 1)
        self.assertEqual(response.context["other_stories"][0], story2)

        self.assertEqual(len(response.context["related_polls"]), 1)
        self.assertEqual(response.context["related_polls"][0], poll1)
        self.assertFalse(poll3 in response.context["related_polls"])

        self.assertEqual(len(response.context["related_stories"]), 1)
        self.assertEqual(response.context["related_stories"][0], story3)

        self.assertFalse(response.context["story_featured_images"])

        story_image1 = StoryImage.objects.create(
            story=story1, image="stories/someimage.jpg", name="image 1", created_by=self.admin, modified_by=self.admin
        )

        response = self.client.get(uganda_story_read_url, SERVER_NAME="uganda.ureport.io")

        self.assertEqual(len(response.context["story_featured_images"]), 1)
        self.assertEqual(response.context["story_featured_images"][0], story_image1)

        story_image2 = StoryImage.objects.create(
            story=story1, image="stories/someimage.jpg", name="image 2", created_by=self.admin, modified_by=self.admin
        )

        response = self.client.get(uganda_story_read_url, SERVER_NAME="uganda.ureport.io")

        self.assertEqual(len(response.context["story_featured_images"]), 2)
        self.assertEqual(response.context["story_featured_images"][0], story_image2)
        self.assertEqual(response.context["story_featured_images"][1], story_image1)

        story_image2.is_active = False
        story_image2.save()

        response = self.client.get(uganda_story_read_url, SERVER_NAME="uganda.ureport.io")

        self.assertEqual(len(response.context["story_featured_images"]), 1)
        self.assertEqual(response.context["story_featured_images"][0], story_image1)

        story_image1.image = ""
        story_image1.save()

        response = self.client.get(uganda_story_read_url, SERVER_NAME="uganda.ureport.io")
        self.assertFalse(response.context["story_featured_images"])

    @mock.patch("django.core.cache.cache.get")
    def test_poll_question_results(self, mock_cache_get):
        mock_cache_get.return_value = None

        poll1 = self.create_poll(self.uganda, "Poll 1", "uuid-1", self.health_uganda, self.admin)

        poll1_question = PollQuestion.objects.create(
            poll=poll1, title="question poll 1", ruleset_uuid="uuid-101", created_by=self.admin, modified_by=self.admin
        )

        poll2 = self.create_poll(self.nigeria, "Poll 2", "uuid-2", self.education_nigeria, self.admin)

        poll2_question = PollQuestion.objects.create(
            poll=poll2, title="question poll 2", ruleset_uuid="uuid-102", created_by=self.admin, modified_by=self.admin
        )

        uganda_results_url = reverse("public.pollquestion_results", args=[poll1_question.pk])
        nigeria_results_url = reverse("public.pollquestion_results", args=[poll2_question.pk])

        with mock.patch("ureport.polls.models.PollQuestion.get_results") as mock_results:
            mock_results.return_value = [
                dict(
                    open_ended=False,
                    set=3462,
                    unset=3694,
                    categories=[dict(count=2210, label="Yes"), dict(count=1252, label="No")],
                    label="All",
                )
            ]

            response = self.client.get(nigeria_results_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 404)

            response = self.client.get(uganda_results_url, SERVER_NAME="uganda.ureport.io")
            self.assertEqual(response.status_code, 200)
            mock_results.assert_called_with(segment=None)

            response = self.client.get(
                uganda_results_url + "?" + urlencode(dict(segment=json.dumps(dict(location="State")))),
                SERVER_NAME="uganda.ureport.io",
            )
            self.assertEqual(response.status_code, 200)
            mock_results.assert_called_with(segment=dict(location="State"))

            self.uganda.set_config("common.is_global", True)
            response = self.client.get(
                uganda_results_url + "?" + urlencode(dict(segment=json.dumps(dict(location="State")))),
                SERVER_NAME="uganda.ureport.io",
            )
            mock_results.assert_called_with(segment=dict(location="State"))

    def test_reporters_results(self):
        reporters_results = reverse("public.contact_field_results")

        response = self.client.get(reporters_results, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "[]")

        with mock.patch("dash.orgs.models.Org.get_ureporters_locations_stats") as mock_ureporters_locations_stats:
            mock_ureporters_locations_stats.return_value = "LOCATIONS_STATS"

            response = self.client.get(
                reporters_results + "?" + urlencode(dict(segment=json.dumps(dict(location="State")))),
                SERVER_NAME="uganda.ureport.io",
            )

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, json.dumps("LOCATIONS_STATS"))
            mock_ureporters_locations_stats.assert_called_with(dict(location="State"))

    def test_news(self):
        news_url = reverse("public.news")

        self.uganda_news1 = NewsItem.objects.create(
            title="uganda news 1",
            description="uganda description 1",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(news_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(json.loads(response.content), dict(next=False, news=[self.uganda_news1.as_brick_json()]))

        response = self.client.get(news_url + "?page=1", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(json.loads(response.content), dict(next=False, news=[self.uganda_news1.as_brick_json()]))

        self.uganda_news2 = NewsItem.objects.create(
            title="uganda news 2",
            description="uganda description 2",
            link="http://uganda2.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.uganda_news3 = NewsItem.objects.create(
            title="uganda news 3",
            description="uganda description 3",
            link="http://uganda3.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.uganda_news4 = NewsItem.objects.create(
            title="uganda news 4",
            description="uganda description 4",
            link="http://uganda4.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        self.uganda_news5 = NewsItem.objects.create(
            title="uganda news 5",
            description="uganda description 5",
            link="http://uganda.ug",
            category=self.health_uganda,
            org=self.uganda,
            created_by=self.admin,
            modified_by=self.admin,
        )

        response = self.client.get(news_url + "?page=1", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            json.loads(response.content),
            dict(
                next=True,
                news=[
                    self.uganda_news5.as_brick_json(),
                    self.uganda_news4.as_brick_json(),
                    self.uganda_news3.as_brick_json(),
                ],
            ),
        )

        response = self.client.get(news_url + "?page=2", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            json.loads(response.content),
            dict(next=False, news=[self.uganda_news2.as_brick_json(), self.uganda_news1.as_brick_json()]),
        )

        response = self.client.get(news_url + "?page=3", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(json.loads(response.content), dict(next=False, news=[]))


class JobsTest(UreportJobsTest):
    def setUp(self):
        super(JobsTest, self).setUp()

    def test_jobs(self):
        fb_source_nigeria = self.create_fb_job_source(self.nigeria, self.nigeria.name)
        fb_source_uganda = self.create_fb_job_source(self.uganda, self.uganda.name)

        tw_source_nigeria = self.create_tw_job_source(self.nigeria, self.nigeria.name)
        tw_source_uganda = self.create_tw_job_source(self.uganda, self.uganda.name)

        jobs_url = reverse("public.jobs")

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(2, len(response.context["job_sources"]))
        self.assertEqual(set(response.context["job_sources"]), set([fb_source_nigeria, tw_source_nigeria]))

        response = self.client.get(jobs_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(2, len(response.context["job_sources"]))
        self.assertEqual(set(response.context["job_sources"]), set([fb_source_uganda, tw_source_uganda]))

        fb_source_nigeria.is_featured = True
        fb_source_nigeria.save()

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(2, len(response.context["job_sources"]))
        self.assertEqual(fb_source_nigeria, response.context["job_sources"][0])
        self.assertEqual(tw_source_nigeria, response.context["job_sources"][1])

        fb_source_nigeria.is_active = False
        fb_source_nigeria.save()

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["job_sources"])
        self.assertEqual(1, len(response.context["job_sources"]))
        self.assertTrue(tw_source_nigeria in response.context["job_sources"])

        tw_source_nigeria.is_active = False
        tw_source_nigeria.save()

        response = self.client.get(jobs_url, SERVER_NAME="nigeria.ureport.io")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["job_sources"])


class CountriesTest(UreportTest):
    def setUp(self):
        super(CountriesTest, self).setUp()

    def test_countries(self):
        countries_url = reverse("public.countries")

        response = self.client.post(countries_url, dict())
        self.assertEqual(response.status_code, 405)

        response = self.client.post(countries_url, dict())
        self.assertEqual(response.status_code, 405)

        response = self.client.get(countries_url)
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("text" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url, SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url + "?text=OK")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "OK")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url + "?text=OK", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertEqual(response_json["exists"], "invalid")
        self.assertEqual(response_json["text"], "OK")
        self.assertFalse("country_code" in response_json)

        response = self.client.get(countries_url + "?text=RW")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "RW")

        response = self.client.get(countries_url + "?text=RW", SERVER_NAME="uganda.ureport.io")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "RW")

        response = self.client.get(countries_url + "?text=USA")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        response = self.client.get(countries_url + "?text=rw")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "RW")

        response = self.client.get(countries_url + "?text=usa")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        CountryAlias.objects.create(name="Etats unies", country="US", created_by=self.admin, modified_by=self.admin)

        response = self.client.get(countries_url + "?text=Etats+Unies")
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        # country text has quotes
        response = self.client.get(countries_url + '?text="Etats+Unies"')
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        # country text has quotes an spaces
        response = self.client.get(countries_url + '?text="    Etats+Unies  "')
        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "US")

        # unicode aliases
        CountryAlias.objects.create(name="এ্যান্ডোরা", country="AD", created_by=self.admin, modified_by=self.admin)

        response = self.client.get(countries_url + "?text=%s" % urlquote("এ্যান্ডোরা"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "AD")

        response = self.client.get(countries_url + '?text="   %s   "' % urlquote("এ্যান্ডোরা"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "AD")

        # unicode aliases
        CountryAlias.objects.create(name="Madžarska", country="MD", created_by=self.admin, modified_by=self.admin)

        response = self.client.get(countries_url + "?text=%s" % urlquote("Madžarska"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "MD")

        response = self.client.get(countries_url + '?text="   %s   "' % urlquote("Madžarska"))

        self.assertEqual(response.status_code, 200)
        response_json = json.loads(response.content)
        self.assertTrue("exists" in response_json)
        self.assertTrue("country_code" in response_json)
        self.assertEqual(response_json["exists"], "valid")
        self.assertEqual(response_json["country_code"], "MD")
