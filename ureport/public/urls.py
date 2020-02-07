# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from django.conf.urls import url
from django.views.decorators.cache import cache_page
from django.views.generic import RedirectView

from .views import (
    AboutView,
    BoundaryView,
    Count,
    CustomPage,
    EngagementDataView,
    IndexView,
    JobsView,
    JoinEngageView,
    NewsView,
    PollQuestionResultsView,
    PollReadView,
    PollRedirectView,
    PollsView,
    ReportersResultsView,
    StoriesView,
    StoryReadView,
    UreportersView,
    status,
)

urlpatterns = [
    url(r"^$", IndexView.as_view(), {}, "public.index"),
    url(r"^news/$", NewsView.as_view(), {}, "public.news"),
    url(r"^about/$", AboutView.as_view(), {}, "public.about"),
    url(r"^opinions/$", PollsView.as_view(), {}, "public.opinions"),
    url(r"^polls/$", RedirectView.as_view(pattern_name="public.opinions"), {}, "public.polls"),
    url(r"^opinion/(?P<pk>\d+)/$", PollReadView.as_view(), {}, "public.opinion_read"),
    url(r"^poll/(?P<pk>\d+)/$", PollRedirectView.as_view(), {}, "public.poll_read"),
    url(r"^contact_field_results/$", ReportersResultsView.as_view(), {}, "public.contact_field_results"),
    url(r"^pollquestion/(?P<pk>\d+)/results/$", PollQuestionResultsView.as_view(), {}, "public.pollquestion_results"),
    url(r"^boundaries/$", cache_page(60 * 30)(BoundaryView.as_view()), {}, "public.boundaries"),
    url(
        r"^boundaries/(?P<osm_id>[a-zA-Z0-9]+)/$",
        cache_page(60 * 30)(BoundaryView.as_view()),
        {},
        "public.boundaries",
    ),
    url(r"^engagement/$", UreportersView.as_view(), {}, "public.engagement"),
    url(r"^ureporters/$", RedirectView.as_view(pattern_name="public.engagement"), {}, "public.ureporters"),
    url(r"^engagement_data/$", EngagementDataView.as_view(), {}, "public.engagement_data"),
    url(r"^stories/$", StoriesView.as_view(), {}, "public.stories"),
    url(r"^story/(?P<pk>\d+)/$", StoryReadView.as_view(), {}, "public.story_read"),
    url(r"^join/$", JoinEngageView.as_view(), {}, "public.join"),
    url(r"^jobs/$", JobsView.as_view(), {}, "public.jobs"),
    url(r"^page/(?P<link>\w+)/$", CustomPage.as_view(), {}, "public.custom_page"),
    url(r"^count/$", Count.as_view(), {}, "public.count"),
    url(r"^status/$", status, {}, "public.status"),
]
